import os
import uuid
import base64
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

load_dotenv()

client = OpenAI()

MODEL          = "gpt-image-1.5"
QUALITY        = "medium"
INPUT_FIDELITY = "low"

PRICING = {
    "input_image":  8.00,
    "input_text":   5.00,
    "output_image": 32.00,
    "output_text":  10.00,
}


def _calc_usage(usage):
    din  = getattr(usage, "input_tokens_details", None)
    dout = getattr(usage, "output_tokens_details", None)

    img_in  = getattr(din,  "image_tokens", 0) if din  else 0
    txt_in  = getattr(din,  "text_tokens",  0) if din  else 0
    img_out = getattr(dout, "image_tokens", 0) if dout else 0
    txt_out = getattr(dout, "text_tokens",  0) if dout else 0

    cost = (
        (img_in  / 1_000_000) * PRICING["input_image"]
        + (txt_in  / 1_000_000) * PRICING["input_text"]
        + (img_out / 1_000_000) * PRICING["output_image"]
        + (txt_out / 1_000_000) * PRICING["output_text"]
    )

    return {
        "img_in":  img_in,
        "txt_in":  txt_in,
        "img_out": img_out,
        "txt_out": txt_out,
        "cost":    cost,
    }


def _detect_size(path):
    with Image.open(path) as img:
        w, h = img.size
    if h > w:
        return "1024x1536"
    elif w > h:
        return "1536x1024"
    return "1024x1024"


def restore_photo(input_path, output_dir, prompt):
    size = _detect_size(input_path)

    with open(input_path, "rb") as f:
        result = client.images.edit(
            model=MODEL,
            image=[f],
            prompt=prompt,
            input_fidelity=INPUT_FIDELITY,
            quality=QUALITY,
            size=size,
        )

    out_name = f"{uuid.uuid4().hex}.png"
    out_path = os.path.join(output_dir, out_name)
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(result.data[0].b64_json))

    usage_info = {"img_in": 0, "txt_in": 0, "img_out": 0, "txt_out": 0, "cost": 0.0}
    if hasattr(result, "usage") and result.usage:
        usage_info = _calc_usage(result.usage)

    return {
        "output_filename": out_name,
        "model":           MODEL,
        "size":            size,
        "quality":         QUALITY,
        "input_fidelity":  INPUT_FIDELITY,
        "usage":           usage_info,
    }