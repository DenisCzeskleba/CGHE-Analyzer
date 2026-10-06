"""Typed configuration and result containers for CGHE Analyzer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np


ProgressCallback = Callable[[float, str], None]
CancelCallback = Callable[[], bool]


@dataclass
class ImportSettings:
    format: str = "auto"
    delimiter: str = "auto"
    decimal: str = "auto"
    header_rows: int = -1
    time_column: str = "auto"
    signal_column: str = "auto"
    sampling_hz: float = 5.0
    detector_delay_s: float = 38.0
    baseline_mode: str = "subtract_minimum"
    baseline_value: float = 0.0
    baseline_start_s: float = 0.0
    baseline_end_s: float = 10.0


@dataclass
class PreprocessingSettings:
    signal_processing_mode: str = "auto"
    tcd_smoothing_method: str = "legacy_multistep"
    rolling_span_samples: int = 21
    rolling_pass_count: int = 2
    isotonic_decay: bool = True
    tail_mode: str = "double"
    tail_start_multiplier: float = 1.7
    stop_fraction: float = 0.05


@dataclass
class GeometrySettings:
    radius_mm: float = 4.0
    height_mm: float = 3.3


@dataclass
class MeshSettings:
    radial_step_mm: float = 4.0 / 39.0
    axial_step_mm: float = 0.1
    angular_step_deg: float = 9.0
    time_step_s: float = 0.01

    def derived(self, geometry: GeometrySettings) -> dict[str, float | int]:
        num_r = max(3, int(round(geometry.radius_mm / self.radial_step_mm)) + 1)
        num_z = max(3, int(round(geometry.height_mm / self.axial_step_mm)) + 1)
        num_theta = max(3, int(round(360.0 / self.angular_step_deg)))
        return {
            "num_r": num_r,
            "num_z": num_z,
            "num_theta": num_theta,
            "dr_mm": geometry.radius_mm / (num_r - 1),
            "dz_mm": geometry.height_mm / (num_z - 1),
            "dtheta_rad": 2.0 * np.pi / num_theta,
            "dtheta_deg": 360.0 / num_theta,
        }


@dataclass
class InitialStateSettings:
    mode: str = "calculate"
    duration_s: float = 120.0
    diffusivity_mm2_s: float = 8.3e-5
    endpoint_path: str = ""

    def resolved_diffusivity(self) -> float:
        return self.diffusivity_mm2_s


@dataclass
class SolverSettings:
    mode: str = "axisymmetric"
    initial_diffusivity_mm2_s: float = 8.3e-5
    minimum_diffusivity_mm2_s: float = 1e-12
    maximum_diffusivity_mm2_s: float = 1e-1


@dataclass
class SnapshotSettings:
    mode: str = "remaining_percent"
    interval: float = 5.0


@dataclass
class EvaluationSettings:
    reliable_upper: float = 0.55
    reliable_lower: float = 0.10
    window_width: float = 0.10
    minimum_time_s: float = 20.0


@dataclass
class AnalysisSettings:
    import_settings: ImportSettings = field(default_factory=ImportSettings)
    preprocessing: PreprocessingSettings = field(default_factory=PreprocessingSettings)
    geometry: GeometrySettings = field(default_factory=GeometrySettings)
    mesh: MeshSettings = field(default_factory=MeshSettings)
    initial_state: InitialStateSettings = field(default_factory=InitialStateSettings)
    solver: SolverSettings = field(default_factory=SolverSettings)
    snapshots: SnapshotSettings = field(default_factory=SnapshotSettings)
    evaluation: EvaluationSettings = field(default_factory=EvaluationSettings)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> "AnalysisSettings":
        values = dict(values or {})
        preprocessing_values = dict(values.get("preprocessing", {}))
        preprocessing_values.setdefault("signal_processing_mode", "auto")
        preprocessing_values.setdefault("tcd_smoothing_method", "legacy_multistep")
        preprocessing_values.setdefault("rolling_pass_count", 2)
        initial_values = dict(values.get("initial_state", {}))
        old_initial_mode = initial_values.get("mode", "calculate")
        initial_values.pop("preset", None)
        if old_initial_mode == "uniform":
            initial_values["mode"] = "calculate"
            initial_values["duration_s"] = 0.0
        elif old_initial_mode == "preset":
            initial_values["mode"] = "calculate"
        elif old_initial_mode == "preconditioned":
            initial_values["mode"] = "calculate"
        initial_values.setdefault("endpoint_path", "")
        return cls(
            import_settings=ImportSettings(**values.get("import_settings", {})),
            preprocessing=PreprocessingSettings(**preprocessing_values),
            geometry=GeometrySettings(**values.get("geometry", {})),
            mesh=MeshSettings(**values.get("mesh", {})),
            initial_state=InitialStateSettings(**initial_values),
            solver=SolverSettings(**values.get("solver", {})),
            snapshots=SnapshotSettings(**values.get("snapshots", {})),
            evaluation=EvaluationSettings(**values.get("evaluation", {})),
        )


@dataclass
class MeasurementData:
    source_name: str
    raw_time_s: np.ndarray
    raw_signal: np.ndarray
    time_s: np.ndarray
    signal: np.ndarray
    mapping: dict[str, Any]


@dataclass
class ProcessedMeasurement:
    measurement: MeasurementData
    time_s: np.ndarray
    signal_interpolated: np.ndarray
    signal_rolling: np.ndarray
    signal_isotonic: np.ndarray
    signal_processed: np.ndarray
    cumulative_release: np.ndarray
    remaining_target: np.ndarray
    tail_fit: dict[str, float] | None
    requested_processing_mode: str = "auto"
    resolved_processing_mode: str = "tcd"
    processing_reason: str = "Legacy-compatible default"
    full_time_s: np.ndarray | None = None
    full_signal_processed: np.ndarray | None = None
    full_remaining_target: np.ndarray | None = None


@dataclass
class InitialEndpoint:
    field_rz: np.ndarray
    metadata: dict[str, Any]


@dataclass
class AnalysisResult:
    settings: AnalysisSettings
    source_name: str
    solver_mode: str
    time_s: np.ndarray
    diffusivity_mm2_s: np.ndarray
    remaining_target: np.ndarray
    remaining_simulated: np.ndarray
    residual: np.ndarray
    measurement: MeasurementData | None = None
    processed: ProcessedMeasurement | None = None
    snapshot_fields: np.ndarray | None = None
    snapshot_time_s: np.ndarray = field(default_factory=lambda: np.empty(0))
    snapshot_remaining: np.ndarray = field(default_factory=lambda: np.empty(0))
    snapshot_diffusivity: np.ndarray = field(default_factory=lambda: np.empty(0))
    snapshot_requested: np.ndarray = field(default_factory=lambda: np.empty(0))
    evaluation: dict[str, Any] = field(default_factory=dict)
    analytical_diffusivity_mm2_s: np.ndarray | None = None
    analytical_exposure_mm2: np.ndarray | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    processing_metadata: dict[str, Any] = field(default_factory=dict)
    initial_state_field_rz: np.ndarray | None = None
    initial_state_metadata: dict[str, Any] = field(default_factory=dict)
    result_path: str | None = None
    legacy_read_only: bool = False

    @property
    def mae(self) -> float:
        return float(np.nanmean(np.abs(self.residual)))

    @property
    def maximum_residual(self) -> float:
        return float(np.nanmax(np.abs(self.residual)))
