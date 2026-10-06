"""Play-button runner for P11 CGHE analyses.

Edit the settings in this first section, then run this file directly.  The GUI
and CLI import :func:`build_default_settings`, so these are also the shipped
defaults shown outside this runner.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

from cghe_analysis import run_batch
from cghe_types import AnalysisSettings


PROJECT_DIR = Path(__file__).resolve().parents[1]

# --- Inputs and output -----------------------------------------------------
INPUTS = ["01_Resources/Examples/CGHE_Example_01.csv"]  # paths and/or glob patterns
SAVE_RESULTS = True
RESULTS_DIRECTORY = PROJECT_DIR / "02_Results"

# --- Signal import ---------------------------------------------------------
IMPORT_FORMAT = "auto"                 # auto, bruker_csv, new_ms_tab, new_ms_converted_csv, generic
DELIMITER = "auto"                     # auto, ;, \\t, comma, or |
DECIMAL_SYMBOL = "auto"                # auto, . or , (measurement files only)
HEADER_ROWS = -1                        # -1 = auto
TIME_COLUMN = "auto"                   # name, zero-based index, auto, or none
SIGNAL_COLUMN = "auto"                 # name, zero-based index, or auto
SAMPLING_FALLBACK_HZ = 5.0
DETECTOR_DELAY_S = 38.0
BASELINE_MODE = "subtract_minimum"      # subtract_minimum, fixed, selected_range, none
FIXED_BASELINE = 0.0
BASELINE_START_S = 0.0
BASELINE_END_S = 10.0

# --- Signal processing -----------------------------------------------------
SIGNAL_PROCESSING_MODE = "auto"         # auto, tcd, direct
TCD_SMOOTHING_METHOD = "legacy_multistep"  # legacy_multistep or custom
CUSTOM_ROLLING_SPAN_SAMPLES = 21
CUSTOM_ROLLING_PASS_COUNT = 2
CUSTOM_ISOTONIC_DECAY = True
CUSTOM_TAIL_MODEL = "double"            # double, single, none
CUSTOM_TAIL_START_MULTIPLIER = 1.7
STOP_AT_REMAINING_FRACTION = 0.05

# --- Cylinder and mesh -----------------------------------------------------
RADIUS_MM = 4.0
HEIGHT_MM = 3.3
RADIAL_STEP_MM = 4.0 / 39.0
AXIAL_STEP_MM = 0.1
ANGULAR_STEP_DEG = 9.0
TIME_STEP_S = 0.01

# --- Initial concentration -------------------------------------------------
ROOM_TEMPERATURE_DIFFUSIVITY_MM2_S = 8.3e-5
PRECONDITIONING_DURATION_S = 120.0
PRECONDITIONING_ENDPOINT_FILE = None     # .h5 endpoint/result path, or None to calculate

# --- Inverse solver --------------------------------------------------------
SOLVER_MODE = "axisymmetric"            # axisymmetric, full_3d, analytical
INITIAL_DIFFUSIVITY_MM2_S = 8.3e-5
MINIMUM_DIFFUSIVITY_MM2_S = 1.0e-12
MAXIMUM_DIFFUSIVITY_MM2_S = 1.0e-1

# --- Evaluation and saved concentration fields ----------------------------
RELIABLE_UPPER = 0.55
RELIABLE_LOWER = 0.10
EVALUATION_WINDOW_WIDTH = 0.10
MINIMUM_EVALUATION_TIME_S = 20.0
CONCENTRATION_SAVE_MODE = "remaining_percent"  # remaining_percent, seconds, final, none
CONCENTRATION_SAVE_INTERVAL = 5.0


def build_default_settings() -> AnalysisSettings:
    settings = AnalysisSettings()
    imported = settings.import_settings
    imported.format = IMPORT_FORMAT
    imported.delimiter = DELIMITER
    imported.decimal = DECIMAL_SYMBOL
    imported.header_rows = HEADER_ROWS
    imported.time_column = TIME_COLUMN
    imported.signal_column = SIGNAL_COLUMN
    imported.sampling_hz = SAMPLING_FALLBACK_HZ
    imported.detector_delay_s = DETECTOR_DELAY_S
    imported.baseline_mode = BASELINE_MODE
    imported.baseline_value = FIXED_BASELINE
    imported.baseline_start_s = BASELINE_START_S
    imported.baseline_end_s = BASELINE_END_S

    processing = settings.preprocessing
    processing.signal_processing_mode = SIGNAL_PROCESSING_MODE
    processing.tcd_smoothing_method = TCD_SMOOTHING_METHOD
    processing.rolling_span_samples = CUSTOM_ROLLING_SPAN_SAMPLES
    processing.rolling_pass_count = CUSTOM_ROLLING_PASS_COUNT
    processing.isotonic_decay = CUSTOM_ISOTONIC_DECAY
    processing.tail_mode = CUSTOM_TAIL_MODEL
    processing.tail_start_multiplier = CUSTOM_TAIL_START_MULTIPLIER
    processing.stop_fraction = STOP_AT_REMAINING_FRACTION

    settings.geometry.radius_mm = RADIUS_MM
    settings.geometry.height_mm = HEIGHT_MM
    settings.mesh.radial_step_mm = RADIAL_STEP_MM
    settings.mesh.axial_step_mm = AXIAL_STEP_MM
    settings.mesh.angular_step_deg = ANGULAR_STEP_DEG
    settings.mesh.time_step_s = TIME_STEP_S

    settings.initial_state.mode = "endpoint" if PRECONDITIONING_ENDPOINT_FILE else "calculate"
    settings.initial_state.diffusivity_mm2_s = ROOM_TEMPERATURE_DIFFUSIVITY_MM2_S
    settings.initial_state.duration_s = PRECONDITIONING_DURATION_S
    settings.initial_state.endpoint_path = str(PRECONDITIONING_ENDPOINT_FILE or "")

    settings.solver.mode = SOLVER_MODE
    settings.solver.initial_diffusivity_mm2_s = INITIAL_DIFFUSIVITY_MM2_S
    settings.solver.minimum_diffusivity_mm2_s = MINIMUM_DIFFUSIVITY_MM2_S
    settings.solver.maximum_diffusivity_mm2_s = MAXIMUM_DIFFUSIVITY_MM2_S
    settings.evaluation.reliable_upper = RELIABLE_UPPER
    settings.evaluation.reliable_lower = RELIABLE_LOWER
    settings.evaluation.window_width = EVALUATION_WINDOW_WIDTH
    settings.evaluation.minimum_time_s = MINIMUM_EVALUATION_TIME_S
    settings.snapshots.mode = CONCENTRATION_SAVE_MODE
    settings.snapshots.interval = CONCENTRATION_SAVE_INTERVAL
    return settings


def expand_inputs(values=INPUTS) -> list[Path]:
    expanded: list[Path] = []
    missing: list[str] = []
    for value in values:
        raw = Path(value)
        candidate = raw if raw.is_absolute() else PROJECT_DIR / raw
        matches = [Path(item) for item in glob.glob(str(candidate), recursive=True)]
        files = matches if matches else [candidate]
        existing = [path.resolve() for path in files if path.is_file()]
        if not existing:
            missing.append(str(value))
        for path in existing:
            if path not in expanded:
                expanded.append(path)
    if missing:
        raise FileNotFoundError("No input file matched: " + ", ".join(missing))
    if not expanded:
        raise ValueError("INPUTS does not contain any measurement files.")
    return expanded


def run_configured() -> int:
    settings = build_default_settings()
    paths = expand_inputs(INPUTS)
    output_dir = RESULTS_DIRECTORY if SAVE_RESULTS else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
    print("Effective AnalysisSettings:")
    print(json.dumps(settings.to_dict(), indent=2, sort_keys=True))

    last_progress = {"percent": -1, "message": None}

    def progress(fraction, message):
        percent = int(fraction * 100)
        if percent > last_progress["percent"] or message != last_progress["message"]:
            print(f"[{fraction * 100:6.2f}%] {message}", flush=True)
            last_progress.update(percent=percent, message=message)

    results, errors = run_batch(paths, settings, output_dir, progress)
    for result in results:
        processing = result.processing_metadata
        print(
            f"{result.source_name}: processing {processing.get('requested_mode')} -> "
            f"{processing.get('resolved_mode')} ({processing.get('reason')})"
        )
        if result.result_path:
            print(f"Saved: {result.result_path}")
    for path, message in errors:
        print(f"FAILED {path}: {message}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(run_configured())
