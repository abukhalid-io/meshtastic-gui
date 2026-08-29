"""Settings tab — mirrors the Android app's Settings screen: a category list
on the left (User, then every radio config section, then every module
config section, then Advanced/danger actions) and the corresponding editable
form on the right."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QListWidget, QListWidgetItem,
    QStackedWidget, QLineEdit, QPushButton, QGroupBox, QLabel, QMessageBox
)

from ..proto_form import build_config_page

# (list label, config_name passed to node.writeConfig, attribute path on the node)
LOCAL_CONFIG_SECTIONS = [
    ("Perangkat (Device)", "device", "device"),
    ("LoRa", "lora", "lora"),
    ("Posisi (GPS)", "position", "position"),
    ("Daya (Power)", "power", "power"),
    ("Jaringan (Network)", "network", "network"),
    ("Layar (Display)", "display", "display"),
    ("Bluetooth", "bluetooth", "bluetooth"),
    ("Keamanan (Security)", "security", "security"),
]

MODULE_CONFIG_SECTIONS = [
    ("MQTT", "mqtt", "mqtt"),
    ("Serial", "serial", "serial"),
    ("Notifikasi Eksternal", "external_notification", "external_notification"),
    ("Store & Forward", "store_forward", "store_forward"),
    ("Range Test", "range_test", "range_test"),
    ("Telemetry", "telemetry", "telemetry"),
    ("Canned Message", "canned_message", "canned_message"),
    ("Audio", "audio", "audio"),
    ("Remote Hardware", "remote_hardware", "remote_hardware"),
    ("Neighbor Info", "neighbor_info", "neighbor_info"),
    ("Sensor Deteksi", "detection_sensor", "detection_sensor"),
    ("Lampu Ambient", "ambient_lighting", "ambient_lighting"),
    ("Paxcounter", "paxcounter", "paxcounter"),
]

ROLE_USER = Qt.UserRole


class _Separator(QListWidgetItem):
    def __init__(self, text):
        super().__init__(f"— {text} —")
        self.setFlags(Qt.NoItemFlags)
        f = self.font()
        f.setBold(True)
        self.setFont(f)


class SettingsTab(QWidget):
    def __init__(self, on_set_owner, on_write_config, on_reboot, on_factory_reset,
                 on_clean_node_db, on_open_channels, parent=None):
        super().__init__(parent)
        self._on_set_owner = on_set_owner
        self._on_write_config = on_write_config
        self._on_reboot = on_reboot
        self._on_factory_reset = on_factory_reset
        self._on_clean_node_db = on_clean_node_db
        self._on_open_channels = on_open_channels

        root = QHBoxLayout(self)

        self.category_list = QListWidget()
        self.category_list.setMaximumWidth(220)
        self.category_list.currentRowChanged.connect(self._on_row_changed)
        root.addWidget(self.category_list)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self._placeholder = QLabel("Hubungkan ke perangkat dulu untuk melihat pengaturan.")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(self._placeholder)

        self._row_to_page = {}
        self._owner_page = None

    # -- lifecycle ---------------------------------------------------------
    def clear(self):
        self.category_list.clear()
        while self.stack.count() > 1:
            w = self.stack.widget(1)
            self.stack.removeWidget(w)
            w.deleteLater()
        self.stack.setCurrentWidget(self._placeholder)
        self._row_to_page.clear()

    def build(self, node):
        """(Re)builds the category list + pages from a freshly-connected node."""
        self.clear()

        # -- User (owner name) ------------------------------------------------
        self._owner_page = self._build_owner_page()
        self._add_page("👤  User", self._owner_page)

        self.category_list.addItem(_Separator("Radio"))
        for label, config_name, attr in LOCAL_CONFIG_SECTIONS:
            message = getattr(node.localConfig, attr)
            page = build_config_page(message, config_name, self._on_write_config)
            self._add_page(label, page)

        self.category_list.addItem(_Separator("Modul"))
        for label, config_name, attr in MODULE_CONFIG_SECTIONS:
            message = getattr(node.moduleConfig, attr)
            page = build_config_page(message, config_name, self._on_write_config)
            self._add_page(label, page)

        self.category_list.addItem(_Separator("Lanjutan"))
        self._add_page("📡  Channels", self._build_channels_shortcut_page())
        self._add_page("⚠️  Reboot / Factory Reset", self._build_danger_page())

        self.category_list.setCurrentRow(0)

    def _add_page(self, label, page):
        item = QListWidgetItem(label)
        self.category_list.addItem(item)
        row = self.category_list.count() - 1
        self.stack.addWidget(page)
        self._row_to_page[row] = page

    def _on_row_changed(self, row):
        page = self._row_to_page.get(row)
        if page is not None:
            self.stack.setCurrentWidget(page)

    def prefill_owner(self, long_name, short_name):
        if self._owner_page is not None:
            self._owner_page.long_name.setText(long_name or "")
            self._owner_page.short_name.setText(short_name or "")

    # -- page builders -------------------------------------------------------
    def _build_owner_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        box = QGroupBox("Nama perangkat (Owner)")
        form = QFormLayout(box)
        page.long_name = QLineEdit()
        page.short_name = QLineEdit()
        page.short_name.setMaxLength(4)
        form.addRow("Long name:", page.long_name)
        form.addRow("Short name (max 4 char):", page.short_name)
        apply_btn = QPushButton("Terapkan nama")
        apply_btn.setObjectName("primary")

        def apply_owner():
            try:
                self._on_set_owner(page.long_name.text().strip(), page.short_name.text().strip())
                QMessageBox.information(self, "Berhasil", "Nama perangkat diperbarui.")
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Gagal", str(e))

        apply_btn.clicked.connect(apply_owner)
        form.addRow(apply_btn)
        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _build_channels_shortcut_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel("Konfigurasi channel LoRa ada di tab tersendiri (import/export URL, lihat daftar channel).")
        label.setWordWrap(True)
        layout.addWidget(label)
        btn = QPushButton("Buka tab Channels")
        btn.setObjectName("primary")
        btn.clicked.connect(self._on_open_channels)
        layout.addWidget(btn)
        layout.addStretch(1)
        return page

    def _build_danger_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        box = QGroupBox("Zona berbahaya")
        box_layout = QVBoxLayout(box)

        reboot_btn = QPushButton("Reboot perangkat")
        reboot_btn.clicked.connect(self._reboot)
        box_layout.addWidget(reboot_btn)

        clean_btn = QPushButton("Bersihkan node database (hapus node lama)")
        clean_btn.clicked.connect(self._clean_node_db)
        box_layout.addWidget(clean_btn)

        factory_btn = QPushButton("Factory reset")
        factory_btn.setObjectName("danger")
        factory_btn.clicked.connect(self._factory_reset)
        box_layout.addWidget(factory_btn)

        layout.addWidget(box)
        layout.addStretch(1)
        return page

    def _reboot(self):
        if QMessageBox.question(self, "Reboot", "Reboot perangkat sekarang?") != QMessageBox.Yes:
            return
        try:
            self._on_reboot()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal", str(e))

    def _clean_node_db(self):
        if QMessageBox.question(self, "Bersihkan node DB", "Hapus semua node lama dari database lokal perangkat?") != QMessageBox.Yes:
            return
        try:
            self._on_clean_node_db()
            QMessageBox.information(self, "Berhasil", "Perintah pembersihan node DB dikirim.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal", str(e))

    def _factory_reset(self):
        confirm = QMessageBox.warning(
            self, "Factory reset",
            "Ini akan MENGHAPUS SEMUA konfigurasi di perangkat (channel, nama, dsb). Tindakan tidak bisa dibatalkan. Lanjutkan?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._on_factory_reset()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal", str(e))
