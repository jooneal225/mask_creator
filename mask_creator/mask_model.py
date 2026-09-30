"""The mask itself: a boolean array plus undo/redo."""

from __future__ import annotations

from collections import deque

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal

UNDO_DEPTH = 30


class MaskModel(QObject):
    """Single source of truth for the mask.  ``True`` means masked/bad."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mask = np.zeros((0, 0), dtype=bool)
        self._undo = deque(maxlen=UNDO_DEPTH)
        self._redo = deque(maxlen=UNDO_DEPTH)

    # -- state -------------------------------------------------------------

    @property
    def mask(self):
        return self._mask

    @property
    def shape(self):
        return self._mask.shape

    @property
    def n_masked(self):
        return int(self._mask.sum())

    @property
    def fraction_masked(self):
        return float(self._mask.mean()) if self._mask.size else 0.0

    @property
    def can_undo(self):
        return bool(self._undo)

    @property
    def can_redo(self):
        return bool(self._redo)

    # -- editing -----------------------------------------------------------

    def set_shape(self, shape, keep=False):
        """Resize the mask.  Existing content is dropped unless it still fits."""
        shape = tuple(shape)
        if keep and self._mask.shape == shape:
            return
        self._undo.clear()
        self._redo.clear()
        self._mask = np.zeros(shape, dtype=bool)
        self.changed.emit()

    def set_mask(self, mask):
        """Replace the whole mask (used when loading an existing mask file)."""
        mask = np.asarray(mask, dtype=bool)
        self._push_undo()
        self._mask = mask.copy()
        self.changed.emit()

    def apply(self, selection, add=True):
        """Add ``selection`` to the mask, or remove it when ``add`` is False.

        Returns the number of pixels that actually changed, so the caller can
        tell the user when a tool did nothing.
        """
        selection = np.asarray(selection, dtype=bool)
        if selection.shape != self._mask.shape:
            raise ValueError(
                f"Selection shape {selection.shape} != mask shape {self._mask.shape}"
            )
        new = (self._mask | selection) if add else (self._mask & ~selection)
        n_changed = int((new != self._mask).sum())
        if n_changed == 0:
            return 0
        self._push_undo()
        self._mask = new
        self.changed.emit()
        return n_changed

    def clear(self):
        if not self._mask.any():
            return
        self._push_undo()
        self._mask = np.zeros_like(self._mask)
        self.changed.emit()

    def invert(self):
        if self._mask.size == 0:
            return
        self._push_undo()
        self._mask = ~self._mask
        self.changed.emit()

    def flip_vertical(self):
        """Mirror the mask top-to-bottom, e.g. after loading a flipped bitmap."""
        if self._mask.size == 0:
            return
        self._push_undo()
        self._mask = self._mask[::-1].copy()
        self.changed.emit()

    # -- undo / redo -------------------------------------------------------

    def _push_undo(self):
        self._undo.append(self._mask.copy())
        self._redo.clear()

    def undo(self):
        if not self._undo:
            return False
        self._redo.append(self._mask.copy())
        self._mask = self._undo.pop()
        self.changed.emit()
        return True

    def redo(self):
        if not self._redo:
            return False
        self._undo.append(self._mask.copy())
        self._mask = self._redo.pop()
        self.changed.emit()
        return True
