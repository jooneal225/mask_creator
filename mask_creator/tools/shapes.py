"""Circle and rectangle tools: a draggable, resizable, rotatable ROI."""

from __future__ import annotations

import pyqtgraph as pg

from ..rasterize import rasterize_polygon, roi_polygon
from .base import BaseTool


class _ShapeTool(BaseTool):
    """Shared behaviour; subclasses only choose the ROI class and outline kind."""

    buttons = ("apply", "cancel")
    roi_kind = "rect"
    #: A rotate handle is pointless on a shape with no orientation.
    rotatable = True

    def __init__(self, window):
        super().__init__(window)
        self._roi = None

    def _make_roi(self, pos, size):
        raise NotImplementedError

    def update_color(self):
        if self._roi is not None:
            self._roi.setPen(pg.mkPen(self.color, width=2))

    # -- lifecycle ---------------------------------------------------------

    def activate(self):
        self._spawn()
        self.window.status(
            f"{self.title}: drag to move, use the handles to resize or rotate, "
            "then press Apply."
        )

    def deactivate(self):
        self._remove()

    # -- buttons -----------------------------------------------------------

    def apply(self):
        if self._roi is None:
            return
        points = roi_polygon(self._roi, self.viewbox, self.roi_kind)
        selection = rasterize_polygon(points, self.image_shape)
        self.commit(selection)
        # Leave the ROI in place so the same shape can be stamped repeatedly.

    # -- internals ---------------------------------------------------------

    def _spawn(self):
        """Drop a new ROI in the middle of whatever is currently on screen."""
        (x0, x1), (y0, y1) = self.viewbox.viewRange()
        width = (x1 - x0) * 0.2
        height = (y1 - y0) * 0.2
        size = max(min(width, height), 4.0)
        pos = ((x0 + x1) / 2.0 - size / 2.0, (y0 + y1) / 2.0 - size / 2.0)

        self._roi = self._make_roi(pos, (size, size))
        self._roi.setZValue(20)
        if self.rotatable:
            self._roi.addRotateHandle([1.0, 0.0], [0.5, 0.5])
        self.viewbox.addItem(self._roi)

    def _remove(self):
        if self._roi is not None:
            self.viewbox.removeItem(self._roi)
            self._roi = None


class CircleTool(_ShapeTool):
    title = "Circle"
    roi_kind = "ellipse"
    # CircleROI locks the aspect ratio and exposes a single radius handle, so
    # the shape can only ever be a true circle.  Rotating one is meaningless.
    rotatable = False

    def _make_roi(self, pos, size):
        return pg.CircleROI(
            pos, size, pen=pg.mkPen(self.color, width=2), removable=False
        )


class RectangleTool(_ShapeTool):
    title = "Rectangle"
    roi_kind = "rect"

    def _make_roi(self, pos, size):
        return pg.RectROI(
            pos, size, pen=pg.mkPen(self.color, width=2), removable=False
        )
