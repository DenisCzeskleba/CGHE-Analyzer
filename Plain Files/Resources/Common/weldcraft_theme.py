"""Shared visual theme support for the WeldCraft desktop applications.

The theme deliberately uses only Qt facilities so every source and frozen
application keeps the same dependency footprint.  Applications read the
selected theme from a suite-wide QSettings entry; the launcher is the place
where users change that preference.
"""

from __future__ import annotations

import os
from copy import deepcopy

from PyQt5 import QtCore, QtGui, QtNetwork, QtWidgets


THEME_ENV_VAR = "WELDCRAFT_THEME"
THEME_CHANNEL_ENV_VAR = "WELDCRAFT_THEME_CHANNEL"
DEFAULT_THEME = "steel"
THEME_CHOOSER_VERSION = 1
THEME_CHOOSER_VERSION_KEY = "onboarding/theme_chooser_version"


THEMES = {
    "basic": {
        "name": "Basic Shmasic",
        "description": "The compact original-style launcher and native Qt controls, with no WeldCraft color treatment applied.",
        "dark": False,
        "native": True,
        "launcher_layout": "basic",
    },
    "steel": {
        "name": "WeldCraft",
        "description": "A modern blue-steel treatment drawn from the WeldCraft emblem, with restrained copper-orange active states.",
        "dark": True,
        "native": False,
        "launcher_layout": "steel",
        "window": "#1B2128",
        "surface": "#222A33",
        "surface_alt": "#293440",
        "surface_hover": "#334253",
        "surface_pressed": "#2A3745",
        "surface_disabled": "#20272F",
        "text": "#E9EDF1",
        "text_muted": "#A6ADB5",
        "text_disabled": "#707983",
        "border": "#3B4B5D",
        "border_strong": "#526A84",
        "primary": "#40699C",
        "heading": "#F4F5F6",
        "brand": "#202833",
        "brand_border": "#40699C",
        "primary_hover": "#527FB4",
        "primary_pressed": "#31547F",
        "primary_text": "#FFFFFF",
        "accent": "#C8793E",
        "accent_hover": "#DA8C4F",
        "accent_pressed": "#A86131",
        "accent_text": "#15191D",
        "active": "#C8793E",
        "active_text": "#15191D",
        "violet": "#40699C",
        "violet_hover": "#5A82B3",
        "violet_soft": "#273548",
        "selection_text": "#FFFFFF",
        "info_bg": "#222A33",
        "info_border": "#3B4B5D",
        "success": "#71AE8A",
        "success_bg": "#21382C",
        "warning": "#E2AD6B",
        "warning_bg": "#403225",
        "error": "#EA7B9D",
        "error_bg": "#432631",
        "rail_start": "#31547F",
        "rail_middle": "#40699C",
        "rail_end": "#B8C4CF",
        "radius": "2px",
        "panel_radius": "3px",
        "module_radius": "2px",
    },
    "violet": {
        "name": "Smoke on the Water",
        "description": "A softer studio treatment with its own two-column launcher, layered lavender, muted amethyst, and restrained violet accents.",
        "dark": False,
        "native": False,
        "launcher_layout": "violet",
        "window": "#F4F2F5",
        "surface": "#FFFFFF",
        "surface_alt": "#ECE7EF",
        "surface_hover": "#E4DCE8",
        "surface_pressed": "#D9CEDF",
        "surface_disabled": "#ECEAEC",
        "text": "#28232B",
        "text_muted": "#6E6572",
        "text_disabled": "#9C959E",
        "border": "#C9C0CC",
        "border_strong": "#A897AD",
        "primary": "#65466E",
        "heading": "#65466E",
        "brand": "#65466E",
        "brand_border": "#4D3554",
        "primary_hover": "#795582",
        "primary_pressed": "#4D3554",
        "primary_text": "#FFFFFF",
        "accent": "#73507C",
        "accent_hover": "#896494",
        "accent_pressed": "#4D3554",
        "active": "#73507C",
        "violet": "#73507C",
        "violet_hover": "#896494",
        "violet_soft": "#E8E0ED",
        "selection_text": "#FFFFFF",
        "info_bg": "#E8EFF4",
        "info_border": "#7895AA",
        "success": "#477255",
        "success_bg": "#E7F0E8",
        "warning": "#956026",
        "warning_bg": "#F9EEDC",
        "error": "#C0003C",
        "error_bg": "#F6E5E7",
        "rail_start": "#4D3554",
        "rail_middle": "#73507C",
        "rail_end": "#B99AC3",
        "radius": "6px",
        "panel_radius": "8px",
        "module_radius": "7px",
    },
    "bam": {
        "name": "Institutional",
        "description": "A restrained institutional treatment built from BAM's exact coral, dark-blue, cyan, and wordmark colors on cool neutral surfaces.",
        "dark": False,
        "native": False,
        "launcher_layout": "institutional",
        "window": "#F4F5F6",
        "surface": "#FFFFFF",
        "surface_alt": "#EEF1F2",
        "surface_hover": "#DDECF1",
        "surface_pressed": "#D4E0E4",
        "surface_disabled": "#ECEFF0",
        "text": "#002831",
        "text_muted": "#526268",
        "text_disabled": "#98A2A5",
        "border": "#C2CDD1",
        "border_strong": "#7E969E",
        "primary": "#00546D",
        "heading": "#002831",
        "brand": "#FFFFFF",
        "brand_border": "#00546D",
        "primary_hover": "#006D8C",
        "primary_pressed": "#003F52",
        "primary_text": "#FFFFFF",
        "accent": "#00546D",
        "accent_hover": "#006D8C",
        "accent_pressed": "#003F52",
        "active": "#00546D",
        "violet": "#00546D",
        "violet_hover": "#006D8C",
        "violet_soft": "#DDECF1",
        "interaction_accent": "#00AEEF",
        "interaction_accent_hover": "#25B9F1",
        "tab_accent": "#00AEEF",
        "selection_text": "#FFFFFF",
        "info_bg": "#FFFFFF",
        "info_border": "#C2CDD1",
        "success": "#00854A",
        "success_bg": "#E4F2EA",
        "warning": "#8A5A00",
        "warning_bg": "#FFF4CF",
        "error": "#D2001E",
        "error_bg": "#FBE8EB",
        "rail_start": "#D2001E",
        "rail_middle": "#00546D",
        "rail_end": "#00AEEF",
        "slider_fill": "#00AEEF",
        "slider_handle": "#00546D",
        "slider_handle_hover": "#006D8C",
        "outline_secondary_actions": True,
        "radius": "1px",
        "panel_radius": "1px",
        "module_radius": "0px",
    },
}


