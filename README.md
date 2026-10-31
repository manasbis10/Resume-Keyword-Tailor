# Resume Keyword Tailor

Tailor the wording of an existing LaTeX resume without rebuilding its design. Upload the `.tex`, review proposed edits, select which to apply, and compile your original template into a PDF. Download both the PDF and the edited `.tex`.

## Run locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/), and Linux for isolated LaTeX compilation.

```bash
cp .env.example .env
# Edit .env and add OPENROUTER_API_KEY.
uv venv
uv pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [http://localhost:8000](http://localhost:8000). If that port is occupied, choose `--port 8001` instead. If using a remote IDE, forward the port in its Ports panel. Without uv, use `python -m venv .venv`, then `.venv/bin/python -m pip install -r requirements.txt`.

Create an API key at [OpenRouter](https://openrouter.ai/keys). The default [free router](https://openrouter.ai/openrouter/free) chooses an available free model. `OPENROUTER_MODEL` can prefer a particular model; HTTP 404/503 falls back to the free router. A paid model ID can incur provider charges. Authentication and rate-limit errors are returned directly. Restart after changing `.env`.

## LaTeX compiler setup

A user-local TinyTeX compiler has been installed in this workspace's host environment. On another Linux x86_64 machine, this helper installs a pinned, checksum-verified TinyTeX distribution and common resume packages:

```bash
bash scripts/install_latex.sh
```

It installs under `~/.local/share/resume-tailor/.TinyTeX`, without editing your shell profile or requiring sudo. Linux `bubblewrap` (`bwrap`) and `prlimit` (from util-linux) must also be installed. On Ubuntu/Debian, the system packages are `bubblewrap` and `util-linux`. An existing TeX Live installation works too: put its binaries on `PATH` or set `LATEX_BIN_DIR` in `.env` to the directory containing `pdflatex` and `xelatex`.

The app runs the compiler in a temporary filesystem with no network, no workspace or home access, no inherited API key, disabled shell escape, and CPU, memory, time, and output-file limits. It requires this sandbox and does not fall back to unrestricted compilation. Compiler package installation happens separately, outside document compilation.

If your template needs a package not installed, use your TeX distribution's package manager. For the installed TinyTeX, for example:

```bash
~/.local/share/resume-tailor/.TinyTeX/bin/x86_64-linux/tlmgr install package-name
```

Select the same engine as your template uses: usually pdfLaTeX, or XeLaTeX for templates using `fontspec` and OpenType fonts. Missing packages, unsupported commands, and missing local assets are reported before requesting model suggestions.

## Use your own template

1. Keep **LaTeX — preserve my template** selected.
2. Upload the complete UTF-8 `.tex` document (up to 512 KB).
3. If it uses local `.cls`, `.sty`, font, or image files, upload them in a supporting ZIP (up to 20 MB compressed / 40 MB expanded / 150 entries). Preserve relative folder paths and omit the main `.tex`. Built-in TeX packages do not need to be zipped. No absolute paths, symlinks, scripts, or parent-directory paths are accepted.
4. Paste a job description (40–24,000 characters) or provide a public job URL. Pasted text takes priority. Pages requiring login or JavaScript should be pasted instead.
5. Choose **Suggest text changes**. The app compiles your original template first, then proposes small prose patches. Each selectable suggestion shows its original wording, proposed wording, and reason. Select all / Clear selection and a live count make the current choice explicit.
6. Uncheck unwanted suggestions. The compile button shows how many changes will be applied; with none selected it says **Compile original unchanged**. Selecting none compiles the original unchanged, without calling a model.
7. Compare the original and edited PDF page images (first three pages shown). Review any page-count, geometry, overflow, or link warnings, then download the PDF and edited `.tex`. The supporting ZIP is unchanged and should be kept with the downloaded source.

`examples/resume.tex` is a synthetic one-page template for trying the workflow. It contains no personal resume data.

### What stays protected

The model never returns a replacement document. The server accepts only validated replacements for known source passages and inserts them at their exact character offsets. Everything outside selected passages stays unchanged, including the preamble, margins, fonts, section order, formatting commands, link targets, education, and project structure. No font shrinking, margin adjustments, or automatic section removal is used to force a page count.

The initial conservative editor supports direct prose inside `\resumeItem{...}`, `\resumeSubItem{...}`, and ordinary ungrouped `\item` bullets. Nested formatting arguments such as `\textbf{...}`, skills lists, math, headings, comments, and other macros are left unchanged. Included `.tex` files are compiled but are not edited. Unknown templates may yield few or no suggestions; unsupported source is never regenerated as a substitute.

Patch checks preserve numbers (including repeated metrics), capitalized technical names, selected proficiency/scope qualifiers such as “familiar,” “internal,” and “contributed,” and bounded passage length. Suggestions failing these checks are excluded and shown separately with specific rejection reasons. If every suggestion fails, the app makes one correction attempt using those reasons. It also supplies complete bullet context and tells the model that fragments split by formatting are not incomplete sentences. If no valid suggestions remain, the page clearly explains that there is nothing to select and offers regeneration. These checks do not prove semantic equivalence: review whether each edit truthfully describes your work. Longer text can still change line wrapping or pagination even with identical template code. Layout warnings compare against a fresh compilation of the uploaded source, not against an older PDF built on a different TeX installation.

## PDF input mode

The optional **PDF — rebuild in the app's layout** mode remains available. It extracts text, asks for a structured resume rewrite, and renders the app's own single-column PDF. It does **not** preserve the original design and has weaker content-preservation checks than LaTeX mode; review all sections and bullets carefully. Use LaTeX mode for design-sensitive resumes.

PDF input limits: text-based unlocked PDF, 5 MB, 20 pages, and 24,000 extracted characters. Scans require OCR first. The rebuilt PDF fonts support accented Latin, Greek, and Cyrillic; full CJK and complex-script shaping are not supported in that mode.

## Privacy and local use

App code does not permanently save uploads, suggestions, or generated resumes. Upload handling can temporarily spool files to disk; compilation uses temporary directories that are removed after the request. The proposal and original upload remain in the browser tab until the inputs change or the tab closes.

Editable passages and their complete bullet context, plus the job description, are sent to OpenRouter and the selected provider; their data policies apply. A supplied URL is fetched by the server. Public-address resolution is pinned and rechecked on each redirect; local/private networks, custom ports, and oversized pages are rejected. Keys remain server-side, and model-provider error bodies are not returned to the browser.

Keep the default loopback binding. This is a single-user local app; public hosting would need authentication, request quotas, and deployment-level upload limits.

## Verification

```bash
uv pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Tests cover exact source patches, preserved projects/links/qualifiers, malformed edits, metrics and duplicate passages, ZIP traversal and asset limits, compiler isolation, real compilation (when the compiler is installed), layout warnings, model fallback, PDF processing, and both API workflows. Provider calls are mocked in automated tests; no API key is required.

