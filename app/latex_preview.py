"""Render PDF thumbnails without depending on browser PDF plug-ins."""
import base64
import io
import threading

import pypdfium2 as pdfium

_LOCK = threading.Lock()  # PDFium calls must not execute concurrently.


def preview_pages(data: bytes) -> list[str]:
    result = []
    with _LOCK:
        with pdfium.PdfDocument(data) as document:
            for index in range(min(len(document), 3)):
                page = document[index]
                bitmap = None
                try:
                    scale = min(1.4, 1400 / max(page.get_width(), page.get_height()))
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil()
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    result.append(base64.b64encode(buffer.getvalue()).decode("ascii"))
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
    return result