THEME_ALIASES = {
    "forge": "steel",
    "smoke": "violet",
    "smoke on the water": "violet",
    "institutional": "bam",
    "bam colors": "bam",
}

THEME_DISPLAY_ORDER = ("basic", "steel", "violet", "bam")


def available_themes():
    """Return independent theme dictionaries in their display order."""

    return [(key, deepcopy(THEMES[key])) for key in THEME_DISPLAY_ORDER]


def normalize_theme_name(name):
    name = THEME_ALIASES.get(name, name)
    return name if name in THEMES else DEFAULT_THEME


def current_theme_name():
    override = os.environ.get(THEME_ENV_VAR, "").strip().lower()
    if override:
        return normalize_theme_name(override)
    settings = QtCore.QSettings("WeldCraft", "Appearance")
    settings.sync()
    return normalize_theme_name(str(settings.value("theme", DEFAULT_THEME)))


def set_current_theme(name):
    name = normalize_theme_name(name)
    settings = QtCore.QSettings("WeldCraft", "Appearance")
    settings.setValue("theme", name)
    settings.sync()
    return name


def theme_chooser_needed():
    """Return whether this user profile still needs the first-run theme choice."""

    settings = QtCore.QSettings("WeldCraft", "Appearance")
    settings.sync()
    try:
        completed_version = int(settings.value(THEME_CHOOSER_VERSION_KEY, 0))
    except (TypeError, ValueError):
        completed_version = 0
    if completed_version >= THEME_CHOOSER_VERSION:
        return False

    # Anyone who already chose a theme predates the welcome screen and should
    # not be interrupted by it after updating WeldCraft.
    if settings.contains("theme"):
        settings.setValue(THEME_CHOOSER_VERSION_KEY, THEME_CHOOSER_VERSION)
        settings.sync()
        return False
    return True


def complete_theme_chooser(name=None):
    """Persist the first-run choice outside the shipped application files."""

    if name is not None:
        set_current_theme(name)
    settings = QtCore.QSettings("WeldCraft", "Appearance")
    settings.setValue(THEME_CHOOSER_VERSION_KEY, THEME_CHOOSER_VERSION)
    settings.sync()


def theme_colors(name=None):
    return deepcopy(THEMES[normalize_theme_name(name or current_theme_name())])


class _WeldCraftStyle(QtWidgets.QProxyStyle):
    """Fusion style with a palette-driven checked indicator."""

    def __init__(self):
        super().__init__("Fusion")

    def drawPrimitive(self, element, option, painter, widget=None):
        if element != QtWidgets.QStyle.PE_IndicatorCheckBox or not (
            option.state & (QtWidgets.QStyle.State_On | QtWidgets.QStyle.State_NoChange)
        ):
            return super().drawPrimitive(element, option, painter, widget)

        rect = option.rect.adjusted(1, 1, -1, -1)
        fill = option.palette.color(QtGui.QPalette.Highlight)
        if option.state & QtWidgets.QStyle.State_MouseOver:
            fill = fill.lighter(112)
        border = fill.darker(118)
        mark = option.palette.color(QtGui.QPalette.HighlightedText)

        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtGui.QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(QtCore.QRectF(rect), 2, 2)

        pen = QtGui.QPen(mark, 2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)
        if option.state & QtWidgets.QStyle.State_NoChange:
            y = rect.center().y()
            painter.drawLine(rect.left() + 3, y, rect.right() - 3, y)
        else:
            path = QtGui.QPainterPath()
            path.moveTo(rect.left() + (rect.width() * 0.20), rect.top() + (rect.height() * 0.53))
            path.lineTo(rect.left() + (rect.width() * 0.43), rect.top() + (rect.height() * 0.75))
            path.lineTo(rect.left() + (rect.width() * 0.82), rect.top() + (rect.height() * 0.27))
            painter.drawPath(path)
        painter.restore()


def _palette(colors):
    palette = QtGui.QPalette()
    active = QtGui.QPalette.Active
    inactive = QtGui.QPalette.Inactive
    disabled = QtGui.QPalette.Disabled

    role_colors = {
        QtGui.QPalette.Window: colors["window"],
        QtGui.QPalette.WindowText: colors["text"],
        QtGui.QPalette.Base: colors["surface"],
        QtGui.QPalette.AlternateBase: colors["surface_alt"],
        QtGui.QPalette.ToolTipBase: colors["surface"],
        QtGui.QPalette.ToolTipText: colors["text"],
        QtGui.QPalette.Text: colors["text"],
        QtGui.QPalette.Button: colors["surface_alt"],
        QtGui.QPalette.ButtonText: colors["text"],
        QtGui.QPalette.BrightText: colors["primary_text"],
        QtGui.QPalette.Highlight: colors.get("active", colors["violet"]),
        QtGui.QPalette.HighlightedText: colors["selection_text"],
        QtGui.QPalette.Link: colors["primary_hover"],
    }
    for group in (active, inactive):
        for role, value in role_colors.items():
            palette.setColor(group, role, QtGui.QColor(value))

    palette.setColor(disabled, QtGui.QPalette.Window, QtGui.QColor(colors["window"]))
    palette.setColor(disabled, QtGui.QPalette.WindowText, QtGui.QColor(colors["text_disabled"]))
    palette.setColor(disabled, QtGui.QPalette.Base, QtGui.QColor(colors["surface_disabled"]))
    palette.setColor(disabled, QtGui.QPalette.Text, QtGui.QColor(colors["text_disabled"]))
    palette.setColor(disabled, QtGui.QPalette.Button, QtGui.QColor(colors["surface_disabled"]))
    palette.setColor(disabled, QtGui.QPalette.ButtonText, QtGui.QColor(colors["text_disabled"]))
    palette.setColor(disabled, QtGui.QPalette.Highlight, QtGui.QColor(colors["border_strong"]))
    palette.setColor(disabled, QtGui.QPalette.HighlightedText, QtGui.QColor(colors["text_disabled"]))
    return palette


