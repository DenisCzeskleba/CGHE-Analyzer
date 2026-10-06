"""P11-local Qt widgets for compact scientific input and collapsible setup sections."""

from __future__ import annotations

import math
import re

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets


_FLOAT_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_INTERMEDIATE_PATTERN = re.compile(r"^[+-]?(?:\d*(?:\.\d*)?)(?:[eE][+-]?\d*)?$")


def parse_dot_float(text: str) -> float:
    value = str(text).strip()
    if "," in value or not _FLOAT_PATTERN.fullmatch(value):
        raise ValueError("Enter a dot-decimal number, for example 0.00005 or 5.0e-5.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("The value must be finite.")
    return number


def format_compact_number(value: float, significant_digits: int = 8) -> str:
    number = float(value)
    if not math.isfinite(number):
        return str(number)
    if number == 0.0:
        return "0"
    return format(number, f".{significant_digits}g")


class ScientificDoubleSpinBox(QtWidgets.QDoubleSpinBox):
    """Locale-independent double editor with compact scientific display."""

    def __init__(self, value=0.0, minimum=0.0, maximum=1e9, step=None, parent=None):
        super().__init__(parent)
        self.setLocale(QtCore.QLocale.c())
        self.setGroupSeparatorShown(False)
        # QDoubleSpinBox rounds its stored value to ``decimals``; the maximum
        # keeps the binary double intact while textFromValue stays compact.
        self.setDecimals(323)
        self.setRange(float(minimum), float(maximum))
        self.setKeyboardTracking(False)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        if step is not None:
            self.setSingleStep(float(step))
        try:
            self.setStepType(QtWidgets.QAbstractSpinBox.AdaptiveDecimalStepType)
        except AttributeError:
            pass
        self.setValue(float(value))

    @staticmethod
    def parseText(text: str) -> float:
        return parse_dot_float(text)

    def validate(self, text, position):
        value = str(text).strip()
        if "," in value:
            state = QtGui.QValidator.Invalid
        elif _FLOAT_PATTERN.fullmatch(value):
            try:
                number = float(value)
                state = (
                    QtGui.QValidator.Acceptable
                    if math.isfinite(number) and self.minimum() <= number <= self.maximum()
                    else QtGui.QValidator.Invalid
                )
            except ValueError:
                state = QtGui.QValidator.Invalid
        elif _INTERMEDIATE_PATTERN.fullmatch(value):
            state = QtGui.QValidator.Intermediate
        else:
            state = QtGui.QValidator.Invalid
        return state, text, position

    def valueFromText(self, text):
        try:
            return parse_dot_float(text)
        except ValueError:
            return self.value()

    def fixup(self, text):
        # In the C locale Qt otherwise treats commas as group separators and
        # can silently turn ``5,0`` into ``50`` during focus-out cleanup.
        return text

    def textFromValue(self, value):
        return format_compact_number(value)

    def wheelEvent(self, event):
        event.ignore()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down, QtCore.Qt.Key_PageUp, QtCore.Qt.Key_PageDown):
            event.ignore()
            return
        super().keyPressEvent(event)

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(135)
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(72)
        return hint


class PlainIntegerSpinBox(QtWidgets.QSpinBox):
    def __init__(self, value=0, minimum=0, maximum=1_000_000, parent=None):
        super().__init__(parent)
        self.setRange(int(minimum), int(maximum))
        self.setValue(int(value))
        self.setKeyboardTracking(False)
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def wheelEvent(self, event):
        event.ignore()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down, QtCore.Qt.Key_PageUp, QtCore.Qt.Key_PageDown):
            event.ignore()
            return
        super().keyPressEvent(event)


class NoWheelComboBox(QtWidgets.QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(0)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(220)
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(72)
        return hint


class CompactFormLayout(QtWidgets.QFormLayout):
    """Two-column form whose labels stay compact while fields use the room left."""

    LABEL_WIDTH = 142

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        self.setRowWrapPolicy(QtWidgets.QFormLayout.DontWrapRows)
        self.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.setHorizontalSpacing(10)
        self.setVerticalSpacing(6)

    def addRow(self, label, field=None):
        if field is None:
            super().addRow(label)
            return
        if isinstance(label, str):
            label_widget = QtWidgets.QLabel(label)
            label_widget.setWordWrap(True)
            label_widget.setFixedWidth(self.LABEL_WIDTH)
            label_widget.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
            label = label_widget
        super().addRow(label, field)


class CollapsibleSection(QtWidgets.QWidget):
    expandedChanged = QtCore.pyqtSignal(bool)

    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = QtWidgets.QToolButton()
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.header.setMinimumWidth(0)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.header.setProperty("role", "sectionHeader")
        self.body = QtWidgets.QFrame()
        self.body.setFrameShape(QtWidgets.QFrame.StyledPanel)
        outer.addWidget(self.header)
        outer.addWidget(self.body)
        self.header.toggled.connect(self.setExpanded)
        self.setExpanded(expanded)

    def setExpanded(self, expanded: bool):
        expanded = bool(expanded)
        changed = self.header.isChecked() != expanded or self.body.isVisible() != expanded
        self.header.blockSignals(True)
        self.header.setChecked(expanded)
        self.header.blockSignals(False)
        self.header.setArrowType(QtCore.Qt.DownArrow if expanded else QtCore.Qt.RightArrow)
        self.body.setVisible(expanded)
        if changed:
            self.expandedChanged.emit(expanded)

    def isExpanded(self) -> bool:
        return self.header.isChecked()

    def setContentLayout(self, layout):
        self.body.setLayout(layout)


class MeasurementTableModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._time = np.empty(0)
        self._signal = np.empty(0)

    def setMeasurement(self, measurement):
        self.beginResetModel()
        if measurement is None:
            self._time = np.empty(0)
            self._signal = np.empty(0)
        else:
            self._time = np.asarray(measurement.time_s)
            self._signal = np.asarray(measurement.signal)
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self._time)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else 2

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or role not in (QtCore.Qt.DisplayRole, QtCore.Qt.ToolTipRole):
            return None
        values = self._time if index.column() == 0 else self._signal
        return format_compact_number(values[index.row()])

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            return ("Time [s]", "Signal [a.u.]")[section]
        return str(section + 1)
