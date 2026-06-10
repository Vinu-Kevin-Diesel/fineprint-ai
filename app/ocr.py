"""OCR for scanned PDFs and image documents.

Two backends, selected by `settings.ocr_backend`:
  - "gemini"    : multimodal OCR via the configured Gemini/Vertex model. No extra
                  dependencies — reuses the same client as the analysis step, and
                  works the same locally (API key) and in production (Vertex AI).
  - "tesseract" : offline OCR via pytesseract + PyMuPDF. Requires the extra deps in
                  requirements-ocr-tesseract.txt and a local tesseract binary.
"""

import io

from google.genai import types

from .config import get_settings
from .genai_client import generate_with_retry

# Image extensions we accept, mapped to their MIME type.
IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}

_OCR_PROMPT = (
    "You are an OCR engine. Transcribe ALL text in this document exactly as it appears, "
    "preserving the reading order and line breaks. Do not summarize, explain, or add "
    "markdown — output only the raw transcribed text."
)


class OcrUnavailable(Exception):
    """Raised when OCR is needed but the configured backend can't run."""


def ocr_bytes(data: bytes, mime_type: str) -> str:
    """OCR a PDF or image given its raw bytes and MIME type."""
    backend = get_settings().ocr_backend
    if backend == "gemini":
        return _gemini_ocr(data, mime_type)
    if backend == "tesseract":
        return _tesseract_ocr(data, mime_type)
    raise OcrUnavailable(
        f"OCR backend is '{backend}', so scanned/image documents can't be read. "
        "Set OCR_BACKEND=gemini (or tesseract) to enable it."
    )


def _gemini_ocr(data: bytes, mime_type: str) -> str:
    s = get_settings()
    response = generate_with_retry(
        model=s.gemini_model,
        contents=[types.Part.from_bytes(data=data, mime_type=mime_type), _OCR_PROMPT],
        config=types.GenerateContentConfig(temperature=0.0),
    )
    return (response.text or "").strip()


def _tesseract_ocr(data: bytes, mime_type: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        import fitz  # PyMuPDF
    except ImportError as e:
        raise OcrUnavailable(
            "Tesseract backend needs extra deps: pip install -r requirements-ocr-tesseract.txt "
            "(and the tesseract binary installed on the system)."
        ) from e

    s = get_settings()
    if s.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = s.tesseract_cmd

    if mime_type == "application/pdf":
        parts: list[str] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=s.ocr_dpi)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                parts.append(pytesseract.image_to_string(img))
        return "\n\n".join(parts).strip()

    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img).strip()
