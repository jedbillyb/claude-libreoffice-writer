# Quill

**Quill** is a LibreOffice Writer extension — an AI writing assistant powered by
**Claude**. It adds a native **Quill** sidebar: chat with Claude, rewrite the
selected text, generate or continue writing, and summarise the document — with
every edit shown as an inline **diff** for **Apply / Reject** before it touches
your document.

It authenticates off your existing **Claude Code login (subscription)** via the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/python) — **no
Anthropic API key required.**

## How it works

```
LibreOffice (Writer)                         agent sidecar (Python 3.10+ venv)
  Quill sidebar panel   ── JSON over a pipe ──  claude-agent-sdk
  owns the document (UNO)                        in-process MCP server "writer"
  applies edits on approval                      drives Claude via Claude Code login
```

The extension exposes the document to Claude as **MCP tools**
(`get_document_text`, `get_selection`, `replace_selection`, `insert_at_cursor`).
Claude calls them; edit tools are gated by the sidebar's preview-then-apply UI.
The agent runs in a separate Python process (the *sidecar*) because LibreOffice's
bundled Python is usually too old for the SDK; the two talk over the subprocess
pipe. Document edits are applied in-process via UNO as single undoable steps.

## Prerequisites

1. **Claude Code CLI**, installed and logged in:
   ```
   claude        # then /login if needed
   ```
2. **LibreOffice** with Python scripting (standard on Linux).
3. A **Python 3.10+ environment with `claude-agent-sdk`** for the sidecar.

## Install

**Easiest — just install the extension; it sets itself up.** Install
`quill-writer.oxt` (Tools → Extension Manager → Add, or `unopkg add
quill-writer.oxt`), restart LibreOffice, and open the **Quill** sidebar. On
first run it auto-creates its own Python environment at
`~/.local/share/quill/venv` and installs the Claude Agent SDK — you'll
see "Setting up Claude…" in the panel for ~30s, then it's ready. Needs a
`python3` with `venv` on PATH (and the Claude Code CLI logged in).

**Or run the installer** (does the setup up-front instead of on first run, and
builds the `.oxt` for you):

```bash
./install.sh
```

It uses [`uv`](https://docs.astral.sh/uv/) or `python3 -m venv`. To remove
everything later: `./uninstall.sh`.

<details>
<summary>Manual install (what install.sh does)</summary>

```bash
uv venv .venv && uv pip install -r requirements.txt   # sidecar SDK env
mkdir -p ~/.config/quill
echo "$PWD/.venv/bin/python" > ~/.config/quill/python
PYTHON=.venv/bin/python ./build.sh                    # -> quill-writer.oxt
unopkg add --force quill-writer.oxt
```
</details>

### Pointing at a different Python

By default the panel launches `<extension>/.venv/bin/python`. Override with:

```bash
export QUILL_PYTHON=/path/to/python3   # has claude-agent-sdk installed
```

Optional model override: `export QUILL_MODEL=claude-opus-4-8`.

## Usage

- **Rewrite**: select text, ask e.g. *"make this more formal"* → Claude reads the
  selection and proposes a replacement; **Apply** or **Reject**.
- **Generate / continue**: place the cursor, ask *"continue this paragraph"* →
  Claude proposes an insertion to approve.
- **Summarise**: ask *"summarise this document"* → Claude reads the full text.
- **Chat**: ask anything; Claude answers in the panel without editing.

Applied edits are single undo steps — **Ctrl+Z** reverts cleanly.

## Project layout

| Path | Role |
|------|------|
| `python/claude_panel.py` | UNO sidebar factory + panel UI, thread marshalling |
| `python/sidecar_client.py` | Launches/streams the sidecar, routes document ops |
| `python/writer_ops.py` | UNO document read/edit operations |
| `sidecar/agent_main.py` | Agent loop: MCP server + `ClaudeSDKClient` |
| `sidecar/writer_tools.py` | The `mcp__writer__*` tool definitions |
| `*.xcu`, `description.xml`, `META-INF/manifest.xml` | Extension manifests |

## Testing the backbone (no GUI)

```bash
cd sidecar
../.venv/bin/python fake_panel_test.py ../.venv/bin/python "Make my selection formal."
```

This drives the real sidecar with a faked document and prints the tools Claude
called and the edits it proposed — verifying Claude Code auth and the MCP
round-trip without LibreOffice.

## Status

v0.1 — working: native sidebar (chat, rewrite selection, generate/continue,
summarise), in-document inline-diff preview with Apply / Improve / Reject,
whole-document rewrite, Enter-to-send, and Claude Code (subscription) auth with
no API key. Document operations and the agent round-trip are verified against a
live LibreOffice.

## License

MIT — see [LICENSE](LICENSE). "Quill" is the name of this extension; it is an
independent project and is not affiliated with or endorsed by Anthropic. Note:
the "Claude" name and the current sidebar icon are Anthropic brand assets and
are **not** covered by the MIT license; replace the icon before redistributing
if you don't have permission to use it.
