"""Turn shapes drawn in image coordinates into boolean pixel selections.

Everything goes through QPainter into an 8-bit QImage with antialiasing off,
so polygons, rotated rectangles, ellipses and brush strokes all share one
well-tested code path and we pick up no extra dependency.

Coordinates are image coordinates: ``x`` is the column axis, ``y`` is the row
axis, and a pixel's centre sits at ``(col + 0.5, row + 0.5)``, which is how
pyqtgraph's ImageItem maps a view position onto the array.
"""

from __future__ import annotations

import numpy as np
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF


def _blank(shape):
    """An 8-bit QImage sized ``(rows, cols)``, zero-filled."""
    height, width = int(shape[0]), int(shape[1])
    image = QImage(width, height, QImage.Format_Grayscale8)
    image.fill(0)
    return image


def _to_bool(image, shape):
    """Read a Format_Grayscale8 QImage back into a bool array.

    Rows in a QImage are padded to a 4-byte boundary, so the buffer has to be
    reshaped using bytesPerLine() and then trimmed to the real width.
    """
    height, width = int(shape[0]), int(shape[1])
    stride = image.bytesPerLine()
    ptr = image.bits()
    ptr.setsize(image.byteCount())
    buf = np.frombuffer(memoryview(ptr), dtype=np.uint8).reshape(height, stride)
    return buf[:, :width] > 0


def _painter(image):
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(255, 255, 255)))
    return painter


def _polygon(points):
    return QPolygonF([QPointF(float(x), float(y)) for x, y in points])


def rasterize_polygon(points, shape):
    """Fill the closed polygon through ``points`` -> bool array of ``shape``."""
    points = list(points)
    if len(points) < 3:
        return np.zeros(shape, dtype=bool)

    image = _blank(shape)
    painter = _painter(image)
    path = QPainterPath()
    path.addPolygon(_polygon(points))
    path.closeSubpath()
    painter.fillPath(path, QBrush(QColor(255, 255, 255)))
    painter.end()
    return _to_bool(image, shape)


def rasterize_stroke(points, width, shape):
    """Stroke a polyline with a round-capped pen ``width`` pixels across.

    Round caps and joins mean a fast drag -- which only delivers a handful of
    mouse events -- still produces a continuous band with no gaps at the
    corners.
    """
    points = list(points)
    if not points:
        return np.zeros(shape, dtype=bool)

    image = _blank(shape)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)
    pen = QPen(QColor(255, 255, 255))
    pen.setWidthF(max(float(width), 1.0))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)

    if len(points) == 1:
        # A single click still has to leave a dot.
        x, y = points[0]
        painter.drawPoint(QPointF(float(x), float(y)))
    else:
        painter.drawPolyline(_polygon(points))
    painter.end()
    return _to_bool(image, shape)


def ellipse_points(center, radii, angle_deg=0.0, n=180):
    """Sample an ellipse outline as a polygon, so it can share the polygon path."""
    cx, cy = center
    rx, ry = radii
    theta = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    x = rx * np.cos(theta)
    y = ry * np.sin(theta)
    if angle_deg:
        a = np.radians(angle_deg)
        x, y = x * np.cos(a) - y * np.sin(a), x * np.sin(a) + y * np.cos(a)
    return np.column_stack([x + cx, y + cy])


def roi_polygon(roi, viewbox, kind, n=180):
    """Outline of a pyqtgraph ROI in image coordinates.

    The outline is built in the ROI's own local frame and mapped out through
    the ROI's transform, so rotation and non-uniform scaling are handled the
    same way for rectangles and ellipses alike.
    """
    width, height = roi.size()
    if kind == "ellipse":
        local = ellipse_points((width / 2.0, height / 2.0),
                               (width / 2.0, height / 2.0), n=n)
    else:
        local = np.array([[0.0, 0.0], [width, 0.0], [width, height], [0.0, height]])

    out = []
    for x, y in local:
        scene_pt = roi.mapToScene(QPointF(float(x), float(y)))
        view_pt = viewbox.mapSceneToView(scene_pt)
        out.append((view_pt.x(), view_pt.y()))
    return out