def _blend_hex(base, target, amount):
    """Blend two opaque colors for subtle, theme-relative material tones."""

    base_color = QtGui.QColor(base)
    target_color = QtGui.QColor(target)
    ratio = max(0.0, min(1.0, float(amount)))
    channels = [
        round((1.0 - ratio) * start + ratio * end)
        for start, end in zip(
            (base_color.red(), base_color.green(), base_color.blue()),
            (target_color.red(), target_color.green(), target_color.blue()),
        )
    ]
    return QtGui.QColor(*channels).name()


def _vertical_gradient(top, bottom, middle=None):
    stops = f"stop: 0 {top}, stop: 1 {bottom}"
    if middle is not None:
        stops = f"stop: 0 {top}, stop: 0.52 {middle}, stop: 1 {bottom}"
    return f"qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, {stops})"


def _diagonal_gradient(top_left, bottom_right):
    return (
        "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1, "
        f"stop: 0 {top_left}, stop: 1 {bottom_right})"
    )


def _stylesheet(c):
    # Qt stylesheets support only a CSS subset.  These rules intentionally
    # avoid animation and shadow effects.
    active = c.get("active", c["violet"])
    checked_border = c.get("checked_border", c["violet"])
    interaction_accent = c.get("interaction_accent", c["violet"])
    interaction_accent_hover = c.get("interaction_accent_hover", c["violet_hover"])
    tab_accent = c.get("tab_accent", active)
    slider_fill = c.get("slider_fill", c["primary"])
    slider_handle = c.get("slider_handle", active)
    slider_handle_hover = c.get("slider_handle_hover", c.get("primary_hover", slider_handle))
    accent_text = c.get("accent_text", "#FFFFFF")
    active_text = c.get("active_text", c["selection_text"])
    dark = bool(c.get("dark"))
    arrow_tone = "light" if dark else "dark"
    asset_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Layout").replace("\\", "/")
    arrow_down = f"{asset_dir}/weldcraft_chevron_down_{arrow_tone}.svg"
    arrow_up = f"{asset_dir}/weldcraft_chevron_up_{arrow_tone}.svg"
    lift = 0.075 if dark else 0.035
    depth = 0.10 if dark else 0.045
    soft_lift = 0.045 if dark else 0.02

    window_top = _blend_hex(c["window"], c["primary"], 0.075 if dark else 0.025)
    window_bottom = _blend_hex(c["window"], "#000000", 0.08 if dark else 0.018)
    surface_top = _blend_hex(c["surface"], "#FFFFFF", lift)
    surface_middle = _blend_hex(c["surface"], c["primary"], 0.025)
    surface_bottom = _blend_hex(c["surface"], "#000000", depth)
    alt_top = _blend_hex(c["surface_alt"], "#FFFFFF", soft_lift)
    alt_bottom = _blend_hex(c["surface_alt"], "#000000", depth)
    hover_top = _blend_hex(c["surface_hover"], "#FFFFFF", soft_lift)
    hover_bottom = _blend_hex(c["surface_hover"], c["primary"], 0.08)
    module_top = _blend_hex(c["surface"], c["primary"], 0.075 if dark else 0.035)
    module_bottom = _blend_hex(c["surface"], "#000000", 0.07 if dark else 0.025)
    primary_top = _blend_hex(c["primary"], "#FFFFFF", 0.12)
    primary_bottom = _blend_hex(c["primary"], "#000000", 0.14)
    primary_hover_top = _blend_hex(c["primary_hover"], "#FFFFFF", 0.12)
    primary_hover_bottom = _blend_hex(c["primary_hover"], "#000000", 0.12)
    accent_top = _blend_hex(c["accent"], "#FFFFFF", 0.10)
    accent_depth = 0.075 if QtGui.QColor(accent_text).lightness() < 128 else 0.13
    accent_bottom = _blend_hex(c["accent"], "#000000", accent_depth)
    accent_hover_top = _blend_hex(c["accent_hover"], "#FFFFFF", 0.10)
    accent_hover_bottom = _blend_hex(c["accent_hover"], "#000000", accent_depth)
    active_top = _blend_hex(active, "#FFFFFF", 0.10)
    active_depth = 0.075 if QtGui.QColor(active_text).lightness() < 128 else 0.13
    active_bottom = _blend_hex(active, "#000000", active_depth)
    slider_handle_top = _blend_hex(slider_handle, "#FFFFFF", 0.12)
    slider_handle_bottom = _blend_hex(slider_handle, "#000000", 0.12)
    slider_handle_hover_top = _blend_hex(slider_handle_hover, "#FFFFFF", 0.12)
    slider_handle_hover_bottom = _blend_hex(slider_handle_hover, "#000000", 0.12)
    slider_fill_top = _blend_hex(slider_fill, "#FFFFFF", 0.12)
    slider_fill_bottom = _blend_hex(slider_fill, "#000000", 0.12)
    border_glint = _blend_hex(c["border_strong"], "#FFFFFF", 0.16 if dark else 0.08)
    scroll_top = _blend_hex(c["border_strong"], "#FFFFFF", 0.12)
    scroll_bottom = _blend_hex(c["border_strong"], "#000000", 0.10)
    brand_top = _blend_hex(c["brand"], c["primary"], 0.12)
    brand_bottom = _blend_hex(c["brand"], "#000000", 0.10 if dark else 0.025)

    window_gradient = _diagonal_gradient(window_top, window_bottom)
    panel_gradient = _vertical_gradient(surface_top, surface_bottom, surface_middle)
    control_gradient = _vertical_gradient(alt_top, alt_bottom)
    hover_gradient = _vertical_gradient(hover_top, hover_bottom)
    pressed_gradient = _vertical_gradient(alt_bottom, alt_top)
    module_gradient = _vertical_gradient(module_top, module_bottom)
    primary_gradient = _vertical_gradient(primary_top, primary_bottom)
    primary_hover_gradient = _vertical_gradient(primary_hover_top, primary_hover_bottom)
    accent_gradient = _vertical_gradient(accent_top, accent_bottom)
    accent_hover_gradient = _vertical_gradient(accent_hover_top, accent_hover_bottom)
    active_gradient = _vertical_gradient(active_top, active_bottom)
    slider_handle_gradient = _vertical_gradient(slider_handle_top, slider_handle_bottom)
    slider_handle_hover_gradient = _vertical_gradient(
        slider_handle_hover_top, slider_handle_hover_bottom
    )
    slider_fill_gradient = _vertical_gradient(slider_fill_top, slider_fill_bottom)
    if "slider_handle" not in c:
        slider_handle_gradient = active_gradient
        slider_handle_hover_gradient = active_gradient
    if "slider_fill" not in c:
        slider_fill_gradient = primary_gradient
    scroll_handle_gradient = _vertical_gradient(scroll_top, scroll_bottom)
    brand_gradient = _diagonal_gradient(brand_top, brand_bottom)
    rail_gradient = (
        "qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, "
        f"stop: 0 {c.get('rail_start', c['primary_pressed'])}, "
        f"stop: 0.52 {c.get('rail_middle', c['primary'])}, "
        f"stop: 1 {c.get('rail_end', c['accent'])})"
    )
    outlined_secondary_rules = ""
    if c.get("outline_secondary_actions"):
        outlined_secondary_rules = f"""
        QPushButton[role="primary"][actionVariant="secondary"] {{
            background: transparent;
            color: {c['primary']};
            border: 1px solid {c['primary']};
            font-weight: 600;
        }}
        QPushButton[role="primary"][actionVariant="secondary"]:hover {{
            background: {hover_gradient};
            color: {c['primary_pressed']};
            border-color: {c['primary_hover']};
        }}
        QPushButton[role="primary"][actionVariant="secondary"]:pressed {{
            background: {pressed_gradient};
            color: {c['primary_pressed']};
            border-color: {c['primary_pressed']};
        }}
        QPushButton[role="primary"][actionVariant="secondary"]:disabled {{
            background: transparent;
            color: {c['text_disabled']};
            border-color: {c['border']};
        }}
        """
    return f"""
    QWidget {{
        color: {c['text']};
        font-family: "Segoe UI";
        font-size: 9pt;
    }}
    QMainWindow, QDialog, QWizard {{
        background: {window_gradient};
    }}
    QMainWindow > QWidget, QWidget#centralwidget, QWidget[role="windowSurface"] {{
        background: {window_gradient};
    }}
    QLabel {{
        background: transparent;
    }}
    QLabel[role="pageTitle"] {{
        color: {c['heading']};
        font-size: 19pt;
        font-weight: 600;
    }}
    QLabel[role="sectionTitle"] {{
        color: {c['text']};
        font-size: 12pt;
        font-weight: 600;
    }}
    QLabel[role="launcherTitle"] {{
        color: {c['heading']};
        font-size: 17pt;
        font-weight: 600;
    }}
    QLabel[role="eyebrow"] {{
        color: {c['text_muted']};
        font-size: 8pt;
        font-weight: 600;
    }}
    QLabel[role="activeChoice"] {{
        color: {c['heading']};
        font-weight: 600;
    }}
    QLabel[role="subtitle"], QLabel[role="muted"] {{
        color: {c['text_muted']};
    }}
    QLabel[role="statusSuccess"] {{
        color: {c['success']};
        font-weight: 600;
    }}
    QLabel[role="statusWarning"] {{
        color: {c['warning']};
        font-weight: 600;
    }}
    QLabel[role="statusError"] {{
        color: {c['error']};
        font-weight: 600;
    }}
    QLabel[tone="info"], QFrame[tone="info"] {{
        color: {c['text']};
        background: {c['info_bg']};
        border: 1px solid {c['info_border']};
        border-radius: 5px;
        padding: 8px;
    }}
    QLabel[tone="success"], QFrame[tone="success"] {{
        color: {c['success']};
        background: {c['success_bg']};
        border: 1px solid {c['success']};
        border-radius: 5px;
        padding: 8px;
    }}
    QLabel[tone="warning"], QFrame[tone="warning"] {{
        color: {c['warning']};
        background: {c['warning_bg']};
        border: 1px solid {c['warning']};
        border-radius: 5px;
        padding: 8px;
    }}
    QLabel[tone="error"], QFrame[tone="error"] {{
        color: {c['error']};
        background: {c['error_bg']};
        border: 1px solid {c['error']};
        border-radius: 5px;
        padding: 8px;
    }}
    QFrame[role="card"], QWidget[role="card"] {{
        background: {panel_gradient};
        border: 1px solid {c['border']};
        border-top-color: {border_glint};
        border-radius: {c['panel_radius']};
    }}
    QFrame[role="brandPanel"] {{
        background: {brand_gradient};
        border: 1px solid {c['brand_border']};
        border-top-color: {border_glint};
        border-radius: {c['panel_radius']};
    }}
    QFrame[role="brandPanel"] QLabel {{
        color: {c['primary_text']};
    }}
    QFrame[role="launcherNav"] {{
        background: transparent;
        border: none;
    }}
    QFrame[role="launcherInfo"] {{
        background: {panel_gradient};
        border: 1px solid {c['border']};
        border-top-color: {border_glint};
        border-radius: {c['panel_radius']};
    }}
    QFrame[role="launcherInfo"] QTextEdit {{
        background: transparent;
        border: none;
    }}
    QFrame[role="launcherTitleBar"] {{
        background: {control_gradient};
        border: none;
        border-bottom: 1px solid {c['border_strong']};
    }}
    QFrame[role="launcherAccentRail"] {{
        background: {rail_gradient};
        border: none;
    }}
    QLabel[role="launcherWindowTitle"] {{
        color: {c['heading']};
        font-weight: 600;
    }}
    QLabel[role="tabBrand"] {{
        color: {c['text_muted']};
        font-size: 10pt;
        font-weight: 600;
        padding: 0 12px;
    }}
    QLabel[role="heroArt"] {{
        background: {panel_gradient};
        border: 1px solid {c['border_strong']};
        border-top-color: {border_glint};
        border-radius: {c['radius']};
        padding: 0;
    }}
    QGroupBox {{
        background: {panel_gradient};
        border: 1px solid {c['border']};
        border-top-color: {border_glint};
        border-radius: {c['radius']};
        margin-top: 5px;
        padding: 24px 8px 8px 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: padding;
        subcontrol-position: top left;
        left: 10px;
        top: 5px;
        padding: 0;
        color: {c['heading']};
        background: transparent;
        font-weight: 600;
    }}
    QGroupBox[role="future"] {{
        background: {c['surface_alt']};
        border-style: dashed;
    }}
    QGroupBox[role="settingsGroup"] {{
        margin-top: 0;
        padding: 8px;
    }}
    QLabel[role="settingsGroupTitle"] {{
        color: {c['heading']};
        font-weight: 600;
        padding: 0 8px;
    }}
    QFrame[role="settingsGroupRule"] {{
        background: {c['border']};
        border: none;
        min-height: 1px;
        max-height: 1px;
    }}
    QToolButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 4px;
        min-height: 28px;
        padding: 2px 7px;
    }}
    QToolButton:hover {{
        background: {hover_gradient};
        border-color: {c['border']};
    }}
    QToolButton:pressed, QToolButton:checked {{
        background: {module_gradient};
        border-color: {checked_border};
    }}
    QToolButton[role="sectionHeader"] {{
        color: {c['heading']};
        font-size: 10pt;
        font-weight: 600;
        text-align: left;
        padding: 5px 8px;
    }}
    QPushButton {{
        background: {control_gradient};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        border-top-color: {border_glint};
        border-radius: {c['radius']};
        min-height: 30px;
        padding: 0 12px;
    }}
    QPushButton:hover {{
        background: {hover_gradient};
        border-color: {c['primary_hover']};
    }}
    QPushButton:pressed {{
        background: {pressed_gradient};
        border-color: {c['primary_pressed']};
    }}
    QPushButton:focus {{
        border: 2px solid {interaction_accent};
    }}
    QPushButton:disabled {{
        background: {c['surface_disabled']};
        color: {c['text_disabled']};
        border-color: {c['border']};
    }}
    QPushButton[role="primary"], QPushButton:default {{
        background: {primary_gradient};
        color: {c['primary_text']};
        border-color: {c['primary']};
        font-weight: 600;
    }}
    QPushButton[role="primary"]:hover, QPushButton:default:hover {{
        background: {primary_hover_gradient};
        border-color: {c['primary_hover']};
    }}
    QPushButton[role="primary"]:pressed, QPushButton:default:pressed {{
        background: {c['primary_pressed']};
        border-color: {c['primary_pressed']};
    }}
    QPushButton[role="accent"] {{
        background: {accent_gradient};
        color: {accent_text};
        border-color: {c['accent']};
        font-weight: 600;
    }}
    QPushButton[role="accent"]:hover {{
        background: {accent_hover_gradient};
        border-color: {c['accent_hover']};
    }}
    QPushButton[role="accent"]:pressed {{
        background: {c['accent_pressed']};
        color: #FFFFFF;
        border-color: {c['accent_pressed']};
    }}
    {outlined_secondary_rules}
    QPushButton[role="danger"] {{
        color: {c['error']};
        border-color: {c['error']};
        background: {c['error_bg']};
    }}
    QPushButton[role="ghost"] {{
        background: transparent;
        border-color: transparent;
        color: {c['heading']};
    }}
    QPushButton[role="launcherOptions"] {{
        background: {control_gradient};
        color: {c['text']};
        border: 1px solid {c['border']};
        min-height: 26px;
        padding: 0 10px;
        font-weight: 600;
    }}
    QPushButton[role="launcherOptions"]:hover {{
        background: {hover_gradient};
        border-color: {active};
    }}
    QPushButton[role="launcherOptions"]:pressed,
    QPushButton[role="launcherOptions"]:open,
    QPushButton[role="launcherOptions"][menuOpen="true"] {{
        background: {active_gradient};
        color: {active_text};
        border-color: {active};
    }}
    QPushButton[role="themeChoice"] {{
        background: {control_gradient};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        min-height: 36px;
        padding: 0 12px;
        font-weight: 600;
    }}
    QPushButton[role="themeChoice"]:hover {{
        background: {hover_gradient};
        border-color: {active};
    }}
    QPushButton[role="themeChoice"]:checked {{
        background: {active_gradient};
        color: {active_text};
        border: 2px solid {active};
    }}
    QPushButton[role="windowControl"], QPushButton[role="windowClose"] {{
        background: transparent;
        color: {c['text']};
        border: none;
        border-radius: 2px;
        min-height: 0;
        padding: 0;
        font-size: 11pt;
    }}
    QPushButton[role="windowControl"]:hover {{
        background: {hover_gradient};
    }}
    QPushButton[role="windowClose"]:hover {{
        background: {c['error']};
        color: #FFFFFF;
    }}
    QPushButton[role="module"] {{
        background: {module_gradient};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-top-color: {border_glint};
        border-radius: {c['module_radius']};
        min-height: 0;
        padding: 0 14px;
        text-align: left;
        font-weight: 600;
    }}
    QPushButton[role="module"]:hover {{
        background: {hover_gradient};
        border-color: {interaction_accent_hover};
    }}
    QPushButton[role="module"]:pressed {{
        background: {pressed_gradient};
    }}
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        border-radius: {c['radius']};
        min-height: 28px;
        padding: 2px 7px;
        selection-background-color: {c['violet']};
        selection-color: {c['selection_text']};
    }}
    QPlainTextEdit, QTextEdit {{
        padding: 7px;
    }}
    QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
        border-color: {c['primary_hover']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 2px solid {interaction_accent};
    }}
    QLineEdit:read-only, QPlainTextEdit:read-only, QTextEdit:read-only {{
        background: {c['surface_alt']};
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
        background: {c['surface_disabled']};
        color: {c['text_disabled']};
        border-color: {c['border']};
    }}
    QLineEdit[validationState="error"], QSpinBox[validationState="error"], QDoubleSpinBox[validationState="error"], QComboBox[validationState="error"] {{
        background: {c['error_bg']};
        border: 2px solid {c['error']};
    }}
    QComboBox {{
        padding-right: 31px;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 26px;
        background: {control_gradient};
        border: none;
        border-left: 1px solid {c['border']};
        border-top-right-radius: {c['radius']};
        border-bottom-right-radius: {c['radius']};
    }}
    QComboBox::drop-down:hover {{
        background: {hover_gradient};
        border-left-color: {c['primary_hover']};
    }}
    QComboBox::drop-down:pressed,
    QComboBox::drop-down:open {{
        background: {pressed_gradient};
        border-left-color: {c['primary']};
    }}
    QComboBox::down-arrow {{
        image: url("{arrow_down}");
        width: 12px;
        height: 8px;
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border;
        width: 22px;
        background: {control_gradient};
        border: none;
        border-left: 1px solid {c['border']};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-position: top right;
        border-bottom: 1px solid {c['border']};
        border-top-right-radius: {c['radius']};
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-position: bottom right;
        border-bottom-right-radius: {c['radius']};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url("{arrow_up}");
        width: 9px;
        height: 6px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url("{arrow_down}");
        width: 9px;
        height: 6px;
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
        background: {hover_gradient};
    }}
    QComboBox QAbstractItemView {{
        background: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        selection-background-color: {c['violet']};
        selection-color: {c['selection_text']};
        outline: none;
    }}
    QCheckBox, QRadioButton {{
        spacing: 7px;
        min-height: 24px;
    }}
    QTabWidget::pane {{
        background: {panel_gradient};
        border: 1px solid {c['border']};
        border-radius: 6px;
        top: -1px;
    }}
    QTabBar::tab {{
        background: {control_gradient};
        color: {c['text_muted']};
        border: 1px solid {c['border']};
        border-top: 3px solid transparent;
        border-bottom: 1px solid {c['border']};
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
        min-height: 28px;
        padding: 3px 14px;
        margin-right: 3px;
    }}
    QTabBar::tab:hover {{
        background: {hover_gradient};
        color: {c['text']};
    }}
    QTabBar::tab:selected {{
        background: {panel_gradient};
        color: {c['heading']};
        border-left-color: {c['border_strong']};
        border-right-color: {c['border_strong']};
        border-top-color: {tab_accent};
        border-bottom-color: {c['surface']};
    }}
    QTabBar::tab:disabled {{
        color: {c['text_disabled']};
        background: {c['surface_disabled']};
    }}
    QHeaderView::section {{
        background: {control_gradient};
        color: {c['text']};
        border: none;
        border-right: 1px solid {c['border']};
        border-bottom: 1px solid {c['border_strong']};
        padding: 7px;
        font-weight: 600;
    }}
    QTableView, QTableWidget, QTreeView, QListView {{
        background: {c['surface']};
        alternate-background-color: {c['surface_alt']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        gridline-color: {c['border']};
        selection-background-color: {c['violet']};
        selection-color: {c['selection_text']};
        outline: none;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: {c['window']};
    }}
    QScrollBar:vertical {{
        background: {c['surface_disabled']};
        width: 13px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {scroll_handle_gradient};
        min-height: 28px;
        border-radius: 5px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {primary_hover_gradient}; }}
    QScrollBar:horizontal {{
        background: {c['surface_disabled']};
        height: 13px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {scroll_handle_gradient};
        min-width: 28px;
        border-radius: 5px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {primary_hover_gradient}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QProgressBar {{
        background: {c['surface_alt']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 5px;
        min-height: 18px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {primary_gradient};
        border-radius: 4px;
    }}
    QSlider::groove:horizontal {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        height: 6px;
        border-radius: 3px;
    }}
    QSlider::sub-page:horizontal {{
        background: {slider_fill_gradient};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {slider_handle_gradient};
        border: 2px solid {c['surface']};
        width: 16px;
        height: 16px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QSlider::handle:horizontal:hover {{
        background: {slider_handle_hover_gradient};
    }}
    QSplitter::handle {{
        background: {c['window']};
    }}
    QSplitter::handle:hover {{
        background: {module_gradient};
    }}
    QMenuBar {{
        background: {panel_gradient};
        color: {c['text']};
        border-bottom: 1px solid {c['border']};
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 6px 10px;
    }}
    QMenuBar::item:selected {{ background: {hover_gradient}; }}
    QMenu {{
        background: {panel_gradient};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        padding: 5px;
    }}
    QWidget[role="menuSection"] {{ background: transparent; }}
    QLabel[role="menuSectionTitle"] {{
        background: transparent;
        color: {c['text_muted']};
        font-size: 8pt;
        font-weight: 600;
        padding: 0 5px;
    }}
    QFrame[role="menuSectionRule"] {{
        background: {c['border']};
        border: none;
        min-height: 1px;
        max-height: 1px;
    }}
    QMenu::item {{ padding: 6px 24px 6px 10px; border-radius: 3px; }}
    QMenu::item:disabled {{ color: {c['text_muted']}; background: transparent; font-weight: 600; }}
    QMenu::item:selected:enabled {{ background: {active_gradient}; color: {active_text}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 3px 6px; }}
    QStatusBar {{
        background: {panel_gradient};
        color: {c['text_muted']};
        border-top: 1px solid {c['border']};
    }}
    QDockWidget {{ color: {c['text']}; }}
    QDockWidget::title {{
        background: {control_gradient};
        border: 1px solid {c['border']};
        padding: 7px;
        font-weight: 600;
        text-align: left;
    }}
    QToolTip {{
        background: {panel_gradient};
        color: {c['text']};
        border: 1px solid {interaction_accent};
        padding: 6px;
    }}
    """


