from pathlib import Path

import pytest

from app.latex_edit import apply_changes, decode_source, editable_spans, validate_change
from app.models import LatexChange
from app import rewrite


@pytest.fixture
def source():
    return Path("examples/resume.tex").read_text()


def change_for(source, old="Designed and developed", new="Engineered and developed"):
    span = editable_spans(source)[0]
    return LatexChange(id=span.id, before=span.text, after=span.text.replace(old, new))


def test_exact_patch_preserves_all_other_bytes(source):
    change = change_for(source)
    edited = apply_changes(source, [change])
    assert edited == source.replace(change.before, change.after, 1)
    assert edited.count(r"\resumeItem{") == source.count(r"\resumeItem{")
    assert r"GraphQL (familiar)" in edited
    assert r"\href{https://github.com/example}{GitHub}" in edited
    assert "Applied SHA-1 hashing" in edited
    assert apply_changes(source, []) == source


def test_only_supported_prose_is_editable(source):
    spans = editable_spans(source)
    assert len(spans) == 5
    assert all("jane@example" not in span.text and "familiar" not in span.text for span in spans)
    assert all(source[span.start:span.end] == span.text for span in spans)


def test_comments_preamble_formatting_and_links_are_protected():
    source = r'''% \begin{document}
\newcommand{\resumeItem}[1]{\item #1}
\begin{document}
% \resumeItem{Designed and developed fake content that must not become editable here.}
\resumeItem{Built reliable internal dashboards to support operations and simplify the reporting process with \textbf{Python and SQL} and \href{https://example.com/a_1}{a very long link label that must stay completely immutable}.}
\end{document}'''
    spans = editable_spans(source)
    assert len(spans) == 1
    assert "fake" not in spans[0].text
    assert "Python" not in spans[0].text
    assert "label" not in spans[0].text


def test_plain_item_supported():
    source = r"\begin{document}\begin{itemize}\item Built reliable internal dashboards using Python and SQL to support daily operations.\end{itemize}\end{document}"
    assert len(editable_spans(source)) == 1


def test_math_is_not_editable():
    source = r"\begin{document}\resumeItem{Built reliable systems around \( designed something with a very long math prose passage inside \alpha plus many more words \) for internal teams with reliable services and consistent reporting workflows.}\end{document}"
    assert all("math prose" not in s.text for s in editable_spans(source))


@pytest.mark.parametrize("old,new,error", [
    ("Built internal dashboards using Python and SQL for daily reporting.", "Built customer-facing dashboards using Python and SQL for daily reporting.", "qualifier"),
    ("Reduced reprocessing by 60--70 in distributed workflows.", "Reduced reprocessing by 80--90 in distributed workflows.", "number"),
    ("Built reliable dashboards using Python and SQL for daily reporting.", "Built reliable dashboards using Java and SQL for daily reporting.", "technology"),
    ("Built reporting tools using C++ and Python for consistent workflows.", "Built reporting tools using C and Python for consistent workflows.", "technology"),
    ("Built dashboards using GraphQL with familiar tools for daily reporting.", "Built dashboards using GraphQL with advanced tools for daily reporting.", "qualifier"),
])
def test_unsupported_factual_changes_rejected(old, new, error):
    with pytest.raises(ValueError, match=error):
        validate_change(old, new)


@pytest.mark.parametrize("replacement", [r"\input{/etc/passwd}", "", "A" * 1000, "Text {new}", "Some text & more text", "A new line\nhere"])
def test_latex_injection_and_deletion_rejected(source, replacement):
    change = change_for(source).model_copy(update={"after": replacement})
    with pytest.raises(ValueError):
        apply_changes(source, [change])


def test_duplicate_unknown_and_stale_changes_rejected(source):
    change = change_for(source)
    for changes in ([change, change], [change.model_copy(update={"id": "missing"})], [change.model_copy(update={"before": "outdated"})]):
        with pytest.raises(ValueError):
            apply_changes(source, changes)


def test_metric_multiplicity_preserved():
    with pytest.raises(ValueError, match="number"):
        validate_change("Built 10 pipelines and 10 reporting jobs for reliable data processing.", "Built 10 pipelines and reporting jobs for reliable data processing.")


