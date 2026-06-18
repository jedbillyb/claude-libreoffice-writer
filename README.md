# Claude Assistant for LibreOffice Writer

A LibreOffice Writer extension that adds a native **Claude** sidebar: chat with
Claude, rewrite the selected text, generate or continue writing, and summarise
the document — with every edit previewed for **Apply / Reject** before it
touches your document.

It authenticates off your existing **Claude Code login (subscription)** via the
[Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/python) — **no
Anthropic API key required.**

## How it works

```
LibreOffice (Writer)                         agent sidecar (Python 3.10+ venv)
  Claude sidebar panel  ── JSON over a pipe ──  claude-agent-sdk
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

One command does everything — creates the sidecar Python environment, installs
the Claude Agent SDK, points the extension at it, builds the `.oxt`, and installs
it into LibreOffice:

```bash
./install.sh
```

It needs [`uv`](https://docs.astral.sh/uv/) (preferred) or a `python3` with
`venv`+`pip`. Then **restart LibreOffice**, open Writer, and pick the **Claude**
tab in the sidebar. To remove it later: `./uninstall.sh`.

<details>
<summary>Manual install (what install.sh does)</summary>

```bash
uv venv .venv && uv pip install -r requirements.txt   # sidecar SDK env
mkdir -p ~/.config/claude-writer
echo "$PWD/.venv/bin/python" > ~/.config/claude-writer/python
PYTHON=.venv/bin/python ./build.sh                    # -> claude-writer.oxt
unopkg add --force claude-writer.oxt
```
</details>

### Pointing at a different Python

By default the panel launches `<extension>/.venv/bin/python`. Override with:

```bash
export CLAUDE_WRITER_PYTHON=/path/to/python3   # has claude-agent-sdk installed
```

Optional model override: `export CLAUDE_WRITER_MODEL=claude-opus-4-8`.

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
summarise), in-document highlighted preview with Apply / Improve / Reject,
whole-document rewrite, Enter-to-send, and Claude Code (subscription) auth with
no API key. Document operations and the agent round-trip are verified against a
live LibreOffice.

## License

MIT — see [LICENSE](LICENSE). Note: the Claude name and the sidebar icon are
Anthropic brand assets and are **not** covered by the MIT license; replace the
icon before redistributing if you don't have permission to use it.
