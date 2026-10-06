"""Versioned HDF5 persistence and exports for CGHE results."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re

import h5py
import numpy as np

from cghe_evaluation import select_evaluation_window
from cghe_initial_state import write_endpoint_group
from cghe_types import AnalysisResult, AnalysisSettings, InitialEndpoint, MeasurementData, ProcessedMeasurement


SCHEMA_NAME = "weldcraft.p11.cghe"
SCHEMA_VERSION = 2
APP_VERSION = "0.6.1"


def sanitize_stem(value: str) -> str:
    stem = Path(value).stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned[:80] or "measurement"


def automatic_result_path(results_dir: str | Path, source_name: str, solver_mode: str, now=None) -> Path:
    results_dir = Path(results_dir)
    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    base = f"{sanitize_stem(source_name)}_{solver_mode}_{stamp}"
    candidate = results_dir / f"{base}.h5"
    counter = 2
    while candidate.exists() or candidate.with_suffix(candidate.suffix + ".partial").exists():
        candidate = results_dir / f"{base}_{counter}.h5"
        counter += 1
    return candidate


def _write_json(group, name, value):
    group.create_dataset(name, data=np.bytes_(json.dumps(value, sort_keys=True)))


def _read_json(group, name, default=None):
    if name not in group:
        return default
    raw = group[name][()]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def save_result(result: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing result: {path}")
    if partial.exists():
        partial.unlink()
    compression = {"compression": "gzip", "compression_opts": 4, "shuffle": True}
    try:
        with h5py.File(partial, "w") as handle:
            handle.attrs.update({
                "schema_name": SCHEMA_NAME,
                "schema_version": SCHEMA_VERSION,
                "app_version": APP_VERSION,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "solver_mode": result.solver_mode,
                "source_basename": Path(result.source_name).name,
                "completion_status": "complete",
            })
            metadata = handle.create_group("metadata")
            _write_json(metadata, "settings_json", result.settings.to_dict())
            _write_json(metadata, "diagnostics_json", result.diagnostics)
            _write_json(metadata, "evaluation_json", result.evaluation)
            _write_json(metadata, "processing_json", result.processing_metadata)

            if result.initial_state_field_rz is None:
                raise ValueError("Schema-v2 results require a canonical initial-state endpoint.")
            write_endpoint_group(
                handle,
                InitialEndpoint(result.initial_state_field_rz, dict(result.initial_state_metadata)),
            )

            if result.measurement is not None:
                raw = handle.create_group("input")
                raw.create_dataset("raw_time_s", data=result.measurement.raw_time_s, **compression)
                raw.create_dataset("raw_signal", data=result.measurement.raw_signal, **compression)
                raw.create_dataset("corrected_time_s", data=result.measurement.time_s, **compression)
                raw.create_dataset("corrected_signal", data=result.measurement.signal, **compression)
                _write_json(raw, "mapping_json", result.measurement.mapping)
            if result.processed is not None:
                processed = handle.create_group("processed")
                for name, values in (
                    ("time_s", result.processed.time_s),
                    ("signal_interpolated", result.processed.signal_interpolated),
                    ("signal_rolling", result.processed.signal_rolling),
                    ("signal_isotonic", result.processed.signal_isotonic),
                    ("signal_processed", result.processed.signal_processed),
                    ("cumulative_release", result.processed.cumulative_release),
                    ("remaining_target", result.processed.remaining_target),
                ):
                    processed.create_dataset(name, data=values, **compression)
                _write_json(processed, "tail_fit_json", result.processed.tail_fit)
                if result.processed.full_time_s is not None:
                    processed.create_dataset("full_time_s", data=result.processed.full_time_s, **compression)
                if result.processed.full_signal_processed is not None:
                    processed.create_dataset(
                        "full_signal_processed", data=result.processed.full_signal_processed, **compression
                    )
                if result.processed.full_remaining_target is not None:
                    processed.create_dataset(
                        "full_remaining_target", data=result.processed.full_remaining_target, **compression
                    )

            results = handle.create_group("results")
            for name, values in (
                ("time_s", result.time_s),
                ("diffusivity_mm2_s", result.diffusivity_mm2_s),
                ("remaining_target", result.remaining_target),
                ("remaining_simulated", result.remaining_simulated),
                ("residual", result.residual),
            ):
                results.create_dataset(name, data=values, **compression)
            results.attrs["mae"] = result.mae
            results.attrs["maximum_residual"] = result.maximum_residual
            if result.analytical_diffusivity_mm2_s is not None:
                analytical = handle.create_group("analytical_beta")
                analytical.create_dataset("diffusivity_mm2_s", data=result.analytical_diffusivity_mm2_s, **compression)
                if result.analytical_exposure_mm2 is not None:
                    analytical.create_dataset("exposure_mm2", data=result.analytical_exposure_mm2, **compression)
            if result.snapshot_fields is not None:
                snapshots = handle.create_group("snapshots")
                snapshots.create_dataset("concentration", data=result.snapshot_fields, **compression)
                snapshots.create_dataset("time_s", data=result.snapshot_time_s)
                snapshots.create_dataset("remaining", data=result.snapshot_remaining)
                snapshots.create_dataset("diffusivity_mm2_s", data=result.snapshot_diffusivity)
                snapshots.create_dataset("requested", data=result.snapshot_requested)
        os.replace(partial, path)
    except BaseException:
        if partial.exists():
            partial.unlink()
        raise
    result.result_path = str(path)
    return path


def _load_new(handle: h5py.File, path: Path) -> AnalysisResult:
    settings = AnalysisSettings.from_dict(_read_json(handle["metadata"], "settings_json", {}))
    measurement = processed_data = None
    if "input" in handle:
        group = handle["input"]
        measurement = MeasurementData(
            source_name=str(handle.attrs.get("source_basename", path.name)),
            raw_time_s=group["raw_time_s"][:],
            raw_signal=group["raw_signal"][:],
            time_s=group["corrected_time_s"][:],
            signal=group["corrected_signal"][:],
            mapping=_read_json(group, "mapping_json", {}),
        )
    if "processed" in handle and measurement is not None:
        group = handle["processed"]
        processing_metadata = _read_json(handle["metadata"], "processing_json", {})
        processed_data = ProcessedMeasurement(
            measurement=measurement,
            time_s=group["time_s"][:],
            signal_interpolated=group["signal_interpolated"][:],
            signal_rolling=group["signal_rolling"][:],
            signal_isotonic=group["signal_isotonic"][:],
            signal_processed=group["signal_processed"][:],
            cumulative_release=group["cumulative_release"][:],
            remaining_target=group["remaining_target"][:],
            tail_fit=_read_json(group, "tail_fit_json"),
            requested_processing_mode=processing_metadata.get("requested_mode", "auto"),
            resolved_processing_mode=processing_metadata.get("resolved_mode", "tcd"),
            processing_reason=processing_metadata.get("reason", "Loaded schema-v1 processing data."),
            full_time_s=group["full_time_s"][:] if "full_time_s" in group else None,
            full_signal_processed=(
                group["full_signal_processed"][:] if "full_signal_processed" in group else None
            ),
            full_remaining_target=(
                group["full_remaining_target"][:] if "full_remaining_target" in group else None
            ),
        )
    group = handle["results"]
    snapshots = handle.get("snapshots")
    analytical = handle.get("analytical_beta")
    initial_state = handle.get("initial_state")
    initial_metadata = {}
    initial_field = None
    if initial_state is not None and "concentration_rz" in initial_state:
        initial_field = initial_state["concentration_rz"][:]
        initial_metadata = _read_json(initial_state, "metadata_json", {})
    return AnalysisResult(
        settings=settings,
        source_name=str(handle.attrs.get("source_basename", path.name)),
        solver_mode=str(handle.attrs.get("solver_mode", settings.solver.mode)),
        time_s=group["time_s"][:],
        diffusivity_mm2_s=group["diffusivity_mm2_s"][:],
        remaining_target=group["remaining_target"][:],
        remaining_simulated=group["remaining_simulated"][:],
        residual=group["residual"][:],
        measurement=measurement,
        processed=processed_data,
        snapshot_fields=snapshots["concentration"][:] if snapshots is not None else None,
        snapshot_time_s=snapshots["time_s"][:] if snapshots is not None else np.empty(0),
        snapshot_remaining=snapshots["remaining"][:] if snapshots is not None else np.empty(0),
        snapshot_diffusivity=snapshots["diffusivity_mm2_s"][:] if snapshots is not None else np.empty(0),
        snapshot_requested=snapshots["requested"][:] if snapshots is not None else np.empty(0),
        evaluation=_read_json(handle["metadata"], "evaluation_json", {}),
        analytical_diffusivity_mm2_s=analytical["diffusivity_mm2_s"][:] if analytical is not None else None,
        analytical_exposure_mm2=analytical["exposure_mm2"][:] if analytical is not None and "exposure_mm2" in analytical else None,
        diagnostics=_read_json(handle["metadata"], "diagnostics_json", {}),
        processing_metadata=_read_json(handle["metadata"], "processing_json", {}),
        initial_state_field_rz=initial_field,
        initial_state_metadata=initial_metadata,
        result_path=str(path),
    )


def _load_legacy(handle: h5py.File, path: Path) -> AnalysisResult:
    settings = AnalysisSettings()
    settings.geometry.radius_mm = float(handle.attrs.get("r_max", settings.geometry.radius_mm))
    settings.geometry.height_mm = float(handle.attrs.get("z_max", settings.geometry.height_mm))
    settings.mesh.time_step_s = float(handle.attrs.get("delta_t", settings.mesh.time_step_s))
    nr = int(handle.attrs.get("num_r", 40))
    nz = int(handle.attrs.get("num_z", 33))
    nt = int(handle.attrs.get("num_theta", 40))
    settings.mesh.radial_step_mm = settings.geometry.radius_mm / max(nr - 1, 1)
    settings.mesh.axial_step_mm = settings.geometry.height_mm / max(nz - 1, 1)
    settings.mesh.angular_step_deg = 360.0 / max(nt, 1)
    settings.solver.mode = "axisymmetric" if bool(handle.attrs.get("axisymmetric_solver", False)) else "full_3d"
    settings.initial_state.mode = "calculate"
    settings.initial_state.duration_s = 0.0
    time = handle["time"][:]
    target = handle["R_target"][:]
    simulated = handle["remaining_fraction"][:]
    diffusivity = handle["alpha_history"][:]
    snapshot_group = handle.get("concentration_snapshots")
    evaluation = {}
    try:
        evaluation = select_evaluation_window(time, diffusivity, target, settings.evaluation)
    except Exception:
        pass
    return AnalysisResult(
        settings=settings,
        source_name=str(handle.attrs.get("source_csv", path.name)),
        solver_mode=settings.solver.mode,
        time_s=time,
        diffusivity_mm2_s=diffusivity,
        remaining_target=target,
        remaining_simulated=simulated,
        residual=simulated - target,
        snapshot_fields=(snapshot_group["h_matrix_rz"][:] if snapshot_group is not None and "h_matrix_rz" in snapshot_group else None),
        snapshot_time_s=snapshot_group["time"][:] if snapshot_group is not None else np.empty(0),
        snapshot_remaining=snapshot_group["remaining_fraction"][:] if snapshot_group is not None else np.empty(0),
        snapshot_diffusivity=snapshot_group["alpha"][:] if snapshot_group is not None else np.empty(0),
        snapshot_requested=snapshot_group["requested_fraction"][:] if snapshot_group is not None else np.empty(0),
        evaluation=evaluation,
        diagnostics={"legacy_metadata": {key: str(value) for key, value in handle.attrs.items()}},
        result_path=str(path),
        legacy_read_only=True,
    )


def load_result(path: str | Path) -> AnalysisResult:
    path = Path(path)
    with h5py.File(path, "r") as handle:
        if handle.attrs.get("schema_name", "") == SCHEMA_NAME:
            return _load_new(handle, path)
        if all(name in handle for name in ("time", "alpha_history", "remaining_fraction", "R_target")):
            return _load_legacy(handle, path)
        raise ValueError("This HDF5 file is neither a CGHE schema-v1/v2 result nor a supported legacy result.")


def update_result_analysis(result: AnalysisResult) -> None:
    if not result.result_path or result.legacy_read_only:
        return
    with h5py.File(result.result_path, "r+") as handle:
        metadata = handle["metadata"]
        if "evaluation_json" in metadata:
            del metadata["evaluation_json"]
        _write_json(metadata, "evaluation_json", result.evaluation)
        if result.analytical_diffusivity_mm2_s is not None:
            if "analytical_beta" in handle:
                del handle["analytical_beta"]
            analytical = handle.create_group("analytical_beta")
            compression = {"compression": "gzip", "compression_opts": 4, "shuffle": True}
            analytical.create_dataset("diffusivity_mm2_s", data=result.analytical_diffusivity_mm2_s, **compression)
            if result.analytical_exposure_mm2 is not None:
                analytical.create_dataset("exposure_mm2", data=result.analytical_exposure_mm2, **compression)


def export_csv(result: AnalysisResult, path: str | Path) -> Path:
    path = Path(path)
    analytical = result.analytical_diffusivity_mm2_s
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["time_s", "D_mm2_s", "remaining_target", "remaining_simulated", "residual"]
        if analytical is not None:
            header.append("D_analytical_beta_mm2_s")
        writer.writerow(header)
        for index in range(len(result.time_s)):
            row = [
                result.time_s[index], result.diffusivity_mm2_s[index], result.remaining_target[index],
                result.remaining_simulated[index], result.residual[index],
            ]
            if analytical is not None:
                row.append(analytical[index])
            writer.writerow(row)
    return path


def _selected_snapshot_indices(result: AnalysisResult, indices) -> np.ndarray:
    if result.snapshot_fields is None or not len(result.snapshot_fields):
        raise ValueError("This result does not contain saved extraction concentration fields.")
    selected = np.unique(np.asarray(list(indices), dtype=int))
    if not len(selected):
        raise ValueError("Select at least one saved concentration state.")
    if np.any(selected < 0) or np.any(selected >= len(result.snapshot_fields)):
        raise IndexError("A selected concentration-state index is out of range.")
    return selected


def _snapshot_value(values, index, default=np.nan):
    return values[index] if values is not None and len(values) > index else default


def _selected_snapshot_values(values, selected) -> np.ndarray:
    return np.asarray([_snapshot_value(values, int(index)) for index in selected], dtype=float)


def export_concentration_csv(result: AnalysisResult, path: str | Path, indices) -> Path:
    """Export every cell of the selected saved concentration states as tidy CSV."""
    path = Path(path)
    selected = _selected_snapshot_indices(result, indices)
    grid = result.settings.mesh.derived(result.settings.geometry)
    radial = np.linspace(0.0, result.settings.geometry.radius_mm, grid["num_r"])
    axial = np.linspace(0.0, result.settings.geometry.height_mm, grid["num_z"])
    fields = np.asarray(result.snapshot_fields)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if fields.ndim == 3:
            writer.writerow(
                [
                    "state_index",
                    "time_s",
                    "remaining_fraction",
                    "D_mm2_s",
                    "requested_remaining_fraction",
                    "r_mm",
                    "z_mm",
                    "concentration",
                ]
            )
            for snapshot_index in selected:
                field = fields[snapshot_index]
                if field.shape != (len(radial), len(axial)):
                    raise ValueError(
                        f"Saved axisymmetric field {snapshot_index} has shape {field.shape}; "
                        f"the configured mesh requires {(len(radial), len(axial))}."
                    )
                metadata = (
                    snapshot_index,
                    _snapshot_value(result.snapshot_time_s, snapshot_index),
                    _snapshot_value(result.snapshot_remaining, snapshot_index),
                    _snapshot_value(result.snapshot_diffusivity, snapshot_index),
                    _snapshot_value(result.snapshot_requested, snapshot_index),
                )
                for radial_index, r_mm in enumerate(radial):
                    for axial_index, z_mm in enumerate(axial):
                        writer.writerow((*metadata, r_mm, z_mm, field[radial_index, axial_index]))
        elif fields.ndim == 4:
            angular = np.arange(grid["num_theta"], dtype=float) * grid["dtheta_deg"]
            writer.writerow(
                [
                    "state_index",
                    "time_s",
                    "remaining_fraction",
                    "D_mm2_s",
                    "requested_remaining_fraction",
                    "r_mm",
                    "theta_deg",
                    "z_mm",
                    "concentration",
                ]
            )
            for snapshot_index in selected:
                field = fields[snapshot_index]
                expected = (len(radial), len(angular), len(axial))
                if field.shape != expected:
                    raise ValueError(
                        f"Saved full-3D field {snapshot_index} has shape {field.shape}; "
                        f"the configured mesh requires {expected}."
                    )
                metadata = (
                    snapshot_index,
                    _snapshot_value(result.snapshot_time_s, snapshot_index),
                    _snapshot_value(result.snapshot_remaining, snapshot_index),
                    _snapshot_value(result.snapshot_diffusivity, snapshot_index),
                    _snapshot_value(result.snapshot_requested, snapshot_index),
                )
                for radial_index, r_mm in enumerate(radial):
                    for angular_index, theta_deg in enumerate(angular):
                        for axial_index, z_mm in enumerate(axial):
                            writer.writerow(
                                (
                                    *metadata,
                                    r_mm,
                                    theta_deg,
                                    z_mm,
                                    field[radial_index, angular_index, axial_index],
                                )
                            )
        else:
            raise ValueError(f"Unsupported saved concentration array shape: {fields.shape}")
    return path


def export_concentration_npz(result: AnalysisResult, path: str | Path, indices) -> Path:
    """Export selected concentration arrays and their realized grid losslessly."""
    path = Path(path)
    selected = _selected_snapshot_indices(result, indices)
    grid = result.settings.mesh.derived(result.settings.geometry)
    fields = np.asarray(result.snapshot_fields)[selected]
    payload = {
        "state_index": selected,
        "concentration": fields,
        "time_s": _selected_snapshot_values(result.snapshot_time_s, selected),
        "remaining_fraction": _selected_snapshot_values(result.snapshot_remaining, selected),
        "diffusivity_mm2_s": _selected_snapshot_values(result.snapshot_diffusivity, selected),
        "requested_remaining_fraction": _selected_snapshot_values(result.snapshot_requested, selected),
        "r_mm": np.linspace(0.0, result.settings.geometry.radius_mm, grid["num_r"]),
        "z_mm": np.linspace(0.0, result.settings.geometry.height_mm, grid["num_z"]),
        "source_name": np.asarray(result.source_name),
        "solver_mode": np.asarray(result.solver_mode),
        "settings_json": np.asarray(json.dumps(result.settings.to_dict(), sort_keys=True)),
    }
    if fields.ndim == 4:
        payload["theta_deg"] = np.arange(grid["num_theta"], dtype=float) * grid["dtheta_deg"]
    with path.open("wb") as handle:
        np.savez_compressed(handle, **payload)
    return path
