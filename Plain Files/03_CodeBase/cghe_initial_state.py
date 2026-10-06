"""Persistence and compatibility checks for reusable P11 preconditioning endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import h5py
import numpy as np

from cghe_types import AnalysisSettings, InitialEndpoint


ENDPOINT_SCHEMA_NAME = "weldcraft.p11.cghe.initial-state"
ENDPOINT_SCHEMA_VERSION = 1


def endpoint_metadata(settings: AnalysisSettings) -> dict[str, object]:
    grid = settings.mesh.derived(settings.geometry)
    return {
        "schema_name": ENDPOINT_SCHEMA_NAME,
        "schema_version": ENDPOINT_SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "radius_mm": float(settings.geometry.radius_mm),
        "height_mm": float(settings.geometry.height_mm),
        "radial_step_mm": float(settings.mesh.radial_step_mm),
        "axial_step_mm": float(settings.mesh.axial_step_mm),
        "angular_step_deg": float(settings.mesh.angular_step_deg),
        "time_step_s": float(settings.mesh.time_step_s),
        "num_r": int(grid["num_r"]),
        "num_z": int(grid["num_z"]),
        "num_theta": int(grid["num_theta"]),
        "dr_mm": float(grid["dr_mm"]),
        "dz_mm": float(grid["dz_mm"]),
        "dtheta_deg": float(grid["dtheta_deg"]),
        "diffusivity_mm2_s": float(settings.initial_state.resolved_diffusivity()),
        "duration_s": float(settings.initial_state.duration_s),
    }


def endpoint_mismatches(endpoint: InitialEndpoint, settings: AnalysisSettings) -> list[str]:
    expected = endpoint_metadata(settings)
    labels = {
        "radius_mm": "radius",
        "height_mm": "height",
        "radial_step_mm": "requested radial step",
        "axial_step_mm": "requested axial step",
        "angular_step_deg": "requested angular step",
        "time_step_s": "timestep",
        "num_r": "radial node count",
        "num_z": "axial node count",
        "num_theta": "angular node count",
        "dr_mm": "realized radial step",
        "dz_mm": "realized axial step",
        "dtheta_deg": "realized angular step",
    }
    mismatches: list[str] = []
    for key, label in labels.items():
        if key not in endpoint.metadata:
            mismatches.append(f"{label}: endpoint metadata is missing '{key}'")
            continue
        actual = endpoint.metadata[key]
        wanted = expected[key]
        if isinstance(wanted, int):
            equal = int(actual) == wanted
        else:
            equal = bool(np.isclose(float(actual), float(wanted), rtol=1e-12, atol=1e-15))
        if not equal:
            mismatches.append(f"{label}: endpoint {actual!r}, current settings {wanted!r}")
    expected_shape = (int(expected["num_r"]), int(expected["num_z"]))
    if tuple(endpoint.field_rz.shape) != expected_shape:
        mismatches.append(
            f"concentration shape: endpoint {tuple(endpoint.field_rz.shape)}, current grid {expected_shape}"
        )
    return mismatches


def validate_endpoint(endpoint: InitialEndpoint, settings: AnalysisSettings) -> None:
    mismatches = endpoint_mismatches(endpoint, settings)
    if mismatches:
        details = "\n".join(f"- {item}" for item in mismatches)
        raise ValueError(f"The preconditioning endpoint does not match the current settings:\n{details}")
    if endpoint.field_rz.ndim != 2 or not np.all(np.isfinite(endpoint.field_rz)):
        raise ValueError("The preconditioning endpoint must contain one finite 2-D r-z concentration field.")


def _metadata_from_group(group: h5py.Group) -> dict[str, object]:
    if "metadata_json" in group:
        raw = group["metadata_json"][()]
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return dict(json.loads(raw))
    return {key: value.item() if isinstance(value, np.generic) else value for key, value in group.attrs.items()}


def _read_group(group: h5py.Group) -> InitialEndpoint:
    if "concentration_rz" not in group:
        raise ValueError("The HDF5 initial-state group has no 'concentration_rz' dataset.")
    return InitialEndpoint(np.asarray(group["concentration_rz"][:], dtype=float), _metadata_from_group(group))


def load_endpoint(path: str | Path, settings: AnalysisSettings | None = None) -> InitialEndpoint:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with h5py.File(path, "r") as handle:
        if "initial_state" in handle:
            endpoint = _read_group(handle["initial_state"])
        elif handle.attrs.get("schema_name", "") == ENDPOINT_SCHEMA_NAME:
            endpoint = _read_group(handle)
        else:
            raise ValueError(
                "This file is neither a standalone P11 endpoint nor a schema-v2 result containing an initial state."
            )
    if settings is not None:
        validate_endpoint(endpoint, settings)
    return endpoint


def write_endpoint_group(parent: h5py.Group, endpoint: InitialEndpoint, name: str = "initial_state") -> h5py.Group:
    group = parent.create_group(name)
    group.create_dataset(
        "concentration_rz", data=np.asarray(endpoint.field_rz, dtype=float),
        compression="gzip", compression_opts=4, shuffle=True,
    )
    group.create_dataset("metadata_json", data=np.bytes_(json.dumps(endpoint.metadata, sort_keys=True)))
    return group


def save_endpoint(endpoint: InitialEndpoint, path: str | Path) -> Path:
    path = Path(path)
    if not path.parent.is_dir():
        raise FileNotFoundError(f"Endpoint destination directory does not exist: {path.parent}")
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing endpoint: {path}")
    partial = path.with_suffix(path.suffix + ".partial")
    if partial.exists():
        partial.unlink()
    try:
        with h5py.File(partial, "w") as handle:
            handle.attrs["schema_name"] = ENDPOINT_SCHEMA_NAME
            handle.attrs["schema_version"] = ENDPOINT_SCHEMA_VERSION
            handle.attrs["created_utc"] = endpoint.metadata.get("created_utc", "")
            handle.create_dataset(
                "concentration_rz", data=np.asarray(endpoint.field_rz, dtype=float),
                compression="gzip", compression_opts=4, shuffle=True,
            )
            handle.create_dataset("metadata_json", data=np.bytes_(json.dumps(endpoint.metadata, sort_keys=True)))
        partial.replace(path)
    except BaseException:
        if partial.exists():
            partial.unlink()
        raise
    return path
