"""Click-to-place polygon tool."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt

from ..rasterize import rasterize_polygon
from .base import BaseTool


class PolygonTool(BaseTool):
    title = "Polygon"
    buttons = ("apply", "complete", "cancel")

    def __init__(self, window):
        super().__init__(window)
        self._points = []
        self._roi = None        # set once the polygon is completed
        self._preview = None    # PlotDataItem for the in-progress outline
        self._cursor = None     # rubber-band segment to the cursor

    # -- lifecycle ---------------------------------------------------------

    def activate(self):
        self._preview = pg.PlotDataItem(
            pen=pg.mkPen(self.color, width=2),
            symbol="o",
            symbolSize=7,
            symbolBrush=self.color,
            symbolPen=None,
        )
        self._preview.setZValue(20)
        self._cursor = pg.PlotDataItem(
            pen=pg.mkPen(self.color, width=1, style=Qt.DashLine)
        )
        self._cursor.setZValue(20)
        self.viewbox.addItem(self._preview)
        self.viewbox.addItem(self._cursor)
        self._refresh()
        self.window.status(
            "Polygon: click to add vertices, right-click to undo the last one. "
            "Complete Polygon closes and lets you drag it; Apply commits."
        )

    def deactivate(self):
        for item in (self._preview, self._cursor, self._roi):
            if item is not None:
                self.viewbox.removeItem(item)
        self._preview = self._cursor = self._roi = None
        self._points = []

    def update_color(self):
        if self._preview is not None:
            self._preview.setPen(pg.mkPen(self.color, width=2))
            self._preview.setSymbolBrush(self.color)
        if self._cursor is not None:
            self._cursor.setPen(pg.mkPen(self.color, width=1, style=Qt.DashLine))
        if self._roi is not None:
            self._roi.setPen(pg.mkPen(self.color, width=2))

    # -- mouse -------------------------------------------------------------

    def on_click(self, ev, pos):
        if self._roi is not None:
            return False  # completed: let the ROI handle its own interaction

        if ev.button() == Qt.RightButton:
            if self._points:
                self._points.pop()
                self._refresh()
                return True
            return False

        if ev.button() != Qt.LeftButton:
            return False

        self._points.append((pos.x(), pos.y()))
        self._refresh()
        return True

    def on_hover(self, pos):
        if self._cursor is None or self._roi is not None:
            return
        if pos is None or not self._points:
            self._cursor.setData([], [])
            return
        x0, y0 = self._points[-1]
        self._cursor.setData([x0, pos.x()], [y0, pos.y()])

    # -- buttons -----------------------------------------------------------

    def complete(self):
        if self._roi is not None:
            return
        if len(self._points) < 3:
            self.window.status("Need at least 3 vertices to complete a polygon.")
            return

        self._roi = pg.PolyLineROI(
            self._points,
            closed=True,
            movable=True,
            pen=pg.mkPen(self.color, width=2),
            handlePen=pg.mkPen("#ffffff", width=1),
        )
        self._roi.setZValue(20)
        self.viewbox.addItem(self._roi)

        self._preview.setData([], [])
        self._cursor.setData([], [])
        self.window.overlay.set_complete_enabled(False)
        self.window.status(
            "Polygon closed. Drag the shape or its handles, then press Apply."
        )

    def apply(self):
        points = self._current_points()
        if len(points) < 3:
            self.window.status("Need at least 3 vertices before applying.")
            return

        selection = rasterize_polygon(points, self.image_shape)
        self.commit(selection)
        self._reset()

    # -- internals ---------------------------------------------------------

    def _current_points(self):
        """Vertices in image coordinates, from the ROI if it exists."""
        if self._roi is None:
            return list(self._points)
        return [
            (p.x(), p.y())
            for _, scene_pt in self._roi.getSceneHandlePositions()
            for p in (self.viewbox.mapSceneToView(scene_pt),)
        ]

    def _reset(self):
        """Clear the shape but stay armed, so regions can be drawn back to back."""
        if self._roi is not None:
            self.viewbox.removeItem(self._roi)
            self._roi = None
        self._points = []
        self._refresh()
        self.window.overlay.set_complete_enabled(True)

    def _refresh(self):
        if self._preview is None:
            return
        if self._points:
            arr = np.asarray(self._points, dtype=float)
            self._preview.setData(arr[:, 0], arr[:, 1])
        else:
            self._preview.setData([], [])
        self._cursor.setData([], [])
