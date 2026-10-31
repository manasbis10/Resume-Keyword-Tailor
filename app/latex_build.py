"""Compile supplied templates in a filesystem and network-isolated Linux sandbox."""
from __future__ import annotations

import io
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pypdf import PdfReader

MAX_ASSET_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 40 * 1024 * 1024
ALLOWED_ASSETS = {".tex", ".sty", ".cls", ".ttf", ".otf", ".png", ".jpg", ".jpeg", ".pdf", ".eps", ".bib", ".bst", ".cfg", ".def", ".fd", ".map", ".enc"}
TINY_ROOT = Path.home() / ".local/share/resume-tailor/.TinyTeX"


class CompilerUnavailable(RuntimeError):
    pass


class CompilationError(ValueError):
    pass


@dataclass
class CompiledLatex:
    pdf: bytes
    pages: int
    sizes: list[tuple[float, float]]
    links: Counter
    overfull: int


def compiler_path(engine: str) -> Path | None:
    if engine not in {"pdflatex", "xelatex"}:
        raise ValueError("Choose pdflatex or xelatex.")
    root = Path(os.getenv("LATEX_BIN_DIR", str(TINY_ROOT / "bin/x86_64-linux")))
    local = root / engine
    if local.is_file() and os.access(local, os.X_OK):
        return local
    found = shutil.which(engine)
    return Path(found) if found else None


def compiler_status() -> dict:
    return {"engines": [name for name in ("pdflatex", "xelatex") if compiler_path(name)],
            "sandbox": bool(shutil.which("bwrap") and shutil.which("prlimit"))}


def unpack_assets(data: bytes, main_name: str) -> dict[str, bytes]:
    if not data:
        return {}
    if len(data) > MAX_ASSET_BYTES:
        raise ValueError("The supporting ZIP must be 20 MB or smaller.")
    result = {}
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if len(archive.infolist()) > 150:
                raise ValueError("The supporting ZIP contains too many entries (maximum 150).")
            for info in archive.infolist():
                path = PurePosixPath(info.filename)
                if info.is_dir():
                    continue
                if (path.is_absolute() or ".." in path.parts or "\\" in info.filename
                        or ":" in info.filename or "\x00" in info.filename
                        or any(part.startswith(".") for part in path.parts)
                        or stat.S_ISLNK(info.external_attr >> 16)):
                    raise ValueError("The ZIP contains an unsafe file path or symbolic link.")
                name = str(path)
                if name == main_name or name in result:
                    raise ValueError("The supporting ZIP must not duplicate the main .tex file or another asset.")
                if path.suffix.lower() not in ALLOWED_ASSETS:
                    raise ValueError(f"Unsupported supporting file type: {path.suffix or '(none)'}.")
                total += info.file_size
                if total > MAX_UNPACKED_BYTES:
                    raise ValueError("The ZIP expands beyond the 40 MB limit.")
                result[name] = archive.read(info)
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError("Could not read the supporting ZIP. Use an unencrypted ZIP archive.") from exc
    return result


def compile_latex(source: str, assets: dict[str, bytes], main_name: str, engine: str = "pdflatex") -> CompiledLatex:
    binary = compiler_path(engine)
    if binary is None:
        raise CompilerUnavailable(f"{engine} is not installed. Install TeX Live or TinyTeX and configure LATEX_BIN_DIR.")
    if not shutil.which("bwrap") or not shutil.which("prlimit"):
        raise CompilerUnavailable("LaTeX compilation requires Linux bubblewrap and prlimit for isolation.")
    # The executable may be a symlink (pdflatex -> pdftex), but the invocation
    # name selects the format. Bind the full installation without changing it.
    resolved = binary.resolve()
    tex_root = resolved.parent.parent.parent if "bin" in resolved.parts and resolved.parent.parent.name == "bin" else None
    with tempfile.TemporaryDirectory(prefix="resume-latex-") as temp:
        work = Path(temp)
        for name, data in assets.items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (work / main_name).write_text(source, encoding="utf-8", newline="")
        command = ["prlimit", "--as=1610612736", "--cpu=40", "--fsize=16777216", "--nofile=128", "--",
                   "bwrap", "--unshare-all", "--die-with-parent", "--new-session",
                   "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin", "--ro-bind", "/lib", "/lib"]
        if Path("/lib64").exists():
            command += ["--ro-bind", "/lib64", "/lib64"]
        command += ["--dir", "/etc"]
        for system_path in ("/etc/fonts", "/etc/texmf", "/var/lib/texmf", "/usr/local/texlive"):
            if Path(system_path).exists():
                command += ["--ro-bind", system_path, system_path]
        if tex_root and not str(tex_root).startswith("/usr/"):
            command += ["--ro-bind", str(tex_root), str(tex_root)]
        command += ["--bind", str(work), "/work", "--chdir", "/work", "--tmpfs", "/tmp",
                    "--proc", "/proc", "--dev", "/dev", "--clearenv",
                    "--setenv", "PATH", f"{binary.parent}:/usr/bin:/bin", "--setenv", "HOME", "/tmp",
                    "--setenv", "TEXMFVAR", "/tmp/texmf-var", "--setenv", "TEXMFCONFIG", "/tmp/texmf-config",
                    "--setenv", "openout_any", "p", "--setenv", "shell_escape", "f",
                    str(binary), "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
                    "-file-line-error", "-jobname=resume", main_name]
        for _ in range(2):
            with (work / "compiler-output.txt").open("wb") as output:
                process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    process.wait(timeout=50)
                except subprocess.TimeoutExpired as exc:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise CompilationError("LaTeX compilation timed out. Check the template for loops or expensive commands.") from exc
            log = (work / "compiler-output.txt").read_text(errors="replace")[-12000:]
            if process.returncode != 0:
                errors = [line for line in log.splitlines() if re.search(r"(?:Error:|^!|not found|Undefined control|bwrap:|can't write|Emergency stop)", line)]
                detail = " ".join(errors[:4])[:900]
                raise CompilationError("LaTeX could not compile this template. " + (detail or "Check missing packages, assets, and engine selection."))
        output_path = work / "resume.pdf"
        if not output_path.is_file() or output_path.stat().st_size > 16 * 1024 * 1024:
            raise CompilationError("The compiler did not produce a PDF within the 16 MB limit.")
        pdf = output_path.read_bytes()
        reader = PdfReader(io.BytesIO(pdf))
        links = Counter()
        for page in reader.pages:
            for ref in page.get("/Annots", []):
                uri = ref.get_object().get("/A", {}).get("/URI")
                if uri:
                    links[str(uri)] += 1
        return CompiledLatex(pdf, len(reader.pages), [(float(p.mediabox.width), float(p.mediabox.height)) for p in reader.pages], links,
                             len(re.findall(r"Overfull \\[hv]box", log)))


def layout_warnings(original: CompiledLatex, edited: CompiledLatex) -> list[str]:
    warnings = []
    if edited.pages != original.pages:
        warnings.append(f"Page count changed from {original.pages} to {edited.pages}. Uncheck longer edits if you want the original pagination.")
    if original.sizes != edited.sizes:
        warnings.append("Page geometry or page count differs from the original compilation.")
    if edited.overfull > original.overfull:
        warnings.append(f"The edited PDF has {edited.overfull - original.overfull} additional LaTeX overflow warning(s). Review line endings in the PDF.")
    if edited.links != original.links:
        warnings.append("Clickable links differ from the original compilation. Review the contact links.")
    return warnings
