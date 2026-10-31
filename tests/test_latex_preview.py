import base64
import io

from PIL import Image

from app.latex_preview import preview_pages


def test_pdf_preview_is_an_actual_image(resume_pdf):
    pages = preview_pages(resume_pdf)
    assert len(pages) == 1
    image = Image.open(io.BytesIO(base64.b64decode(pages[0])))
    assert image.format == "PNG"
    assert image.width > 500 and image.height > 500
