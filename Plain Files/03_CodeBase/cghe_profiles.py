"""Local GUI-state and user-profile persistence for the CGHE analyzer."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from cghe_types import AnalysisSettings


def load_runtime_state(path: str | Path, defaults: AnalysisSettings | None = None):
    path = Path(path)
    defaults = deepcopy(defaults) if defaults is not None else AnalysisSettings()
    if not path.exists():
        return defaults, {}, {}
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
        settings = AnalysisSettings.from_dict(values.get("last_settings", {}))
        profiles = {
            str(name): AnalysisSettings.from_dict(profile)
            for name, profile in values.get("profiles", {}).items()
            if name != "Default"
        }
        gui_state = dict(values.get("gui_state", {}))
        return settings, profiles, gui_state
    except Exception as exc:
        raise ValueError(f"Could not read CGHE Analyzer runtime settings: {exc}") from exc


def save_runtime_state(path, settings, profiles, gui_state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "last_settings": settings.to_dict(),
        "profiles": {name: profile.to_dict() for name, profile in profiles.items() if name != "Default"},
        "gui_state": gui_state,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(values, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def profile_choices(profiles, defaults: AnalysisSettings | None = None):
    default_settings = deepcopy(defaults) if defaults is not None else AnalysisSettings()
    return {"Default": default_settings, **{name: deepcopy(value) for name, value in profiles.items()}}
