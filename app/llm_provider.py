"""Provider-agnostic structured generation.

`generate_structured(prompt, schema)` returns a validated Pydantic object, routing to:
  - Gemini / Vertex  — native response_schema (server-side structured output)
  - OpenAI-compatible — NVIDIA NIM, Groq, vLLM, OpenAI: JSON mode + the schema in the
    prompt + Pydantic validation, retrying on bad JSON (with the validation error fed
    back to the model) and on transient HTTP errors.

This is what lets the reasoning backend be swapped via config without touching the
analysis or rule-extraction code. OCR stays separate (see ocr.py) since it needs a
vision-capable model.
"""

import json
import logging
import time

from pydantic import BaseModel, ValidationError

from .config import get_settings

logger = logging.getLogger(__name__)

_RETRYABLE_HTTP = {408, 409, 429, 500, 502, 503, 504}


def generate_structured(*, prompt: str, schema: type[BaseModel], temperature: float = 0.2) -> BaseModel:
    s = get_settings()
    if s.llm_provider == "openai_compatible":
        return _openai_structured(prompt, schema, temperature)
    return _gemini_structured(prompt, schema, temperature)


# ---------- Gemini backend ----------

def _gemini_structured(prompt: str, schema: type[BaseModel], temperature: float) -> BaseModel:
    from google.genai import types

    from .genai_client import generate_with_retry

    response = generate_with_retry(
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
        ),
    )
    return response.parsed


# ---------- OpenAI-compatible backend (NIM / Groq / vLLM / OpenAI) ----------

def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    return t.strip()


def _openai_client():
    from openai import OpenAI

    s = get_settings()
    return OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key)


def _create(client, model, messages, temperature, use_json_mode: bool):
    kwargs = dict(model=model, messages=messages, temperature=temperature)
    if use_json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    return client.chat.completions.create(**kwargs)


def _openai_structured(
    prompt: str, schema: type[BaseModel], temperature: float,
    max_attempts: int = 4, base_delay: float = 1.5,
) -> BaseModel:
    from openai import APIStatusError, BadRequestError

    s = get_settings()
    client = _openai_client()
    schema_json = json.dumps(schema.model_json_schema())

    system = (
        "You are a precise extraction engine. Respond with a SINGLE JSON object and nothing "
        "else — no markdown, no code fences, no commentary."
    )
    user = f"{prompt}\n\nReturn a JSON object conforming to this JSON Schema:\n{schema_json}"

    use_json_mode = True
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        try:
            resp = _create(
                client, s.llm_model,
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature, use_json_mode,
            )
            content = resp.choices[0].message.content or ""
            return schema.model_validate_json(_strip_fences(content))

        except ValidationError as e:
            last_exc = e
            logger.warning("Structured output failed validation (attempt %d/%d); re-asking",
                           attempt + 1, max_attempts)
            user += f"\n\nYour previous response did not validate against the schema:\n{e}\nReturn corrected JSON only."

        except BadRequestError as e:
            # Some models reject response_format=json_object — drop it and rely on the prompt.
            if use_json_mode:
                logger.warning("Model rejected JSON mode; retrying without response_format")
                use_json_mode = False
                last_exc = e
                continue
            raise

        except APIStatusError as e:
            last_exc = e
            if e.status_code not in _RETRYABLE_HTTP or attempt == max_attempts - 1:
                raise
            delay = base_delay * (2**attempt)
            logger.warning("LLM call failed with %s (attempt %d/%d); retrying in %.0fs",
                           e.status_code, attempt + 1, max_attempts, delay)
            time.sleep(delay)

    if last_exc:
        raise last_exc
    raise RuntimeError("structured generation exhausted attempts without a result")
