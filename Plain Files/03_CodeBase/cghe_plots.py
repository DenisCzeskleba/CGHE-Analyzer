"""Matplotlib result views for the CGHE analyzer."""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from cghe_types import AnalysisResult


GREEN = "#43a047"


def _evaluation_span(result: AnalysisResult):
    values = result.evaluation or {}
    return values.get("selection_time_start_s"), values.get("selection_time_end_s")


def build_dashboard(result: AnalysisResult) -> Figure:
    """Build one synchronized diagnostic graph with separate y scales."""
    figure = Figure(figsize=(11, 7), constrained_layout=True)
    axis = figure.subplots()
    remaining_axis = axis.twinx()
    signal_axis = axis.twinx()
    signal_axis.spines["right"].set_position(("outward", 70))
    time = result.time_s

    if result.analytical_diffusivity_mm2_s is not None and result.solver_mode != "analytical":
        axis.plot(
            time,
            result.analytical_diffusivity_mm2_s,
            color="tab:orange",
            lw=1.1,
            ls="--",
            alpha=0.8,
            zorder=2,
            label="Analytical comparison (Beta)",
        )
    axis.plot(
        time,
        result.diffusivity_mm2_s,
        color="tab:blue",
        lw=1.5,
        zorder=5,
        label="Numerical inverse" if result.solver_mode != "analytical" else "Analytical inversion (Beta)",
    )
    start, end = _evaluation_span(result)
    if start is not None:
        axis.axvspan(start, end, color=GREEN, alpha=0.18, zorder=0, label="Evaluation interval")
    remaining_axis.plot(
        time,
        result.remaining_target,
        color="black",
        lw=1.25,
        zorder=4,
        label=r"Measured Remaining Hydrogen $R_H$",
    )
    remaining_axis.plot(
        time,
        result.remaining_simulated,
        color="tab:red",
        lw=1.05,
        ls="--",
        zorder=3,
        label=r"Simulated Remaining Hydrogen $R_{H,\mathrm{sim}}$",
    )

    if result.processed is not None:
        processed = result.processed
        signal_time = processed.full_time_s if processed.full_time_s is not None else processed.time_s
        signal_values = (
            processed.full_signal_processed
            if processed.full_signal_processed is not None
            else processed.signal_processed
        )
        signal_axis.plot(
            signal_time,
            signal_values,
            color="tab:purple",
            lw=1.0,
            alpha=0.7,
            zorder=1,
            label="Processed signal",
        )

    axis.set_xlabel("Time [s]")
    axis.set_ylabel("D [mm²/s]", color="tab:blue")
    remaining_axis.set_ylabel("Remaining Hydrogen Fraction", color="tab:red")
    remaining_axis.set_ylim(-0.02, 1.02)
    signal_axis.set_ylabel("Signal [a.u.]", color="tab:purple")
    axis.tick_params(axis="y", colors="tab:blue")
    remaining_axis.tick_params(axis="y", colors="tab:red")
    signal_axis.tick_params(axis="y", colors="tab:purple")
    axis.grid(alpha=0.25)
    handles, labels = axis.get_legend_handles_labels()
    for extra_axis in (remaining_axis, signal_axis):
        extra_handles, extra_labels = extra_axis.get_legend_handles_labels()
        handles.extend(extra_handles)
        labels.extend(extra_labels)
    legend = signal_axis.legend(handles, labels, loc="best", ncol=2)
    legend.set_zorder(1000)
    axis.set_title(
        f"Combined diagnostics · MAE {result.mae:.3g} · max residual {result.maximum_residual:.3g}"
    )
    figure.suptitle(f"CGHE Reverse Analysis — {result.source_name}", fontsize=14)
    return figure


def _snapshot_section(field):
    if field.ndim == 2:
        section = field
    elif field.ndim == 3:
        section = field[:, 0, :]
    else:
        raise ValueError(f"Unsupported concentration snapshot shape: {field.shape}")
    return np.concatenate((section[:0:-1], section), axis=0)


def default_concentration_indices(result: AnalysisResult, maximum: int = 6) -> np.ndarray:
    if result.snapshot_fields is None or not len(result.snapshot_fields):
        return np.empty(0, dtype=int)
    count = len(result.snapshot_fields)
    return np.unique(np.linspace(0, count - 1, min(maximum, count), dtype=int))


