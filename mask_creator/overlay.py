"""The floating Apply / Complete / Cancel bar drawn over the top-left of the graph."""

from __future__ import annotations

from PyQt5.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

_BAR_STYLE = """
QWidget#overlayBar {
    background-color: rgba(32, 32, 32, 215);
    border: 1px solid rgba(255, 255, 255, 60);
    border-radius: 5px;
}
QLabel#overlayTitle {
    color: #d7d7d7;
    font-weight: bold;
    padding-right: 4px;
}
QPushButton {
    padding: 4px 10px;
    border-radius: 3px;
    border: 1px solid #555;
    background: #3c3c3c;
    color: #eee;
}
QPushButton:hover { background: #4a4a4a; }
QPushButton#applyBtn  { background: #2f6b34; border-color: #3f8a46; }
QPushButton#applyBtn:hover { background: #3c8543; }
QPushButton#cancelBtn { background: #6b2f2f; border-color: #8a3f3f; }
QPushButton#cancelBtn:hover { background: #853c3c; }
"""


class OverlayButtonBar(QWidget):
    """Plain QWidgets floated over the graphics view.

    Real widgets rather than pyqtgraph items: they lay out predictably, take
    focus properly and cannot be panned away with the view.
    """

    applyClicked = pyqtSignal()
    completeClicked = pyqtSignal()
    cancelClicked = pyqtSignal()

    def __init__(self, host):
        super().__init__(host)
        self.setObjectName("overlayBar")
        self.setStyleSheet(_BAR_STYLE)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.title = QLabel("", self)
        self.title.setObjectName("overlayTitle")

        self.apply_btn = QPushButton("Apply", self)
        self.apply_btn.setObjectName("applyBtn")
        self.complete_btn = QPushButton("Complete Polygon", self)
        self.cancel_btn = QPushButton("Cancel", self)
        self.cancel_btn.setObjectName("cancelBtn")

        self.apply_btn.clicked.connect(self.applyClicked)
        self.complete_btn.clicked.connect(self.completeClicked)
        self.cancel_btn.clicked.connect(self.cancelClicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.apply_btn)
        layout.addWidget(self.complete_btn)
        layout.addWidget(self.cancel_btn)

        host.installEventFilter(_Reposition(self, host))
        self.hide()

    def show_for(self, title, buttons):
        """Display the bar with only the named buttons visible."""
        self.title.setText(title)
        self.apply_btn.setVisible("apply" in buttons)
        self.complete_btn.setVisible("complete" in buttons)
        self.cancel_btn.setVisible("cancel" in buttons)
        self.adjustSize()
        self.move(10, 10)
        self.show()
        self.raise_()

    def set_complete_enabled(self, enabled):
        self.complete_btn.setEnabled(enabled)


class _Reposition(QObject):
    """Keeps the bar pinned to the top-left corner when the view resizes."""

    def __init__(self, bar, host):
        super().__init__(bar)
        self._bar = bar
        host.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize and self._bar.isVisible():
            self._bar.move(10, 10)
            self._bar.raise_()
        return False
