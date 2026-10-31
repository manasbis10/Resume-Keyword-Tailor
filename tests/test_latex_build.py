import io
import zipfile
from collections import Counter

import pytest

from app.latex_build import CompilationError, CompiledLatex, compile_latex, compiler_status, layout_warnings, unpack_assets


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for name, content in files:
            z.writestr(name, content)
    return stream.getvalue()


def test_supporting_assets_keep_relative_paths():
    data = archive([("styles/resume.cls", "class text"), ("assets/photo.png", b"image")])
    assert unpack_assets(data, "main.tex") == {"styles/resume.cls": b"class text", "assets/photo.png": b"image"}


@pytest.mark.parametrize("name", ["../secret.tex", "/tmp/file.tex", "a/../../secret.tex", "a\\secret.tex", ".env", "main.tex", "script.sh"])
def test_bad_zip_paths_and_types(name):
    with pytest.raises(ValueError):
        unpack_assets(archive([(name, "test")]), "main.tex")


def test_layout_warnings_are_explicit():
    original = CompiledLatex(b"", 1, [(612, 792)], Counter({"https://example.com": 1}), 0)
    edited = CompiledLatex(b"", 2, [(612, 792)] * 2, Counter(), 1)
    warnings = layout_warnings(original, edited)
    assert any("Page count" in w for w in warnings)
    assert any("overflow" in w for w in warnings)
    assert any("links" in w for w in warnings)


def compiler_ready():
    status = compiler_status()
    return status["sandbox"] and "pdflatex" in status["engines"]


@pytest.mark.skipif(not compiler_ready(), reason="Isolated pdflatex is not installed")
def test_real_compilation_keeps_links():
    source = r"\documentclass{article}\usepackage{hyperref}\begin{document}\href{https://example.com}{My profile}\end{document}"
    result = compile_latex(source, {}, "main.tex")
    assert result.pdf.startswith(b"%PDF-")
    assert result.pages == 1
    assert result.links == Counter({"https://example.com": 1})


@pytest.mark.skipif(not compiler_ready(), reason="Isolated pdflatex is not installed")
def test_compiler_cannot_read_workspace_secret(tmp_path):
    secret = tmp_path / "secret.tex"
    secret.write_text("PRIVATE SECRET")
    source = r"\documentclass{article}\begin{document}\input{" + str(secret) + r"}\end{document}"
    with pytest.raises(CompilationError):
        compile_latex(source, {}, "main.tex")


@pytest.mark.skipif(not compiler_ready(), reason="Isolated pdflatex is not installed")
def test_invalid_latex_has_actionable_error():
    with pytest.raises(CompilationError, match="Undefined control"):
        compile_latex(r"\documentclass{article}\begin{document}\notARealCommand\end{document}", {}, "main.tex")


@pytest.mark.skipif(not compiler_ready(), reason="Isolated pdflatex is not installed")
def test_shell_escape_is_disabled():
    source = r"\documentclass{article}\begin{document}\immediate\write18{touch /work/shell-ran}\IfFileExists{shell-ran}{\errmessage{Shell escape was enabled}}{Shell disabled}\end{document}"
    assert compile_latex(source, {}, "main.tex").pages == 1


@pytest.mark.skipif(not compiler_ready(), reason="Isolated pdflatex is not installed")
def test_supporting_tex_file_compiles_unchanged():
    source = r"\documentclass{article}\begin{document}\input{sections/project}\end{document}"
    result = compile_latex(source, {"sections/project.tex": b"Preserved supporting project text."}, "main.tex")
    assert result.pages == 1


@pytest.mark.skipif(not compiler_ready() or "xelatex" not in compiler_status()["engines"], reason="Isolated XeLaTeX is not installed")
def test_xelatex_with_system_font():
    source = r"\documentclass{article}\usepackage{fontspec}\setmainfont{DejaVu Sans}\begin{document}Zoë García\end{document}"
    assert compile_latex(source, {}, "main.tex", "xelatex").pages == 1
