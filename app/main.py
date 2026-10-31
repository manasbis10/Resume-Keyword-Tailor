from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from httpx import HTTPError
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, RateLimitError

from app.config import MAX_PDF_BYTES, MAX_TEXT_CHARS, configured_model, has_api_key
from app.extract import extract_job_from_url, extract_pdf_text
from app.pdf_build import build_resume_pdf
from app.rewrite import tailor_resume
from app.latex_api import router as latex_router

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
logger = logging.getLogger(__name__)
app = FastAPI(title="Resume Keyword Tailor", version="1.0.0")
app.include_router(latex_router)
STATIC = ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "has_key": has_api_key(), "model": configured_model()}


@app.post("/api/tailor")
def tailor(
    resume: UploadFile = File(...),
    job_url: str = Form("", max_length=2048),
    job_text: str = Form("", max_length=MAX_TEXT_CHARS),
):
    # A synchronous route runs extraction, HTTP calls, and rendering in FastAPI's
    # worker pool, keeping health checks and other requests responsive.
    if not resume.filename or not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF resume.")
    raw = resume.file.read(MAX_PDF_BYTES + 1)
    if not raw:
        raise HTTPException(400, "The resume file is empty.")
    if len(raw) > MAX_PDF_BYTES:
        raise HTTPException(413, "The resume must be 5 MB or smaller.")
    try:
        resume_text = extract_pdf_text(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, "Could not read this PDF. Upload an unlocked, text-based PDF.") from exc
    if len(resume_text) < 40:
        raise HTTPException(400, "Could not extract enough text. Scanned PDFs need OCR before uploading.")
    if len(resume_text) > MAX_TEXT_CHARS:
        raise HTTPException(400, f"The resume is too long. Use at most {MAX_TEXT_CHARS:,} text characters.")

    pasted = job_text.strip()
    warnings = []
    # Pasted text is authoritative and also works for pages that block scraping.
    combined_job = pasted
    if not pasted and job_url.strip():
        try:
            combined_job = extract_job_from_url(job_url.strip())
        except (HTTPError, ValueError) as exc:
            raise HTTPException(400, "Could not read that public job page. Paste the job description instead.") from exc
        if len(combined_job) > MAX_TEXT_CHARS:
            raise HTTPException(400, "That page contains too much text. Paste just the job description instead.")
    if len(combined_job) < 40:
        raise HTTPException(400, "Provide a job URL or paste a job description of at least 40 characters.")
    if not has_api_key():
        raise HTTPException(503, "Add OPENROUTER_API_KEY to the server's .env file and restart the app.")

    try:
        tailored = tailor_resume(resume_text, combined_job)
    except AuthenticationError as exc:
        raise HTTPException(503, "OpenRouter rejected the API key. Check the server configuration.") from exc
    except RateLimitError as exc:
        raise HTTPException(429, "The model's rate limit was reached. Try again later.") from exc
    except (APITimeoutError, APIConnectionError) as exc:
        raise HTTPException(504, "The model could not be reached in time. Please try again.") from exc
    except APIStatusError as exc:
        raise HTTPException(502, "The configured model is unavailable. Try again or change OPENROUTER_MODEL.") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(502, "The model returned an incomplete or unsupported rewrite. Please try again.") from exc
    except Exception as exc:
        logger.error("Unexpected rewrite failure (%s)", type(exc).__name__)
        raise HTTPException(502, "The rewrite could not be completed. Please try again.") from exc

    try:
        pdf_bytes = build_resume_pdf(tailored)
    except Exception as exc:
        logger.error("PDF rendering failed (%s)", type(exc).__name__)
        raise HTTPException(500, "The PDF could not be generated. Please try again.") from exc
    safe_name = re.sub(r"[^a-z0-9_-]+", "-", (tailored.name or "resume").lower()).strip("-")[:60] or "resume"
    return {
        "filename": f"{safe_name}-tailored.pdf",
        "keywords_used": tailored.keywords_used,
        "notes": tailored.notes,
        "model_used": tailored.model_used,
        "warnings": warnings,
        "resume": tailored.model_dump(),
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
    }
