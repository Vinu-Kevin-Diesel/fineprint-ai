"""Runtime configuration, loaded from environment / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Reasoning provider (clause analysis + rule extraction) ---
    # "gemini": Google Gemini / Vertex.  "openai_compatible": NVIDIA NIM, Groq, vLLM, OpenAI.
    llm_provider: str = "gemini"

    # Gemini provider
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    # Comma-separated models to fail over to when the primary stays overloaded (503).
    gemini_fallback_models: str = "gemini-2.0-flash,gemini-2.5-flash-lite"
    use_vertex: bool = False
    gcp_project: str | None = None
    gcp_location: str = "us-central1"

    # OpenAI-compatible provider (NIM / Groq / vLLM / OpenAI)
    llm_base_url: str | None = None         # e.g. https://integrate.api.nvidia.com/v1
    llm_api_key: str | None = None          # e.g. nvapi-... (NIM) or gsk_... (Groq)
    llm_model: str = "meta/llama-3.3-70b-instruct"

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
        """Primary Gemini model first, then de-duplicated fallbacks."""
        chain = [self.gemini_model]
        for m in self.gemini_fallback_models.split(","):
            m = m.strip()
            if m and m not in chain:
                chain.append(m)
        return chain

    def active_model(self) -> str:
        """The reasoning model id reported to clients."""
        return self.llm_model if self.llm_provider == "openai_compatible" else self.gemini_model

    @property
    def is_llm_configured(self) -> bool:
        if self.llm_provider == "openai_compatible":
            return bool(self.llm_base_url and self.llm_api_key)
        if self.use_vertex:
            return bool(self.gcp_project)
        return bool(self.gemini_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
