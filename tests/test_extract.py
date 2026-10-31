import io
import socket

import httpx
import pytest
from pypdf import PdfWriter

from app import extract


def test_pdf_extraction(resume_pdf):
    assert "Jane Doe" in extract.extract_pdf_text(resume_pdf)


def test_page_limit_and_encryption():
    writer = PdfWriter()
    for _ in range(21):
        writer.add_blank_page(width=612, height=792)
    stream = io.BytesIO()
    writer.write(stream)
    with pytest.raises(ValueError, match="20 pages"):
        extract.extract_pdf_text(stream.getvalue())
    writer.encrypt("password")
    stream = io.BytesIO()
    writer.write(stream)
    with pytest.raises(ValueError, match="password protected"):
        extract.extract_pdf_text(stream.getvalue())


def test_html_cleanup():
    assert extract._clean_html_text("<nav>Ignore</nav><main><h1>Engineer</h1><p>Python</p><script>bad</script></main>") == "Engineer\nPython"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/job", "http://user:pass@example.com", "http://example.com:9000"])
def test_disallowed_urls(url):
    with pytest.raises(ValueError):
        extract._public_target(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.2", "169.254.169.254", "::1", "::ffff:127.0.0.1", "0.0.0.0"])
def test_private_networks_blocked(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", (ip, 80))])
    with pytest.raises(ValueError, match="public website"):
        extract._public_target("http://example.com")


def mock_network(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(extract.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("93.184.215.14", 443))])


def test_fetch_pins_address_and_verifies_original_hostname(monkeypatch):
    def handler(request):
        assert request.url.host == "93.184.215.14"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(200, text="<main>Python job</main>", headers={"content-type": "text/html"})
    mock_network(monkeypatch, handler)
    assert extract.extract_job_from_url("https://example.com/job") == "Python job"


def test_redirect_target_checked(monkeypatch):
    mock_network(monkeypatch, lambda request: httpx.Response(302, headers={"location": "file:///etc/passwd"}))
    with pytest.raises(ValueError):
        extract.extract_job_from_url("https://example.com/job")


def test_redirect_loop(monkeypatch):
    mock_network(monkeypatch, lambda request: httpx.Response(302, headers={"location": "/loop"}))
    with pytest.raises(ValueError, match="too many"):
        extract.extract_job_from_url("https://example.com/job")


def test_oversized_page(monkeypatch):
    monkeypatch.setattr(extract, "MAX_JOB_BYTES", 100)
    mock_network(monkeypatch, lambda request: httpx.Response(200, content=b"a" * 101))
    with pytest.raises(ValueError, match="too large"):
        extract.extract_job_from_url("https://example.com/job")
