"""Optional browser check: python -m tests.browser_smoke [base URL].

Uses a synthetic API response so this check never calls a paid provider.
Start the app separately before running this check.
"""
import base64
import io
import sys

from playwright.sync_api import expect, sync_playwright
from reportlab.pdfgen import canvas

from app.models import TailoredResume
from app.pdf_build import build_resume_pdf


def run():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    draft = TailoredResume(
        name="Zoë García", contact="zoe@example.com", skills=["Python", "SQL"],
        experience=[{"title": "Engineer", "company": "Acme", "dates": "2021-2024", "bullets": ["Built Python APIs; reduced latency by 25%."]}],
        keywords_used=["Python APIs"], notes="Unsupported Kubernetes experience was not added.",
    )
    payload = {"resume": draft.model_dump(), "filename": "zoe-tailored.pdf", "keywords_used": draft.keywords_used,
               "notes": draft.notes, "pdf_base64": base64.b64encode(build_resume_pdf(draft)).decode()}
    upload = io.BytesIO()
    pdf = canvas.Canvas(upload)
    pdf.drawString(40, 750, "Zoë García Engineer Python SQL 2021-2024 Acme Built Python APIs")
    pdf.save()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base_url)
        page.locator("#workflow").select_option("pdf")
        expect(page.locator("#result")).to_be_hidden()
        page.locator("#resume").set_input_files({"name": "resume.pdf", "mimeType": "application/pdf", "buffer": upload.getvalue()})
        page.locator("#submit").click()
        expect(page.locator("#status")).to_contain_text("Provide a job URL")
        page.locator("#job_text").fill("We need a software engineer experienced in Python APIs and SQL queries.")
        page.route("**/api/tailor", lambda route: route.fulfill(json=payload))
        page.locator("#submit").click()
        expect(page.locator("#result")).to_be_visible()
        expect(page.locator("#preview")).to_contain_text("Zoë García")
        expect(page.locator("#preview")).to_contain_text("25%")
        expect(page.locator("#keywords li")).to_have_text(["Python APIs"])
        with page.expect_download() as download_info:
            page.locator("#download").click()
        assert download_info.value.suggested_filename == "zoe-tailored.pdf"
        with open(download_info.value.path(), "rb") as downloaded:
            assert downloaded.read().startswith(b"%PDF-")
        page.screenshot(path="/tmp/resume-tailor-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path="/tmp/resume-tailor-mobile.png", full_page=True)
        page.unroute("**/api/tailor")
        page.route("**/api/tailor", lambda route: route.fulfill(status=429, json={"detail": "Rate limit reached. Try again later."}))
        page.locator("#submit").click()
        expect(page.locator("#status")).to_contain_text("Rate limit reached")
        expect(page.locator("#result")).to_be_hidden()
        expect(page.locator("#submit")).to_be_enabled()
        # Untrusted model text must stay text rather than becoming executable HTML.
        payload["resume"]["name"] = '<img src=x onerror="window.injected=true">'
        page.unroute("**/api/tailor")
        page.route("**/api/tailor", lambda route: route.fulfill(json=payload))
        page.locator("#submit").click()
        expect(page.locator("#preview")).to_contain_text("<img src=x")
        assert page.evaluate("window.injected") is None
        assert not errors, errors
        browser.close()
    print("Browser checks passed: validation, preview, download, mobile layout, retry, and escaped model output.")


if __name__ == "__main__":
    run()
