from __future__ import annotations

import base64
import json
import re
from contextlib import contextmanager

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from httpx import HTTPError
from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError, RateLimitError
from pydantic import TypeAdapter, ValidationError

from app.config import MAX_TEXT_CHARS, has_api_key
from app.extract import extract_job_from_url
from app.latex_build import MAX_ASSET_BYTES, CompilationError, CompilerUnavailable, compile_latex, compiler_status, layout_warnings, unpack_assets
from app.latex_edit import MAX_SOURCE_BYTES, apply_changes, decode_source, editable_spans
from app.models import LatexChange
from app.keywords import add_selected_skills, coverage_report, report_for_terms
from app.latex_preview import preview_pages
from app.rewrite import ProposalInputError, propose_latex

router = APIRouter(prefix="/api/latex", tags=["LaTeX"])


@contextmanager
def compile_errors():
    try:
        yield
    except CompilerUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (CompilationError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


def read_inputs(resume: UploadFile, assets: UploadFile | None):
    name = resume.filename or ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.tex", name, re.I):
        raise ValueError("Upload a .tex source with a simple filename (letters, numbers, dots, underscores, and hyphens).")
    source = decode_source(resume.file.read(MAX_SOURCE_BYTES + 1))
    data = assets.file.read(MAX_ASSET_BYTES + 1) if assets else b""
    if assets and data and not (assets.filename or "").lower().endswith(".zip"):
        raise ValueError("Supporting files must be uploaded as a ZIP archive.")
    return name, source, unpack_assets(data, name)


def job_description(text: str, url: str) -> str:
    job = text.strip()
    if not job and url.strip():
        try:
            job = extract_job_from_url(url.strip())
        except (HTTPError, ValueError) as exc:
            raise HTTPException(400, "Could not read that public job page. Paste the description instead.") from exc
    if not 40 <= len(job) <= MAX_TEXT_CHARS:
        raise HTTPException(400, "Provide a job description between 40 and 24,000 characters, or a readable public job URL.")
    return job


@router.get("/health")
def health():
    return compiler_status()


@router.post("/propose")
def propose(
    resume: UploadFile = File(...),
    assets: UploadFile | None = File(None),
    job_text: str = Form("", max_length=MAX_TEXT_CHARS),
    job_url: str = Form("", max_length=2048),
    engine: str = Form("pdflatex"),
):
    with compile_errors():
        name, source, support = read_inputs(resume, assets)
        if not editable_spans(source):
            raise ValueError("No editable bullet prose was found. Use resumeItem, resumeSubItem, or ordinary item bullets; unsupported text stays unchanged.")
    job = job_description(job_text, job_url)
    if not has_api_key():
        raise HTTPException(503, "Add OPENROUTER_API_KEY to the server's .env file and restart the app.")
    with compile_errors():
        baseline = compile_latex(source, support, name, engine)
    try:
        proposal = propose_latex(source, job)
    except ProposalInputError as exc:
        raise HTTPException(400, str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(503, "OpenRouter rejected the API key. Check the server configuration.") from exc
    except RateLimitError as exc:
        raise HTTPException(429, "The model's rate limit was reached. Try again later.") from exc
    except (APITimeoutError, APIConnectionError) as exc:
        raise HTTPException(504, "The model could not be reached in time. Please try again.") from exc
    except (APIStatusError, RuntimeError, ValueError) as exc:
        raise HTTPException(502, "The model could not produce a valid proposal. Please try again.") from exc
    return {**proposal.model_dump(), "original_pdf_base64": base64.b64encode(baseline.pdf).decode("ascii"),
            "original_preview": preview_pages(baseline.pdf),
            "original_pages": baseline.pages, "editable_passages": len(editable_spans(source))}


@router.post("/compile")
def compile_approved(
    resume: UploadFile = File(...),
    assets: UploadFile | None = File(None),
    changes: str = Form("[]", max_length=120000),
    keyword_terms: str = Form("[]", max_length=8000),
    added_keywords: str = Form("[]", max_length=8000),
    engine: str = Form("pdflatex"),
):
    with compile_errors():
        name, source, support = read_inputs(resume, assets)
        try:
            approved = TypeAdapter(list[LatexChange]).validate_json(changes)
        except ValidationError as exc:
            raise ValueError("The approved changes are invalid. Generate suggestions again.") from exc
        try:
            terms = json.loads(keyword_terms)
            selected_skills = json.loads(added_keywords)
        except ValueError as exc:
            raise ValueError("Invalid keyword list.") from exc
        if not isinstance(terms, list) or len(terms) > 100 or any(not isinstance(term, str) for term in terms):
            raise ValueError("Invalid keyword list.")
        if not isinstance(selected_skills, list) or len(selected_skills) > 100 or any(not isinstance(term, str) for term in selected_skills):
            raise ValueError("Invalid selected keyword list.")
        if len(approved) > 160:
            raise ValueError("Too many changes.")
        edited_source = apply_changes(source, approved)
        edited_source, additions = add_selected_skills(edited_source, selected_skills)
        baseline = compile_latex(source, support, name, engine)
        edited = compile_latex(edited_source, support, name, engine) if edited_source != source else baseline
    return {"filename": f"{name[:-4]}-tailored.pdf", "tex_filename": f"{name[:-4]}-tailored.tex",
            "pdf_base64": base64.b64encode(edited.pdf).decode("ascii"),
            "original_pdf_base64": base64.b64encode(baseline.pdf).decode("ascii"),
            "preview": preview_pages(edited.pdf),
            "tex_source": edited_source, "original_pages": baseline.pages, "pages": edited.pages,
            "applied_changes": len(approved), "added_keywords": additions,
            "keyword_report": coverage_report(report_for_terms(source, terms), source, edited_source),
            "warnings": layout_warnings(baseline, edited)}
