"""The application window."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtGui import QColor, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QShortcut,
    QSlider,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from .help_text import HELP_HTML
from .io_utils import (
    MaskIOError,
    load_h5_image,
    load_mask,
    project_stack,
    save_mask_bmp,
    save_mask_h5,
)
from .mask_model import MaskModel
from .overlay import OverlayButtonBar
from .tools import TOOL_REGISTRY, ThresholdDialog
from .viewbox import MaskViewBox

pg.setConfigOptions(imageAxisOrder="row-major", antialias=False)

DEFAULT_OPACITY = 45
DEFAULT_MASK_COLOR = QColor(255, 40, 40)

SETTINGS_ORG = "12ID"
SETTINGS_APP = "MaskCreator"

_SWITCH_STYLE = """
QPushButton { padding: 7px; border: 1px solid #666; border-radius: 3px; }
QPushButton#addBtn:checked    { background: #2f7d36; color: white; font-weight: bold; }
QPushButton#removeBtn:checked { background: #b06000; color: white; font-weight: bold; }
"""


class MainWindow(QMainWindow):
    def __init__(self, initial_path=None):
        super().__init__()
        self.setWindowTitle("Mask Creator")
        self.resize(1500, 950)

        self.settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.model = MaskModel(self)
        self.model.changed.connect(self._on_mask_changed)

        self._raw = None          # full dataset as loaded (2D or 3D)
        self._image = None        # current 2D working image
        self._dataset_name = ""
        self._mask_color = QColor(DEFAULT_MASK_COLOR)
        self._active_tool = None
        self._tools = {}

        self._build_graph()
        panel = self._build_panel()

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(panel, 0)
        layout.addWidget(self._build_graph_container(), 1)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Load an h5 image to begin.")
        self._build_shortcuts()
        self._restore_settings()
        self._update_mask_lut()
        self._sync_enabled()

        # An explicit command-line path wins over the remembered one, and is
        # the only case that loads automatically -- reopening the app should
        # not spend seconds reading a large stack you may not want.
        if initial_path:
            self.path_edit.setText(str(initial_path))
            self.load_image()

    # ==================================================================
    # Construction
    # ==================================================================

    def _build_graph(self):
        self.graph = pg.GraphicsLayoutWidget()
        self.viewbox = MaskViewBox(lockAspect=True, invertY=True)
        self.plot = self.graph.addPlot(viewBox=self.viewbox)
        self.plot.setLabel("bottom", "column")
        self.plot.setLabel("left", "row")

        self.image_item = pg.ImageItem()
        self.image_item.setZValue(0)
        self.viewbox.addItem(self.image_item)

        self.mask_item = pg.ImageItem()
        self.mask_item.setZValue(10)
        self.mask_item.setOpacity(DEFAULT_OPACITY / 100.0)
        self.viewbox.addItem(self.mask_item)

        # Live outline of a brush stroke before it is committed.  Its colour
        # is set alongside the mask's in _update_mask_lut.
        self.preview_item = pg.ImageItem()
        self.preview_item.setZValue(15)
        self.preview_item.setOpacity(0.55)
        self.viewbox.addItem(self.preview_item)

        self.histogram = pg.HistogramLUTItem(image=self.image_item)
        self.graph.addItem(self.histogram)

        self.overlay = OverlayButtonBar(self.graph)
        self.overlay.applyClicked.connect(lambda: self._tool_call("apply"))
        self.overlay.completeClicked.connect(lambda: self._tool_call("complete"))
        self.overlay.cancelClicked.connect(lambda: self._tool_call("cancel"))

        self._build_context_menu()

    def _build_graph_container(self):
        """The graph plus a legend naming what the overlay colour means."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        legend = QHBoxLayout()
        self.mask_swatch = QLabel()
        self.mask_swatch.setFixedSize(14, 14)
        legend.addWidget(self.mask_swatch)
        legend.addWidget(QLabel("Masked pixels excluded from data reduction"))
        legend.addStretch(1)
        layout.addLayout(legend)
        layout.addWidget(self.graph, 1)
        return container

    def _build_context_menu(self):
        menu = self.viewbox.menu.addMenu("Mask")

        opacity_action = QWidgetAction(menu)
        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(8, 2, 8, 2)
        holder_layout.addWidget(QLabel("Opacity"))
        self.ctx_opacity = QSlider(Qt.Horizontal)
        self.ctx_opacity.setRange(0, 100)
        self.ctx_opacity.setValue(DEFAULT_OPACITY)
        self.ctx_opacity.setMinimumWidth(130)
        holder_layout.addWidget(self.ctx_opacity)
        opacity_action.setDefaultWidget(holder)
        menu.addAction(opacity_action)

        color_action = QAction("Mask colour...", menu)
        color_action.triggered.connect(self._pick_color)
        menu.addAction(color_action)

        self.show_mask_action = QAction("Show mask", menu, checkable=True)
        self.show_mask_action.setChecked(True)
        self.show_mask_action.toggled.connect(self.mask_item.setVisible)
        menu.addAction(self.show_mask_action)

        menu.addSeparator()
        invert = QAction("Invert mask", menu)
        invert.triggered.connect(self.model.invert)
        menu.addAction(invert)
        clear = QAction("Clear mask", menu)
        clear.triggered.connect(self.model.clear)
        menu.addAction(clear)

        menu.addSeparator()
        # Placeholder for the niche tools to be added later.
        more = menu.addMenu("More tools")
        more.setEnabled(False)

    def _build_panel(self):
        panel = QWidget()
        panel.setFixedWidth(345)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_input_group())
        layout.addWidget(self._build_output_group())
        layout.addWidget(self._build_mode_group())
        layout.addWidget(self._build_tools_group())
        layout.addWidget(self._build_settings_group())
        layout.addStretch(1)

        bottom = QHBoxLayout()
        self.stats_label = QLabel("No mask")
        bottom.addWidget(self.stats_label, 1)
        help_btn = QPushButton("Help")
        help_btn.setMaximumWidth(60)
        help_btn.clicked.connect(self.show_help)
        bottom.addWidget(help_btn, 0)
        layout.addLayout(bottom)
        return panel

    def _build_input_group(self):
        box = QGroupBox("Input")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("path to .h5 image")
        self.path_edit.returnPressed.connect(self.load_image)
        browse = QPushButton("Browse...")
        browse.clicked.connect(self.browse_image)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse, 0)
        layout.addLayout(row)

        load = QPushButton("Load Image")
        load.clicked.connect(self.load_image)
        layout.addWidget(load)

        form = QFormLayout()
        self.dataset_edit = QLineEdit()
        self.dataset_edit.setPlaceholderText("auto")
        form.addRow("Dataset:", self.dataset_edit)

        self.display_combo = QComboBox()
        self.display_combo.addItems(["Single frame", "Sum all frames", "Max projection"])
        self.display_combo.currentIndexChanged.connect(self._refresh_working_image)
        self.frame_spin = QSpinBox()
        self.frame_spin.valueChanged.connect(self._refresh_working_image)
        stack_row = QHBoxLayout()
        stack_row.addWidget(self.display_combo, 1)
        stack_row.addWidget(QLabel("Frame:"))
        stack_row.addWidget(self.frame_spin)
        self.stack_row_widget = QWidget()
        self.stack_row_widget.setLayout(stack_row)
        stack_row.setContentsMargins(0, 0, 0, 0)
        self.stack_row_widget.setVisible(False)
        form.addRow("Display:", self.stack_row_widget)
        layout.addLayout(form)

        self.log_check = QCheckBox("Log (log10 of image)")
        # On by default: these detector frames have a median of a few counts
        # against a beam centre in the millions, so the linear view is almost
        # entirely black and the features you mask around are invisible.
        self.log_check.setChecked(True)
        self.log_check.toggled.connect(self._redraw_image)
        layout.addWidget(self.log_check)

        self.info_label = QLabel("No image loaded")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #888;")
        layout.addWidget(self.info_label)
        return box

    def _build_output_group(self):
        box = QGroupBox("Output")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        self.save_h5_btn = QPushButton("Save HDF5...")
        self.save_h5_btn.clicked.connect(self.save_h5)
        self.save_bmp_btn = QPushButton("Save BMP...")
        self.save_bmp_btn.clicked.connect(self.save_bmp)
        row.addWidget(self.save_h5_btn)
        row.addWidget(self.save_bmp_btn)
        layout.addLayout(row)

        self.load_mask_btn = QPushButton("Load Existing Mask...")
        self.load_mask_btn.clicked.connect(self.load_existing_mask)
        layout.addWidget(self.load_mask_btn)
        return box

    def _build_mode_group(self):
        box = QGroupBox("Add or Remove Pixels from Mask")
        layout = QHBoxLayout(box)
        box.setStyleSheet(_SWITCH_STYLE)

        self.add_btn = QPushButton("ADD")
        self.add_btn.setObjectName("addBtn")
        self.add_btn.setCheckable(True)
        self.add_btn.setChecked(True)
        self.remove_btn = QPushButton("REMOVE")
        self.remove_btn.setObjectName("removeBtn")
        self.remove_btn.setCheckable(True)

        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.add_btn)
        group.addButton(self.remove_btn)

        layout.addWidget(self.add_btn)
        layout.addWidget(self.remove_btn)
        return box

    def _build_tools_group(self):
        box = QGroupBox("Tools")
        layout = QVBoxLayout(box)

        grid = QGridLayout()
        self.tool_buttons = {}
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(False)  # handled manually so a click can disarm

        for i, (key, label) in enumerate(
            [("polygon", "Polygon"), ("circle", "Circle"),
             ("rectangle", "Rectangle"), ("brush", "Paintbrush")]
        ):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, k=key: self._on_tool_button(k))
            grid.addWidget(btn, i // 2, i % 2)
            self.tool_buttons[key] = btn
            self.tool_group.addButton(btn)
        layout.addLayout(grid)

        brush_row = QHBoxLayout()
        brush_row.addWidget(QLabel("Brush size"))
        self.brush_slider = QSlider(Qt.Horizontal)
        self.brush_slider.setRange(1, 200)
        self.brush_slider.setValue(24)
        self.brush_spin = QSpinBox()
        self.brush_spin.setRange(1, 200)
        self.brush_spin.setValue(24)
        self.brush_spin.setSuffix(" px")
        self.brush_slider.valueChanged.connect(self.brush_spin.setValue)
        self.brush_spin.valueChanged.connect(self.brush_slider.setValue)
        self.brush_slider.valueChanged.connect(self._on_brush_size)
        brush_row.addWidget(self.brush_slider, 1)
        brush_row.addWidget(self.brush_spin, 0)
        layout.addLayout(brush_row)

        self.threshold_btn = QPushButton("Apply Threshold...")
        self.threshold_btn.clicked.connect(self.apply_threshold)
        layout.addWidget(self.threshold_btn)

        note = QLabel("Further tools will appear here and in the graph's\n"
                      "right-click menu.")
        note.setStyleSheet("color: #777; font-style: italic;")
        layout.addWidget(note)
        return box

    def _build_settings_group(self):
        box = QGroupBox("Settings")
        layout = QVBoxLayout(box)

        row = QHBoxLayout()
        row.addWidget(QLabel("Mask opacity"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(DEFAULT_OPACITY)
        row.addWidget(self.opacity_slider, 1)
        self.color_btn = QPushButton()
        self.color_btn.setFixedWidth(34)
        self.color_btn.clicked.connect(self._pick_color)
        row.addWidget(self.color_btn, 0)
        layout.addLayout(row)

        # Two-way sync between the panel slider and the context-menu slider.
        self.opacity_slider.valueChanged.connect(self._set_opacity)
        self.ctx_opacity.valueChanged.connect(self._set_opacity)

        row2 = QHBoxLayout()
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.clicked.connect(self.model.undo)
        self.redo_btn = QPushButton("Redo")
        self.redo_btn.clicked.connect(self.model.redo)
        clear_btn = QPushButton("Clear Mask")
        clear_btn.clicked.connect(self.model.clear)
        row2.addWidget(self.undo_btn)
        row2.addWidget(self.redo_btn)
        row2.addWidget(clear_btn)
        layout.addLayout(row2)
        return box

    def _build_shortcuts(self):
        QShortcut(QKeySequence.Undo, self, self.model.undo)
        QShortcut(QKeySequence.Redo, self, self.model.redo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.model.redo)
        QShortcut(QKeySequence("Escape"), self, lambda: self.set_active_tool(None))

    # ==================================================================
    # Properties used by the tools
    # ==================================================================

    @property
    def add_mode(self):
        return self.add_btn.isChecked()

    @property
    def brush_size(self):
        return self.brush_slider.value()

    @property
    def mask_color(self):
        """Overlay colour; tools draw their outlines in it so the two match."""
        return self._mask_color

    @property
    def image(self):
        """The raw 2D working image; what the threshold tool reads."""
        return self._image

    def status(self, message):
        self.statusBar().showMessage(message, 8000)

    # ==================================================================
    # Image loading and display
    # ==================================================================

    def browse_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open h5 image", self.path_edit.text() or "",
            "HDF5 files (*.h5 *.hdf5 *.nxs);;All files (*)",
        )
        if path:
            self.path_edit.setText(path)
            self.load_image()

    def load_image(self):
        path = self.path_edit.text().strip().strip('"')
        if not path:
            self.status("Enter or browse for an h5 file first.")
            return
        dataset = self.dataset_edit.text().strip() or None
        try:
            data, name = load_h5_image(path, dataset)
        except (MaskIOError, OSError) as exc:
            QMessageBox.critical(self, "Could not load image", str(exc))
            return

        self.set_active_tool(None)
        self._raw = data
        self._dataset_name = name
        self.dataset_edit.setPlaceholderText(name)

        is_stack = data.ndim == 3
        self.stack_row_widget.setVisible(is_stack)
        if is_stack:
            self.frame_spin.blockSignals(True)
            self.frame_spin.setRange(0, data.shape[0] - 1)
            self.frame_spin.setValue(0)
            self.frame_spin.blockSignals(False)

        self._refresh_working_image(reset_view=True)
        self.status(f"Loaded {Path(path).name} [{name}]")
        # Remember it now rather than only at exit, so an unclean shutdown
        # does not lose it.
        self.settings.setValue("io/last_image_path", path)
        self._sync_enabled()

    def _refresh_working_image(self, *_args, reset_view=False):
        if self._raw is None:
            return
        mode = ("frame", "sum", "max")[self.display_combo.currentIndex()]
        self.frame_spin.setEnabled(mode == "frame")
        self._image = project_stack(self._raw, mode, self.frame_spin.value())

        if self.model.shape != self._image.shape:
            self.model.set_shape(self._image.shape)

        shape_text = " x ".join(str(s) for s in self._raw.shape)
        self.info_label.setText(
            f"{shape_text}  {self._raw.dtype}\n{self._dataset_name}\n"
            f"range {self._image.min():g} to {self._image.max():g}"
        )
        self._redraw_image(reset_view=reset_view)

    def _redraw_image(self, *_args, reset_view=False):
        if self._image is None:
            return
        data = self._image.astype(np.float64, copy=False)

        if self.log_check.isChecked():
            positive = data[data > 0]
            # Clamp rather than producing -inf/NaN, which breaks autolevelling.
            floor = float(positive.min()) if positive.size else 1e-3
            data = np.log10(np.maximum(data, floor))

        self.image_item.setImage(data, autoLevels=False)
        lo, hi = np.percentile(data, [1.0, 99.5])
        if hi <= lo:
            lo, hi = float(data.min()), float(data.max()) or 1.0
        self.histogram.setLevels(lo, hi)
        self.image_item.setLevels((lo, hi))

        if reset_view:
            self.viewbox.autoRange()

    # ==================================================================
    # Mask display
    # ==================================================================

    def _on_mask_changed(self):
        mask = self.model.mask
        if mask.size:
            self.mask_item.setImage(
                mask.astype(np.ubyte), levels=(0, 1), autoLevels=False
            )
        else:
            self.mask_item.clear()
        self.stats_label.setText(
            f"masked: {self.model.n_masked:,} px "
            f"({100 * self.model.fraction_masked:.2f}%)"
        )
        self.undo_btn.setEnabled(self.model.can_undo)
        self.redo_btn.setEnabled(self.model.can_redo)

    def _update_mask_lut(self):
        c = self._mask_color
        lut = np.array(
            [[0, 0, 0, 0], [c.red(), c.green(), c.blue(), 255]], dtype=np.ubyte
        )
        self.mask_item.setLookupTable(lut)
        self.preview_item.setLookupTable(lut)
        self.color_btn.setStyleSheet(f"background-color: {c.name()};")
        self.mask_swatch.setStyleSheet(
            f"background-color: {c.name()}; border: 1px solid #555;"
        )
        # Keep the armed tool's outline in step with the overlay.
        if self._active_tool is not None:
            self._active_tool.update_color()

    def _set_opacity(self, value):
        for slider in (self.opacity_slider, self.ctx_opacity):
            if slider.value() != value:
                slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(False)
        self.mask_item.setOpacity(value / 100.0)

    def _pick_color(self):
        color = QColorDialog.getColor(self._mask_color, self, "Mask overlay colour")
        if color.isValid():
            self._mask_color = color
            self._update_mask_lut()

    def show_stroke_preview(self, selection):
        self.preview_item.setImage(
            selection.astype(np.ubyte), levels=(0, 1), autoLevels=False
        )

    def clear_stroke_preview(self):
        self.preview_item.clear()

    # ==================================================================
    # Tools
    # ==================================================================

    def _on_tool_button(self, key):
        # Clicking the armed tool's own button disarms it.
        self.set_active_tool(None if self._active_tool_key() == key else key)

    def _active_tool_key(self):
        for key, tool in self._tools.items():
            if tool is self._active_tool:
                return key
        return None

    def set_active_tool(self, key):
        if self._active_tool is not None:
            self._active_tool.deactivate()
            self._active_tool = None
        self.viewbox.active_tool = None
        self.overlay.hide()
        for btn in self.tool_buttons.values():
            btn.setChecked(False)

        if key is None:
            return
        if self._image is None:
            self.status("Load an image before using a tool.")
            return

        tool = self._tools.get(key)
        if tool is None:
            tool = self._tools[key] = TOOL_REGISTRY[key](self)

        self._active_tool = tool
        self.viewbox.active_tool = tool
        self.tool_buttons[key].setChecked(True)
        self.overlay.set_complete_enabled(True)
        self.overlay.show_for(tool.title, tool.buttons)
        tool.activate()

    def _tool_call(self, name):
        if self._active_tool is not None:
            getattr(self._active_tool, name)()

    def _on_brush_size(self, _value):
        tool = self._tools.get("brush")
        if tool is not None and tool is self._active_tool:
            tool.update_size()

    def apply_threshold(self):
        if self._image is None:
            self.status("Load an image first.")
            return
        dialog = ThresholdDialog(self._image, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        try:
            selection = dialog.selection()
        except ValueError:
            QMessageBox.warning(self, "Threshold", "Those limits are not numbers.")
            return
        n = self.model.apply(selection, add=self.add_mode)
        verb = "Added" if self.add_mode else "Removed"
        self.status(f"Threshold: {verb.lower()} {n:,} pixels.")

    # ==================================================================
    # Mask I/O
    # ==================================================================

    def load_existing_mask(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load existing mask", "",
            "Mask files (*.h5 *.hdf5 *.bmp *.png *.tif *.tiff);;All files (*)",
        )
        if not path:
            return
        expected = self._image.shape if self._image is not None else None
        try:
            mask = load_mask(path, expected)
        except (MaskIOError, OSError) as exc:
            QMessageBox.critical(self, "Could not load mask", str(exc))
            return

        if self._image is None:
            self.model.set_shape(mask.shape)
        self.model.set_mask(mask)
        self.status(
            f"Loaded mask {Path(path).name}: {int(mask.sum()):,} masked pixels."
        )
        self._sync_enabled()

    def _check_saveable(self):
        if self.model.shape == (0, 0):
            self.status("Nothing to save yet.")
            return False
        return True

    def save_h5(self):
        if not self._check_saveable():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save mask as HDF5", "", "HDF5 files (*.h5 *.hdf5)"
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".h5"
        try:
            save_mask_h5(path, self.model.mask)
        except (MaskIOError, OSError) as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return
        self.status(f"Saved valid_pixel_mask to {Path(path).name}")

    def save_bmp(self):
        if not self._check_saveable():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save mask as BMP", "", "Bitmap files (*.bmp)"
        )
        if not path:
            return
        if not Path(path).suffix:
            path += ".bmp"
        try:
            save_mask_bmp(path, self.model.mask)
        except (MaskIOError, OSError) as exc:
            QMessageBox.critical(self, "Could not save", str(exc))
            return
        self.status(f"Saved 1-bit bitmap to {Path(path).name} (white = valid)")

    # ==================================================================
    # Misc
    # ==================================================================

    # -- persistence -------------------------------------------------------

    def _restore_settings(self):
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

        last = self.settings.value("io/last_image_path", "", type=str)
        if last:
            self.path_edit.setText(last)
            self.statusBar().showMessage(
                f"Last file: {Path(last).name}  --  press Load Image to open it."
            )

    def _save_settings(self):
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("io/last_image_path", self.path_edit.text().strip())

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    # -- misc --------------------------------------------------------------

    def _sync_enabled(self):
        has_mask = self.model.shape != (0, 0)
        for widget in (self.save_h5_btn, self.save_bmp_btn, self.threshold_btn):
            widget.setEnabled(has_mask)
        for btn in self.tool_buttons.values():
            btn.setEnabled(has_mask)
        self._on_mask_changed()

    def show_help(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Mask Creator - Help")
        dialog.resize(640, 700)
        browser = QTextBrowser(dialog)
        browser.setHtml(HELP_HTML)
        browser.setOpenExternalLinks(True)
        layout = QVBoxLayout(dialog)
        layout.addWidget(browser)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignRight)
        dialog.show()
