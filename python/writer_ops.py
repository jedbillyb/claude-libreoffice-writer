"""UNO document operations, executed inside the LibreOffice process.

These run in-process against the live document model, so they are the only code
that touches UNO. They perform the *actual* apply; the preview-then-apply gating
lives in the panel, which calls apply_* only after the user clicks Apply.
"""

import difflib
import re

import uno
from com.sun.star.beans import PropertyValue  # noqa: F401  (kept for callers)
from com.sun.star.awt.FontStrikeout import SINGLE as STRIKEOUT_SINGLE
from com.sun.star.awt.FontUnderline import SINGLE as UNDERLINE_SINGLE


def get_desktop(ctx):
    smgr = ctx.getServiceManager()
    return smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)


def current_text_doc(ctx):
    """Return the active Writer document model, or None if it isn't a text doc."""
    desktop = get_desktop(ctx)
    comp = desktop.getCurrentComponent()
    if comp is None:
        return None
    if comp.supportsService("com.sun.star.text.TextDocument"):
        return comp
    return None


def get_document_text(doc):
    if doc is None:
        return ""
    return doc.getText().getString()


def get_selection(doc):
    """Return the currently selected text ('' if no/empty selection)."""
    if doc is None:
        return ""
    controller = doc.getCurrentController()
    selection = controller.getSelection()
    if selection is None or not hasattr(selection, "getCount"):
        return ""
    if selection.getCount() == 0:
        return ""
    text_range = selection.getByIndex(0)
    return text_range.getString()


# ---------------------------------------------------------------------------
# In-document preview: a proposed edit is written into the document as an inline
# word-level diff (deletions struck through on a red wash, insertions on a green
# wash) so the user can see exactly what changed in context, then Apply (collapse
# to the new text) or Reject (restore the original). One pending preview at a
# time, tracked by a bookmark so it survives the user clicking around.
# ---------------------------------------------------------------------------
INSERT_BACK = 0xCCEFCC   # light green wash behind added words
INSERT_FORE = 0x116611   # dark green added-text colour
DELETE_BACK = 0xF6CCCC   # light red wash behind removed words
DELETE_FORE = 0x992222   # dark red removed-text colour
PREVIEW_BOOKMARK = "ClaudePreview"

# Char properties the diff touches; reset to default to clear the preview wash.
_DIFF_PROPS = ("CharBackColor", "CharColor", "CharStrikeout", "CharUnderline")


def _clear_stale_preview(doc):
    bms = doc.getBookmarks()
    if bms.hasByName(PREVIEW_BOOKMARK):
        doc.getText().removeTextContent(bms.getByName(PREVIEW_BOOKMARK))


def _tokenize(s):
    """Split into words and whitespace runs, preserving every character."""
    return re.findall(r"\s+|\S+", s)


def diff_runs(original, new):
    """Word-level diff as a list of ('equal'|'delete'|'insert', text) runs."""
    a, b = _tokenize(original), _tokenize(new)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    runs = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            runs.append(("equal", "".join(a[i1:i2])))
        elif tag == "delete":
            runs.append(("delete", "".join(a[i1:i2])))
        elif tag == "insert":
            runs.append(("insert", "".join(b[j1:j2])))
        elif tag == "replace":
            runs.append(("delete", "".join(a[i1:i2])))
            runs.append(("insert", "".join(b[j1:j2])))
    return runs


def _style_for(cursor, run_kind):
    """Set the char properties a collapsed cursor will hand to inserted text."""
    if run_kind == "insert":
        cursor.CharBackColor = INSERT_BACK
        cursor.CharColor = INSERT_FORE
        cursor.CharStrikeout = 0
        cursor.CharUnderline = UNDERLINE_SINGLE
    elif run_kind == "delete":
        cursor.CharBackColor = DELETE_BACK
        cursor.CharColor = DELETE_FORE
        cursor.CharStrikeout = STRIKEOUT_SINGLE
        cursor.CharUnderline = 0
    else:  # equal -> leave the document's own formatting alone
        for prop in _DIFF_PROPS:
            cursor.setPropertyToDefault(prop)


def _write_diff(body, anchor, runs):
    """Insert diff runs at the collapsed ``anchor`` cursor; bookmark the span."""
    start = anchor.getStart()
    for run_kind, text in runs:
        if not text:
            continue
        _style_for(anchor, run_kind)
        body.insertString(anchor, text, False)  # cursor moves past the run
    span = body.createTextCursorByRange(start)
    span.gotoRange(anchor.getEnd(), True)
    return span


def start_preview(doc, kind, new_text):
    """Write a proposed edit into the document as an inline diff and bookmark it.

    kind: 'replace_selection' | 'replace_document' | 'insert_at_cursor'.
    Returns {handle, original, new, kind} for a later accept/reject.
    """
    if doc is None:
        raise RuntimeError("No active Writer document.")
    body = doc.getText()
    controller = doc.getCurrentController()
    _clear_stale_preview(doc)

    undo = doc.getUndoManager()
    undo.enterUndoContext("Claude proposed change")
    try:
        if kind == "replace_selection":
            sel = controller.getSelection()
            if (sel is None or not hasattr(sel, "getCount")
                    or sel.getCount() == 0 or not sel.getByIndex(0).getString()):
                raise RuntimeError("Nothing is selected to replace.")
            cur = body.createTextCursorByRange(sel.getByIndex(0))
            original = cur.getString()
        elif kind == "replace_document":
            cur = body.createTextCursor()
            cur.gotoStart(False)
            cur.gotoEnd(True)
            original = cur.getString()
        elif kind == "insert_at_cursor":
            original = ""
            cur = body.createTextCursorByRange(controller.getViewCursor().getStart())
        else:
            raise RuntimeError("Unknown edit kind: %s" % kind)

        cur.setString("")  # clear the target region; cur collapses to its start
        span = _write_diff(body, cur, diff_runs(original, new_text))

        bm = doc.createInstance("com.sun.star.text.Bookmark")
        bm.setName(PREVIEW_BOOKMARK)
        body.insertTextContent(span, bm, True)  # absorb -> bookmark spans the diff
    finally:
        undo.leaveUndoContext()

    return {"handle": PREVIEW_BOOKMARK, "original": original,
            "new": new_text, "kind": kind}


def _collapse_preview(doc, handle, final_text, undo_label):
    """Replace the diff region with clean ``final_text`` and drop the bookmark."""
    bms = doc.getBookmarks()
    if not bms.hasByName(handle):
        return
    bm = bms.getByName(handle)
    undo = doc.getUndoManager()
    undo.enterUndoContext(undo_label)
    try:
        cur = doc.getText().createTextCursorByRange(bm.getAnchor())
        cur.setString(final_text)  # '' deletes (e.g. a rejected insertion)
        for prop in _DIFF_PROPS:
            cur.setPropertyToDefault(prop)
        if bms.hasByName(handle):
            doc.getText().removeTextContent(bms.getByName(handle))
    finally:
        undo.leaveUndoContext()


def accept_preview(doc, handle, new_text):
    """Apply the edit: collapse the diff to the proposed text, clean of styling."""
    _collapse_preview(doc, handle, new_text, "Claude change applied")


def reject_preview(doc, handle, original, kind):
    """Revert the edit: collapse the diff back to the original text."""
    _collapse_preview(doc, handle, original, "Claude change rejected")
