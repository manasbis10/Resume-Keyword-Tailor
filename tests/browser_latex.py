"""Browser check with mocked suggestions and real sandboxed PDF compilation.

Run with the app started: python -m tests.browser_latex [base URL]
No model call is made. Uses the synthetic example, never personal documents.
"""
import base64
import io
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

from app.latex_build import compile_latex
from app.latex_edit import editable_spans
from app.models import LatexChange
from app.latex_preview import preview_pages


def run():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    source = Path("examples/resume.tex").read_text()
    spans = editable_spans(source)
    changes = [LatexChange(id=s.id, before=s.text, after=s.text.replace("Designed", "Engineered"), reason="Clearer wording without changing experience.").model_dump() for s in (spans[0], next(span for span in spans if span.text.startswith("Designed and implemented")))]
    original = compile_latex(source, {}, "resume.tex")
    proposal = {"changes": changes, "notes": "All skills, qualifiers, and project bullets remain in place.", "original_pdf_base64": base64.b64encode(original.pdf).decode(), "original_pages": 1, "original_preview": preview_pages(original.pdf)}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base_url)
        expect(page.locator("#workflow")).to_have_value("latex")
        page.locator("#resume").set_input_files("examples/resume.tex")
        page.locator("#job_text").fill("We need a Python software engineer building APIs, distributed workflows, and reliable reporting systems.")
        page.route("**/api/latex/propose", lambda route: route.fulfill(json=proposal))
        page.locator("#submit").click()
        expect(page.locator("#latex-review")).to_be_visible()
        expect(page.locator(".change-card")).to_have_count(2)
        page.locator("#changes input").nth(1).uncheck()
        page.locator("#compile").click()
        expect(page.locator("#compiled-result")).to_be_visible(timeout=20000)
        expect(page.locator("#compile-status")).to_contain_text("Applied 1 selected change")
        expect(page.locator("#page-count")).to_contain_text("Original: 1 page(s) · Edited: 1 page(s)")
        expect(page.locator("#latex-warnings")).to_be_hidden()
        expect(page.locator("#compiled-pdf img")).to_have_count(1)
        assert page.locator("#compiled-pdf img").evaluate("el => el.complete && el.naturalWidth > 0")
        with page.expect_download() as info:
            page.locator("#tex-download").click()
        edited = Path(info.value.path()).read_text()
        assert edited == source.replace(changes[0]["before"], changes[0]["after"], 1)
        assert changes[1]["before"] in edited
        assert "GraphQL (familiar)" in edited
        with page.expect_download() as info:
            page.locator("#latex-download").click()
        reader = PdfReader(info.value.path())
        assert len(reader.pages) == 1
        assert sum(len(p.get("/Annots", [])) for p in reader.pages) == 2
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        assert "Engineered" in text and "SHA-1" in text and "familiar" in text
        page.screenshot(path="/tmp/resume-tailor-latex-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path="/tmp/resume-tailor-latex-mobile.png", full_page=True)
        # A changed selection must invalidate previously compiled downloads.
        page.locator("#changes input").first.uncheck()
        expect(page.locator("#compiled-result")).to_be_hidden()
        page.locator("#compile").click()
        expect(page.locator("#compile-status")).to_contain_text("Applied 0 selected change", timeout=20000)
        # Editing the input must discard the old proposal and results.
        page.locator("#job_text").fill("A different job description with Python APIs and reporting requirements.")
        expect(page.locator("#latex-review")).to_be_hidden()
        # Reproduce the reported empty state: the model proposed edits, but
        # every edit failed preservation checks. Nothing should look selectable.
        rejected = {
            **proposal, "changes": [], "notes": "No selectable edits passed the checks.",
            "rejected_changes": [{"id": changes[0]["id"], "before": changes[0]["before"],
                                  "after": "Built external dashboards using Kubernetes.",
                                  "reason": "A replacement changed a proficiency or scope qualifier."}],
        }
        page.unroute("**/api/latex/propose")
        page.route("**/api/latex/propose", lambda route: route.fulfill(json=rejected))
        page.locator("#submit").click()
        expect(page.locator("#no-changes")).to_be_visible()
        expect(page.locator("#changes input")).to_have_count(0)
        expect(page.locator("#selection-controls")).to_be_hidden()
        expect(page.locator("#compile")).to_have_text("Compile original unchanged")
        expect(page.locator("#rejected-changes")).to_be_visible()
        expect(page.locator("#rejected-list")).to_contain_text("scope qualifier")
        expect(page.locator("#retry-suggestions")).to_be_visible()
        # Regenerating can produce selectable suggestions without losing inputs.
        page.unroute("**/api/latex/propose")
        page.route("**/api/latex/propose", lambda route: route.fulfill(json=proposal))
        page.locator("#retry-suggestions").click()
        expect(page.locator("#changes input")).to_have_count(2)
        expect(page.locator("#rejected-changes")).to_be_hidden()
        expect(page.locator("#selection-count")).to_have_text("2 of 2 changes selected")
        page.locator("#clear-selection").click()
        expect(page.locator("#selection-count")).to_have_text("0 of 2 changes selected")
        page.locator('label[for="change-0"]').click()
        expect(page.locator("#change-0")).to_be_checked()
        expect(page.locator("#selection-count")).to_have_text("1 of 2 changes selected")
        page.locator("#select-all").click()
        expect(page.locator("#selection-count")).to_have_text("2 of 2 changes selected")
        assert not errors, errors
        browser.close()
    print("LaTeX browser checks passed: proposal review, selected patches, real compilation, links, page count, source download, mobile layout, stale-result invalidation, rejected suggestions, regeneration, and selection controls.")


if __name__ == "__main__":
    run()
