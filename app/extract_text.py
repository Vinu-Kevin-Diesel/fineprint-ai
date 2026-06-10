"""Native text extraction (no OCR) for PDF, DOCX, and plain-text files.

Scanned PDFs and images are handled by the OCR layer (see ocr.py); the
orchestration that decides native-vs-OCR lives in ingest.py.
"""

import io

from pypdf import PdfReader
from docx import Document


class UnsupportedFileType(Exception):
    pass


def pdf_to_text(data: bytes) -> str:
    """Extract the embedded text layer of a PDF. Returns '' for scanned PDFs."""
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def docx_to_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs).strip()


def plain_to_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()
