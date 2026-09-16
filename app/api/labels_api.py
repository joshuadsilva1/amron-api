import base64
import csv
import io
import re
import zipfile
from datetime import datetime

from flask import Blueprint, request, jsonify
from PIL import Image, ImageDraw, ImageFont
import qrcode

from app.models.item import InternalProduct
from app.core.decorators import jwt_required

labels_bp = Blueprint('labels', __name__)


def _sanitize_filename(name):
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', name).strip('_')
    return cleaned or 'item'


def _centered_text(draw, canvas_width, y, text, font, fill="black"):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((canvas_width - w) / 2, y), text, font=font, fill=fill)


def _wrap_text(draw, text, font, max_width, max_lines=2):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), trial, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines[:max_lines]


def render_label_png(qr_content, code_text, name_text):
    """Builds one self-contained, print-ready label: a QR code with the
    item code and name printed underneath — so the PNG can be dropped
    straight into BarTender (or placed on a label by hand) with nothing
    further to configure. Rendered server-side so it never depends on a
    third-party QR image API being reachable at print time."""
    # box_size/border are deliberately generous (not tied to any physical
    # label size) so the PNG stays crisp when BarTender scales it down onto
    # a small thermal label — and border=4 is the QR spec's recommended
    # minimum quiet zone for reliable scanning, not just cosmetic padding.
    qr = qrcode.QRCode(border=4, box_size=14, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(qr_content)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    qr_size = qr_img.width
    text_area_height = 110
    canvas = Image.new("RGB", (qr_size, qr_size + text_area_height), "white")
    canvas.paste(qr_img, (0, 0))

    draw = ImageDraw.Draw(canvas)
    code_font = ImageFont.load_default(size=32)
    name_font = ImageFont.load_default(size=22)

    _centered_text(draw, qr_size, qr_size + 10, code_text, code_font)

    y = qr_size + 50
    for line in _wrap_text(draw, name_text, name_font, qr_size - 10):
        _centered_text(draw, qr_size, y, line, name_font, fill="#444444")
        y += 26

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def _lookup_and_render(requested):
    """Shared by qr-zip and qr-images: looks up each requested item and
    renders its label PNG once. Returns a list of
    (filename, png_bytes, item_code, item_name, quantity, qr_content, item_id)."""
    rendered = []
    used_filenames = set()

    for row in requested:
        item_id = row.get('item_id')
        if not item_id:
            continue

        item = InternalProduct.query.get(item_id)
        if not item:
            continue

        try:
            quantity = int(row.get('quantity', 1))
        except (TypeError, ValueError):
            quantity = 1

        qr_content = item.item_code or item.id
        png_bytes = render_label_png(qr_content, item.item_code or "", item.name or "")

        base_name = _sanitize_filename(item.item_code or item.name or item.id)
        filename = f"{base_name}.png"
        suffix = 2
        while filename in used_filenames:
            filename = f"{base_name}_{suffix}.png"
            suffix += 1
        used_filenames.add(filename)

        rendered.append((filename, png_bytes, item.item_code, item.name, quantity, qr_content, item.id))

    return rendered


@labels_bp.route('/qr-zip', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def download_qr_zip():
    """Renders one print-ready QR label PNG per requested item and bundles
    them into a ZIP for the client to save/share — meant to be dropped
    straight into BarTender for printing on the TSC TE244.
    Body: {"items": [{"item_id": "...", "quantity": 3}, ...]}
    quantity isn't turned into duplicate image files — identical labels
    don't need N copies of the same PNG, BarTender's own print-run count
    handles that. It's recorded in manifest.csv so you know how many of
    each to print.
    """
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    requested = data.get('items', [])
    if not requested:
        return jsonify({"error": "items is required — a list of {item_id, quantity}"}), 400

    rendered = _lookup_and_render(requested)
    if not rendered:
        return jsonify({"error": "None of the requested items were found."}), 404

    manifest_buf = io.StringIO()
    writer = csv.writer(manifest_buf)
    writer.writerow(["filename", "item_code", "item_name", "quantity", "qr_content"])
    for filename, _png, item_code, item_name, quantity, qr_content, _item_id in rendered:
        writer.writerow([filename, item_code, item_name, quantity, qr_content])

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for filename, png_bytes, *_ in rendered:
            zf.writestr(filename, png_bytes)
        zf.writestr("manifest.csv", manifest_buf.getvalue())

    filename = f"qr-labels-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"

    return jsonify({
        "status": "success",
        "filename": filename,
        "label_count": len(rendered),
        "base64": base64.b64encode(zip_buf.getvalue()).decode('ascii'),
    }), 200


@labels_bp.route('/qr-images', methods=['POST', 'OPTIONS'], strict_slashes=False)
@jwt_required
def get_qr_images():
    """Same server-side rendering as qr-zip, but returns raw base64 PNGs
    (one per unique requested item, no zip) for a caller that wants to
    embed them directly — e.g. the app builds one combined A4 print sheet
    HTML from these instead of pointing <img> tags at a third-party QR
    image API. Body: {"items": [{"item_id": "..."}]}"""
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json(silent=True) or {}
    requested = data.get('items', [])
    if not requested:
        return jsonify({"error": "items is required — a list of {item_id}"}), 400

    rendered = _lookup_and_render(requested)
    if not rendered:
        return jsonify({"error": "None of the requested items were found."}), 404

    return jsonify({
        "status": "success",
        "items": [
            {
                "item_id": item_id,
                "item_code": item_code,
                "item_name": item_name,
                "png_base64": base64.b64encode(png_bytes).decode('ascii'),
            }
            for _filename, png_bytes, item_code, item_name, _quantity, _qr_content, item_id in rendered
        ],
    }), 200