class ThemeBroadcaster(QtCore.QObject):
    """Send theme changes to the processes launched by one launcher."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.channel_name = f"WeldCraftTheme-{os.getpid()}-{id(self):x}"
        self._clients = []
        self._server = QtNetwork.QLocalServer(self)
        QtNetwork.QLocalServer.removeServer(self.channel_name)
        if not self._server.listen(self.channel_name):
            raise RuntimeError(
                f"Could not open the theme update channel: {self._server.errorString()}"
            )
        self._server.newConnection.connect(self._accept_connections)

    def _accept_connections(self):
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            client.setParent(self)
            client.disconnected.connect(
                lambda connected_client=client: self._remove_client(connected_client)
            )
            self._clients.append(client)
            self._send(client, current_theme_name())

    def _remove_client(self, client):
        if client in self._clients:
            self._clients.remove(client)
        client.deleteLater()

    @staticmethod
    def _send(client, theme_name):
        if client.state() == QtNetwork.QLocalSocket.ConnectedState:
            client.write((normalize_theme_name(theme_name) + "\n").encode("ascii"))
            client.flush()

    def broadcast(self, theme_name):
        """Notify every live tool started by this launcher."""

        for client in list(self._clients):
            self._send(client, theme_name)


class _ThemeListener(QtCore.QObject):
    """Receive event-driven theme changes from the owning launcher."""

    def __init__(self, app, channel_name):
        super().__init__(app)
        self._app = app
        self._channel_name = channel_name
        self._buffer = b""
        self._socket = QtNetwork.QLocalSocket(self)
        self._socket.readyRead.connect(self._read_messages)

    def start(self):
        self._socket.connectToServer(self._channel_name)

    def _read_messages(self):
        self._buffer += bytes(self._socket.readAll())
        while b"\n" in self._buffer:
            message, self._buffer = self._buffer.split(b"\n", 1)
            requested = message.decode("ascii", errors="ignore").strip().lower()
            if requested not in THEMES and requested not in THEME_ALIASES:
                continue
            selected = normalize_theme_name(requested)
            active = normalize_theme_name(
                str(self._app.property("weldcraftTheme") or DEFAULT_THEME)
            )
            if selected != active:
                apply_theme(self._app, selected)


def _ensure_theme_listener(app):
    """Connect a launched tool to its launcher's event channel once."""

    if hasattr(app, "_weldcraft_theme_listener"):
        return
    channel_name = os.environ.get(THEME_CHANNEL_ENV_VAR, "").strip()
    if not channel_name:
        return
    listener = _ThemeListener(app, channel_name)
    app._weldcraft_theme_listener = listener
    listener.start()


