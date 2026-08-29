from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QLineEdit, QComboBox, QMenu, QMessageBox
)

from ..utils import fmt_timestamp, node_display_id, flatten

COLUMNS = ["", "ID", "Long Name", "Short Name", "Model", "SNR", "Battery", "Last Heard", "Position"]

SORT_OPTIONS = ["Last heard", "Alfabetis", "Baterai", "SNR"]


class NodesTab(QWidget):
    def __init__(self, actions, parent=None):
        """actions: dict of callbacks keyed by
        favorite/unfavorite/ignore/unignore/traceroute/request_position/remove/message,
        each called with the node_id string (e.g. "!a1b2c3d4")."""
        super().__init__(parent)
        self._actions = actions
        self._nodes = {}  # node_id -> raw node dict
        self._row_by_id = {}

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        self.info_label = QLabel("0 node diketahui")
        top_row.addWidget(self.info_label)
        top_row.addStretch(1)

        top_row.addWidget(QLabel("Cari:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("nama atau ID...")
        self.search_edit.setMaximumWidth(180)
        self.search_edit.textChanged.connect(self._apply_filter_sort)
        top_row.addWidget(self.search_edit)

        top_row.addWidget(QLabel("Urutkan:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(SORT_OPTIONS)
        self.sort_combo.currentIndexChanged.connect(self._apply_filter_sort)
        top_row.addWidget(self.sort_combo)

        layout.addLayout(top_row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.cellDoubleClicked.connect(self._show_detail)
        layout.addWidget(self.table)

    # -- data lifecycle --------------------------------------------------
    def clear(self):
        self.table.setRowCount(0)
        self._row_by_id.clear()
        self._nodes.clear()
        self.info_label.setText("0 node diketahui")

    def upsert_node(self, node: dict):
        node_id = node_display_id(node)
        self._nodes[node_id] = node
        self._apply_filter_sort()

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def known_nodes(self):
        """Returns {node_id: display_label} for other tabs (e.g. DM target picker)."""
        out = {}
        for node_id, node in self._nodes.items():
            user = node.get("user", {}) or {}
            label = user.get("longName") or user.get("shortName") or node_id
            out[node_id] = f"{label} ({node_id})"
        return out

    # -- render ------------------------------------------------------------
    def _apply_filter_sort(self):
        query = self.search_edit.text().strip().lower()
        rows = []
        for node_id, node in self._nodes.items():
            user = node.get("user", {}) or {}
            haystack = f"{user.get('longName', '')} {user.get('shortName', '')} {node_id}".lower()
            if query and query not in haystack:
                continue
            rows.append((node_id, node))

        sort_mode = self.sort_combo.currentText()
        if sort_mode == "Alfabetis":
            rows.sort(key=lambda x: (x[1].get("user", {}) or {}).get("longName", x[0]).lower())
        elif sort_mode == "Baterai":
            rows.sort(key=lambda x: (x[1].get("deviceMetrics", {}) or {}).get("batteryLevel", -1), reverse=True)
        elif sort_mode == "SNR":
            rows.sort(key=lambda x: x[1].get("snr", -999), reverse=True)
        else:  # Last heard
            rows.sort(key=lambda x: x[1].get("lastHeard", 0), reverse=True)

        self.table.setRowCount(len(rows))
        self._row_by_id.clear()
        for row, (node_id, node) in enumerate(rows):
            self._row_by_id[node_id] = row
            self._fill_row(row, node_id, node)

    def _fill_row(self, row, node_id, node):
        user = node.get("user", {}) or {}
        pos = node.get("position", {}) or {}
        metrics = node.get("deviceMetrics", {}) or {}

        star = "★" if node.get("isFavorite") else ("🚫" if node.get("isIgnored") else "")
        long_name = user.get("longName", "-")
        short_name = user.get("shortName", "-")
        model = user.get("hwModel", "-")
        snr = node.get("snr", "-")
        battery = metrics.get("batteryLevel", "-")
        last_heard = fmt_timestamp(node.get("lastHeard"))
        lat = pos.get("latitude")
        lon = pos.get("longitude")
        position = f"{lat:.5f}, {lon:.5f}" if lat is not None and lon is not None else "-"

        values = [star, node_id, long_name, short_name, model, str(snr), str(battery), last_heard, position]
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setData(Qt.UserRole, node_id)
            self.table.setItem(row, col, item)

        self.info_label.setText(f"{len(self._nodes)} node diketahui")

    def _node_id_at_row(self, row):
        item = self.table.item(row, 1)
        return item.text() if item else None

    # -- context menu / detail ----------------------------------------------
    def _show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        node_id = self._node_id_at_row(row)
        if not node_id:
            return
        node = self._nodes.get(node_id, {})

        menu = QMenu(self)
        menu.addAction("💬 Kirim pesan (DM)", lambda: self._run(self._actions.get("message"), node_id))
        menu.addSeparator()
        if node.get("isFavorite"):
            menu.addAction("☆ Batal favorit", lambda: self._run(self._actions.get("unfavorite"), node_id))
        else:
            menu.addAction("★ Jadikan favorit", lambda: self._run(self._actions.get("favorite"), node_id))
        if node.get("isIgnored"):
            menu.addAction("Batal abaikan", lambda: self._run(self._actions.get("unignore"), node_id))
        else:
            menu.addAction("Abaikan node ini", lambda: self._run(self._actions.get("ignore"), node_id))
        menu.addSeparator()
        menu.addAction("📍 Minta posisi", lambda: self._run(self._actions.get("request_position"), node_id))
        menu.addAction("🛰 Trace route", lambda: self._run(self._actions.get("traceroute"), node_id))
        menu.addSeparator()
        menu.addAction("🗑 Hapus node", lambda: self._confirm_remove(node_id))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _confirm_remove(self, node_id):
        if QMessageBox.question(self, "Hapus node", f"Hapus {node_id} dari node database lokal perangkat?") == QMessageBox.Yes:
            self._run(self._actions.get("remove"), node_id)

    def _run(self, fn, node_id):
        if fn is None:
            return
        try:
            fn(node_id)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal", str(e))

    def _show_detail(self, row, _col):
        node_id = self._node_id_at_row(row)
        if not node_id:
            return
        node = self._nodes.get(node_id, {})
        rows = flatten(node)
        text = "\n".join(f"{k}: {v}" for k, v in rows)
        QMessageBox.information(self, f"Detail node {node_id}", text or "(tidak ada data)")
