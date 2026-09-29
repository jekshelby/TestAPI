import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'generations.db')


def get_conn():
    """Buka koneksi dengan timeout panjang & autocommit."""
    conn = sqlite3.connect(
        DB_PATH,
        timeout=60,              # tunggu max 60 detik kalau di-lock
        check_same_thread=False,
        isolation_level=None,    # autocommit mode
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def init_db():
    """Setup DB SEKALI. WAL mode hanya di sini."""
    conn = sqlite3.connect(DB_PATH, timeout=60)
    try:
        # Set WAL mode (persistent di file DB)
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        print(f"[DB] journal_mode = {mode}")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_filename TEXT NOT NULL,
                output_filename TEXT,
                prompt TEXT NOT NULL,
                model TEXT,
                size TEXT,
                quality TEXT,
                input_fidelity TEXT,
                input_image_tokens INTEGER DEFAULT 0,
                input_text_tokens INTEGER DEFAULT 0,
                output_image_tokens INTEGER DEFAULT 0,
                output_text_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Cleanup row yatim dari restart server
        n = conn.execute("""
            UPDATE generations
            SET status='error',
                error_message='Dihentikan (server restart)'
            WHERE status IN ('pending', 'processing')
        """).rowcount
        if n > 0:
            print(f"[DB CLEANUP] {n} row yatim ditandai sebagai error")

        conn.commit()
    finally:
        conn.close()


def create_pending(input_filename, prompt):
    conn = get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO generations (input_filename, prompt, status)
            VALUES (?, ?, 'pending')
        """, (input_filename, prompt))
        return cur.lastrowid
    finally:
        conn.close()


def update_processing(gen_id):
    conn = get_conn()
    try:
        conn.execute("UPDATE generations SET status='processing' WHERE id=?", (gen_id,))
    finally:
        conn.close()


def update_success(gen_id, **k):
    conn = get_conn()
    try:
        total = (k['input_image_tokens'] + k['input_text_tokens']
                 + k['output_image_tokens'] + k['output_text_tokens'])
        conn.execute("""
            UPDATE generations
            SET output_filename = ?, model = ?, size = ?, quality = ?,
                input_fidelity = ?, input_image_tokens = ?, input_text_tokens = ?,
                output_image_tokens = ?, output_text_tokens = ?,
                total_tokens = ?, cost_usd = ?, status = 'done',
                error_message = NULL
            WHERE id = ?
        """, (
            k['output_filename'], k['model'], k['size'], k['quality'],
            k['input_fidelity'], k['input_image_tokens'], k['input_text_tokens'],
            k['output_image_tokens'], k['output_text_tokens'],
            total, k['cost_usd'], gen_id,
        ))
    finally:
        conn.close()


def update_error(gen_id, message):
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE generations SET status='error', error_message=? WHERE id=?
        """, (message, gen_id))
    finally:
        conn.close()


def get_all_generations():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM generations ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_generation(gen_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM generations WHERE id = ?", (gen_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()