class _NoWheelInputFilter(QtCore.QObject):
    """Prevent page scrolling from silently changing input values."""

    @staticmethod
    def _forward_to_scroll_area(watched, event):
        parent = watched.parentWidget() if isinstance(watched, QtWidgets.QWidget) else None
        while parent is not None and not isinstance(parent, QtWidgets.QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is None:
            return
        viewport = parent.viewport()
        global_position = QtCore.QPointF(event.globalPos())
        viewport_position = QtCore.QPointF(viewport.mapFromGlobal(event.globalPos()))
        forwarded = QtGui.QWheelEvent(
            viewport_position,
            global_position,
            event.pixelDelta(),
            event.angleDelta(),
            event.buttons(),
            event.modifiers(),
            event.phase(),
            event.inverted(),
        )
        QtWidgets.QApplication.sendEvent(viewport, forwarded)

    def eventFilter(self, watched, event):
        if event.type() != QtCore.QEvent.Wheel:
            return False
        if isinstance(watched, QtWidgets.QComboBox):
            # An open popup may still scroll its list.  A closed combo must
            # only change through an explicit click or keyboard action.
            if watched.view().isVisible():
                return False
            self._forward_to_scroll_area(watched, event)
            return True
        if isinstance(watched, QtWidgets.QAbstractSpinBox):
            self._forward_to_scroll_area(watched, event)
            return True
        if isinstance(watched, (QtWidgets.QSlider, QtWidgets.QDial)):
            self._forward_to_scroll_area(watched, event)
            return True
        return False


def _ensure_no_wheel_input_filter(app):
    """Install the suite-wide accidental-wheel-edit guard once per app."""

    if hasattr(app, "_weldcraft_no_wheel_input_filter"):
        return
    event_filter = _NoWheelInputFilter(app)
    app._weldcraft_no_wheel_input_filter = event_filter
    app.installEventFilter(event_filter)


def apply_theme(app=None, name=None):
    """Apply a WeldCraft theme and return its normalized key."""

    app = app or QtWidgets.QApplication.instance()
    if app is None:
        return normalize_theme_name(name or DEFAULT_THEME)
    _ensure_no_wheel_input_filter(app)
    key = normalize_theme_name(name or current_theme_name())
    colors = THEMES[key]

    if not hasattr(app, "_weldcraft_native_style_name"):
        app._weldcraft_native_style_name = app.style().objectName()
        app._weldcraft_active_base_style = app._weldcraft_native_style_name.lower()
        app._weldcraft_native_palette = QtGui.QPalette(app.palette())
        app._weldcraft_native_font = QtGui.QFont(app.font())
        app._weldcraft_native_stylesheet = app.styleSheet()

    if colors.get("native"):
        native_style = app._weldcraft_native_style_name
        if native_style and app.style().objectName().lower() != native_style.lower():
            app.setStyle(native_style)
        app._weldcraft_active_base_style = native_style.lower()
        app.setPalette(QtGui.QPalette(app._weldcraft_native_palette))
        app.setFont(QtGui.QFont(app._weldcraft_native_font))
        app.setStyleSheet(app._weldcraft_native_stylesheet)
        app.setProperty("weldcraftTheme", key)
        _refresh_name_tags(app, colors)
        _ensure_theme_listener(app)
        return key

    if app._weldcraft_active_base_style != "weldcraft-fusion":
        proxy_style = _WeldCraftStyle()
        app.setStyle(proxy_style)
        app._weldcraft_theme_proxy_style = proxy_style
        app._weldcraft_active_base_style = "weldcraft-fusion"
    font = QtGui.QFont("Segoe UI", 9)
    font.setStyleStrategy(QtGui.QFont.PreferAntialias)
    app.setFont(font)
    app.setPalette(_palette(colors))
    app.setStyleSheet(_stylesheet(colors))
    app.setProperty("weldcraftTheme", key)
    _refresh_name_tags(app, colors)
    _ensure_theme_listener(app)
    return key


def refresh_widget_style(widget):
    """Re-evaluate property selectors after a dynamic property changes."""

    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def set_widget_state(widget, property_name, value):
    widget.setProperty(property_name, value)
    refresh_widget_style(widget)


def _crop_name_tag(pixmap, alpha_threshold=16):
    """Remove the large transparent canvas around a name-tag image."""

    if pixmap is None or pixmap.isNull():
        return QtGui.QPixmap()
    image = pixmap.toImage().convertToFormat(QtGui.QImage.Format_RGBA8888)
    width = image.width()
    height = image.height()
    if width <= 0 or height <= 0:
        return QtGui.QPixmap()

    bits = image.constBits()
    bits.setsize(image.byteCount())
    pixels = bytes(bits)
    stride = image.bytesPerLine()
    left, top, right, bottom = width, height, -1, -1
    for y in range(height):
        row_start = (y * stride) + 3
        alpha_values = pixels[row_start:row_start + (width * 4):4]
        for x, alpha in enumerate(alpha_values):
            if alpha >= alpha_threshold:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

    if right < left or bottom < top:
        return QtGui.QPixmap()
    return pixmap.copy(left, top, right - left + 1, bottom - top + 1)


def _render_name_tag(label, colors):
    source = getattr(label, "_weldcraft_name_tag_source", None)
    title = getattr(label, "_weldcraft_name_tag_title", "")
    if source is None or source.isNull():
        label.clear()
        label.setText(title)
        label.setProperty("role", "pageTitle")
        label.setMinimumHeight(0)
        label.setMaximumHeight(16777215)
        refresh_widget_style(label)
        return

    cropped = getattr(label, "_weldcraft_name_tag_cropped", None)
    if cropped is None:
        cropped = _crop_name_tag(source)
        label._weldcraft_name_tag_cropped = cropped
    if cropped.isNull():
        label.clear()
        label.setText(title)
        label.setProperty("role", "pageTitle")
        refresh_widget_style(label)
        return

    bounds = (
        getattr(label, "_weldcraft_name_tag_basic_bounds", (230, 38))
        if colors.get("native")
        else getattr(label, "_weldcraft_name_tag_themed_bounds", (250, 44))
    )
    displayed = cropped.scaled(
        int(bounds[0]),
        int(bounds[1]),
        QtCore.Qt.KeepAspectRatio,
        QtCore.Qt.SmoothTransformation,
    )
    label.setText("")
    label.setPixmap(displayed)
    label.setProperty("role", "nameTag")
    label.setMinimumWidth(0)
    label.setMinimumHeight(0)
    label.setMaximumHeight(16777215)
    label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
    refresh_widget_style(label)


def _refresh_name_tags(app, colors):
    """Resize name tags when a running application changes theme."""

    for widget in app.allWidgets():
        if hasattr(widget, "_weldcraft_name_tag_source"):
            _render_name_tag(widget, colors)


def set_name_tag(
    label,
    pixmap,
    title,
    basic_bounds=(230, 38),
    themed_bounds=(250, 44),
):
    """Crop and proportionally fit a product name tag for the active theme."""

    label._weldcraft_name_tag_source = (
        QtGui.QPixmap(pixmap) if pixmap is not None else QtGui.QPixmap()
    )
    label._weldcraft_name_tag_cropped = None
    label._weldcraft_name_tag_title = title
    label._weldcraft_name_tag_basic_bounds = basic_bounds
    label._weldcraft_name_tag_themed_bounds = themed_bounds
    label.setAccessibleName(title)
    label.setToolTip(title)
    app = QtWidgets.QApplication.instance()
    active_theme = app.property("weldcraftTheme") if app is not None else None
    _render_name_tag(
        label,
        theme_colors(active_theme or current_theme_name()),
    )


def create_brand_text(title, subtitle="", parent=None):
    """Create a compact, theme-aware product title block."""

    container = QtWidgets.QWidget(parent)
    container.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
    layout = QtWidgets.QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(1)

    title_label = QtWidgets.QLabel(title, container)
    title_label.setProperty("role", "pageTitle")
    title_font = title_label.font()
    title_font.setPointSize(14)
    title_font.setBold(True)
    title_label.setFont(title_font)
    layout.addWidget(title_label)
    if subtitle:
        subtitle_label = QtWidgets.QLabel(subtitle, container)
        subtitle_label.setProperty("role", "subtitle")
        subtitle_label.setWordWrap(False)
        layout.addWidget(subtitle_label)
    return container
