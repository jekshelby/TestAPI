import os
import uuid
import threading
from dotenv import load_dotenv

load_dotenv()

from flask import (Flask, render_template, request, jsonify,
                   send_from_directory)

from database import (init_db, create_pending, update_processing,
                      update_success, update_error,
                      get_all_generations, get_generation)
from services.openai_restore import restore_photo

# ==========================================
# KONFIGURASI
# ==========================================
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER    = os.path.join(BASE_DIR, 'uploads')
GENERATE_FOLDER  = os.path.join(BASE_DIR, 'generate')
ALLOWED_EXT      = {'png', 'jpg', 'jpeg', 'webp'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['GENERATE_FOLDER']    = GENERATE_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATE_FOLDER, exist_ok=True)
init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


# ==========================================
# BACKGROUND WORKER
# ==========================================
def _process_generation(gen_id, input_path, prompt):
    try:
        update_processing(gen_id)

        result = restore_photo(input_path, GENERATE_FOLDER, prompt)
        u = result['usage']

        update_success(
            gen_id,
            output_filename     = result['output_filename'],
            model               = result['model'],
            size                = result['size'],
            quality             = result['quality'],
            input_fidelity      = result['input_fidelity'],
            input_image_tokens  = u['img_in'],
            input_text_tokens   = u['txt_in'],
            output_image_tokens = u['img_out'],
            output_text_tokens  = u['txt_out'],
            cost_usd            = u['cost'],
        )

        print("─" * 60)
        print(f"[GEN #{gen_id}] DONE → {result['output_filename']}")
        print(f"[TOKEN] img_in={u['img_in']}  txt_in={u['txt_in']}  "
              f"img_out={u['img_out']}  txt_out={u['txt_out']}")
        print(f"[COST ] ${u['cost']:.6f}  (≈ Rp{u['cost'] * 17915:,.2f})")
        print("─" * 60)

    except Exception as e:
        update_error(gen_id, str(e))
        print(f"[GEN #{gen_id}] ERROR: {e}")


# ==========================================
# ROUTES
# ==========================================
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'Tidak ada file'}), 400

    f = request.files['file']
    if not f.filename or not allowed_file(f.filename):
        return jsonify({'error': 'Format tidak didukung'}), 400

    ext      = f.filename.rsplit('.', 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    path     = os.path.join(UPLOAD_FOLDER, new_name)
    f.save(path)

    return jsonify({
        'success':  True,
        'filename': new_name,
        'url':      f'/uploads/{new_name}',
    })


@app.route('/generate', methods=['POST'])
def generate():
    data     = request.get_json(silent=True) or {}
    filename = data.get('filename')
    prompt   = (data.get('prompt') or '').strip()

    if not filename or not prompt:
        return jsonify({'error': 'Filename dan prompt wajib diisi'}), 400

    input_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.isfile(input_path):
        return jsonify({'error': 'File tidak ditemukan'}), 404

    try:
        gen_id = create_pending(filename, prompt)
    except Exception as e:
        return jsonify({'error': f'DB error: {e}'}), 500

    t = threading.Thread(
        target=_process_generation,
        args=(gen_id, input_path, prompt),
        daemon=True,
    )
    t.start()

    return jsonify({'success': True, 'id': gen_id})


@app.route('/api/generation/<int:gen_id>')
def api_generation(gen_id):
    g = get_generation(gen_id)
    if not g:
        return jsonify({'error': 'Tidak ditemukan'}), 404

    return jsonify({
        'id':              g['id'],
        'status':          g['status'],
        'error':           g.get('error_message'),
        'input_filename':  g['input_filename'],
        'output_filename': g['output_filename'],
        'size':            g['size'],
        'prompt':          g['prompt'],
        'input_image_tokens':  g['input_image_tokens'],
        'input_text_tokens':   g['input_text_tokens'],
        'output_image_tokens': g['output_image_tokens'],
        'output_text_tokens':  g['output_text_tokens'],
        'total_tokens':        g['total_tokens'],
        'cost_usd':            g['cost_usd'],
        'created_at':          g['created_at'],
    })


@app.route('/results')
def results_page():
    rows = get_all_generations()
    return render_template('results.html', generations=rows)


@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/generate/<filename>')
def serve_generate(filename):
    return send_from_directory(GENERATE_FOLDER, filename)


if __name__ == '__main__':
    app.run(
        debug=True,
        port=5000,
        exclude_patterns=[
            '**/uploads/*',
            '**/generate/*',
            '**/*.db',
            '**/__pycache__/*',
        ]
    )