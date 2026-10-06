"""Numerical and analytical inverse-diffusion solvers for the CGHE analyzer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy.special import jn_zeros

from cghe_initial_state import endpoint_metadata, load_endpoint, validate_endpoint
from cghe_types import AnalysisSettings, CancelCallback, InitialEndpoint, ProgressCallback, ProcessedMeasurement


class SimulationCancelled(RuntimeError):
    pass


@njit(cache=True)
def _update_axisymmetric(field, diffusivity, dr, dz, dt):
    nr, nz = field.shape
    updated = field.copy()
    for i in range(1, nr - 1):
        radius = i * dr
        for k in range(1, nz - 1):
            radial_second = (field[i + 1, k] - 2.0 * field[i, k] + field[i - 1, k]) / (dr * dr)
            radial_first = (field[i + 1, k] - field[i - 1, k]) / (2.0 * dr)
            axial_second = (field[i, k + 1] - 2.0 * field[i, k] + field[i, k - 1]) / (dz * dz)
            updated[i, k] = field[i, k] + diffusivity * dt * (
                radial_second + radial_first / radius + axial_second
            )
    updated[0, :] = updated[1, :]
    updated[-1, :] = 0.0
    updated[:, 0] = 0.0
    updated[:, -1] = 0.0
    return updated


@njit(cache=True)
def _update_full_3d(field, diffusivity, dr, dtheta, dz, dt):
    nr, ntheta, nz = field.shape
    updated = field.copy()
    for i in range(1, nr - 1):
        radius = i * dr
        for j in range(ntheta):
            previous_j = (j - 1) % ntheta
            next_j = (j + 1) % ntheta
            for k in range(1, nz - 1):
                radial_second = (field[i + 1, j, k] - 2.0 * field[i, j, k] + field[i - 1, j, k]) / (dr * dr)
                radial_first = (field[i + 1, j, k] - field[i - 1, j, k]) / (2.0 * dr)
                angular_second = (
                    field[i, next_j, k] - 2.0 * field[i, j, k] + field[i, previous_j, k]
                ) / (dtheta * dtheta * radius * radius)
                axial_second = (field[i, j, k + 1] - 2.0 * field[i, j, k] + field[i, j, k - 1]) / (dz * dz)
                updated[i, j, k] = field[i, j, k] + diffusivity * dt * (
                    radial_second + radial_first / radius + angular_second + axial_second
                )
    for j in range(ntheta):
        updated[0, j, :] = updated[1, j, :]
    updated[-1, :, :] = 0.0
    updated[:, :, 0] = 0.0
    updated[:, :, -1] = 0.0
    return updated


@njit(cache=True)
def _total_axisymmetric(field, dr):
    total = 0.0
    for i in range(field.shape[0]):
        weight = i * dr
        for k in range(field.shape[1]):
            total += field[i, k] * weight
    return total


@njit(cache=True)
def _total_full_3d(field, dr):
    total = 0.0
    for i in range(field.shape[0]):
        weight = i * dr
        for j in range(field.shape[1]):
            for k in range(field.shape[2]):
                total += field[i, j, k] * weight
    return total


@dataclass
class SolverOutput:
    diffusivity: np.ndarray
    remaining: np.ndarray
    snapshot_fields: np.ndarray | None
    snapshot_times: np.ndarray
    snapshot_remaining: np.ndarray
    snapshot_diffusivity: np.ndarray
    snapshot_requested: np.ndarray
    diagnostics: dict
    exposure: np.ndarray | None = None
    initial_endpoint: InitialEndpoint | None = None


def validate_numerical_settings(settings: AnalysisSettings) -> dict[str, float | int]:
    geometry, mesh, solver = settings.geometry, settings.mesh, settings.solver
    if geometry.radius_mm <= 0 or geometry.height_mm <= 0:
        raise ValueError("Cylinder radius and height must be positive.")
    if min(mesh.radial_step_mm, mesh.axial_step_mm, mesh.angular_step_deg, mesh.time_step_s) <= 0:
        raise ValueError("Mesh steps and timestep must be positive.")
    grid = mesh.derived(geometry)
    inverse_square_sum = 1.0 / grid["dr_mm"] ** 2 + 1.0 / grid["dz_mm"] ** 2
    conservative_limit = 0.5 / (solver.maximum_diffusivity_mm2_s * inverse_square_sum)
    if mesh.time_step_s > conservative_limit:
        raise ValueError(
            f"Explicit timestep {mesh.time_step_s:g} s exceeds the conservative stability limit "
            f"{conservative_limit:.6g} s for Dmax={solver.maximum_diffusivity_mm2_s:g} mm²/s."
        )
    return grid


def _cancelled(callback: CancelCallback | None) -> bool:
    return bool(callback and callback())


def _progress(callback: ProgressCallback | None, fraction: float, text: str) -> None:
    if callback:
        callback(float(np.clip(fraction, 0.0, 1.0)), text)


def _preconditioning_schedule(duration_s: float, time_step_s: float) -> tuple[int, float]:
    """Return full steps and an optional final partial step for the exact duration."""
    if duration_s < 0.0:
        raise ValueError("Preconditioning duration cannot be negative.")
    ratio = duration_s / time_step_s
    nearest = int(round(ratio))
    if np.isclose(ratio, nearest, rtol=0.0, atol=1e-12):
        return nearest, 0.0
    full_steps = int(np.floor(ratio))
    return full_steps, float(duration_s - full_steps * time_step_s)


def _precondition_axisymmetric(settings, grid, progress, cancel):
    nr, nz = int(grid["num_r"]), int(grid["num_z"])
    field = np.full((nr, nz), 100.0, dtype=np.float64)
    initial = settings.initial_state
    if initial.mode == "uniform":
        return field
    diffusivity = initial.resolved_diffusivity()
    steps, final_step_s = _preconditioning_schedule(initial.duration_s, settings.mesh.time_step_s)
    updates = steps + int(final_step_s > 0.0)
    report_every = max(1, updates // 100)
    for index in range(updates):
        if index % report_every == 0:
            if _cancelled(cancel):
                raise SimulationCancelled("Preconditioning cancelled")
            _progress(progress, 0.15 * index / max(updates, 1), "Preparing initial concentration")
        step_s = settings.mesh.time_step_s if index < steps else final_step_s
        field = _update_axisymmetric(
            field, diffusivity, grid["dr_mm"], grid["dz_mm"], step_s
        )
    return field


def _precondition_full_3d(settings, grid, progress, cancel):
    symmetric = _precondition_axisymmetric(settings, grid, progress, cancel)
    return np.repeat(symmetric[:, np.newaxis, :], int(grid["num_theta"]), axis=1)


def prepare_initial_endpoint(
    settings: AnalysisSettings,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
) -> InitialEndpoint:
    """Load or calculate one canonical theta-symmetric r-z endpoint."""
    grid = validate_numerical_settings(settings)
    initial = settings.initial_state
    if initial.mode == "endpoint":
        if not initial.endpoint_path:
            raise ValueError("Initial-state mode is 'endpoint', but no endpoint file was selected.")
        loaded = load_endpoint(initial.endpoint_path, settings)
        endpoint = InitialEndpoint(loaded.field_rz, dict(loaded.metadata))
        endpoint.metadata["source"] = "endpoint_file"
        endpoint.metadata["loaded_from"] = str(initial.endpoint_path)
        _progress(progress, 0.15, "Loaded preconditioning endpoint")
        return endpoint
    if initial.mode not in {"calculate", "preconditioned", "preset", "uniform"}:
        raise ValueError(f"Unknown initial-state mode: {initial.mode}")
    field = _precondition_axisymmetric(settings, grid, progress, cancel)
    endpoint = InitialEndpoint(field_rz=field, metadata=endpoint_metadata(settings))
    endpoint.metadata["source"] = "calculated"
    _progress(progress, 0.15, "Initial concentration ready")
    return endpoint


class _SnapshotCollector:
    def __init__(self, settings, initial_field, initial_d, final_time):
        self.settings = settings
        self.fields = []
        self.times = []
        self.remaining = []
        self.diffusivity = []
        self.requested = []
        self.next_time = settings.interval if settings.mode == "seconds" else None
        if settings.mode == "remaining_percent":
            interval = settings.interval / 100.0
            self.levels = list(np.arange(1.0 - interval, 0.0, -interval)) if interval > 0 else []
        else:
            self.levels = []
        self.final_time = final_time
        if settings.mode != "none":
            self.add(initial_field, 0.0, 1.0, initial_d, 1.0)

    def add(self, field, time_s, remaining, diffusivity, requested):
        self.fields.append(field.copy())
        self.times.append(float(time_s))
        self.remaining.append(float(remaining))
        self.diffusivity.append(float(diffusivity))
        self.requested.append(float(requested))

    def consider(self, field, time_s, remaining, diffusivity):
        if self.settings.mode == "remaining_percent":
            while self.levels and remaining <= self.levels[0] + 1e-12:
                level = self.levels.pop(0)
                self.add(field, time_s, remaining, diffusivity, level)
        elif self.settings.mode == "seconds" and self.next_time is not None:
            while time_s >= self.next_time - 1e-12:
                requested = self.next_time
                self.add(field, time_s, remaining, diffusivity, requested)
                self.next_time += self.settings.interval

    def finalize(self, field, time_s, remaining, diffusivity):
        if self.settings.mode == "final" or (
            self.settings.mode != "none" and (not self.times or abs(self.times[-1] - time_s) > 1e-12)
        ):
            self.add(field, time_s, remaining, diffusivity, remaining)
        fields = np.asarray(self.fields) if self.fields else None
        return (
            fields,
            np.asarray(self.times),
            np.asarray(self.remaining),
            np.asarray(self.diffusivity),
            np.asarray(self.requested),
        )


def _run_numerical(processed, settings, full_3d, progress, cancel, initial_endpoint=None):
    grid = validate_numerical_settings(settings)
    endpoint = initial_endpoint or prepare_initial_endpoint(settings, progress, cancel)
    validate_endpoint(endpoint, settings)
    if full_3d:
        field = np.repeat(endpoint.field_rz[:, np.newaxis, :], int(grid["num_theta"]), axis=1)
        update = lambda matrix, value: _update_full_3d(
            matrix, value, grid["dr_mm"], grid["dtheta_rad"], grid["dz_mm"], settings.mesh.time_step_s
        )
        total = lambda matrix: _total_full_3d(matrix, grid["dr_mm"])
    else:
        field = endpoint.field_rz.copy()
        update = lambda matrix, value: _update_axisymmetric(
            matrix, value, grid["dr_mm"], grid["dz_mm"], settings.mesh.time_step_s
        )
        total = lambda matrix: _total_axisymmetric(matrix, grid["dr_mm"])

    target = processed.remaining_target
    time = processed.time_s
    initial_total = float(total(field))
    if initial_total <= 0:
        raise RuntimeError("Initial hydrogen integral is not positive.")
    values = np.empty(len(time), dtype=float)
    remaining = np.empty(len(time), dtype=float)
    values[0] = settings.solver.initial_diffusivity_mm2_s
    remaining[0] = 1.0
    collector = _SnapshotCollector(settings.snapshots, field, values[0], time[-1])
    clipped_min = clipped_max = 0
    report_every = max(1, (len(time) - 1) // 500)

    for index in range(1, len(time)):
        if index % report_every == 0:
            if _cancelled(cancel):
                raise SimulationCancelled("Numerical inversion cancelled")
            _progress(progress, 0.15 + 0.80 * index / max(len(time) - 1, 1), "Solving inverse diffusion")
        zero = update(field, 0.0)
        one = update(field, 1.0)
        fraction_zero = total(zero) / initial_total
        fraction_one = total(one) / initial_total
        slope = fraction_one - fraction_zero
        if abs(slope) < 1e-15:
            raise RuntimeError(f"Inverse step {index} is insensitive to diffusivity.")
        raw_value = (target[index] - fraction_zero) / slope
        value = float(np.clip(
            raw_value,
            settings.solver.minimum_diffusivity_mm2_s,
            settings.solver.maximum_diffusivity_mm2_s,
        ))
        clipped_min += int(raw_value < settings.solver.minimum_diffusivity_mm2_s)
        clipped_max += int(raw_value > settings.solver.maximum_diffusivity_mm2_s)
        field = zero + value * (one - zero)
        current_remaining = float(total(field) / initial_total)
        values[index] = value
        remaining[index] = current_remaining
        collector.consider(field, time[index], current_remaining, value)

    snapshots = collector.finalize(field, time[-1], remaining[-1], values[-1])
    _progress(progress, 0.96, "Finalizing numerical result")
    return SolverOutput(
        values, remaining, *snapshots,
        diagnostics={
            "grid": grid,
            "initial_total_hydrogen": initial_total,
            "hydrogen_integration": "cylindrical_r_weighted",
            "clipped_minimum_steps": clipped_min,
            "clipped_maximum_steps": clipped_max,
            "axisymmetric_solver": not full_3d,
            "initial_state_source": endpoint.metadata.get("source", "endpoint file"),
        },
        initial_endpoint=endpoint,
    )


def run_axisymmetric(
    processed: ProcessedMeasurement,
    settings: AnalysisSettings,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
    initial_endpoint: InitialEndpoint | None = None,
) -> SolverOutput:
    return _run_numerical(processed, settings, False, progress, cancel, initial_endpoint)


def run_full_3d(
    processed: ProcessedMeasurement,
    settings: AnalysisSettings,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
    initial_endpoint: InitialEndpoint | None = None,
) -> SolverOutput:
    return _run_numerical(processed, settings, True, progress, cancel, initial_endpoint)


_BESSEL_ZEROS = jn_zeros(0, 80)
_ODD_AXIAL = np.arange(1, 160, 2, dtype=float)


def finite_cylinder_remaining(exposure_mm2, radius_mm, height_mm):
    exposure = np.atleast_1d(np.asarray(exposure_mm2, dtype=float))
    radial = 4.0 * np.sum(
        np.exp(-np.outer(exposure / radius_mm**2, _BESSEL_ZEROS**2)) / _BESSEL_ZEROS**2,
        axis=1,
    )
    axial = 8.0 / np.pi**2 * np.sum(
        np.exp(-np.outer(exposure / height_mm**2, (_ODD_AXIAL * np.pi) ** 2)) / _ODD_AXIAL**2,
        axis=1,
    )
    result = radial * axial
    result[exposure == 0.0] = 1.0
    if np.ndim(exposure_mm2) == 0:
        return float(result[0])
    return result


def run_analytical(
    processed: ProcessedMeasurement,
    settings: AnalysisSettings,
    progress: ProgressCallback | None = None,
    cancel: CancelCallback | None = None,
    initial_endpoint: InitialEndpoint | None = None,
) -> SolverOutput:
    if _cancelled(cancel):
        raise SimulationCancelled("Analytical inversion cancelled")
    _progress(progress, 0.20, "Building finite-cylinder exposure map")
    endpoint = initial_endpoint or prepare_initial_endpoint(settings, progress, cancel)
    validate_endpoint(endpoint, settings)
    theta0 = float(endpoint.metadata.get("diffusivity_mm2_s", 0.0)) * float(
        endpoint.metadata.get("duration_s", 0.0)
    )
    initial_fraction = finite_cylinder_remaining(theta0, settings.geometry.radius_mm, settings.geometry.height_mm)
    minimum_target = max(float(np.nanmin(processed.remaining_target)), 1e-6)
    high = max(settings.geometry.radius_mm**2, settings.geometry.height_mm**2, 1.0)
    while finite_cylinder_remaining(theta0 + high, settings.geometry.radius_mm, settings.geometry.height_mm) / initial_fraction > minimum_target:
        high *= 2.0
    exposure_grid = np.linspace(0.0, high, 50001)
    remaining_grid = finite_cylinder_remaining(
        theta0 + exposure_grid, settings.geometry.radius_mm, settings.geometry.height_mm
    ) / initial_fraction
    exposure = np.interp(processed.remaining_target, remaining_grid[::-1], exposure_grid[::-1])
    diffusivity = np.gradient(exposure, processed.time_s, edge_order=2)
    simulated = np.interp(exposure, exposure_grid, remaining_grid)
    _progress(progress, 0.95, "Finalizing analytical result")
    return SolverOutput(
        diffusivity=diffusivity,
        remaining=simulated,
        snapshot_fields=None,
        snapshot_times=np.empty(0),
        snapshot_remaining=np.empty(0),
        snapshot_diffusivity=np.empty(0),
        snapshot_requested=np.empty(0),
        diagnostics={
            "analytical_beta": True,
            "preconditioning_exposure_mm2": theta0,
            "exposure_grid_points": len(exposure_grid),
        },
        exposure=exposure,
        initial_endpoint=endpoint,
    )


def run_solver(processed, settings, progress=None, cancel=None, initial_endpoint=None):
    mode = settings.solver.mode
    if mode == "axisymmetric":
        return run_axisymmetric(processed, settings, progress, cancel, initial_endpoint)
    if mode == "full_3d":
        return run_full_3d(processed, settings, progress, cancel, initial_endpoint)
    if mode == "analytical":
        return run_analytical(processed, settings, progress, cancel, initial_endpoint)
    raise ValueError(f"Unknown solver mode: {mode}")
