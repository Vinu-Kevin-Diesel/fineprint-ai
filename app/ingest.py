"""Turn an uploaded file into text, choosing native extraction vs. OCR.

Strategy:
  - images (.png/.jpg/...)  -> OCR directly
  - .pdf                    -> native text layer first; if it's empty/too sparse
                               (i.e. a scanned PDF), fall back to OCR
  - .docx / .txt / .md      -> native extraction
"""

from dataclasses import dataclass
from pathlib import Path

from .config import get_settings
from .extract_text import (
    UnsupportedFileType,
    docx_to_text,
    looks_garbled,
    pdf_to_text,
    plain_to_text,
)
from .ocr import IMAGE_MIME, ocr_bytes


@dataclass
class Ingested:
    text: str
    method: str  # "native" | "ocr" | "native+ocr"


def ingest(filename: str, data: bytes) -> Ingested:
    ext = Path(filename.lower()).suffix

    # Image uploads are always scanned content -> OCR.
    if ext in IMAGE_MIME:
        return Ingested(ocr_bytes(data, IMAGE_MIME[ext]), "ocr")

    if ext == ".pdf":
        native = pdf_to_text(data)
        # Use native text only if there's enough of it AND it isn't mis-decoded glyphs
        # (some PDFs use custom fonts that pypdf turns into symbol junk).
        if len(native) >= get_settings().ocr_min_chars and not looks_garbled(native):
            return Ingested(native, "native")
        # Empty, too short, or garbled text layer -> OCR the whole PDF.
        ocr_text = ocr_bytes(data, "application/pdf")
        method = "native+ocr" if native else "ocr"
        # Prefer OCR text; keep whatever native text existed only if OCR came back empty.
        return Ingested(ocr_text or native, method)

    if ext == ".docx":
        return Ingested(docx_to_text(data), "native")

    if ext in (".txt", ".md"):
        return Ingested(plain_to_text(data), "native")

    raise UnsupportedFileType(
        f"Unsupported file type: {filename!r}. Supported: PDF, DOCX, TXT, MD, "
        f"and images ({', '.join(sorted(IMAGE_MIME))})."
    )
