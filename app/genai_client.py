"""Single place that builds the google-genai client.

Shared by the analysis (llm.py) and OCR (ocr.py) paths so both honor the same
provider config: a Gemini API key for local dev, or Vertex AI in production.
"""

from functools import lru_cache

from google import genai

from .config import get_settings


@lru_cache
def get_client() -> genai.Client:
    s = get_settings()
    if s.use_vertex:
        return genai.Client(vertexai=True, project=s.gcp_project, location=s.gcp_location)
    return genai.Client(api_key=s.gemini_api_key)
