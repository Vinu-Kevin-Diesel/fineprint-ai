"""Single place that builds the google-genai client and calls the model.

Shared by the analysis (llm.py) and OCR (ocr.py) paths so both honor the same
provider config (a Gemini API key for local dev, or Vertex AI in production)
and the same transient-error retry policy.
"""

import logging
import time
from functools import lru_cache

from google import genai
from google.genai import errors

from .config import get_settings

logger = logging.getLogger(__name__)

# HTTP status codes worth retrying: rate limiting and transient server errors.
_RETRYABLE_CODES = {429, 500, 502, 503, 504}


@lru_cache
def get_client() -> genai.Client:
    s = get_settings()
    if s.use_vertex:
        return genai.Client(vertexai=True, project=s.gcp_project, location=s.gcp_location)
    return genai.Client(api_key=s.gemini_api_key)


def generate_with_retry(*, model, contents, config=None, max_attempts=4, base_delay=2.0):
    """Call generate_content, retrying transient 429/5xx errors with backoff.

    Backoff is 2s, 4s, 8s between attempts. Non-retryable errors (e.g. a bad
    request or auth failure) are raised immediately.
    """
    client = get_client()
    for attempt in range(max_attempts):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:
            code = getattr(e, "code", None)
            if code not in _RETRYABLE_CODES or attempt == max_attempts - 1:
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "Gemini call failed with %s (attempt %d/%d); retrying in %.0fs",
                code, attempt + 1, max_attempts, delay,
            )
            time.sleep(delay)
