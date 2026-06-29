#!/usr/bin/env bash
# One-shot installer for Quill, the Claude-powered LibreOffice Writer extension.
# Creates the sidecar Python environment, installs the Claude Agent SDK, points
# the extension at it, builds the .oxt, and installs it into LibreOffice.
set -euo pipefail
cd "$(dirname "$0")"
EXT_DIR="$PWD"
VENV="$EXT_DIR/.venv"
PY="$VENV/bin/python"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! \033[0m %s\n' "$*"; }

say "Quill for LibreOffice Writer — installer"

# 1. Prerequisites -----------------------------------------------------------
command -v soffice >/dev/null || { echo "LibreOffice ('soffice') not found. Install LibreOffice first."; exit 1; }
command -v unopkg  >/dev/null || { echo "'unopkg' not found (ships with LibreOffice)."; exit 1; }

if ! command -v claude >/dev/null; then
  warn "Claude Code CLI ('claude') is not on your PATH."
  warn "Install it and run 'claude' to log in — the extension uses that login (no API key)."
fi

# 2. Sidecar Python environment with the SDK (idempotent) -------------------
say "Setting up the sidecar Python environment (.venv)…"
if [ -x "$PY" ]; then
  say "Reusing existing venv."
elif command -v uv >/dev/null; then
  uv venv "$VENV"
elif ! python3 -m venv "$VENV" 2>/dev/null || ! "$PY" -m pip --version >/dev/null 2>&1; then
  echo "Could not create a Python environment. Install 'uv' (https://docs.astral.sh/uv/)"
  echo "or a python3 with venv+pip, then re-run."; exit 1
fi

say "Installing/updating the Claude Agent SDK…"
if command -v uv >/dev/null; then
  uv pip install --python "$PY" -r requirements.txt
else
  "$PY" -m pip install -r requirements.txt
fi

"$PY" -c "import claude_agent_sdk" 2>/dev/null \
  || { echo "claude-agent-sdk failed to import in the new venv."; exit 1; }
say "SDK installed: $("$PY" -c 'import claude_agent_sdk as c; print(getattr(c,"__version__","?"))')"

# 3. Tell the extension which interpreter to use ----------------------------
mkdir -p "$HOME/.config/quill"
printf '%s\n' "$PY" > "$HOME/.config/quill/python"
say "Configured interpreter -> $PY"

# 4. Build and install the extension ----------------------------------------
say "Building the extension package…"
PYTHON="$PY" ./build.sh >/dev/null

if pgrep -x soffice.bin >/dev/null 2>&1; then
  warn "LibreOffice is running — installing with --force; restart it afterwards."
fi
say "Installing into LibreOffice…"
unopkg add --force "$EXT_DIR/quill-writer.oxt"

echo
say "Done. Restart LibreOffice, open Writer, and choose the Quill sidebar tab."
command -v claude >/dev/null || warn "Remember to install + log in to the Claude Code CLI."
