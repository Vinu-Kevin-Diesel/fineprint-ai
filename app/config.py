"""Runtime configuration, loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM provider ---
    # Local dev: a Gemini API key. Production: USE_VERTEX=true (uses GCP credentials).
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

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

    @property
    def is_llm_configured(self) -> bool:
        if self.use_vertex:
            return bool(self.gcp_project)
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
