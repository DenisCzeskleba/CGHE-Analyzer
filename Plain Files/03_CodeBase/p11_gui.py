"""WeldCraft graphical interface for CGHE Analyzer."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import traceback

import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from PyQt5 import QtCore, QtGui, QtWidgets

from cghe_analysis import add_analytical_comparison, analyze_file, analyze_pasted_table, estimate_result_bytes
from cghe_evaluation import select_window_from_time
from cghe_import import load_measurement, parse_table_text
from cghe_initial_state import load_endpoint, save_endpoint
from cghe_plots import build_all_figures, build_concentration_cutaways, default_concentration_indices
from cghe_preprocess import preprocess_measurement
from cghe_profiles import load_runtime_state, profile_choices, save_runtime_state
from cghe_results import export_concentration_csv, export_concentration_npz, export_csv, load_result, update_result_analysis
from cghe_solver import SimulationCancelled, prepare_initial_endpoint
from cghe_types import AnalysisSettings
from p11_run import build_default_settings
from p11_widgets import (
    CollapsibleSection,
    CompactFormLayout,
    MeasurementTableModel,
    NoWheelComboBox,
    PlainIntegerSpinBox,
    ScientificDoubleSpinBox,
    format_compact_number,
)


PROJECT_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)
REPO_ROOT = PROJECT_DIR.parent
LOCAL_RESOURCES_DIR = PROJECT_DIR / "Resources"
RESOURCES_DIR = LOCAL_RESOURCES_DIR if LOCAL_RESOURCES_DIR.is_dir() else REPO_ROOT / "Resources"
RESULTS_DIR = PROJECT_DIR / "02_Results"
RUNTIME_SETTINGS = PROJECT_DIR / "01_Resources" / "settings" / "settings.json"
if str(RESOURCES_DIR) not in sys.path:
    sys.path.insert(0, str(RESOURCES_DIR))

from Common.launch_ready import StartupReadySignal
from Common.weldcraft_theme import apply_theme, set_name_tag, set_widget_state


APP_NAME = "WeldCraft - CGHE Analyzer"
SETUP_PANEL_MINIMUM_WIDTH = 400
PREVIEW_MAX_PLOT_POINTS = 8_000


class AnalysisWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(float, str)
    completed = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)
    cancelled = QtCore.pyqtSignal()

    def __init__(self, settings, source_path=None, pasted_text=None, parent=None):
        super().__init__(parent)
        self.settings = deepcopy(settings)
        self.source_path = source_path
        self.pasted_text = pasted_text
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def run(self):
        try:
            callback = lambda fraction, message: self.progress.emit(fraction, message)
            cancelled = lambda: self._cancel
            if self.pasted_text is not None:
                result = analyze_pasted_table(
                    self.pasted_text, self.settings, RESULTS_DIR, callback, cancelled
                )
            else:
                result = analyze_file(
                    self.source_path, self.settings, RESULTS_DIR, callback, cancelled
                )
            if self._cancel:
                self.cancelled.emit()
            else:
                self.completed.emit(result)
        except SimulationCancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())


class AnalyticalWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(float, str)
    completed = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)
    cancelled = QtCore.pyqtSignal()

    def __init__(self, result, parent=None):
        super().__init__(parent)
        self.result = result
        self._cancel = False

    def request_cancel(self):
        self._cancel = True

    def run(self):
        try:
            add_analytical_comparison(
                self.result,
                lambda fraction, message: self.progress.emit(fraction, message),
                lambda: self._cancel,
            )
            if self._cancel:
                self.cancelled.emit()
            else:
                update_result_analysis(self.result)
                self.completed.emit(self.result)
        except SimulationCancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())


class PreviewWorker(QtCore.QThread):
    completed = QtCore.pyqtSignal(int, object)
    failed = QtCore.pyqtSignal(int, str)

    def __init__(self, generation, measurement, settings, parent=None):
        super().__init__(parent)
        self.generation = generation
        self.measurement = measurement
        self.settings = deepcopy(settings)

    def run(self):
        try:
            processed = preprocess_measurement(
                self.measurement, self.settings.preprocessing, self.settings.mesh.time_step_s
            )
            self.completed.emit(self.generation, processed)
        except Exception as exc:
            self.failed.emit(self.generation, str(exc))


def _double(value, minimum=0.0, maximum=1e9, decimals=6, step=None):
    return ScientificDoubleSpinBox(value, minimum, maximum, step)


def _integer(value, minimum=0, maximum=1_000_000):
    return PlainIntegerSpinBox(value, minimum, maximum)


def _combo(items):
    widget = NoWheelComboBox()
    for label, value in items:
        widget.addItem(label, value)
    return widget


def _form_layout():
    return CompactFormLayout()


def _preview_plot_data(x_values, y_values, maximum=PREVIEW_MAX_PLOT_POINTS):
    """Return a lightweight display view without altering analysis data."""
    x_values = np.asarray(x_values)
    y_values = np.asarray(y_values)
    count = min(len(x_values), len(y_values))
    if count <= maximum:
        return x_values[:count], y_values[:count]
    indices = np.linspace(0, count - 1, maximum, dtype=int)
    return x_values[indices], y_values[indices]


def _set_combo(widget, value):
    index = widget.findData(value)
    if index >= 0:
        widget.setCurrentIndex(index)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, settings, profiles, gui_state):
        super().__init__()
        self.settings = settings
        self.profiles = profiles
        self.gui_state = gui_state
        self.measurement_preview = None
        self.processed_preview = None
        self.preview_input_dirty = False
        self.preview_generation = 0
        self.preview_workers = set()
        self.pasted_text = None
        self.current_result = None
        self.worker = None
        self.figures = {}
        self.canvases = {}
        self.dragging_boundary = None
        self.band_lines = []
        self._loading = True
        self.default_settings = build_default_settings()
        self.sections = {}
        self.preview_debounce = QtCore.QTimer(self)
        self.preview_debounce.setSingleShot(True)
        self.preview_debounce.setInterval(250)
        self.preview_debounce.timeout.connect(self._refresh_loaded_preview)
        self.input_preview_debounce = QtCore.QTimer(self)
        self.input_preview_debounce.setSingleShot(True)
        self.input_preview_debounce.setInterval(350)
        self.input_preview_debounce.timeout.connect(lambda: self._preview(silent=True))

        self.setWindowTitle(APP_NAME)
        icon = RESOURCES_DIR / "Images" / "WeldCraft.ico"
        self.setWindowIcon(QtGui.QIcon(str(icon)))
        self.resize(1500, 920)
        self._build_ui()
        self._populate_profiles()
        self._write_settings(settings)
        self._restore_gui_state()
        self._connect()
        self._loading = False
        self._update_derived()
        if self._preview_source_available():
            self.preview_input_dirty = True
            self.input_preview_debounce.start()
        self.startup_ready_signal = StartupReadySignal(self)
        self.showMaximized()

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        self.tabs = QtWidgets.QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_setup_tab()
        self._build_results_tab()
        status_row = QtWidgets.QHBoxLayout()
        self.status_label = QtWidgets.QLabel("Ready")
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.progress)
        root.addLayout(status_row)

    def _build_setup_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QHBoxLayout(tab)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.setup_splitter = splitter
        splitter.setChildrenCollapsible(False)
        splitter.setOpaqueResize(True)
        outer.addWidget(splitter)

        left = QtWidgets.QWidget()
        left.setMinimumWidth(SETUP_PANEL_MINIMUM_WIDTH)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(0)
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)

        heading = QtWidgets.QLabel()
        set_name_tag(
            heading,
            QtGui.QPixmap(
                str(RESOURCES_DIR / "Images" / "Name Tags" / "CGHE Analyzer.png")
            ),
            "CGHE Analyzer",
        )
        heading.setMinimumWidth(0)
        layout.addWidget(heading)

        profile_group = CollapsibleSection("Working profiles", False)
        self.sections["profiles"] = profile_group
        profile_layout = QtWidgets.QGridLayout()
        profile_group.setContentLayout(profile_layout)
        self.profile_combo = NoWheelComboBox()
        self.profile_load = QtWidgets.QPushButton("Load")
        self.profile_save = QtWidgets.QPushButton("Save new…")
        self.profile_delete = QtWidgets.QPushButton("Delete")
        self.profile_delete.setProperty("role", "danger")
        self.restore_defaults = QtWidgets.QPushButton("Restore Default")
        for button in (self.profile_load, self.profile_save, self.profile_delete, self.restore_defaults):
            button.setMinimumWidth(0)
            button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        profile_layout.addWidget(self.profile_combo, 0, 0, 1, 2)
        profile_layout.addWidget(self.profile_load, 1, 0)
        profile_layout.addWidget(self.profile_save, 1, 1)
        profile_layout.addWidget(self.profile_delete, 2, 0)
        profile_layout.addWidget(self.restore_defaults, 2, 1)
        layout.addWidget(profile_group)

        source_group = CollapsibleSection("Measurement input", True)
        self.sections["measurement"] = source_group
        source_form = _form_layout()
        source_group.setContentLayout(source_form)
        source_row = QtWidgets.QHBoxLayout()
        self.source_edit = QtWidgets.QLineEdit()
        self.browse_button = QtWidgets.QPushButton("Browse…")
        source_row.addWidget(self.source_edit, 1)
        source_row.addWidget(self.browse_button)
        source_form.addRow("File", source_row)
        buttons = QtWidgets.QHBoxLayout()
        self.paste_button = QtWidgets.QPushButton("Paste Table")
        buttons.addWidget(self.paste_button)
        source_form.addRow(buttons)
        self.format_combo = _combo([
            ("Auto detect", "auto"), ("Bruker CSV", "bruker_csv"),
            ("New MS TAB", "new_ms_tab"), ("Converted new-MS CSV", "new_ms_converted_csv"),
            ("Generic table", "generic"),
        ])
        self.delimiter_combo = _combo([
            ("Auto", "auto"), ("Semicolon", ";"), ("Tab", "\\t"),
            ("Comma", ","), ("Pipe", "|"),
        ])
        self.decimal_combo = _combo([("Auto", "auto"), ("Decimal point", "."), ("Decimal comma", ",")])
        self.header_rows = _integer(-1, -1, 10000)
        self.header_rows.setSpecialValueText("Auto")
        self.time_column = QtWidgets.QLineEdit("auto")
        self.signal_column = QtWidgets.QLineEdit("auto")
        self.sampling_hz = _double(5.0, 1e-6, 1e6, 6)
        self.detector_delay = _double(38.0, 0, 1e6, 3)
        source_form.addRow("Format", self.format_combo)
        source_form.addRow("Delimiter", self.delimiter_combo)
        source_form.addRow("Decimal symbol", self.decimal_combo)
        source_form.addRow("Header rows", self.header_rows)
        source_form.addRow("Time column", self.time_column)
        source_form.addRow("Signal column", self.signal_column)
        source_form.addRow("Sampling fallback [Hz]", self.sampling_hz)
        source_form.addRow("Detector delay [s]", self.detector_delay)
        self.baseline_mode = _combo([
            ("Subtract minimum (legacy)", "subtract_minimum"),
            ("Fixed value", "fixed"), ("Selected time range", "selected_range"), ("None", "none"),
        ])
        self.baseline_value = _double(0.0, -1e12, 1e12, 8)
        self.baseline_start = _double(0.0, 0, 1e9, 3)
        self.baseline_end = _double(10.0, 0, 1e9, 3)
        source_form.addRow("Baseline", self.baseline_mode)
        source_form.addRow("Fixed baseline", self.baseline_value)
        source_form.addRow("Baseline start [s]", self.baseline_start)
        source_form.addRow("Baseline end [s]", self.baseline_end)
        layout.addWidget(source_group)

        preprocess_group = CollapsibleSection("Signal processing", False)
        self.sections["processing"] = preprocess_group
        preprocess_form = _form_layout()
        preprocess_group.setContentLayout(preprocess_form)
        self.processing_mode = _combo([
            ("Auto", "auto"), ("TCD smoothing", "tcd"), ("Direct", "direct"),
        ])
        self.resolved_mode_label = QtWidgets.QLabel("Load a measurement to resolve Auto.")
        self.resolved_mode_label.setWordWrap(True)
        self.tcd_method = _combo([
            ("Legacy multistep (published)", "legacy_multistep"), ("Custom", "custom"),
        ])
        self.rolling_span = _integer(21, 1, 10001)
        self.rolling_pass_count = _integer(2, 0, 20)
        self.isotonic = QtWidgets.QCheckBox("Enforce decreasing post-peak signal")
        self.isotonic.setChecked(True)
        self.isotonic.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.tail_mode = _combo([("Double exponential", "double"), ("Single exponential", "single"), ("Off", "none")])
        self.tail_multiplier = _double(1.7, 1.0, 100.0, 3)
        self.stop_fraction = _double(0.05, 0.001, 0.99, 4)
        preprocess_form.addRow("Processing mode", self.processing_mode)
        preprocess_form.addRow("Resolved", self.resolved_mode_label)
        preprocess_form.addRow("TCD method", self.tcd_method)
        preprocess_form.addRow("Rolling span [samples]", self.rolling_span)
        preprocess_form.addRow("Rolling passes", self.rolling_pass_count)
        preprocess_form.addRow(self.isotonic)
        preprocess_form.addRow("Tail fit", self.tail_mode)
        preprocess_form.addRow("Tail-start peak multiplier", self.tail_multiplier)
        self.stop_fraction.setToolTip(
            "The inverse solver stops below this remaining-hydrogen fraction because the late signal is usually noise-dominated."
        )
        cutoff_explanation = QtWidgets.QLabel(
            "The inverse ends below this remaining-hydrogen fraction, where the late signal is usually noise-dominated."
        )
        cutoff_explanation.setWordWrap(True)
        preprocess_form.addRow("Solver cutoff", self.stop_fraction)
        preprocess_form.addRow(cutoff_explanation)
        self.custom_processing_controls = [
            self.rolling_span, self.rolling_pass_count, self.isotonic, self.tail_mode, self.tail_multiplier,
        ]
        layout.addWidget(preprocess_group)

        geometry_group = CollapsibleSection("Cylinder and numerical mesh", False)
        self.sections["geometry"] = geometry_group
        geometry_form = _form_layout()
        geometry_group.setContentLayout(geometry_form)
        self.radius = _double(4.0, 1e-6, 1e6, 6)
        self.height = _double(3.3, 1e-6, 1e6, 6)
        self.dr = _double(4 / 39, 1e-6, 1e6, 8)
        self.dz = _double(0.1, 1e-6, 1e6, 8)
        self.dtheta = _double(9.0, 0.01, 120.0, 4)
        self.dt = _double(0.01, 1e-8, 1e6, 8)
        self.derived_label = QtWidgets.QLabel()
        self.derived_label.setWordWrap(True)
        self.derived_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        geometry_form.addRow("Radius [mm]", self.radius)
        geometry_form.addRow("Height [mm]", self.height)
        geometry_form.addRow("Requested radial step [mm]", self.dr)
        geometry_form.addRow("Requested axial step [mm]", self.dz)
        geometry_form.addRow("Requested angular step [°]", self.dtheta)
        geometry_form.addRow("Timestep [s]", self.dt)
        geometry_form.addRow("Realized grid", self.derived_label)
        layout.addWidget(geometry_group)

        initial_group = CollapsibleSection("Initial concentration", False)
        self.sections["initial"] = initial_group
        initial_form = _form_layout()
        initial_group.setContentLayout(initial_form)
        self.initial_mode = _combo([
            ("Calculate from D and duration", "calculate"), ("Load endpoint HDF5", "endpoint"),
        ])
        self.pre_duration = _double(120.0, 0, 1e9, 3)
        self.pre_diffusivity = _double(8.3e-5, 0, 1.0, 10)
        self.endpoint_edit = QtWidgets.QLineEdit()
        self.endpoint_edit.setReadOnly(True)
        endpoint_buttons = QtWidgets.QHBoxLayout()
        self.load_endpoint_button = QtWidgets.QPushButton("Load endpoint…")
        self.clear_endpoint_button = QtWidgets.QPushButton("Clear endpoint")
        self.save_endpoint_button = QtWidgets.QPushButton("Build / Save endpoint…")
        for button in (self.load_endpoint_button, self.clear_endpoint_button, self.save_endpoint_button):
            button.setMinimumWidth(0)
            button.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        endpoint_buttons.addWidget(self.load_endpoint_button)
        endpoint_buttons.addWidget(self.clear_endpoint_button)
        initial_form.addRow("Source", self.initial_mode)
        initial_form.addRow("Room-temperature D [mm²/s]", self.pre_diffusivity)
        initial_form.addRow("Duration [s]", self.pre_duration)
        initial_form.addRow("Endpoint file", self.endpoint_edit)
        initial_form.addRow(endpoint_buttons)
        initial_form.addRow(self.save_endpoint_button)
        layout.addWidget(initial_group)

        solver_group = CollapsibleSection("Inverse solver", False)
        self.sections["solver"] = solver_group
        solver_form = _form_layout()
        solver_group.setContentLayout(solver_form)
        solver_row = QtWidgets.QHBoxLayout()
        self.solver_combo = _combo([
            ("Axisymmetric Numerical (Recommended)", "axisymmetric"),
            ("Full 3D Numerical", "full_3d"),
            ("Analytical Inversion (Experimental Beta)", "analytical"),
        ])
        self.beta_help = QtWidgets.QToolButton()
        self.beta_help.setText("?")
        self.beta_help.setToolTip("About the analytical exposure inversion")
        solver_row.addWidget(self.solver_combo, 1)
        solver_row.addWidget(self.beta_help)
        self.initial_d = _double(8.3e-5, 0, 1.0, 10)
        solver_form.addRow("Method", solver_row)
        solver_form.addRow("Initial D [mm²/s]", self.initial_d)
        layout.addWidget(solver_group)

        snapshot_group = CollapsibleSection("Saved concentration fields", False)
        self.sections["snapshots"] = snapshot_group
        snapshot_form = _form_layout()
        snapshot_group.setContentLayout(snapshot_form)
        self.snapshot_mode = _combo([
            ("Save every remaining-H percentage", "remaining_percent"),
            ("Save every N seconds", "seconds"), ("Save initial and final only", "final"),
            ("Do not save extraction fields", "none"),
        ])
        self.snapshot_interval = _double(5.0, 0.001, 1e9, 3)
        self.size_label = QtWidgets.QLabel("Preview source data to estimate the saved file size.")
        self.size_label.setWordWrap(True)
        snapshot_form.addRow("Save policy", self.snapshot_mode)
        snapshot_form.addRow("Interval", self.snapshot_interval)
        snapshot_form.addRow("Estimate", self.size_label)
        layout.addWidget(snapshot_group)

        run_row = QtWidgets.QHBoxLayout()
        self.run_button = QtWidgets.QPushButton("Run Analysis")
        self.run_button.setProperty("role", "primary")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.cancel_button.setProperty("role", "danger")
        self.cancel_button.setEnabled(False)
        run_row.addWidget(self.run_button)
        run_row.addWidget(self.cancel_button)
        layout.addStretch(1)
        scroll.setWidget(panel)
        left_layout.addWidget(scroll, 1)
        left_layout.addLayout(run_row)

        preview_panel = QtWidgets.QWidget()
        preview_layout = QtWidgets.QVBoxLayout(preview_panel)
        title = QtWidgets.QLabel("Measurement and processing preview")
        title.setProperty("role", "sectionTitle")
        preview_layout.addWidget(title)
        self.preview_summary = QtWidgets.QLabel("Choose a file or paste a table.")
        self.preview_summary.setWordWrap(True)
        preview_layout.addWidget(self.preview_summary)
        preview_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.preview_splitter = preview_splitter
        preview_splitter.setChildrenCollapsible(False)
        plot_holder = QtWidgets.QWidget()
        plot_layout = QtWidgets.QVBoxLayout(plot_holder)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_figure = Figure(figsize=(8, 6), constrained_layout=False)
        self.preview_figure.subplots_adjust(left=0.085, right=0.985, top=0.98, bottom=0.08, hspace=0.08)
        self.preview_signal_axis, self.preview_remaining_axis = self.preview_figure.subplots(2, 1, sharex=True)
        self.preview_canvas = FigureCanvas(self.preview_figure)
        self.preview_toolbar = NavigationToolbar(self.preview_canvas, plot_holder)
        plot_layout.addWidget(self.preview_toolbar)
        plot_layout.addWidget(self.preview_canvas, 1)
        table_holder = QtWidgets.QWidget()
        table_layout = QtWidgets.QVBoxLayout(table_holder)
        table_layout.setContentsMargins(0, 0, 0, 0)
        self.data_table_header = QtWidgets.QToolButton()
        self.data_table_header.setText("Data Table")
        self.data_table_header.setCheckable(True)
        self.data_table_header.setChecked(False)
        self.data_table_header.setArrowType(QtCore.Qt.RightArrow)
        self.data_table_header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.data_table_header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.data_table_header.setProperty("role", "sectionHeader")
        table_layout.addWidget(self.data_table_header)
        self.preview_table = QtWidgets.QTableView()
        self.preview_table_model = MeasurementTableModel(self.preview_table)
        self.preview_table.setModel(self.preview_table_model)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        self.preview_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.preview_table.setMinimumHeight(0)
        self.preview_table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Ignored)
        self.preview_table.setVisible(False)
        table_layout.addWidget(self.preview_table, 1)
        table_holder.setMinimumHeight(self.data_table_header.sizeHint().height())
        preview_splitter.addWidget(plot_holder)
        preview_splitter.addWidget(table_holder)
        preview_splitter.setStretchFactor(0, 3)
        preview_splitter.setStretchFactor(1, 1)
        preview_splitter.setSizes([1, 0])
        self.data_table_header.toggled.connect(self._set_data_table_expanded)
        preview_splitter.splitterMoved.connect(self._preview_splitter_moved)
        self._set_data_table_expanded(False)
        preview_layout.addWidget(preview_splitter, 1)
        splitter.addWidget(left)
        splitter.addWidget(preview_panel)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([SETUP_PANEL_MINIMUM_WIDTH, 1000])
        self.tabs.addTab(tab, "Setup")

    def _set_data_table_expanded(self, expanded):
        expanded = bool(expanded)
        self.data_table_header.blockSignals(True)
        self.data_table_header.setChecked(expanded)
        self.data_table_header.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.data_table_header.blockSignals(False)
        self.preview_table.setVisible(expanded)
        self.preview_splitter.handle(1).setEnabled(expanded)

        def resize_panes():
            total = max(1, sum(self.preview_splitter.sizes()))
            header_height = self.data_table_header.sizeHint().height()
            if expanded:
                table_height = max(header_height + 80, total // 4)
            else:
                table_height = header_height
            self.preview_splitter.setSizes([max(1, total - table_height), table_height])

        QtCore.QTimer.singleShot(0, resize_panes)

    def _preview_splitter_moved(self, _position, _index):
        if not self.data_table_header.isChecked():
            return
        table_height = self.preview_splitter.sizes()[1]
        if table_height <= self.data_table_header.sizeHint().height() + 16:
            self.data_table_header.setChecked(False)

    def _build_results_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        actions = QtWidgets.QHBoxLayout()
        self.load_result_button = QtWidgets.QPushButton("Load HDF5…")
        self.beta_button = QtWidgets.QPushButton("Add Analytical Comparison (Beta)")
        self.export_csv_button = QtWidgets.QPushButton("Export CSV…")
        self.export_figure_button = QtWidgets.QPushButton("Export Current Figure…")
        actions.addWidget(self.load_result_button)
        actions.addWidget(self.beta_button)
        actions.addWidget(self.export_csv_button)
        actions.addWidget(self.export_figure_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.metrics_label = QtWidgets.QLabel("No result loaded.")
        self.metrics_label.setWordWrap(True)
        layout.addWidget(self.metrics_label)

        interval_group = QtWidgets.QGroupBox("Accepted CGHE evaluation interval")
        interval_layout = QtWidgets.QHBoxLayout(interval_group)
        self.interval_start = _double(0.0, 0, 1e9, 4)
        self.interval_end = _double(0.0, 0, 1e9, 4)
        self.apply_interval_button = QtWidgets.QPushButton("Apply / Accept")
        interval_layout.addWidget(QtWidgets.QLabel("Start [s]"))
        interval_layout.addWidget(self.interval_start)
        interval_layout.addWidget(QtWidgets.QLabel("End [s]"))
        interval_layout.addWidget(self.interval_end)
        interval_layout.addWidget(self.apply_interval_button)
        interval_layout.addWidget(QtWidgets.QLabel("Tip: drag either green boundary in the Result view."), 1)
        layout.addWidget(interval_group)

        self.result_views = QtWidgets.QTabWidget()
        for key, label in (
            ("main_result", "Result"),
            ("diagnostic_dashboard", "Diagnostics"),
            ("concentration_cutaways", "Concentration fields"),
        ):
            holder = QtWidgets.QWidget()
            holder.setLayout(QtWidgets.QVBoxLayout())
            self.result_views.addTab(holder, label)
            if key == "concentration_cutaways":
                content = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
                selector = QtWidgets.QWidget()
                selector_layout = QtWidgets.QVBoxLayout(selector)
                selector_layout.addWidget(QtWidgets.QLabel("Saved states to display"))
                self.concentration_list = QtWidgets.QListWidget()
                self.concentration_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
                selector_layout.addWidget(self.concentration_list, 1)
                self.update_concentration_button = QtWidgets.QPushButton("Show selected states")
                self.export_concentration_button = QtWidgets.QPushButton("Export selected data…")
                selector_layout.addWidget(self.update_concentration_button)
                selector_layout.addWidget(self.export_concentration_button)
                figure_holder = QtWidgets.QWidget()
                figure_holder.setLayout(QtWidgets.QVBoxLayout())
                content.addWidget(selector)
                content.addWidget(figure_holder)
                content.setSizes([260, 1000])
                holder.layout().addWidget(content)
                self.canvases[key] = (figure_holder, None)
            else:
                self.canvases[key] = (holder, None)
        layout.addWidget(self.result_views, 1)
        self.tabs.addTab(tab, "Results")
        for button in (
            self.beta_button, self.export_csv_button, self.export_figure_button,
            self.apply_interval_button, self.update_concentration_button, self.export_concentration_button,
        ):
            button.setEnabled(False)

    def _connect(self):
        self.browse_button.clicked.connect(self._browse)
        self.paste_button.clicked.connect(self._paste)
        self.run_button.clicked.connect(self._run)
        self.cancel_button.clicked.connect(self._cancel)
        self.beta_help.clicked.connect(self._show_beta_help)
        self.beta_button.clicked.connect(self._add_beta)
        self.load_result_button.clicked.connect(self._load_result)
        self.export_csv_button.clicked.connect(self._export_csv)
        self.export_figure_button.clicked.connect(self._export_figure)
        self.apply_interval_button.clicked.connect(self._apply_interval)
        self.update_concentration_button.clicked.connect(self._refresh_concentration_figure)
        self.export_concentration_button.clicked.connect(self._export_concentration_data)
        self.concentration_list.itemSelectionChanged.connect(self._concentration_selection_changed)
        self.profile_load.clicked.connect(self._load_profile)
        self.profile_save.clicked.connect(self._save_profile)
        self.profile_delete.clicked.connect(self._delete_profile)
        self.restore_defaults.clicked.connect(lambda: self._write_settings(deepcopy(self.default_settings)))
        self.load_endpoint_button.clicked.connect(self._load_endpoint)
        self.clear_endpoint_button.clicked.connect(self._clear_endpoint)
        self.save_endpoint_button.clicked.connect(self._build_save_endpoint)
        for widget in (self.radius, self.height, self.dr, self.dz, self.dtheta, self.dt, self.snapshot_interval, self.snapshot_mode, self.solver_combo):
            signal = widget.currentIndexChanged if isinstance(widget, QtWidgets.QComboBox) else widget.valueChanged
            signal.connect(self._update_derived)
        self.initial_mode.currentIndexChanged.connect(self._update_initial_controls)
        self.processing_mode.currentIndexChanged.connect(self._processing_changed)
        self.tcd_method.currentIndexChanged.connect(self._processing_changed)
        self.rolling_span.valueChanged.connect(self._processing_changed)
        self.rolling_pass_count.valueChanged.connect(self._processing_changed)
        self.isotonic.toggled.connect(self._processing_changed)
        self.tail_mode.currentIndexChanged.connect(self._processing_changed)
        self.tail_multiplier.valueChanged.connect(self._processing_changed)
        self.stop_fraction.valueChanged.connect(self._processing_changed)
        self.dt.valueChanged.connect(self._processing_changed)
        for widget in (
            self.format_combo, self.delimiter_combo, self.decimal_combo, self.baseline_mode,
        ):
            widget.currentIndexChanged.connect(self._mark_input_dirty)
        for widget in (self.header_rows, self.sampling_hz, self.detector_delay, self.baseline_value,
                       self.baseline_start, self.baseline_end):
            widget.valueChanged.connect(self._mark_input_dirty)
        for widget in (self.source_edit, self.time_column, self.signal_column):
            widget.textChanged.connect(self._mark_input_dirty)

    def _settings_from_widgets(self):
        settings = deepcopy(getattr(self, "settings_template", self.default_settings))
        imported = settings.import_settings
        imported.format = self.format_combo.currentData()
        imported.delimiter = self.delimiter_combo.currentData()
        imported.decimal = self.decimal_combo.currentData()
        imported.header_rows = self.header_rows.value()
        imported.time_column = self.time_column.text().strip() or "auto"
        imported.signal_column = self.signal_column.text().strip() or "auto"
        imported.sampling_hz = self.sampling_hz.value()
        imported.detector_delay_s = self.detector_delay.value()
        imported.baseline_mode = self.baseline_mode.currentData()
        imported.baseline_value = self.baseline_value.value()
        imported.baseline_start_s = self.baseline_start.value()
        imported.baseline_end_s = self.baseline_end.value()
        preprocessing = settings.preprocessing
        preprocessing.signal_processing_mode = self.processing_mode.currentData()
        preprocessing.tcd_smoothing_method = self.tcd_method.currentData()
        preprocessing.rolling_span_samples = self.rolling_span.value()
        preprocessing.rolling_pass_count = self.rolling_pass_count.value()
        preprocessing.isotonic_decay = self.isotonic.isChecked()
        preprocessing.tail_mode = self.tail_mode.currentData()
        preprocessing.tail_start_multiplier = self.tail_multiplier.value()
        preprocessing.stop_fraction = self.stop_fraction.value()
        settings.geometry.radius_mm = self.radius.value()
        settings.geometry.height_mm = self.height.value()
        settings.mesh.radial_step_mm = self.dr.value()
        settings.mesh.axial_step_mm = self.dz.value()
        settings.mesh.angular_step_deg = self.dtheta.value()
        settings.mesh.time_step_s = self.dt.value()
        settings.initial_state.mode = self.initial_mode.currentData()
        settings.initial_state.duration_s = self.pre_duration.value()
        settings.initial_state.diffusivity_mm2_s = self.pre_diffusivity.value()
        settings.initial_state.endpoint_path = self.endpoint_edit.text().strip()
        settings.solver.mode = self.solver_combo.currentData()
        settings.solver.initial_diffusivity_mm2_s = self.initial_d.value()
        settings.snapshots.mode = self.snapshot_mode.currentData()
        settings.snapshots.interval = self.snapshot_interval.value()
        return settings

    def _write_settings(self, settings):
        previous_loading = self._loading
        self._loading = True
        self.settings_template = deepcopy(settings)
        imported = settings.import_settings
        _set_combo(self.format_combo, imported.format)
        _set_combo(self.delimiter_combo, imported.delimiter)
        _set_combo(self.decimal_combo, imported.decimal)
        self.header_rows.setValue(imported.header_rows)
        self.time_column.setText(imported.time_column)
        self.signal_column.setText(imported.signal_column)
        self.sampling_hz.setValue(imported.sampling_hz)
        self.detector_delay.setValue(imported.detector_delay_s)
        _set_combo(self.baseline_mode, imported.baseline_mode)
        baseline_value = imported.baseline_value
        if 0.0 < abs(baseline_value) < sys.float_info.min:
            baseline_value = 0.0
        self.baseline_value.setValue(baseline_value)
        self.baseline_start.setValue(imported.baseline_start_s)
        self.baseline_end.setValue(imported.baseline_end_s)
        _set_combo(self.processing_mode, settings.preprocessing.signal_processing_mode)
        _set_combo(self.tcd_method, settings.preprocessing.tcd_smoothing_method)
        self.rolling_span.setValue(settings.preprocessing.rolling_span_samples)
        self.rolling_pass_count.setValue(settings.preprocessing.rolling_pass_count)
        self.isotonic.setChecked(settings.preprocessing.isotonic_decay)
        _set_combo(self.tail_mode, settings.preprocessing.tail_mode)
        self.tail_multiplier.setValue(settings.preprocessing.tail_start_multiplier)
        self.stop_fraction.setValue(settings.preprocessing.stop_fraction)
        self.radius.setValue(settings.geometry.radius_mm)
        self.height.setValue(settings.geometry.height_mm)
        self.dr.setValue(settings.mesh.radial_step_mm)
        self.dz.setValue(settings.mesh.axial_step_mm)
        self.dtheta.setValue(settings.mesh.angular_step_deg)
        self.dt.setValue(settings.mesh.time_step_s)
        _set_combo(self.initial_mode, settings.initial_state.mode)
        self.pre_duration.setValue(settings.initial_state.duration_s)
        self.pre_diffusivity.setValue(settings.initial_state.diffusivity_mm2_s)
        self.endpoint_edit.setText(settings.initial_state.endpoint_path)
        _set_combo(self.solver_combo, settings.solver.mode)
        self.initial_d.setValue(settings.solver.initial_diffusivity_mm2_s)
        _set_combo(self.snapshot_mode, settings.snapshots.mode)
        self.snapshot_interval.setValue(settings.snapshots.interval)
        self._loading = previous_loading
        self._update_initial_controls()
        self._update_processing_controls()
        self._update_derived()
        if not self._loading and self._preview_source_available():
            self.preview_input_dirty = True
            self.preview_generation += 1
            self.preview_summary.setText("Settings loaded; refreshing the preview…")
            self.resolved_mode_label.setText("Refreshing automatically…")
            self.input_preview_debounce.start()

    def _populate_profiles(self, selected="Default"):
        self.profile_combo.clear()
        self.profile_combo.addItems(profile_choices(self.profiles, self.default_settings))
        index = self.profile_combo.findText(selected)
        self.profile_combo.setCurrentIndex(max(index, 0))

    def _load_profile(self):
        name = self.profile_combo.currentText()
        settings = deepcopy(self.default_settings) if name == "Default" else deepcopy(self.profiles[name])
        self._write_settings(settings)
        self._status(f"Loaded profile: {name}", "success")

    def _save_profile(self):
        name, accepted = QtWidgets.QInputDialog.getText(self, "Save profile", "Profile name")
        name = name.strip()
        if not accepted or not name:
            return
        if name == "Default":
            QtWidgets.QMessageBox.warning(self, "Reserved profile", "Default is locked and cannot be overwritten.")
            return
        previous_profiles = deepcopy(self.profiles)
        self.profiles[name] = self._settings_from_widgets()
        try:
            self._persist_runtime_state()
        except Exception as exc:
            self.profiles = previous_profiles
            QtWidgets.QMessageBox.critical(
                self,
                "Could not save profile",
                f"CGHE Analyzer could not write the profile.\n\n{exc}",
            )
            return
        self._populate_profiles(name)
        self._status(f"Saved profile: {name}", "success")

    def _delete_profile(self):
        name = self.profile_combo.currentText()
        if name == "Default":
            QtWidgets.QMessageBox.information(self, "Locked profile", "Default cannot be deleted.")
            return
        if QtWidgets.QMessageBox.question(self, "Delete profile", f"Delete '{name}'?") == QtWidgets.QMessageBox.Yes:
            previous_profiles = deepcopy(self.profiles)
            self.profiles.pop(name, None)
            try:
                self._persist_runtime_state()
            except Exception as exc:
                self.profiles = previous_profiles
                QtWidgets.QMessageBox.critical(
                    self,
                    "Could not delete profile",
                    f"CGHE Analyzer could not write the profile change.\n\n{exc}",
                )
                return
            self._populate_profiles()

    def _browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose CGHE measurement", str(PROJECT_DIR / "01_Resources"),
            "Measurement files (*.csv *.tab *.txt *.tsv);;All files (*)",
        )
        if path:
            self.source_edit.setText(path)
            self.pasted_text = None
            self._status("Input selected; refreshing preview…")
            self._preview(silent=True)

    def _paste(self):
        text = QtWidgets.QApplication.clipboard().text()
        if not text.strip():
            QtWidgets.QMessageBox.warning(self, "Clipboard empty", "Copy a table before using Paste Table.")
            return
        self.pasted_text = text
        self.source_edit.setText("Clipboard Table")
        self._status("Clipboard table captured; refreshing preview…")
        self._preview(silent=True)

    def _preview(self, silent=False):
        self.input_preview_debounce.stop()
        self.preview_generation += 1
        try:
            settings = self._settings_from_widgets()
            if self.pasted_text is not None and self.source_edit.text() == "Clipboard Table":
                measurement = parse_table_text(self.pasted_text, settings.import_settings, "Clipboard_Table")
            else:
                path = Path(self.source_edit.text().strip())
                measurement = load_measurement(path, settings.import_settings)
                self.pasted_text = None
            self.measurement_preview = measurement
            self.processed_preview = None
            self.preview_input_dirty = False
            self.preview_table_model.setMeasurement(measurement)
            mapping = measurement.mapping
            self.preview_input_summary = (
                f"{measurement.source_name} · {len(measurement.raw_time_s)} raw / {len(measurement.time_s)} corrected samples · "
                f"corrected duration {format_compact_number(measurement.time_s[-1])} s · "
                f"format {mapping.get('format', 'unknown')} · "
                f"baseline {format_compact_number(mapping.get('baseline_value_applied', 0))}"
            )
            self.preview_summary.setText(self.preview_input_summary + " · processing…")
            estimate = estimate_result_bytes(settings, len(measurement.raw_time_s), measurement.time_s[-1])
            warning = " — WARNING: exceeds 500 MB" if estimate > 500 * 1024**2 else ""
            self.size_label.setText(
                f"Estimated HDF5 size: {format_compact_number(estimate / 1024**2)} MB{warning}"
            )
            self._start_preview_processing(settings)
        except Exception as exc:
            self.preview_input_dirty = True
            self._status(f"Input error: {exc}", "error")
            if self.measurement_preview is None:
                self.preview_table_model.setMeasurement(None)
            if silent:
                self.preview_summary.setText(f"Could not refresh the preview: {exc}")
                self.resolved_mode_label.setText("Correct the input settings to refresh automatically.")
            else:
                QtWidgets.QMessageBox.warning(self, "Could not parse measurement", str(exc))

    def _start_preview_processing(self, settings=None):
        if self.measurement_preview is None:
            return
        try:
            settings = settings or self._settings_from_widgets()
        except Exception as exc:
            self._status(f"Preview settings error: {exc}", "error")
            return
        self.preview_generation += 1
        generation = self.preview_generation
        self.resolved_mode_label.setText("Resolving and processing…")
        worker = PreviewWorker(generation, self.measurement_preview, settings, self)
        self.preview_workers.add(worker)
        worker.completed.connect(self._preview_completed)
        worker.failed.connect(self._preview_failed)
        worker.finished.connect(lambda worker=worker: self.preview_workers.discard(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _refresh_loaded_preview(self):
        if self.measurement_preview is not None and not self.preview_input_dirty:
            self._start_preview_processing()

    def _preview_completed(self, generation, processed):
        if generation != self.preview_generation:
            return
        self.processed_preview = processed
        resolved = processed.resolved_processing_mode.upper()
        self.resolved_mode_label.setText(f"{resolved}: {processed.processing_reason}")
        self.preview_summary.setText(
            self.preview_input_summary
            + f" · requested {processed.requested_processing_mode}, resolved {processed.resolved_processing_mode}"
        )
        top = self.preview_signal_axis
        bottom = self.preview_remaining_axis
        top.clear()
        bottom.clear()
        measurement = processed.measurement
        full_time = processed.full_time_s if processed.full_time_s is not None else processed.time_s
        full_signal = (
            processed.full_signal_processed
            if processed.full_signal_processed is not None
            else processed.signal_processed
        )
        full_remaining = (
            processed.full_remaining_target
            if processed.full_remaining_target is not None
            else processed.remaining_target
        )
        input_time, input_signal = _preview_plot_data(measurement.time_s, measurement.signal)
        processed_time, processed_signal = _preview_plot_data(full_time, full_signal)
        remaining_time, remaining_values = _preview_plot_data(full_time, full_remaining)
        top.plot(input_time, input_signal, color="#7f8c8d", lw=1.0, label="Corrected input")
        top.plot(processed_time, processed_signal, color="#1565c0", lw=1.4, label="Final processed")
        top.set_ylabel("Signal [a.u.]")
        top.grid(True, alpha=0.25)
        bottom.plot(
            remaining_time,
            remaining_values,
            color="#b23a48",
            lw=1.4,
            label=r"Measured Remaining Hydrogen $R_H$",
        )
        cutoff_time = float(processed.time_s[-1])
        if cutoff_time < float(full_time[-1]):
            self.preview_summary.setText(
                self.preview_summary.text()
                + f" · inverse solver uses data through {format_compact_number(cutoff_time)} s "
                + f"(remaining hydrogen {format_compact_number(processed.remaining_target[-1])})"
            )
            for axis in (top, bottom):
                axis.axvline(
                    cutoff_time,
                    color="#6f7479",
                    lw=1.2,
                    ls="--",
                    label="Inverse-solver cutoff" if axis is top else None,
                )
                axis.axvspan(cutoff_time, full_time[-1], color="#7f8c8d", alpha=0.08)
        bottom.set_xlabel("Time [s]")
        bottom.set_ylabel("Remaining Hydrogen Fraction")
        bottom.set_ylim(-0.02, 1.02)
        bottom.grid(True, alpha=0.25)
        top.legend(loc="best")
        bottom.legend(loc="best")
        self.preview_canvas.draw_idle()
        self._status("Measurement parsed and processed successfully", "success")

    def _preview_failed(self, generation, message):
        if generation != self.preview_generation:
            return
        self.processed_preview = None
        self.resolved_mode_label.setText(f"Processing error: {message}")
        self._status(f"Processing error: {message}", "error")

    def _run(self):
        if self.worker is not None:
            return
        try:
            settings = self._settings_from_widgets()
            if self.pasted_text is not None and self.source_edit.text() == "Clipboard Table":
                source_path = None
                pasted = self.pasted_text
            else:
                source_path = str(Path(self.source_edit.text().strip()).resolve())
                if not Path(source_path).is_file():
                    raise FileNotFoundError(source_path)
                pasted = None
            RESULTS_DIR.mkdir(parents=True, exist_ok=True)
            self.worker = AnalysisWorker(settings, source_path, pasted, self)
            self.worker.progress.connect(self._worker_progress)
            self.worker.completed.connect(self._worker_completed)
            self.worker.failed.connect(self._worker_failed)
            self.worker.cancelled.connect(self._worker_cancelled)
            self._set_running(True)
            self.worker.start()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Cannot start analysis", str(exc))

    def _add_beta(self):
        if self.worker is not None or self.current_result is None:
            return
        self.worker = AnalyticalWorker(self.current_result, self)
        self.worker.progress.connect(self._worker_progress)
        self.worker.completed.connect(self._worker_completed)
        self.worker.failed.connect(self._worker_failed)
        self.worker.cancelled.connect(self._worker_cancelled)
        self._set_running(True)
        self.worker.start()

    def _cancel(self):
        if self.worker is not None:
            self.worker.request_cancel()
            self._status("Cancellation requested…", "warning")

    def _worker_progress(self, fraction, message):
        self.progress.setValue(int(fraction * 1000))
        self._status(message)

    def _worker_completed(self, result):
        self.worker = None
        self._set_running(False)
        self.progress.setValue(1000)
        self._show_result(result)
        self.tabs.setCurrentIndex(1)
        self._status(f"Complete: {result.result_path or result.source_name}", "success")

    def _worker_failed(self, details):
        self.worker = None
        self._set_running(False)
        self._status("Analysis failed", "error")
        QtWidgets.QMessageBox.critical(self, "Analysis failed", details)

    def _worker_cancelled(self):
        self.worker = None
        self._set_running(False)
        self.progress.setValue(0)
        self._status("Analysis cancelled", "warning")

    def _set_running(self, running):
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.beta_button.setEnabled(not running and self.current_result is not None and self.current_result.solver_mode != "analytical")

    def _load_result(self):
        existing_results = list(RESULTS_DIR.glob("*.h5")) + list(RESULTS_DIR.glob("*.hdf5"))
        start_directory = RESULTS_DIR if existing_results else PROJECT_DIR / "01_Resources" / "Examples"
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load CGHE result", str(start_directory), "HDF5 (*.h5 *.hdf5)"
        )
        if not path:
            return
        try:
            self._show_result(load_result(path))
            note = " (legacy read-only)" if self.current_result.legacy_read_only else ""
            self._status(f"Loaded {Path(path).name}{note}", "success")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Could not load result", str(exc))

    def _show_result(self, result):
        self.current_result = result
        evaluation = result.evaluation or {}
        self.interval_start.setMaximum(float(result.time_s[-1]))
        self.interval_end.setMaximum(float(result.time_s[-1]))
        self.interval_start.setValue(float(evaluation.get("selection_time_start_s", 0.0)))
        self.interval_end.setValue(float(evaluation.get("selection_time_end_s", result.time_s[-1])))
        selected = evaluation.get("D_CGHE_mm2_s")
        selected_text = "unavailable" if selected is None else f"{format_compact_number(selected)} mm²/s"
        quality = evaluation.get("selection_quality", "unavailable")
        clipping = result.diagnostics.get("clipped_minimum_steps", 0) + result.diagnostics.get("clipped_maximum_steps", 0)
        processing = result.processing_metadata or {}
        processing_text = processing.get("resolved_mode", "unknown")
        self.metrics_label.setText(
            f"Source: {result.source_name} · Solver: {result.solver_mode} · Processing: {processing_text} · "
            f"D_CGHE: {selected_text} · "
            f"Quality: {quality} · MAE: {format_compact_number(result.mae)} · "
            f"Max residual: {format_compact_number(result.maximum_residual)} · "
            f"Clipped steps: {clipping}" + (" · Legacy result (read-only)" if result.legacy_read_only else "")
        )
        for figure in self.figures.values():
            figure.clear()
        self.concentration_list.blockSignals(True)
        self.concentration_list.clear()
        has_concentrations = result.snapshot_fields is not None and len(result.snapshot_fields) > 0
        default_indices = set(default_concentration_indices(result).tolist())
        if has_concentrations:
            for index in range(len(result.snapshot_fields)):
                time_s = result.snapshot_time_s[index]
                remaining = result.snapshot_remaining[index]
                diffusivity = result.snapshot_diffusivity[index]
                item = QtWidgets.QListWidgetItem(
                    f"{index + 1}: t={format_compact_number(time_s)} s · "
                    f"Remaining hydrogen={format_compact_number(remaining)} · "
                    f"D={format_compact_number(diffusivity)}"
                )
                item.setData(QtCore.Qt.UserRole, index)
                self.concentration_list.addItem(item)
                item.setSelected(index in default_indices)
        self.concentration_list.blockSignals(False)
        selected_indices = self._selected_concentration_indices()
        self.figures = build_all_figures(result, selected_indices)
        for key, figure in self.figures.items():
            self._install_figure(key, figure)
        self._install_band_dragging()
        self.result_views.setCurrentIndex(0)
        self.beta_button.setEnabled(result.solver_mode != "analytical" and result.processed is not None)
        self.export_csv_button.setEnabled(True)
        self.export_figure_button.setEnabled(True)
        self.apply_interval_button.setEnabled(bool(result.evaluation))
        self.update_concentration_button.setEnabled(has_concentrations)
        self.export_concentration_button.setEnabled(bool(selected_indices))

    def _install_figure(self, key, figure):
        holder, old_canvas = self.canvases[key]
        layout = holder.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        canvas = FigureCanvas(figure)
        toolbar = NavigationToolbar(canvas, holder)
        layout.addWidget(toolbar)
        layout.addWidget(canvas, 1)
        canvas.draw()
        self.canvases[key] = (holder, canvas)

    def _install_band_dragging(self):
        if not self.current_result or not self.current_result.evaluation:
            return
        canvas = self.canvases["main_result"][1]
        axis = self.figures["main_result"].axes[0]
        start = self.current_result.evaluation["selection_time_start_s"]
        end = self.current_result.evaluation["selection_time_end_s"]
        self.band_lines = [axis.axvline(start, color="#2e7d32", lw=2.0, picker=7), axis.axvline(end, color="#2e7d32", lw=2.0, picker=7)]
        canvas.mpl_connect("button_press_event", self._band_press)
        canvas.mpl_connect("motion_notify_event", self._band_motion)
        canvas.mpl_connect("button_release_event", self._band_release)
        canvas.draw_idle()

    def _band_press(self, event):
        if event.inaxes is None or event.xdata is None or len(self.band_lines) != 2:
            return
        positions = [float(line.get_xdata()[0]) for line in self.band_lines]
        tolerance = max(self.current_result.time_s[-1] * 0.025, 0.1)
        nearest = int(abs(event.xdata - positions[1]) < abs(event.xdata - positions[0]))
        if abs(event.xdata - positions[nearest]) <= tolerance:
            self.dragging_boundary = nearest

    def _band_motion(self, event):
        if self.dragging_boundary is None or event.xdata is None:
            return
        value = float(min(max(event.xdata, 0.0), self.current_result.time_s[-1]))
        self.band_lines[self.dragging_boundary].set_xdata([value, value])
        self.canvases["main_result"][1].draw_idle()

    def _band_release(self, event):
        if self.dragging_boundary is None:
            return
        values = sorted(float(line.get_xdata()[0]) for line in self.band_lines)
        self.dragging_boundary = None
        self.interval_start.setValue(values[0])
        self.interval_end.setValue(values[1])
        self._apply_interval()

    def _apply_interval(self):
        if self.current_result is None:
            return
        try:
            self.current_result.evaluation = select_window_from_time(
                self.current_result.time_s,
                self.current_result.diffusivity_mm2_s,
                self.current_result.remaining_target,
                self.current_result.settings.evaluation,
                self.interval_start.value(), self.interval_end.value(),
            )
            update_result_analysis(self.current_result)
            self._show_result(self.current_result)
            note = " (not written: legacy result)" if self.current_result.legacy_read_only else ""
            self._status("Evaluation interval accepted" + note, "success")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Invalid interval", str(exc))

    def _export_csv(self):
        if self.current_result is None:
            return
        default = RESULTS_DIR / f"{Path(self.current_result.result_path or self.current_result.source_name).stem}_history.csv"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export result history", str(default), "CSV (*.csv)")
        if path:
            try:
                export_csv(self.current_result, path)
                self._status(f"Exported {path}", "success")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))

    def _export_figure(self):
        if self.current_result is None:
            return
        key = ("main_result", "diagnostic_dashboard", "concentration_cutaways")[self.result_views.currentIndex()]
        default = RESULTS_DIR / f"{Path(self.current_result.result_path or self.current_result.source_name).stem}_{key}.png"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export current figure", str(default), "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)"
        )
        if path:
            try:
                self.figures[key].savefig(path, dpi=220, bbox_inches="tight")
                self._status(f"Exported {path}", "success")
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))

    def _selected_concentration_indices(self):
        return sorted(
            int(item.data(QtCore.Qt.UserRole)) for item in self.concentration_list.selectedItems()
        )

    def _concentration_selection_changed(self):
        selected = self._selected_concentration_indices()
        self.export_concentration_button.setEnabled(bool(selected))
        if self.current_result is not None:
            self._refresh_concentration_figure()

    def _refresh_concentration_figure(self):
        if self.current_result is None:
            return
        selected = self._selected_concentration_indices()
        figure = build_concentration_cutaways(self.current_result, selected)
        old_figure = self.figures.get("concentration_cutaways")
        if old_figure is not None:
            old_figure.clear()
        self.figures["concentration_cutaways"] = figure
        self._install_figure("concentration_cutaways", figure)

    def _export_concentration_data(self):
        if self.current_result is None:
            return
        selected = self._selected_concentration_indices()
        if not selected:
            QtWidgets.QMessageBox.information(
                self, "No concentration states selected", "Select at least one saved state to export."
            )
            return
        stem = Path(self.current_result.result_path or self.current_result.source_name).stem
        default = RESULTS_DIR / f"{stem}_concentration_fields.csv"
        path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export selected concentration data",
            str(default),
            "CSV table (*.csv);;Compressed NumPy data (*.npz)",
        )
        if not path:
            return
        try:
            output = Path(path)
            use_npz = output.suffix.lower() == ".npz" or selected_filter.startswith("Compressed")
            if use_npz:
                if output.suffix.lower() != ".npz":
                    output = output.with_suffix(".npz")
                export_concentration_npz(self.current_result, output, selected)
            else:
                if output.suffix.lower() != ".csv":
                    output = output.with_suffix(".csv")
                export_concentration_csv(self.current_result, output, selected)
            self._status(f"Exported {output}", "success")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Export failed", str(exc))

    def _show_beta_help(self):
        QtWidgets.QMessageBox.information(
            self,
            "Analytical Inversion (Experimental Beta)",
            "This method treats spatially uniform, time-dependent diffusivity through cumulative diffusion "
            "exposure Θ(t)=∫D(t)dt. The finite-cylinder remaining-hydrogen solution is inverted to obtain Θ, "
            "then differentiated to obtain the local D(t). A preconditioned state is represented by the prior "
            "exposure D_pre·t_pre.\n\nThis analytical route is under active development and has not been validated "
            "to the same level as the recommended numerical inverse. It is not the classical half-time method.",
        )

    def _processing_changed(self, *args):
        self._update_processing_controls()
        if self._loading:
            return
        self.preview_generation += 1
        self.resolved_mode_label.setText("Refreshing automatically…")
        if self.preview_input_dirty or self.measurement_preview is None:
            if self._preview_source_available():
                self.input_preview_debounce.start()
        else:
            self.preview_debounce.start()

    def _mark_input_dirty(self, *args):
        if self._loading:
            return
        self.preview_input_dirty = True
        self.preview_debounce.stop()
        self.preview_generation += 1
        if self._preview_source_available():
            self.preview_summary.setText("Input settings changed; refreshing the preview…")
            self.resolved_mode_label.setText("Refreshing automatically…")
            self.input_preview_debounce.start()

    def _preview_source_available(self):
        source = self.source_edit.text().strip()
        if self.pasted_text is not None and source == "Clipboard Table":
            return True
        return bool(source) and Path(source).is_file()

    def _update_processing_controls(self):
        direct = self.processing_mode.currentData() == "direct"
        custom = self.tcd_method.currentData() == "custom" and not direct
        self.tcd_method.setEnabled(not direct)
        for widget in self.custom_processing_controls:
            widget.setEnabled(custom)

    def _load_endpoint(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load preconditioning endpoint", str(RESULTS_DIR), "HDF5 (*.h5 *.hdf5)"
        )
        if not path:
            return
        try:
            settings = self._settings_from_widgets()
            load_endpoint(path, settings)
            self.endpoint_edit.setText(path)
            _set_combo(self.initial_mode, "endpoint")
            self._update_initial_controls()
            self._status(f"Loaded compatible endpoint: {Path(path).name}", "success")
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Endpoint mismatch", str(exc))

    def _clear_endpoint(self):
        self.endpoint_edit.clear()
        _set_combo(self.initial_mode, "calculate")
        self._update_initial_controls()
        self._status("Endpoint cleared; the initial state will be calculated.")

    def _build_save_endpoint(self):
        default = RESULTS_DIR / "preconditioning_endpoint.h5"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Build and save preconditioning endpoint", str(default), "HDF5 (*.h5 *.hdf5)"
        )
        if not path:
            return
        try:
            settings = self._settings_from_widgets()
            settings.initial_state.mode = "calculate"
            settings.initial_state.endpoint_path = ""
            endpoint = prepare_initial_endpoint(settings)
            saved = save_endpoint(endpoint, path)
            self.endpoint_edit.setText(str(saved))
            _set_combo(self.initial_mode, "endpoint")
            self._update_initial_controls()
            self._status(f"Saved endpoint: {saved}", "success")
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Could not save endpoint", str(exc))

    def _update_initial_controls(self):
        mode = self.initial_mode.currentData()
        calculate = mode == "calculate"
        self.pre_duration.setEnabled(calculate)
        self.pre_diffusivity.setEnabled(calculate)
        self.load_endpoint_button.setEnabled(True)
        self.clear_endpoint_button.setEnabled(bool(self.endpoint_edit.text()))

    def _update_derived(self, *args):
        if self._loading:
            return
        try:
            settings = self._settings_from_widgets()
            grid = settings.mesh.derived(settings.geometry)
            self.derived_label.setText(
                f"{grid['num_r']} × {grid['num_theta']} × {grid['num_z']} nodes · "
                f"dr={format_compact_number(grid['dr_mm'])} mm · "
                f"dθ={format_compact_number(grid['dtheta_deg'])}° · "
                f"dz={format_compact_number(grid['dz_mm'])} mm"
            )
            if self.measurement_preview is not None:
                estimate = estimate_result_bytes(
                    settings, len(self.measurement_preview.raw_time_s), self.measurement_preview.time_s[-1]
                )
                warning = " — WARNING: exceeds 500 MB" if estimate > 500 * 1024**2 else ""
                self.size_label.setText(
                    f"Estimated HDF5 size: {format_compact_number(estimate / 1024**2)} MB{warning}"
                )
        except Exception as exc:
            self.derived_label.setText(str(exc))

    def _status(self, text, state=None):
        self.status_label.setText(text)
        if state:
            set_widget_state(self.status_label, "state", state)

    def _restore_gui_state(self):
        geometry = self.gui_state.get("window_geometry")
        if geometry:
            self.restoreGeometry(QtCore.QByteArray.fromBase64(geometry.encode("ascii")))
        splitter_sizes = self.gui_state.get("setup_splitter_sizes")
        if (
            self.gui_state.get("setup_layout_version") == 2
            and isinstance(splitter_sizes, list)
            and len(splitter_sizes) == 2
        ):
            left_width = max(SETUP_PANEL_MINIMUM_WIDTH, int(splitter_sizes[0]))
            self.setup_splitter.setSizes([left_width, max(1, int(splitter_sizes[1]))])
        else:
            self.setup_splitter.setSizes([SETUP_PANEL_MINIMUM_WIDTH, 1000])

    def _save_gui_state(self):
        return {
            "window_geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            "setup_layout_version": 2,
            "setup_splitter_sizes": self.setup_splitter.sizes(),
        }

    def _persist_runtime_state(self):
        save_runtime_state(
            RUNTIME_SETTINGS,
            self._settings_from_widgets(),
            self.profiles,
            self._save_gui_state(),
        )

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            if QtWidgets.QMessageBox.question(self, "Analysis running", "Cancel the analysis and close?") != QtWidgets.QMessageBox.Yes:
                event.ignore()
                return
            self.worker.request_cancel()
            if not self.worker.wait(10_000):
                QtWidgets.QMessageBox.information(self, "Still cancelling", "The solver is still leaving its numerical loop safely.")
                event.ignore()
                return
        self.preview_debounce.stop()
        self.input_preview_debounce.stop()
        self.preview_generation += 1
        for preview_worker in tuple(self.preview_workers):
            preview_worker.wait(2_000)
        try:
            self._persist_runtime_state()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(
                self,
                "Could not save before closing",
                "CGHE Analyzer could not save its current settings and will remain open.\n\n"
                f"{exc}",
            )
            event.ignore()
            return
        event.accept()


def launch_gui():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("WeldCraft")
    apply_theme(app)
    icon = RESOURCES_DIR / "Images" / "WeldCraft.ico"
    app.setWindowIcon(QtGui.QIcon(str(icon)))
    try:
        defaults = build_default_settings()
        settings, profiles, gui_state = load_runtime_state(RUNTIME_SETTINGS, defaults)
    except Exception as exc:
        QtWidgets.QMessageBox.warning(None, "CGHE settings recovery", f"{exc}\n\nShipped defaults will be used.")
        settings, profiles, gui_state = build_default_settings(), {}, {}
    window = MainWindow(settings, profiles, gui_state)
    window.show()
    if "--smoke-test" in sys.argv[1:]:
        QtCore.QTimer.singleShot(100, window.close)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(launch_gui())
