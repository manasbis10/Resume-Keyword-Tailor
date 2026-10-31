import base64
import io

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import AuthenticationError, RateLimitError
from pypdf import PdfReader

import app.main as main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return TestClient(main.app)


def send(client, resume_pdf, **data):
    return client.post("/api/tailor", files={"resume": ("resume.pdf", resume_pdf, "application/pdf")}, data=data)


JOB = "We are looking for a software engineer experienced with Python APIs and SQL."


def test_home_and_health(client, monkeypatch):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    monkeypatch.setenv("OPENROUTER_API_KEY", " ")
    monkeypatch.setenv("OPENROUTER_MODEL", " ")
    assert client.get("/api/health").json() == {"ok": True, "has_key": False, "model": "openrouter/free"}


def test_full_flow_returns_readable_pdf_and_preview(client, resume_pdf, tailored, monkeypatch):
    seen = []
    monkeypatch.setattr(main, "tailor_resume", lambda source, job: seen.append((source, job)) or tailored)
    response = send(client, resume_pdf, job_text=JOB)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["resume"]["name"] == "Jane Doe"
    assert data["filename"] == "jane-doe-tailored.pdf"
    assert data["keywords_used"] == ["Python APIs"]
    pdf = PdfReader(io.BytesIO(base64.b64decode(data["pdf_base64"])))
    text = "\n".join(p.extract_text() for p in pdf.pages)
    assert "Jane Doe" in text and "25%" in text and "Acme" in text
    assert "Jane Doe" in seen[0][0] and seen[0][1] == JOB


def test_paste_takes_priority(client, resume_pdf, tailored, monkeypatch):
    def no_fetch(url):
        pytest.fail("A URL should not be fetched when text is supplied")
    monkeypatch.setattr(main, "extract_job_from_url", no_fetch)
    monkeypatch.setattr(main, "tailor_resume", lambda *args: tailored)
    assert send(client, resume_pdf, job_url="https://example.com", job_text=JOB).status_code == 200


def test_url_flow(client, resume_pdf, tailored, monkeypatch):
    monkeypatch.setattr(main, "extract_job_from_url", lambda url: JOB)
    monkeypatch.setattr(main, "tailor_resume", lambda *args: tailored)
    assert send(client, resume_pdf, job_url="https://example.com/job").status_code == 200


@pytest.mark.parametrize("raw, expected", [(b"", 400), (b"not a pdf", 400), (b"x" * (5 * 1024 * 1024 + 1), 413)])
def test_bad_files(client, raw, expected):
    assert send(client, raw, job_text=JOB).status_code == expected


def test_missing_job_and_key(client, resume_pdf, monkeypatch):
    assert send(client, resume_pdf).status_code == 400
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert send(client, resume_pdf, job_text=JOB).status_code == 503


def test_text_not_silently_truncated(client, resume_pdf, monkeypatch):
    assert send(client, resume_pdf, job_text="a" * 24001).status_code == 422
    monkeypatch.setattr(main, "extract_pdf_text", lambda _: "x" * 24001)
    assert send(client, resume_pdf, job_text=JOB).status_code == 400


def test_scrape_failure_explains_paste(client, resume_pdf, monkeypatch):
    def failed(url):
        raise ValueError("Private address")
    monkeypatch.setattr(main, "extract_job_from_url", failed)
    response = send(client, resume_pdf, job_url="http://localhost")
    assert response.status_code == 400
    assert "Paste" in response.json()["detail"]


@pytest.mark.parametrize("error, code", [(ValueError("secret"), 502), (RuntimeError("secret"), 502)])
def test_model_failure_is_actionable_and_private(client, resume_pdf, monkeypatch, error, code):
    def failed(*args):
        raise error
    monkeypatch.setattr(main, "tailor_resume", failed)
    response = send(client, resume_pdf, job_text=JOB)
    assert response.status_code == code
    assert "secret" not in response.text


@pytest.mark.parametrize("error_type, code", [(RateLimitError, 429), (AuthenticationError, 503)])
def test_provider_errors(client, resume_pdf, monkeypatch, error_type, code):
    def failed(*args):
        raise error_type("secret-key", response=httpx.Response(code, request=httpx.Request("POST", "https://example.com")), body=None)
    monkeypatch.setattr(main, "tailor_resume", failed)
    response = send(client, resume_pdf, job_text=JOB)
    assert response.status_code == code
    assert "secret-key" not in response.text
