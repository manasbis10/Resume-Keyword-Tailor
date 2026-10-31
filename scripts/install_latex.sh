#!/usr/bin/env bash
# Install a user-local, pinned TinyTeX distribution; no sudo or shell profile edits.
set -euo pipefail
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'This helper supports Linux x86_64. Install TeX Live and set LATEX_BIN_DIR for other systems.' >&2
  exit 1
fi
latex_install_dir="${RESUME_LATEX_INSTALL_DIR:-$HOME/.local/share/resume-tailor}"
latex_temp_dir="$(mktemp -d)"
trap 'rm -rf "$latex_temp_dir"' EXIT
if [[ ! -x "$latex_install_dir/.TinyTeX/bin/x86_64-linux/pdflatex" ]]; then
  curl -fL --retry 2 -o "$latex_temp_dir/tinytex.tar.gz" \
    'https://github.com/rstudio/tinytex-releases/releases/download/v2026.10/TinyTeX-v2026.10.tar.gz'
  echo '4ac08282f9964cdd9698cb141bc4d9fa3418024f055f3568e573af42ab9d936b  '"$latex_temp_dir/tinytex.tar.gz" | sha256sum --check
  mkdir -p "$latex_install_dir"
  tar -xzf "$latex_temp_dir/tinytex.tar.gz" -C "$latex_install_dir"
fi
latex_package_manager="$latex_install_dir/.TinyTeX/bin/x86_64-linux/tlmgr"
"$latex_package_manager" update --self
"$latex_package_manager" install cm-super fontawesome5 titlesec marvosym preprint enumitem fancyhdr tools collection-fontsrecommended
printf '\nCompiler directory: %s\n' "$latex_install_dir/.TinyTeX/bin/x86_64-linux"
if ! command -v bwrap >/dev/null || ! command -v prlimit >/dev/null; then
  echo 'Install bubblewrap and util-linux using your system package manager to enable sandboxed compilation.'
fi
