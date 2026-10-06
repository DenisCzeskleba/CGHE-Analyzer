"""High-level CGHE analysis workflow used by the GUI and CLI."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from cghe_evaluation import select_evaluation_window
from cghe_import import load_measurement, parse_table_text
from cghe_preprocess import preprocess_measurement
from cghe_results import automatic_result_path, save_result
from cghe_solver import prepare_initial_endpoint, run_analytical, run_solver
from cghe_types import AnalysisResult, AnalysisSettings, InitialEndpoint


def estimate_result_bytes(settings: AnalysisSettings, sample_count: int, duration_s: float) -> int:
    steps = max(2, int(duration_s / settings.mesh.time_step_s) + 1)
    scalar_bytes = steps * 8 * 12
    grid = settings.mesh.derived(settings.geometry)
    initial_endpoint_bytes = int(grid["num_r"]) * int(grid["num_z"]) * 8
    if settings.snapshots.mode == "none":
        snapshots = 0
    elif settings.snapshots.mode == "final":
        snapshots = 2
    elif settings.snapshots.mode == "seconds":
        snapshots = max(2, int(duration_s / max(settings.snapshots.interval, 1e-9)) + 2)
    else:
        snapshots = max(2, int(100.0 / max(settings.snapshots.interval, 1e-9)))
    cells = int(grid["num_r"]) * int(grid["num_z"])
    if settings.solver.mode == "full_3d":
        cells *= int(grid["num_theta"])
    if settings.solver.mode == "analytical":
        cells = snapshots = 0
    input_bytes = max(sample_count, 1) * 8 * 12
    return int((scalar_bytes + snapshots * cells * 8 + input_bytes + initial_endpoint_bytes) * 0.75)


def _build_result(processed, settings, output):
    residual = output.remaining - processed.remaining_target
    result = AnalysisResult(
        settings=deepcopy(settings),
        source_name=processed.measurement.source_name,
        solver_mode=settings.solver.mode,
        time_s=processed.time_s,
        diffusivity_mm2_s=output.diffusivity,
        remaining_target=processed.remaining_target,
        remaining_simulated=output.remaining,
        residual=residual,
        measurement=processed.measurement,
        processed=processed,
        snapshot_fields=output.snapshot_fields,
        snapshot_time_s=output.snapshot_times,
        snapshot_remaining=output.snapshot_remaining,
        snapshot_diffusivity=output.snapshot_diffusivity,
        snapshot_requested=output.snapshot_requested,
        analytical_exposure_mm2=output.exposure if settings.solver.mode == "analytical" else None,
        diagnostics=output.diagnostics,
        processing_metadata={
            "requested_mode": processed.requested_processing_mode,
            "resolved_mode": processed.resolved_processing_mode,
            "reason": processed.processing_reason,
            "tcd_smoothing_method": settings.preprocessing.tcd_smoothing_method,
        },
        initial_state_field_rz=(output.initial_endpoint.field_rz if output.initial_endpoint is not None else None),
        initial_state_metadata=(dict(output.initial_endpoint.metadata) if output.initial_endpoint is not None else {}),
    )
    result.evaluation = select_evaluation_window(
        result.time_s, result.diffusivity_mm2_s, result.remaining_target, settings.evaluation
    )
    return result


def analyze_measurement(measurement, settings, progress=None, cancel=None, initial_endpoint=None):
    endpoint = initial_endpoint or prepare_initial_endpoint(settings, progress, cancel)
    if progress:
        progress(0.15, "Preprocessing measurement")
    processed = preprocess_measurement(measurement, settings.preprocessing, settings.mesh.time_step_s)
    output = run_solver(processed, settings, progress, cancel, endpoint)
    result = _build_result(processed, settings, output)
    if progress:
        progress(1.0, "Analysis complete")
    return result


def analyze_file(path, settings, results_dir=None, progress=None, cancel=None, initial_endpoint=None):
    measurement = load_measurement(path, settings.import_settings)
    result = analyze_measurement(measurement, settings, progress, cancel, initial_endpoint)
    if results_dir is not None:
        output = automatic_result_path(results_dir, measurement.source_name, settings.solver.mode)
        save_result(result, output)
    return result


def analyze_pasted_table(text, settings, results_dir=None, progress=None, cancel=None, initial_endpoint=None):
    measurement = parse_table_text(text, settings.import_settings, "Clipboard_Table")
    result = analyze_measurement(measurement, settings, progress, cancel, initial_endpoint)
    if results_dir is not None:
        output = automatic_result_path(results_dir, measurement.source_name, settings.solver.mode)
        save_result(result, output)
    return result


def add_analytical_comparison(result, progress=None, cancel=None):
    if result.processed is None:
        raise ValueError("Analytical comparison requires a result containing its processed measurement.")
    beta_settings = deepcopy(result.settings)
    beta_settings.solver.mode = "analytical"
    endpoint = None
    if result.initial_state_field_rz is not None:
        endpoint = InitialEndpoint(result.initial_state_field_rz, dict(result.initial_state_metadata))
    output = run_analytical(result.processed, beta_settings, progress, cancel, endpoint)
    result.analytical_diffusivity_mm2_s = output.diffusivity
    result.analytical_exposure_mm2 = output.exposure
    return result


def run_batch(paths, settings, results_dir, progress=None, cancel=None):
    paths = [Path(path) for path in paths]
    results, errors = [], []
    def endpoint_progress(fraction, message):
        if progress:
            progress(0.10 * fraction / 0.15, message)
    endpoint = prepare_initial_endpoint(settings, endpoint_progress, cancel)
    for index, path in enumerate(paths):
        if cancel and cancel():
            break
        try:
            def case_progress(fraction, message):
                if progress:
                    progress(0.10 + 0.90 * (index + fraction) / max(len(paths), 1), f"{path.name}: {message}")
            results.append(analyze_file(
                path, deepcopy(settings), results_dir, case_progress, cancel, endpoint
            ))
        except Exception as exc:
            errors.append((str(path), str(exc)))
    return results, errors
