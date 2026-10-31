import io

from pypdf import PdfReader

from app.pdf_build import build_resume_pdf


def test_unicode_and_markup_are_preserved(tailored):
    tailored.name = "Zoë García"
    tailored.summary = "Built <APIs> & tools."
    tailored.extra_sections = {"Projects": ["An open-source café dashboard"]}
    pdf = PdfReader(io.BytesIO(build_resume_pdf(tailored)))
    text = "\n".join(page.extract_text() for page in pdf.pages)
    for value in ["Zoë García", "<APIs> & tools", "café", "25%"]:
        assert value in text


def test_multiple_pages(tailored):
    tailored.experience[0].bullets *= 100
    reader = PdfReader(io.BytesIO(build_resume_pdf(tailored)))
    assert len(reader.pages) > 1
    assert all(page.extract_text().strip() for page in reader.pages)
