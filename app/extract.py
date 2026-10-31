from __future__ import annotations

import io
import ipaddress
import re
import socket

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.config import MAX_JOB_BYTES, MAX_PDF_PAGES

USER_AGENT = "ResumeKeywordTailor/1.0"


def extract_pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise ValueError("The file is not a valid PDF.")
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("This PDF is password protected. Upload an unlocked copy.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"Use a PDF with at most {MAX_PDF_PAGES} pages.")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _clean_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
    return re.sub(r"\n{3,}", "\n\n", main.get_text("\n", strip=True)).strip()


def _public_target(url: str) -> tuple[httpx.URL, str]:
    """Resolve once and pin the connection to a public IP (including redirects)."""
    try:
        target = httpx.URL(url)
        if target.scheme not in {"http", "https"} or not target.host:
            raise ValueError("Job URL must be a public http:// or https:// URL.")
        if target.username or target.password or target.port not in {None, 80, 443}:
            raise ValueError("Job URLs cannot contain credentials or custom ports.")
        addresses = socket.getaddrinfo(target.host, target.port or (443 if target.scheme == "https" else 80), type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(item[4][0] for item in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError("Job URLs must point to a public website, not a local or private address.")
        return target, ips[0]
    except (socket.gaierror, httpx.InvalidURL) as exc:
        raise ValueError("The job website address could not be resolved.") from exc


def extract_job_from_url(url: str) -> str:
    with httpx.Client(follow_redirects=False, timeout=20.0, trust_env=False) as client:
        for _ in range(6):
            target, ip = _public_target(url)
            # Keep Host and TLS certificate verification tied to the original hostname.
            with client.stream(
                "GET", target.copy_with(host=ip),
                headers={"User-Agent": USER_AGENT, "Host": target.netloc.decode("ascii")},
                extensions={"sni_hostname": target.host},
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("The job website returned an invalid redirect.")
                    url = str(target.join(location))
                    continue
                response.raise_for_status()
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_JOB_BYTES:
                        raise ValueError("That job page is too large. Paste the description instead.")
                    chunks.append(chunk)
                data = b"".join(chunks)
                content_type = response.headers.get("content-type", "").lower()
                if "pdf" in content_type or data.startswith(b"%PDF-"):
                    return extract_pdf_text(data)
                if content_type and not any(kind in content_type for kind in ("text/", "application/xhtml+xml")):
                    raise ValueError("That URL does not return a job page or PDF.")
                return _clean_html_text(data.decode(response.encoding or "utf-8", errors="replace"))
    raise ValueError("The job website redirected too many times. Paste the description instead.")
