"""Common interface for every mask-editing tool.

Adding a niche tool later means subclassing BaseTool, implementing whichever
of the hooks it needs, and registering it in tools/__init__.py -- either as a
button in the left panel or as an entry in the graph context menu.
"""

from __future__ import annotations

from PyQt5.QtCore import QObject


class BaseTool(QObject):
    #: Shown in the overlay bar while the tool is armed.
    title = "Tool"
    #: Any of "apply", "complete", "cancel".
    buttons = ("apply", "cancel")

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    # -- convenience -------------------------------------------------------

    @property
    def viewbox(self):
        return self.window.viewbox

    @property
    def model(self):
        return self.window.model

    @property
    def image_shape(self):
        return self.window.model.shape

    @property
    def color(self):
        """The mask overlay colour, so a tool's outline matches what it paints."""
        return self.window.mask_color

    def commit(self, selection):
        """Push a selection through the Add/Remove switch into the model."""
        n = self.model.apply(selection, add=self.window.add_mode)
        verb = "Added" if self.window.add_mode else "Removed"
        preposition = "to" if self.window.add_mode else "from"
        if n:
            self.window.status(f"{verb} {n:,} pixels {preposition} the mask.")
        else:
            self.window.status("No pixels changed.")
        return n

    # -- lifecycle ---------------------------------------------------------

    def activate(self):
        """Install graphics items and start listening for mouse input."""

    def deactivate(self):
        """Tear everything down; must be safe to call twice."""

    def update_color(self):
        """Re-apply ``self.color`` to any graphics items this tool owns."""

    # -- mouse hooks; return True to consume the event ---------------------

    def on_click(self, ev, pos):
        return False

    def on_drag(self, ev, pos):
        return False

    def on_hover(self, pos):
        """``pos`` is None when the cursor leaves the view."""

    # -- overlay bar hooks -------------------------------------------------

    def apply(self):
        """Apply button pressed."""

    def complete(self):
        """Complete Polygon button pressed."""

    def cancel(self):
        """Cancel button pressed; default is to disarm the tool entirely."""
        self.window.set_active_tool(None)
