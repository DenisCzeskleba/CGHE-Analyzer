"""Legacy-compatible signal conditioning and remaining-hydrogen calculation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from lmfit import Model
from scipy.integrate import cumulative_trapezoid
from scipy.interpolate import interp1d
from sklearn.isotonic import IsotonicRegression

from cghe_types import MeasurementData, PreprocessingSettings, ProcessedMeasurement


LEGACY_ROLLING_SPAN_SAMPLES = 21
LEGACY_ROLLING_PASSES = 2
LEGACY_TAIL_START_MULTIPLIER = 1.7


def resolve_processing_mode(
    measurement: MeasurementData, settings: PreprocessingSettings
) -> tuple[str, str]:
    """Resolve Auto from importer evidence, falling back safely to the TCD pipeline."""
    requested = settings.signal_processing_mode.casefold()
    if requested == "direct":
        return "direct", "Direct processing was selected explicitly."
    if requested == "tcd":
        return "tcd", "TCD smoothing was selected explicitly."
    if requested != "auto":
        raise ValueError(f"Unknown signal processing mode: {settings.signal_processing_mode}")
    format_name = str(measurement.mapping.get("format", "")).casefold()
    if format_name in {"new_ms_tab", "new_ms_converted_csv"}:
        return "direct", "Detected replacement-MS content; the exported smoothed signal is used directly."
    if format_name == "bruker_csv":
        return "tcd", "Detected a Bruker detector/hydrogen header; legacy TCD smoothing is applied."
    return "tcd", "The input format is generic or unrecognized; Auto falls back to legacy TCD smoothing."


def _tail_start(time: np.ndarray, peak_index: int, multiplier: float) -> int:
    target = time[peak_index] * multiplier
    found = np.flatnonzero((np.arange(len(time)) > peak_index) & (time >= target))
    return int(found[0]) if len(found) else len(time) - 1


def _fit_tail(signal: np.ndarray, time: np.ndarray, start: int, mode: str):
    values = signal.copy()
    if mode == "none" or start >= len(values) - 2 or start < 1:
        return values, None
    t_tail = time[start:]
    y_tail = values[start:]
    t0, y0 = t_tail[0], y_tail[0]
    if mode == "single":
        def single_exp(t, A, tau):
            return y0 * np.exp(-(t - t0) / tau)
        model = Model(single_exp)
        params = model.make_params(A=y0, tau=(t_tail[-1] - t_tail[0]) / 5)
    elif mode == "double":
        def double_exp(t, A1, tau1, A2, tau2):
            return y0 * (A1 * np.exp(-(t - t0) / tau1) + A2 * np.exp(-(t - t0) / tau2))
        model = Model(double_exp)
        params = model.make_params(
            A1=0.5, tau1=(t_tail[-1] - t_tail[0]) / 5,
            A2=0.5, tau2=(t_tail[-1] - t_tail[0]) / 2,
        )
        params["A1"].set(min=0, max=1)
        params["A2"].set(min=0, max=1)
    else:
        raise ValueError(f"Unknown tail fit mode: {mode}")
    try:
        result = model.fit(y_tail, params, t=t_tail)
    except Exception as exc:
        raise RuntimeError(f"Exponential tail fit failed: {exc}") from exc
    fitted = np.maximum(result.best_fit, 0.0)
    values[start:] = fitted
    return values, {name: float(value) for name, value in result.best_values.items()}


def preprocess_measurement(
    measurement: MeasurementData,
    settings: PreprocessingSettings,
    simulation_dt_s: float,
) -> ProcessedMeasurement:
    if simulation_dt_s <= 0:
        raise ValueError("Simulation timestep must be positive.")
    time_original = measurement.time_s
    signal_original = measurement.signal
    if len(time_original) < 3 or time_original[-1] <= 0:
        raise ValueError("Measurement duration is too short.")
    sample_dt = float(np.median(np.diff(time_original)))
    regularly_sampled = np.allclose(np.diff(time_original), sample_dt, rtol=1e-8, atol=1e-10)
    if regularly_sampled:
        sample_dt = round(sample_dt, 12)
    # Preserve the legacy regularly sampled axis exactly.  In the PhD script the
    # time vector was rebuilt with ``arange(n) / sampling_hz``; that final binary
    # floating-point value can admit one additional simulation sample.
    duration = time_original[-1]
    if regularly_sampled:
        duration = sample_dt * (len(time_original) - 1)
    upsampled_time = np.arange(0.0, duration, simulation_dt_s)
    if len(upsampled_time) < 3:
        raise ValueError("Simulation timestep is too large for this measurement.")
    signal = interp1d(time_original, signal_original, kind="linear", fill_value="extrapolate")(upsampled_time)
    resolved_mode, processing_reason = resolve_processing_mode(measurement, settings)
    if resolved_mode == "direct":
        rolling_copy = signal.copy()
        isotonic_copy = signal.copy()
        processed = signal.copy()
        fit = None
    else:
        method = settings.tcd_smoothing_method.casefold()
        if method == "legacy_multistep":
            rolling_span = LEGACY_ROLLING_SPAN_SAMPLES
            rolling_passes = LEGACY_ROLLING_PASSES
            isotonic_decay = True
            tail_mode = "double"
            tail_multiplier = LEGACY_TAIL_START_MULTIPLIER
        elif method == "custom":
            rolling_span = settings.rolling_span_samples
            rolling_passes = settings.rolling_pass_count
            isotonic_decay = settings.isotonic_decay
            tail_mode = settings.tail_mode
            tail_multiplier = settings.tail_start_multiplier
        else:
            raise ValueError(f"Unknown TCD smoothing method: {settings.tcd_smoothing_method}")
        if rolling_passes < 0:
            raise ValueError("Rolling-pass count cannot be negative.")
        window = max(1, int(rolling_span * sample_dt / simulation_dt_s))
        if window >= len(signal):
            raise ValueError("Rolling span is longer than the delayed measurement.")
        rolling = signal.copy()
        for _ in range(rolling_passes):
            rolling = pd.Series(rolling).rolling(window=window, center=True).mean().to_numpy()
            half = window // 2
            if half:
                rolling[:half] = rolling[half]
                rolling[-half:] = rolling[-half - 1]
        rolling_copy = rolling.copy()
        peak_index = int(np.argmax(rolling))
        if isotonic_decay:
            rolling[peak_index:] = IsotonicRegression(increasing=False).fit_transform(
                upsampled_time[peak_index:], rolling[peak_index:]
            )
        isotonic_copy = rolling.copy()
        start = _tail_start(upsampled_time, peak_index, tail_multiplier)
        processed, fit = _fit_tail(rolling, upsampled_time, start, tail_mode)
    cumulative = cumulative_trapezoid(processed, dx=simulation_dt_s, initial=0.0)
    total = float(cumulative[-1])
    if not np.isfinite(total) or total <= 0:
        raise ValueError("Processed signal integral must be positive.")
    remaining = 1.0 - cumulative / total
    stop = np.flatnonzero(remaining <= settings.stop_fraction)
    stop_index = int(stop[0]) if len(stop) else len(remaining) - 1
    section = slice(0, stop_index + 1)
    return ProcessedMeasurement(
        measurement=measurement,
        time_s=upsampled_time[section],
        signal_interpolated=signal[section],
        signal_rolling=rolling_copy[section],
        signal_isotonic=isotonic_copy[section],
        signal_processed=processed[section],
        cumulative_release=cumulative[section],
        remaining_target=remaining[section],
        tail_fit=fit,
        requested_processing_mode=settings.signal_processing_mode,
        resolved_processing_mode=resolved_mode,
        processing_reason=processing_reason,
        full_time_s=upsampled_time,
        full_signal_processed=processed,
        full_remaining_target=remaining,
    )