For browser checks, start the app, then run:

```bash
.venv/bin/playwright install chromium
.venv/bin/python -m tests.browser_latex http://127.0.0.1:8000
.venv/bin/python -m tests.browser_smoke http://127.0.0.1:8000
```

The LaTeX check mocks model suggestions and uses real compilation. It verifies selective approval, PDF previews, actual PDF and source downloads, preserved links and page count, mobile overflow, and invalidation of stale results. The legacy PDF browser check mocks the rewrite response. Both use synthetic documents. Screenshots are written under `/tmp/resume-tailor-*`.

## API

- `GET /api/health`: app status, key presence, configured model.
- `GET /api/latex/health`: available engines and sandbox prerequisites.
- `POST /api/latex/propose`: multipart `resume` (`.tex`), optional `assets` (ZIP), `engine`, and `job_text`/`job_url`; returns validated change proposals, original PDF and preview images.
- `POST /api/latex/compile`: multipart original `resume`, optional `assets`, `engine`, and JSON `changes`; returns the edited source, original and edited PDFs, preview images, page counts, and warnings. Revalidates every selected patch; needs no model call or API key.
- `POST /api/tailor`: legacy PDF workflow.
- `GET /docs`: interactive API reference.

Bundled fonts for PDF input mode are licensed under `app/fonts/LICENSE`. TinyTeX is installed outside the repository and maintains its own package licenses.
