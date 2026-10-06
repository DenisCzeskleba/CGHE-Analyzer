"""Automatic and manual CGHE evaluation-window selection."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from cghe_types import EvaluationSettings


def _metrics(r_grid, d_grid, time_grid, upper, lower, settings):
    mask = (
        (r_grid <= upper + 1e-12)
        & (r_grid >= lower - 1e-12)
        & (time_grid >= settings.minimum_time_s)
        & np.isfinite(d_grid)
        & (d_grid > 0.0)
    )
    if np.count_nonzero(mask) < 30:
        return None
    r, diffusivity, time = r_grid[mask], d_grid[mask], time_grid[mask]
    median = float(np.median(diffusivity))
    p10, p90 = np.percentile(diffusivity, [10, 90])
    slope = float(np.polyfit(r, diffusivity, 1)[0])
    spread = float((p90 - p10) / median)
    drift = float(abs(slope) * (upper - lower) / median)
    return {
        "score": spread + 0.75 * drift,
        "median": median,
        "p10": float(p10),
        "p90": float(p90),
        "mad": float(np.median(np.abs(diffusivity - median))),
        "relative_spread": spread,
        "relative_drift": drift,
        "time_start": float(np.min(time)),
        "time_end": float(np.max(time)),
        "n_grid": int(np.count_nonzero(mask)),
    }


def select_evaluation_window(time, diffusivity, remaining, settings: EvaluationSettings, override=None):
    time = np.asarray(time)
    diffusivity = np.asarray(diffusivity)
    remaining = np.asarray(remaining)
    valid = np.isfinite(time) & np.isfinite(diffusivity) & np.isfinite(remaining) & (diffusivity > 0)
    time, diffusivity, remaining = time[valid], diffusivity[valid], remaining[valid]
    order = np.argsort(remaining)
    unique_r, unique_indices = np.unique(remaining[order], return_index=True)
    d_sorted = diffusivity[order][unique_indices]
    t_sorted = time[order][unique_indices]
    r_grid = np.linspace(settings.reliable_lower, settings.reliable_upper, 451)
    d_grid = np.interp(r_grid, unique_r, d_sorted)
    t_grid = np.interp(r_grid, unique_r, t_sorted)
    d_grid = pd.Series(d_grid).rolling(9, center=True, min_periods=1).median().to_numpy()

    candidates = []
    for upper in np.arange(
        settings.reliable_upper,
        settings.reliable_lower + settings.window_width - 1e-9,
        -0.01,
    ):
        lower = float(upper - settings.window_width)
        values = _metrics(r_grid, d_grid, t_grid, float(upper), lower, settings)
        if values is not None:
            candidates.append((float(upper), lower, values))
    if not candidates:
        raise RuntimeError("No eligible inverse-D selection window.")
    if override is None:
        best_score = min(candidate[2]["score"] for candidate in candidates)
        near = [candidate for candidate in candidates if candidate[2]["score"] <= best_score * 1.08 + 1e-9]
        upper, lower, values = max(near, key=lambda candidate: candidate[2]["median"])
        mode = "automatic flattest remaining-hydrogen window"
    else:
        upper, lower = max(override), min(override)
        values = _metrics(r_grid, d_grid, t_grid, upper, lower, settings)
        if values is None:
            raise ValueError("The selected evaluation interval contains insufficient reliable data.")
        mode = "manual reviewed window"
    selected = (
        (remaining <= upper + 1e-12)
        & (remaining >= lower - 1e-12)
        & (time >= settings.minimum_time_s)
        & (diffusivity > 0)
    )
    selected_d = diffusivity[selected]
    selected_time = time[selected]
    selected_r = remaining[selected]
    median = float(np.median(selected_d))
    p10, p90 = np.percentile(selected_d, [10, 90])
    if values["relative_spread"] <= 0.05 and values["relative_drift"] <= 0.08:
        quality = "excellent"
    elif values["relative_spread"] <= 0.10 and values["relative_drift"] <= 0.15:
        quality = "good"
    elif values["relative_spread"] <= 0.20 and values["relative_drift"] <= 0.30:
        quality = "usable"
    else:
        quality = "review"
    return {
        "D_CGHE_mm2_s": median,
        "p10_mm2_s": float(p10),
        "p90_mm2_s": float(p90),
        "relative_spread": float((p90 - p10) / median),
        "relative_drift": values["relative_drift"],
        "selection_R_upper": float(upper),
        "selection_R_lower": float(lower),
        "selection_time_start_s": float(np.min(selected_time)),
        "selection_time_end_s": float(np.max(selected_time)),
        "selection_R_mid": float(np.median(selected_r)),
        "selection_quality": quality,
        "selection_touches_reliable_boundary": bool(
            math.isclose(upper, settings.reliable_upper, abs_tol=0.006)
            or math.isclose(lower, settings.reliable_lower, abs_tol=0.006)
        ),
        "selection_mode": mode,
    }


def select_window_from_time(time, diffusivity, remaining, settings, start_s, end_s):
    start_s, end_s = sorted((float(start_s), float(end_s)))
    upper = float(np.interp(start_s, time, remaining))
    lower = float(np.interp(end_s, time, remaining))
    return select_evaluation_window(time, diffusivity, remaining, settings, (upper, lower))
