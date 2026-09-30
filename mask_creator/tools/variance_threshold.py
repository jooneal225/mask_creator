"""Variance histogram dialog: mask pixels outside a variance range."""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

_HIST_BINS = 1000


class VarianceThresholdDialog(QDialog):
    """Log-log histogram of pixel-wise variance with a draggable in-range region.

    Both axes are log-scaled since variance across a detector can span many
    orders of magnitude. The histogram itself uses log-spaced bins so it
    stays informative across that whole range rather than collapsing
    everything but the first bin or two.

    Pixels whose variance falls *outside* the shaded region -- below the
    lower bar or above the upper bar -- are the ones that get added to the
    mask.
    """

    def __init__(self, variance, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Pixels by Time-Series Variance")
        self.resize(640, 440)
        self._variance = np.asarray(variance, dtype=np.float64)
        self._updating = False

        finite = self._variance[np.isfinite(self._variance)]
        positive = finite[finite > 0]
        if positive.size:
            data_min, data_max = float(positive.min()), float(positive.max())
            if data_min == data_max:
                data_min = data_min / 10
        else:
            data_min, data_max = 1e-12, 1.0

        # One decade below the smallest observed positive variance. log10(0)
        # is undefined, so a lower limit of zero (or the region being dragged
        # all the way to the left) is drawn here instead -- visually "no
        # floor applied", one edge of a log axis can never truly reach it.
        self._log_floor = math.log10(data_min) - 1.0

        edges = np.logspace(
            math.log10(data_min), math.log10(data_max), _HIST_BINS + 1
        )
        y, x = np.histogram(positive, bins=edges)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Pixel variance")
        self.plot_widget.setLabel("left", "Pixel count")
        self.plot_widget.setLogMode(x=True, y=True)
        self.plot_widget.plot(
            x,
            y,
            stepMode=True,
            fillLevel=0,
            brush=(100, 100, 255, 120),
            pen=pg.mkPen((80, 80, 200)),
        )

        if finite.size:
            lo0 = float(np.percentile(finite, 1))
            hi0 = float(np.percentile(finite, 99))
            if lo0 == hi0:
                lo0, hi0 = float(finite.min()), float(finite.max())
        else:
            lo0, hi0 = data_min, data_max
        self._lo, self._hi = lo0, hi0

        self.region = pg.LinearRegionItem(
            values=(self._to_log(lo0), self._to_log(hi0)), movable=True
        )
        self.region.sigRegionChanged.connect(self._on_region_changed)
        self.plot_widget.addItem(self.region)

        self.min_edit = QLineEdit(f"{lo0:g}")
        self.max_edit = QLineEdit(f"{hi0:g}")
        self.min_edit.editingFinished.connect(self._on_edits_changed)
        self.max_edit.editingFinished.connect(self._on_edits_changed)

        self.count_label = QLabel()
        self.count_label.setWordWrap(True)

        form = QFormLayout()
        form.addRow("Lower limit:", self.min_edit)
        form.addRow("Upper limit:", self.max_edit)

        info = QLabel(
            "Drag the two bars on the histogram, or type exact limits. "
            "Pixels with variance <b>outside</b> the shaded region are "
            "added to the mask."
        )
        info.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(self.plot_widget, 1)
        layout.addLayout(form)
        layout.addWidget(self.count_label)
        layout.addWidget(buttons)

        self._update_count()

    # -- log10 <-> linear, for the region only --------------------------
    # The histogram curve is transformed to log space internally by
    # PlotDataItem.setLogMode; LinearRegionItem is not, so its values must
    # be supplied and read back in log10 units to line up with the plot.

    def _to_log(self, value):
        return math.log10(value) if value > 0 else self._log_floor

    # -- results -------------------------------------------------------

    def limits(self):
        return self._lo, self._hi

    def selection(self):
        return (self._variance < self._lo) | (self._variance > self._hi)

    # -- syncing the region and the text fields -------------------------

    def _on_region_changed(self):
        if self._updating:
            return
        self._updating = True
        lo_log, hi_log = self.region.getRegion()
        self._lo, self._hi = 10.0**lo_log, 10.0**hi_log
        self.min_edit.setText(f"{self._lo:g}")
        self.max_edit.setText(f"{self._hi:g}")
        self._updating = False
        self._update_count()

    def _on_edits_changed(self):
        if self._updating:
            return
        try:
            lo = float(self.min_edit.text())
            hi = float(self.max_edit.text())
        except ValueError:
            return
        self._lo, self._hi = lo, hi
        self._updating = True
        self.region.setRegion((self._to_log(lo), self._to_log(hi)))
        self._updating = False
        self._update_count()

    def _update_count(self):
        n = int(self.selection().sum())
        pct = 100.0 * n / self._variance.size if self._variance.size else 0.0
        self.count_label.setText(
            f"Would add <b>{n:,}</b> pixels ({pct:.2f}%) to the mask."
        )
