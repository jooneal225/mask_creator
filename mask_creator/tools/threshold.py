"""Threshold dialog: mask every pixel whose raw value falls in a range."""

from __future__ import annotations

import numpy as np
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

DEFAULT_MIN = "-inf"
DEFAULT_MAX = "-0.1"


def parse_limit(text, default):
    """Accept a float, ``inf``/``-inf``/``infinity``, or blank (-> default)."""
    text = text.strip().lower()
    if not text:
        return default
    if text in ("inf", "+inf", "infinity", "+infinity"):
        return np.inf
    if text in ("-inf", "-infinity"):
        return -np.inf
    return float(text)


class ThresholdDialog(QDialog):
    """Asks for min/max and previews how many pixels that would affect.

    The threshold is evaluated against the raw image -- the currently selected
    frame or projection -- not the log-scaled display array, so the defaults
    mean what they say for a detector that writes -1/-2 into module gaps.
    """

    def __init__(self, image, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply Threshold")
        self._image = np.asarray(image)

        self.min_edit = QLineEdit(DEFAULT_MIN)
        self.max_edit = QLineEdit(DEFAULT_MAX)
        self.count_label = QLabel()
        self.count_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Minimum value:", self.min_edit)
        form.addRow("Maximum value:", self.max_edit)

        info = QLabel(
            "Selects pixels of the <b>original</b> image with "
            "min &le; value &le; max.<br>"
            "Blank or <tt>-inf</tt> / <tt>inf</tt> means unbounded."
        )
        info.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(self.count_label)
        layout.addWidget(buttons)

        self.min_edit.textChanged.connect(self._update_count)
        self.max_edit.textChanged.connect(self._update_count)
        self._update_count()

    # -- results -----------------------------------------------------------

    def limits(self):
        return (
            parse_limit(self.min_edit.text(), -np.inf),
            parse_limit(self.max_edit.text(), np.inf),
        )

    def selection(self):
        vmin, vmax = self.limits()
        return (self._image >= vmin) & (self._image <= vmax)

    # -- live preview ------------------------------------------------------

    def _update_count(self):
        try:
            vmin, vmax = self.limits()
        except ValueError:
            self.count_label.setText(
                "<span style='color:#c33'>Not a number.</span>"
            )
            return
        if vmin > vmax:
            self.count_label.setText(
                "<span style='color:#c33'>Minimum is above maximum; "
                "nothing would be selected.</span>"
            )
            return
        n = int(((self._image >= vmin) & (self._image <= vmax)).sum())
        pct = 100.0 * n / self._image.size if self._image.size else 0.0
        self.count_label.setText(f"Selects <b>{n:,}</b> pixels ({pct:.2f}%).")
