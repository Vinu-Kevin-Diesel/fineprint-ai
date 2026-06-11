"""Runtime configuration, loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM provider ---
    # Local dev: a Gemini API key. Production: USE_VERTEX=true (uses GCP credentials).
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    # Comma-separated models to fail over to when the primary stays overloaded (503).
    gemini_fallback_models: str = "gemini-2.0-flash,gemini-2.5-flash-lite"

    use_vertex: bool = False
    gcp_project: str | None = None
    gcp_location: str = "us-central1"

    # --- App ---
    max_upload_mb: int = 15
    default_domain: str = "generic"

    # --- OCR (for scanned PDFs and image documents) ---
    # gemini  : multimodal OCR via the configured Gemini/Vertex model (no extra deps)
    # tesseract: offline OCR (needs `pip install -r requirements-ocr-tesseract.txt` + the tesseract binary)
    # none    : disable OCR; scanned docs return an error
    ocr_backend: str = "gemini"
    # If a PDF's native text layer yields fewer than this many characters, treat it as scanned.
    ocr_min_chars: int = 50
    # Tesseract-only knobs:
    tesseract_cmd: str | None = None  # path to tesseract.exe if not on PATH
    ocr_dpi: int = 200

    def model_chain(self) -> list[str]:
        """Primary model first, then de-duplicated fallbacks."""
        chain = [self.gemini_model]
        for m in self.gemini_fallback_models.split(","):
            m = m.strip()
            if m and m not in chain:
                chain.append(m)
        return chain

    @property
    def is_llm_configured(self) -> bool:
        if self.use_vertex:
            return bool(self.gcp_project)
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
