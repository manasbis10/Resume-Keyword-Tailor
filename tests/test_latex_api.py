import base64
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import latex_api
from app.latex_build import CompiledLatex
from app.latex_edit import apply_changes, editable_spans
from app.models import LatexChange, LatexProposal

JOB = "We need a software engineer building reliable Python APIs and SQL reporting systems."


@pytest.fixture
def source():
    return Path("examples/resume.tex").read_text()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(latex_api, "preview_pages", lambda _: ["test-preview"])
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return TestClient(app)


def post(client, route, source, **data):
    return client.post(f"/api/latex/{route}", files={"resume": ("resume.tex", source.encode(), "text/plain")}, data=data)


def test_propose_uses_source_and_returns_baseline_pdf(client, source, monkeypatch):
    span = editable_spans(source)[0]
    change = LatexChange(id=span.id, before=span.text, after=span.text.replace("Designed", "Engineered"))
    seen = []
    def fake_proposal(actual_source, job):
        seen.append((actual_source, job))
        return LatexProposal(changes=[change], model_used="test-model")
    monkeypatch.setattr(latex_api, "propose_latex", fake_proposal)
    monkeypatch.setattr(latex_api, "compile_latex", lambda *a: CompiledLatex(b"%PDF-original", 1, [(612, 792)], Counter(), 0))
    response = post(client, "propose", source, job_text=JOB)
    assert response.status_code == 200, response.text
    assert seen == [(source, JOB)]
    assert response.json()["changes"][0]["id"] == span.id
    assert base64.b64decode(response.json()["original_pdf_base64"]).startswith(b"%PDF-")


def test_compile_only_selected_patches_and_returns_source(client, source, monkeypatch):
    span = editable_spans(source)[0]
    change = LatexChange(id=span.id, before=span.text, after=span.text.replace("Designed", "Engineered"))
    compiled = []
    def fake_compile(text, *args):
        compiled.append(text)
        return CompiledLatex(b"%PDF-test", 1, [(612, 792)], Counter({"https://example.com": 1}), 0)
    monkeypatch.setattr(latex_api, "compile_latex", fake_compile)
    response = post(client, "compile", source, changes="[" + change.model_dump_json() + "]")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["tex_source"] == apply_changes(source, [change])
    assert compiled == [source, data["tex_source"]]
    assert data["applied_changes"] == 1
    assert data["warnings"] == []
    assert data["tex_filename"] == "resume-tailored.tex"


def test_compile_unchanged_does_not_need_model_or_key(client, source, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    calls = []
    monkeypatch.setattr(latex_api, "compile_latex", lambda text, *a: calls.append(text) or CompiledLatex(b"%PDF-test", 1, [(612, 792)], Counter(), 0))
    response = post(client, "compile", source)
    assert response.status_code == 200
    assert response.json()["tex_source"] == source
    assert calls == [source]


def test_compile_rejects_unapproved_or_structural_edits(client, source):
    response = post(client, "compile", source, changes='[{"id":"preamble","before":"old","after":"new"}]')
    assert response.status_code == 400
    response = post(client, "compile", source, changes="broken JSON")
    assert response.status_code == 400


def test_missing_key_and_invalid_upload(client, source, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert post(client, "propose", source, job_text=JOB).status_code == 503
    assert post(client, "propose", "invalid", job_text=JOB).status_code == 400


def test_no_supported_spans_is_explained(client):
    response = post(client, "propose", r"\documentclass{article}\begin{document}Just a name\end{document}", job_text=JOB)
    assert response.status_code == 400
    assert "No editable" in response.json()["detail"]
