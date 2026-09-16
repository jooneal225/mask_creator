"""A ViewBox that lets the active tool see mouse events before pan/zoom does."""

from __future__ import annotations

import pyqtgraph as pg
from PyQt5.QtCore import Qt


class MaskViewBox(pg.ViewBox):
    """Routes mouse input to ``active_tool`` first.

    A tool handler returns True to consume the event; anything it does not
    consume falls through to the normal ViewBox behaviour, so wheel-zoom and
    right-drag keep working even while the paintbrush owns the left button.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.active_tool = None
        self.setMenuEnabled(True)

    # -- event routing -----------------------------------------------------

    def mouseClickEvent(self, ev):
        tool = self.active_tool
        if tool is not None and tool.on_click(ev, self._image_pos(ev)):
            ev.accept()
            return
        super().mouseClickEvent(ev)

    def mouseDragEvent(self, ev, axis=None):
        tool = self.active_tool
        if (
            tool is not None
            and axis is None
            and ev.button() == Qt.LeftButton
            and tool.on_drag(ev, self._image_pos(ev))
        ):
            ev.accept()
            return
        super().mouseDragEvent(ev, axis=axis)

    def hoverEvent(self, ev):
        # Defining this method is what opts the ViewBox into receiving hover
        # events at all -- pyqtgraph's scene dispatches on hasattr -- so the
        # base class has nothing to chain to on most versions.  Forward only
        # if some future version does define it.
        tool = self.active_tool
        if tool is not None:
            if ev.isExit():
                tool.on_hover(None)
            else:
                tool.on_hover(self.mapSceneToView(ev.scenePos()))
        parent_hover = getattr(super(), "hoverEvent", None)
        if parent_hover is not None:
            parent_hover(ev)

    # -- helpers -----------------------------------------------------------

    def _image_pos(self, ev):
        """Event position in image/data coordinates."""
        return self.mapSceneToView(ev.scenePos())
