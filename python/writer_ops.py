"""UNO document operations, executed inside the LibreOffice process.

These run in-process against the live document model, so they are the only code
that touches UNO. They perform the *actual* apply; the preview-then-apply gating
lives in the panel, which calls apply_* only after the user clicks Apply.
"""

import uno
from com.sun.star.beans import PropertyValue  # noqa: F401  (kept for callers)


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
# In-document preview: a proposed edit is written into the document with a
# highlight so the user can read it in context, then Apply (keep, clear the
# highlight) or Reject (revert). One pending preview at a time, tracked by a
# bookmark so it survives the user clicking around.
# ---------------------------------------------------------------------------
PREVIEW_COLOR = 0xFFF6BF  # soft yellow highlight
PREVIEW_BOOKMARK = "ClaudePreview"


def _clear_stale_preview(doc):
    bms = doc.getBookmarks()
    if bms.hasByName(PREVIEW_BOOKMARK):
        doc.getText().removeTextContent(bms.getByName(PREVIEW_BOOKMARK))


def start_preview(doc, kind, new_text):
    """Write a proposed edit into the document, highlighted, and bookmark it.

    kind: 'replace_selection' | 'replace_document' | 'insert_at_cursor'.
    Returns {handle, original, kind} for a later accept/reject.
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
            cur.setString(new_text)
        elif kind == "replace_document":
            original = body.getString()
            cur = body.createTextCursor()
            cur.gotoStart(False)
            cur.gotoEnd(True)
            cur.setString(new_text)
        elif kind == "insert_at_cursor":
            original = ""
            cur = body.createTextCursorByRange(controller.getViewCursor().getStart())
            cur.setString(new_text)
        else:
            raise RuntimeError("Unknown edit kind: %s" % kind)

        cur.CharBackColor = PREVIEW_COLOR
        bm = doc.createInstance("com.sun.star.text.Bookmark")
        bm.setName(PREVIEW_BOOKMARK)
        body.insertTextContent(cur, bm, True)  # absorb -> bookmark spans the range
    finally:
        undo.leaveUndoContext()

    return {"handle": PREVIEW_BOOKMARK, "original": original, "kind": kind}


def accept_preview(doc, handle):
    """Keep the previewed text; just clear the highlight and the bookmark."""
    bms = doc.getBookmarks()
    if not bms.hasByName(handle):
        return
    bm = bms.getByName(handle)
    undo = doc.getUndoManager()
    undo.enterUndoContext("Claude change applied")
    try:
        cur = doc.getText().createTextCursorByRange(bm.getAnchor())
        cur.setPropertyToDefault("CharBackColor")
        doc.getText().removeTextContent(bm)
    finally:
        undo.leaveUndoContext()


def reject_preview(doc, handle, original, kind):
    """Revert the previewed text (restore original / delete insertion)."""
    bms = doc.getBookmarks()
    if not bms.hasByName(handle):
        return
    bm = bms.getByName(handle)
    undo = doc.getUndoManager()
    undo.enterUndoContext("Claude change rejected")
    try:
        cur = doc.getText().createTextCursorByRange(bm.getAnchor())
        cur.setPropertyToDefault("CharBackColor")
        cur.setString(original)  # '' for an insertion -> deletes it
        if bms.hasByName(handle):
            doc.getText().removeTextContent(bms.getByName(handle))
    finally:
        undo.leaveUndoContext()
