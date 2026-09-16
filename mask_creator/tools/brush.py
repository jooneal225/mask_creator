"""Freehand paintbrush."""

from __future__ import annotations

import pyqtgraph as pg
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtWidgets import QGraphicsEllipseItem

from ..rasterize import rasterize_stroke
from .base import BaseTool


class BrushTool(BaseTool):
    title = "Paintbrush"
    buttons = ("cancel",)  # strokes commit on mouse release; there is nothing to Apply

    def __init__(self, window):
        super().__init__(window)
        self._cursor = None
        self._stroke = []
        self._preview = None

    # -- lifecycle ---------------------------------------------------------

    def activate(self):
        self._cursor = QGraphicsEllipseItem()
        self._cursor.setPen(pg.mkPen("#00e5ff", width=1))
        self._cursor.setBrush(pg.mkBrush(0, 229, 255, 40))
        self._cursor.setZValue(25)
        self._cursor.setVisible(False)
        self.viewbox.addItem(self._cursor, ignoreBounds=True)

        self._preview = pg.PlotDataItem(pen=None)
        self.window.status(
            "Paintbrush: click and drag to paint. The Add/Remove switch decides "
            "whether the stroke adds to or erases from the mask."
        )

    def deactivate(self):
        if self._cursor is not None:
            self.viewbox.removeItem(self._cursor)
            self._cursor = None
        self._stroke = []
        self.window.clear_stroke_preview()

    # -- mouse -------------------------------------------------------------

    def on_click(self, ev, pos):
        """A bare click (press and release without moving) still paints a dot."""
        if ev.button() != Qt.LeftButton:
            return False
        selection = rasterize_stroke(
            [(pos.x(), pos.y())], self.window.brush_size, self.image_shape
        )
        self.commit(selection)
        return True

    def on_drag(self, ev, pos):
        if ev.button() != Qt.LeftButton:
            return False

        if ev.isStart():
            self._stroke = [(pos.x(), pos.y())]
        else:
            self._stroke.append((pos.x(), pos.y()))

        self._move_cursor(pos)

        if ev.isFinish():
            selection = rasterize_stroke(
                self._stroke, self.window.brush_size, self.image_shape
            )
            self._stroke = []
            self.window.clear_stroke_preview()
            # One model.apply per stroke, so undo steps back a whole stroke.
            self.commit(selection)
        else:
            self.window.show_stroke_preview(
                rasterize_stroke(
                    self._stroke, self.window.brush_size, self.image_shape
                )
            )
        return True

    def on_hover(self, pos):
        if self._cursor is None:
            return
        if pos is None:
            self._cursor.setVisible(False)
            return
        self._move_cursor(pos)

    # -- internals ---------------------------------------------------------

    def _move_cursor(self, pos):
        if self._cursor is None:
            return
        r = self.window.brush_size / 2.0
        self._cursor.setRect(QRectF(pos.x() - r, pos.y() - r, 2 * r, 2 * r))
        self._cursor.setVisible(True)

    def update_size(self):
        """Called when the size slider moves, so the cursor ring keeps up."""
        if self._cursor is not None and self._cursor.isVisible():
            rect = self._cursor.rect()
            cx, cy = rect.center().x(), rect.center().y()
            r = self.window.brush_size / 2.0
            self._cursor.setRect(QRectF(cx - r, cy - r, 2 * r, 2 * r))
