"""Mask-editing tools.

``TOOL_REGISTRY`` maps the key used by the left-panel buttons onto the tool
class.  Niche tools added later can either be appended here (to get a button)
or wired straight into the graph context menu in main_window.py.
"""

from .base import BaseTool
from .brush import BrushTool
from .polygon import PolygonTool
from .shapes import CircleTool, RectangleTool
from .threshold import ThresholdDialog

TOOL_REGISTRY = {
    "polygon": PolygonTool,
    "circle": CircleTool,
    "rectangle": RectangleTool,
    "brush": BrushTool,
}

__all__ = [
    "BaseTool",
    "BrushTool",
    "CircleTool",
    "PolygonTool",
    "RectangleTool",
    "ThresholdDialog",
    "TOOL_REGISTRY",
]
