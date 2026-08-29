"""Builds an editable Qt form directly from a protobuf message's descriptor.

Meshtastic's Device/LoRa/Position/Power/Network/Display/Bluetooth/Security
config sections (and the module-config sections: MQTT, Serial, etc.) are all
just protobuf messages on `node.localConfig.*` / `node.moduleConfig.*`. Rather
than hand-writing one bespoke form per section (13+ sections, all drifting
out of sync with whatever meshtastic-python/firmware version is installed),
we introspect the message's fields and generate the right widget per field
type. This keeps every section automatically up to date with the installed
protobuf schema — the same approach the field editor in `meshtastic --configure`
relies on, just rendered as widgets instead of YAML.
"""
from google.protobuf.descriptor import FieldDescriptor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QCheckBox, QComboBox, QLineEdit, QSpinBox,
    QDoubleSpinBox, QScrollArea, QVBoxLayout, QPushButton, QLabel, QHBoxLayout,
    QMessageBox
)

_SIGNED_INT = {
    FieldDescriptor.TYPE_INT32, FieldDescriptor.TYPE_SINT32,
    FieldDescriptor.TYPE_SFIXED32, FieldDescriptor.TYPE_INT64,
    FieldDescriptor.TYPE_SINT64, FieldDescriptor.TYPE_SFIXED64,
}
_UNSIGNED_INT = {
    FieldDescriptor.TYPE_UINT32, FieldDescriptor.TYPE_FIXED32,
    FieldDescriptor.TYPE_UINT64, FieldDescriptor.TYPE_FIXED64,
}
_FLOAT_TYPES = {FieldDescriptor.TYPE_FLOAT, FieldDescriptor.TYPE_DOUBLE}


def _label_for(name: str) -> str:
    return name.replace("_", " ").capitalize()


class ProtoForm(QWidget):
    """An editable form for the top-level scalar fields of `message`.

    Repeated fields and nested sub-messages are skipped (shown nowhere) —
    they cover things like ignored-node lists or nested structs that need
    dedicated UI; the scalar fields already cover the vast majority of what
    the Android app's settings screens expose per section.
    """

    def __init__(self, message, parent=None):
        super().__init__(parent)
        self.message = message
        self._setters = []

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        any_fields = False
        for field in message.DESCRIPTOR.fields:
            if field.is_repeated:
                continue
            if field.type == FieldDescriptor.TYPE_MESSAGE:
                continue
            widget = self._build_widget(field)
            if widget is None:
                continue
            form.addRow(_label_for(field.name) + ":", widget)
            any_fields = True

        if not any_fields:
            form.addRow(QLabel("(tidak ada field yang bisa diedit di sini)"))

        self.setLayout(form)

    def _build_widget(self, field):
        value = getattr(self.message, field.name)

        if field.type == FieldDescriptor.TYPE_BOOL:
            w = QCheckBox()
            w.setChecked(bool(value))
            self._setters.append(lambda w=w, f=field: setattr(self.message, f.name, w.isChecked()))
            return w

        if field.type == FieldDescriptor.TYPE_ENUM:
            w = QComboBox()
            enum_type = field.enum_type
            w.addItems([v.name for v in enum_type.values])
            try:
                w.setCurrentText(enum_type.values_by_number[value].name)
            except KeyError:
                pass
            def set_enum(w=w, f=field, et=enum_type):
                setattr(self.message, f.name, et.values_by_name[w.currentText()].number)
            self._setters.append(set_enum)
            return w

        if field.type in _SIGNED_INT:
            w = QSpinBox()
            w.setRange(-2147483648, 2147483647)
            w.setValue(int(value))
            self._setters.append(lambda w=w, f=field: setattr(self.message, f.name, w.value()))
            return w

        if field.type in _UNSIGNED_INT:
            w = QSpinBox()
            w.setRange(0, 2147483647)
            w.setValue(min(int(value), 2147483647))
            self._setters.append(lambda w=w, f=field: setattr(self.message, f.name, w.value()))
            return w

        if field.type in _FLOAT_TYPES:
            w = QDoubleSpinBox()
            w.setRange(-1_000_000, 1_000_000)
            w.setDecimals(4)
            w.setValue(float(value))
            self._setters.append(lambda w=w, f=field: setattr(self.message, f.name, w.value()))
            return w

        if field.type == FieldDescriptor.TYPE_STRING:
            w = QLineEdit(value)
            self._setters.append(lambda w=w, f=field: setattr(self.message, f.name, w.text()))
            return w

        if field.type == FieldDescriptor.TYPE_BYTES:
            w = QLineEdit(value.hex() if value else "")
            w.setReadOnly(True)
            w.setToolTip("Nilai biner (read-only di sini)")
            return w

        return None

    def apply(self):
        """Push all edited widget values back into the bound protobuf message."""
        for setter in self._setters:
            setter()


def build_config_page(message, config_name, on_write, parent=None):
    """Wraps a ProtoForm with a scrollable container + an Apply button that
    calls on_write(config_name) after pushing edits into the message."""
    page = QWidget(parent)
    layout = QVBoxLayout(page)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    form = ProtoForm(message)
    scroll.setWidget(form)
    layout.addWidget(scroll)

    row = QHBoxLayout()
    apply_btn = QPushButton("Simpan ke perangkat")
    apply_btn.setObjectName("primary")

    def do_apply():
        try:
            form.apply()
            on_write(config_name)
            QMessageBox.information(page, "Berhasil", f"Config '{config_name}' disimpan ke perangkat.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(page, "Gagal menyimpan", str(e))

    apply_btn.clicked.connect(do_apply)
    row.addWidget(apply_btn)
    row.addStretch(1)
    layout.addLayout(row)

    return page
