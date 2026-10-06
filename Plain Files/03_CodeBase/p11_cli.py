"""CGHE Analyzer command-line interface for single and batch inverse analyses."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
import sys

from cghe_analysis import estimate_result_bytes, run_batch
from cghe_import import load_measurement
from cghe_types import AnalysisSettings
from p11_run import build_default_settings


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = PROJECT_DIR / "02_Results"


def _settings(path, solver):
    settings = build_default_settings()
    if path:
        settings = AnalysisSettings.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    if solver:
        settings.solver.mode = solver
    return settings


def _paths(arguments):
    paths = []
    for value in arguments.inputs:
        matches = glob.glob(value)
        paths.extend(Path(match) for match in (matches or [value]))
    if arguments.manifest:
        values = json.loads(Path(arguments.manifest).read_text(encoding="utf-8"))
        entries = values.get("inputs", values) if isinstance(values, dict) else values
        paths.extend(Path(value) for value in entries)
    unique = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", help="Measurement files or glob patterns")
    parser.add_argument("--manifest", type=Path, help="JSON list or {'inputs': [...]} batch manifest")
    parser.add_argument("--settings", type=Path, help="AnalysisSettings JSON file")
    parser.add_argument("--solver", choices=["axisymmetric", "full_3d", "analytical"])
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--gui", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.gui:
        from p11_gui import launch_gui
        return launch_gui()
    paths = _paths(arguments)
    if not paths:
        parser.error("Supply at least one input, a manifest, or --gui.")
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        parser.error("Input files not found: " + ", ".join(missing))
    settings = _settings(arguments.settings, arguments.solver)
    estimates = []
    for path in paths:
        measurement = load_measurement(path, settings.import_settings)
        estimates.append(estimate_result_bytes(settings, len(measurement.raw_time_s), measurement.time_s[-1]))
    for path, estimate in zip(paths, estimates):
        suffix = " WARNING >500 MB" if estimate > 500 * 1024**2 else ""
        print(f"{path.name}: estimated {estimate / 1024**2:.1f} MB{suffix}")
    total = sum(estimates)
    print(f"Batch total: {total / 1024**3:.2f} GB" + (" WARNING >5 GB" if total > 5 * 1024**3 else ""))
    if arguments.estimate_only:
        return 0
    arguments.output_dir.mkdir(parents=True, exist_ok=True)

    def progress(fraction, message):
        print(f"[{fraction * 100:6.2f}%] {message}", flush=True)
    try:
        results, errors = run_batch(paths, settings, arguments.output_dir, progress)
    except KeyboardInterrupt:
        print("Cancelled by user.", file=sys.stderr)
        return 130
    for result in results:
        print(f"Saved: {result.result_path}")
    for path, message in errors:
        print(f"FAILED {path}: {message}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
