"""Shared limits for uploads, prompts, and network requests."""
import os

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_TEXT_CHARS = 24000
MAX_JOB_BYTES = 2 * 1024 * 1024
DEFAULT_MODEL = "openrouter/free"


def configured_model() -> str:
    return os.getenv("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL


def has_api_key() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip())