def build_concentration_cutaways(result: AnalysisResult, indices=None) -> Figure:
    figure = Figure(figsize=(13, 7.5), constrained_layout=True)
    if result.snapshot_fields is None or not len(result.snapshot_fields):
        axis = figure.subplots()
        axis.text(
            0.5,
            0.5,
            "No extraction concentration fields were saved for this result.\n"
            "Run a new analysis with a concentration-field save policy enabled to view them here.",
            ha="center",
            va="center",
        )
        axis.set_axis_off()
        return figure
    count = len(result.snapshot_fields)
    if indices is None:
        indices = default_concentration_indices(result)
    indices = np.unique(np.asarray(indices, dtype=int))
    if not len(indices):
        axis = figure.subplots()
        axis.text(0.5, 0.5, "Select one or more saved concentration states.", ha="center", va="center")
        axis.set_axis_off()
        return figure
    if np.any(indices < 0) or np.any(indices >= count):
        raise IndexError("A selected concentration-state index is out of range.")
    columns = min(3, len(indices))
    rows = int(np.ceil(len(indices) / columns))
    figure.set_size_inches(4.4 * columns, 3.6 * rows + 0.8, forward=True)
    axes = figure.subplots(rows, columns, squeeze=False)
    maximum = float(np.nanmax(result.snapshot_fields))
    image = None
    for axis, index in zip(axes.flat, indices):
        section = _snapshot_section(result.snapshot_fields[index])
        image = axis.imshow(
            section.T,
            origin="lower",
            aspect="auto",
            cmap="inferno",
            vmin=0.0,
            vmax=maximum,
            extent=(
                -result.settings.geometry.radius_mm,
                result.settings.geometry.radius_mm,
                0,
                result.settings.geometry.height_mm,
            ),
        )
        axis.set_title(
            f"State {index + 1} · t={result.snapshot_time_s[index]:.4g} s · "
            f"Remaining hydrogen={result.snapshot_remaining[index]:.4g}"
        )
        axis.set_xlabel("Radius [mm]")
        axis.set_ylabel("Height [mm]")
    for axis in axes.flat[len(indices):]:
        axis.set_axis_off()
    if image is not None:
        figure.colorbar(image, ax=list(axes.flat), label="Normalized concentration")
    figure.suptitle("Cylinder concentration fields", fontsize=14)
    return figure


def build_result_figure(result: AnalysisResult) -> Figure:
    figure = Figure(figsize=(10.5, 7), constrained_layout=True)
    top, bottom = figure.subplots(2, 1, sharex=True, height_ratios=(2.2, 1.0))
    if result.analytical_diffusivity_mm2_s is not None and result.solver_mode != "analytical":
        top.plot(
            result.time_s,
            result.analytical_diffusivity_mm2_s,
            color="tab:orange",
            lw=1.15,
            ls="--",
            alpha=0.8,
            zorder=2,
            label="Analytical comparison (Beta)",
        )
    top.plot(
        result.time_s,
        result.diffusivity_mm2_s,
        color="tab:blue",
        lw=1.6,
        zorder=5,
        label="Numerical inverse" if result.solver_mode != "analytical" else "Analytical inversion (Beta)",
    )
    start, end = _evaluation_span(result)
    if start is not None:
        top.axvspan(start, end, color=GREEN, alpha=0.25, label="Accepted interval")
    selected = result.evaluation.get("D_CGHE_mm2_s") if result.evaluation else None
    if selected is not None:
        top.axhline(selected, color=GREEN, lw=1.0, ls="--")
        if start is not None and end is not None:
            time_span = float(np.max(result.time_s) - np.min(result.time_s))
            annotation_x = end + 0.015 * time_span
            annotation_transform = top.get_xaxis_transform()
            annotation_alignment = "left"
        else:
            annotation_x = 0.98
            annotation_transform = top.transAxes
            annotation_alignment = "right"
        top.text(
            annotation_x,
            0.78,
            rf"$D_{{\mathrm{{CGHE}}}} = {selected:.4g}\ \mathrm{{mm^2/s}}$",
            ha=annotation_alignment,
            va="center",
            transform=annotation_transform,
            fontsize=17,
            fontweight="bold",
            color="#1b5e20",
            zorder=8,
            bbox={"boxstyle": "round,pad=0.3", "facecolor": "white", "edgecolor": GREEN, "alpha": 0.82},
        )
    top.set_ylabel("D [mm²/s]")
    top.grid(alpha=0.25)
    top.legend(loc="best")
    bottom.plot(
        result.time_s,
        result.remaining_target,
        color="black",
        lw=1.2,
        label=r"Measured Remaining Hydrogen $R_H$",
    )
    bottom.plot(
        result.time_s,
        result.remaining_simulated,
        color="tab:red",
        lw=1.0,
        ls="--",
        label=r"Simulated Remaining Hydrogen $R_{H,\mathrm{sim}}$",
    )
    if start is not None:
        bottom.axvspan(start, end, color=GREEN, alpha=0.25)
    bottom.set_xlabel("Time [s]")
    bottom.set_ylabel("Remaining Hydrogen Fraction")
    bottom.set_ylim(-0.02, 1.02)
    bottom.grid(alpha=0.25)
    bottom.legend(loc="best")
    figure.suptitle("CGHE diffusivity result", fontsize=14)
    return figure


def build_all_figures(result: AnalysisResult, concentration_indices=None) -> dict[str, Figure]:
    return {
        "main_result": build_result_figure(result),
        "diagnostic_dashboard": build_dashboard(result),
        "concentration_cutaways": build_concentration_cutaways(result, concentration_indices),
    }