@pytest.mark.parametrize("data", [b"", b"x" * (512 * 1024 + 1), b"\xff", b"not latex"])
def test_bad_source(data):
    with pytest.raises(ValueError):
        decode_source(data)


def test_model_cannot_change_whole_document(source, monkeypatch):
    change = change_for(source)
    invalid = change.model_copy(update={"id": "fake"})
    monkeypatch.setattr(rewrite, "_generate_json", lambda *a: ({"changes": [change.model_dump(), invalid.model_dump()], "notes": "Review facts"}, "test-model"))
    result = rewrite.propose_latex(source, "A Python software engineer position working on reporting APIs.")
    assert len(result.changes) == 1
    assert "excluded" in result.notes
    assert result.model_used == "test-model"


def test_full_bullet_context_is_not_truncated_at_formatting():
    bullet = r"Implemented reliable workflows for distributed services using \textbf{checkpointing and recovery} to reduce redundant reprocessing by 60--70\% and improve reliability across long-running pipelines."
    source = r"\begin{document}\resumeItem{" + bullet + r"}\end{document}"
    spans = editable_spans(source)
    assert spans
    assert all(s.context == bullet for s in spans)


def test_whitespace_echo_is_anchored_to_exact_source(source, monkeypatch):
    source = source.replace("daily reporting", "daily\n reporting")
    span = editable_spans(source)[0]
    before = " ".join(span.text.split())
    after = before.replace("Designed", "Engineered")
    monkeypatch.setattr(rewrite, "_generate_json", lambda *a: ({"changes": [{"id": span.id, "before": before, "after": after}]}, "test-model"))
    result = rewrite.propose_latex(source, "Python software engineering and operational reporting role.")
    assert len(result.changes) == 1
    assert result.changes[0].before == span.text
    edited = apply_changes(source, result.changes)
    assert edited == source.replace(span.text, after, 1)


def test_all_rejected_suggestions_are_repaired_once(source, monkeypatch):
    span = editable_spans(source)[0]
    invalid = {"id": span.id, "before": span.text, "after": span.text.replace("Python", "Kubernetes")}
    valid = {"id": span.id, "before": span.text, "after": span.text.replace("Designed", "Engineered")}
    requests = []
    def generate(system, user):
        requests.append((system, user))
        return {"changes": [invalid if len(requests) == 1 else valid]}, "test-model"
    monkeypatch.setattr(rewrite, "_generate_json", generate)
    result = rewrite.propose_latex(source, "Python software engineering and operational reporting role.")
    assert len(requests) == 2
    assert len(result.changes) == 1
    assert not result.rejected_changes
    assert "corrected automatically" in result.notes
    assert "complete_bullet_context" in requests[0][1]
    assert "truncated or broken sentence" in requests[0][0]
    assert "named technology" in requests[1][1]


def test_all_rejected_suggestions_show_exact_reasons(source, monkeypatch):
    span = editable_spans(source)[0]
    invalid = {"id": span.id, "before": span.text, "after": span.text.replace("internal", "external")}
    requests = []
    def generate(*args):
        requests.append(args)
        return {"changes": [invalid], "notes": "All edits are valid."}, "test-model"
    monkeypatch.setattr(rewrite, "_generate_json", generate)
    result = rewrite.propose_latex(source, "Python software engineering and operational reporting role.")
    assert len(requests) == 2
    assert not result.changes
    assert len(result.rejected_changes) == 1
    assert "qualifier" in result.rejected_changes[0].reason
    assert "No selectable" in result.notes
    assert "All edits are valid" not in result.notes


def test_failed_repair_still_returns_rejection_details(source, monkeypatch):
    span = editable_spans(source)[0]
    invalid = {"id": span.id, "before": span.text, "after": span.text.replace("internal", "external")}
    requests = []
    def generate(*args):
        requests.append(args)
        if len(requests) > 1:
            raise RuntimeError("Provider unavailable")
        return {"changes": [invalid]}, "test-model"
    monkeypatch.setattr(rewrite, "_generate_json", generate)
    result = rewrite.propose_latex(source, "Python software engineering and operational reporting role.")
    assert not result.changes
    assert result.rejected_changes
    assert "could not finish" in result.notes
