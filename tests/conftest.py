import io

import pytest
from reportlab.pdfgen import canvas

from app.models import TailoredResume


@pytest.fixture
def resume_pdf():
    stream = io.BytesIO()
    doc = canvas.Canvas(stream)
    for i, line in enumerate([
        "Jane Doe", "jane@example.com", "Software Engineer | Acme | 2021-2024",
        "Built Python APIs and reduced latency by 25%.", "Skills: Python, SQL",
    ]):
        doc.drawString(50, 750 - i * 20, line)
    doc.save()
    return stream.getvalue()


@pytest.fixture
def tailored():
    return TailoredResume(
        name="Jane Doe", contact="jane@example.com", skills=["Python", "SQL"],
        experience=[{"title": "Software Engineer", "company": "Acme", "dates": "2021-2024",
                     "bullets": ["Built Python APIs and reduced latency by 25%."]}],
        keywords_used=["Python APIs"], notes="Kubernetes was not supported by the source.", model_used="test-model",
    )
