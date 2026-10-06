"""Measurement import and preview support for CGHE Analyzer."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Iterable

import numpy as np

from cghe_types import ImportSettings, MeasurementData


def _number(value: str, decimal: str = "auto") -> float:
    text = value.strip().replace("\u2212", "-")
    if decimal == "," or (decimal == "auto" and "," in text and "." not in text):
        text = text.replace(".", "").replace(",", ".")
    return float(text)


def _detect_delimiter(lines: Iterable[str]) -> str:
    sample = "\n".join(list(lines)[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=";\t,|").delimiter
    except csv.Error:
        scores = {delimiter: sample.count(delimiter) for delimiter in ("\t", ";", ",", "|")}
        return max(scores, key=scores.get)


def _apply_baseline_and_delay(
    source_name: str,
    raw_time: np.ndarray,
    raw_signal: np.ndarray,
    mapping: dict,
    settings: ImportSettings,
) -> MeasurementData:
    valid = np.isfinite(raw_time) & np.isfinite(raw_signal)
    raw_time = np.asarray(raw_time[valid], dtype=float)
    raw_signal = np.asarray(raw_signal[valid], dtype=float)
    if len(raw_time) < 3:
        raise ValueError("The measurement must contain at least three numeric samples.")
    order = np.argsort(raw_time, kind="stable")
    raw_time = raw_time[order]
    raw_signal = raw_signal[order]
    unique = np.r_[True, np.diff(raw_time) > 0]
    raw_time = raw_time[unique]
    raw_signal = raw_signal[unique]
    if len(raw_time) < 3:
        raise ValueError("Time values must contain at least three strictly increasing samples.")

    start_time = raw_time[0] + max(0.0, settings.detector_delay_s)
    delayed = raw_time >= start_time - 1e-12
    if np.count_nonzero(delayed) < 3:
        raise ValueError("Detector delay removes the complete measurement.")
    time = raw_time[delayed] - raw_time[delayed][0]
    signal = raw_signal[delayed].copy()

    if settings.baseline_mode == "subtract_minimum":
        baseline = float(np.min(signal))
    elif settings.baseline_mode == "fixed":
        baseline = float(settings.baseline_value)
    elif settings.baseline_mode == "selected_range":
        mask = (time >= settings.baseline_start_s) & (time <= settings.baseline_end_s)
        if not np.any(mask):
            raise ValueError("The selected baseline range contains no samples.")
        baseline = float(np.mean(signal[mask]))
    elif settings.baseline_mode == "none":
        baseline = 0.0
    else:
        raise ValueError(f"Unknown baseline mode: {settings.baseline_mode}")
    signal -= baseline
    mapping = dict(mapping)
    mapping.update({"baseline_mode": settings.baseline_mode, "baseline_value_applied": baseline})
    return MeasurementData(source_name, raw_time, raw_signal, time, signal, mapping)


def _read_bruker(path: Path, settings: ImportSettings) -> MeasurementData:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    rows = list(csv.reader(lines, delimiter=";"))
    header = next((i for i, row in enumerate(rows) if row and row[0].strip() == "Detector:"), None)
    if header is None:
        raise ValueError("No Bruker Detector header was found.")
    values = []
    for row in rows[header + 1 :]:
        if len(row) <= 6 or not row[6].strip():
            continue
        try:
            values.append(_number(row[6], "auto"))
        except ValueError:
            continue
    signal = np.asarray(values, dtype=float)
    time = np.arange(len(signal), dtype=float) / settings.sampling_hz
    return _apply_baseline_and_delay(
        path.name, time, signal,
        {"format": "bruker_csv", "delimiter": ";", "time_column": None, "signal_column": 6,
         "header_rows": header + 1, "sampling_hz": settings.sampling_hz},
        settings,
    )


def _read_new_ms(path: Path, settings: ImportSettings) -> MeasurementData:
    lines = path.read_text(encoding="latin1", errors="replace").splitlines()
    metadata = dict(zip(lines[0].split("\t"), lines[1].split("\t"))) if len(lines) >= 2 else {}
    header = next((i for i, line in enumerate(lines) if line.startswith("Time [s]\t")), None)
    if header is None:
        raise ValueError("No replacement-MS time-series header was found.")
    fields = lines[header].split("\t")
    time_index = fields.index("Time [s]")
    signal_label = "Smoothed Data" if "Smoothed Data" in fields else "Raw Data"
    signal_index = fields.index(signal_label)
    baseline_time_index = fields.index("Time Baseline/Peak [s]") if "Time Baseline/Peak [s]" in fields else None
    baseline_index = fields.index("Baseline") if "Baseline" in fields else None
    times, signals, baseline_times, baselines = [], [], [], []
    for line in lines[header + 1 :]:
        parts = line.split("\t")
        try:
            times.append(_number(parts[time_index], ","))
            signals.append(_number(parts[signal_index], ","))
        except (IndexError, ValueError):
            continue
        if baseline_time_index is not None and baseline_index is not None:
            try:
                baseline_times.append(_number(parts[baseline_time_index], ","))
                baselines.append(_number(parts[baseline_index], ","))
            except (IndexError, ValueError):
                pass
    time = np.asarray(times, dtype=float)
    signal = np.asarray(signals, dtype=float)
    if baseline_times and settings.baseline_mode == "subtract_minimum":
        signal = np.maximum(signal - np.interp(time, baseline_times, baselines), 0.0)
        try:
            integration_start = _number(metadata["Startpoint [s]"], ",")
            integration_end = _number(metadata["Endpoint [s]"], ",")
            signal[(time < integration_start) | (time > integration_end)] = 0.0
        except (KeyError, ValueError):
            pass
    local_settings = settings
    return _apply_baseline_and_delay(
        path.name, time, signal,
        {"format": "new_ms_tab", "delimiter": "tab", "time_column": time_index,
         "signal_column": signal_index, "signal_label": signal_label, "header_rows": header + 1},
        local_settings,
    )


def _select_column(spec: str, header: list[str] | None, default: int | None) -> int | None:
    text = str(spec).strip()
    if text.lower() == "none":
        return None
    if text.lower() in {"", "auto"}:
        return default
    try:
        return int(text)
    except ValueError:
        if header is None:
            raise ValueError(f"Column name '{text}' requires a header row.")
        normalized = [name.strip().casefold() for name in header]
        if text.casefold() not in normalized:
            raise ValueError(f"Column '{text}' is not present. Available columns: {header}")
        return normalized.index(text.casefold())


def parse_table_text(text: str, settings: ImportSettings, source_name: str = "Clipboard") -> MeasurementData:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("No table data was supplied.")
    delimiter = _detect_delimiter(lines) if settings.delimiter == "auto" else settings.delimiter
    if delimiter == "\\t":
        delimiter = "\t"
    rows = list(csv.reader(StringIO("\n".join(lines)), delimiter=delimiter))
    header_rows = settings.header_rows
    header: list[str] | None = None
    if header_rows < 0:
        try:
            [_number(value, settings.decimal) for value in rows[0][:2]]
            header_rows = 0
        except (ValueError, IndexError):
            header_rows = 1
    if header_rows:
        header = [value.strip() for value in rows[header_rows - 1]]
    data_rows = rows[header_rows:]
    time_index = _select_column(settings.time_column, header, 0)
    signal_index = _select_column(settings.signal_column, header, 1 if time_index == 0 else 0)
    if signal_index is None:
        raise ValueError("A signal column is required.")
    times, signals = [], []
    for index, row in enumerate(data_rows):
        try:
            signal = _number(row[signal_index], settings.decimal)
            time = index / settings.sampling_hz if time_index is None else _number(row[time_index], settings.decimal)
        except (IndexError, ValueError):
            continue
        times.append(time)
        signals.append(signal)
    return _apply_baseline_and_delay(
        source_name, np.asarray(times), np.asarray(signals),
        {"format": "generic_table", "delimiter": delimiter, "decimal": settings.decimal,
         "header_rows": header_rows, "time_column": time_index, "signal_column": signal_index,
         "sampling_hz": settings.sampling_hz},
        settings,
    )


def load_measurement(path: str | Path, settings: ImportSettings) -> MeasurementData:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    format_name = settings.format.casefold()
    head = path.read_text(encoding="utf-8-sig", errors="replace")[:65536]
    if format_name == "auto":
        if "Converted replacement-MS export" in head or "Experiment:;NEWMS_2025" in head:
            format_name = "new_ms_converted_csv"
        elif "Time [s]\t" in head and ("Smoothed Data" in head or "Raw Data" in head):
            format_name = "new_ms_tab"
        elif "Detector:" in head and "Hydrogen" in head:
            format_name = "bruker_csv"
        else:
            format_name = "generic"
    if format_name == "bruker_csv":
        return _read_bruker(path, settings)
    if format_name == "new_ms_converted_csv":
        measurement = _read_bruker(path, settings)
        measurement.mapping["format"] = "new_ms_converted_csv"
        measurement.mapping["signal_label"] = "Baseline-corrected Smoothed Data"
        return measurement
    if format_name == "new_ms_tab":
        return _read_new_ms(path, settings)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return parse_table_text(text, settings, path.name)
