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


def generate_with_retry(*, model=None, contents, config=None, max_attempts=3, base_delay=1.5):
    """Call generate_content with transient-error retry AND model failover.

    For each model in the chain (primary model first, then configured fallbacks),
    retry 429/5xx errors with exponential backoff. If a model stays overloaded after
    its attempts, fail over to the next model — congestion is usually per-model, so a
    different flash model often succeeds. Non-retryable errors (bad request, auth) are
    raised immediately. Raises the last error only if every model is exhausted.
    """
    settings = get_settings()
    chain = settings.model_chain()
    if model and model not in chain:
        chain = [model] + chain  # honor an explicit override

    client = get_client()
    last_exc = None
    for model_idx, mdl in enumerate(chain):
        for attempt in range(max_attempts):
            try:
                return client.models.generate_content(model=mdl, contents=contents, config=config)
            except errors.APIError as e:
                code = getattr(e, "code", None)
                last_exc = e
                if code not in _RETRYABLE_CODES:
                    raise
                is_last_attempt = attempt == max_attempts - 1
                is_last_model = model_idx == len(chain) - 1
                if is_last_attempt:
                    if is_last_model:
                        raise
                    logger.warning("Model %s exhausted (%s); failing over to %s",
                                   mdl, code, chain[model_idx + 1])
                    break  # move to next model
                delay = base_delay * (2**attempt)
                logger.warning("Gemini %s failed with %s (attempt %d/%d); retrying in %.0fs",
                               mdl, code, attempt + 1, max_attempts, delay)
                time.sleep(delay)
    if last_exc:
        raise last_exc
