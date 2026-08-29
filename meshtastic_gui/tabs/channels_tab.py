from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QLineEdit, QLabel, QMessageBox
)


class ChannelsTab(QWidget):
    def __init__(self, on_refresh, on_import_url, on_export_url, parent=None):
        """
        on_refresh() -> list[dict{index, role, name}]
        on_import_url(url: str) -> None  (raises on failure)
        on_export_url() -> str
        """
        super().__init__(parent)
        self._on_refresh = on_refresh
        self._on_import_url = on_import_url
        self._on_export_url = on_export_url

        layout = QVBoxLayout(self)

        hint = QLabel(
            "Channel LoRa mengatur siapa yang bisa saling mendengar di mesh (offline).\n"
            "Import URL untuk bergabung ke channel/PSK milik orang lain; Export untuk membagikan channel Anda."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Index", "Role", "Name"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        refresh_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh channel list")
        self.refresh_btn.clicked.connect(self.refresh)
        refresh_row.addWidget(self.refresh_btn)
        refresh_row.addStretch(1)
        layout.addLayout(refresh_row)

        layout.addWidget(QLabel("Channel URL (meshtastic.org/...):"))
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://meshtastic.org/e/#...")
        url_row.addWidget(self.url_edit, 1)

        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self._import)
        url_row.addWidget(self.import_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._export)
        url_row.addWidget(self.export_btn)

        layout.addLayout(url_row)

        self.set_enabled(False)

    def set_enabled(self, enabled: bool):
        for w in (self.refresh_btn, self.import_btn, self.export_btn, self.url_edit):
            w.setEnabled(enabled)

    def clear(self):
        self.table.setRowCount(0)
        self.url_edit.clear()

    def refresh(self):
        try:
            channels = self._on_refresh()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal membaca channel", str(e))
            return
        self.table.setRowCount(len(channels))
        for row, ch in enumerate(channels):
            self.table.setItem(row, 0, QTableWidgetItem(str(ch.get("index", "-"))))
            self.table.setItem(row, 1, QTableWidgetItem(str(ch.get("role", "-"))))
            self.table.setItem(row, 2, QTableWidgetItem(str(ch.get("name", "-"))))

    def _import(self):
        url = self.url_edit.text().strip()
        if not url:
            return
        confirm = QMessageBox.question(
            self, "Import channel",
            "Ini akan mengganti konfigurasi channel di perangkat dengan channel dari URL ini. Lanjutkan?",
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            self._on_import_url(url)
            QMessageBox.information(self, "Berhasil", "Channel URL berhasil di-import. Perangkat mungkin reboot.")
            self.refresh()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal import", str(e))

    def _export(self):
        try:
            url = self._on_export_url()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal export", str(e))
            return
        self.url_edit.setText(url)
        self.url_edit.selectAll()
