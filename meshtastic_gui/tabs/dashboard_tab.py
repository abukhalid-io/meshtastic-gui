import ipaddress

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView
)

from .. import theme
from ..utils import proto_to_dict, flatten, fmt_timestamp


def _ip_str(ip_int):
    if not ip_int:
        return "-"
    try:
        return str(ipaddress.IPv4Address(ip_int))
    except Exception:  # noqa: BLE001
        return str(ip_int)


def _yn(b):
    return "✅ Ya" if b else "❌ Tidak"


class DashboardTab(QWidget):
    def __init__(self, on_check_connection_status, parent=None):
        """on_check_connection_status() -> None, fires the async admin
        request; the reply comes back later via show_connection_status()."""
        super().__init__(parent)
        self._on_check_connection_status = on_check_connection_status
        self._mqtt_nodes = {}  # node_id -> {"node_id", "gateway_id", "channel", "ts"}
        layout = QVBoxLayout(self)

        self.status_label = QLabel("Status: Not connected")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        layout.addWidget(self.status_label)

        # -- MQTT proxy status (this app's own broker connection) --------
        self.proxy_status_label = QLabel("🌉 MQTT Proxy (internet via app): belum aktif")
        self.proxy_status_label.setStyleSheet(f"padding: 4px; color: {theme.TEXT_MUTED};")
        layout.addWidget(self.proxy_status_label)

        # -- device's own native WiFi/Ethernet/Bluetooth status ------------
        conn_row = QHBoxLayout()
        self.check_conn_btn = QPushButton("📡 Cek status koneksi native perangkat")
        self.check_conn_btn.setObjectName("primary")
        self.check_conn_btn.setEnabled(False)
        self.check_conn_btn.clicked.connect(self._on_check_connection_status)
        conn_row.addWidget(self.check_conn_btn)
        conn_row.addStretch(1)
        layout.addLayout(conn_row)

        self.conn_status_label = QLabel("")
        self.conn_status_label.setWordWrap(True)
        self.conn_status_label.setStyleSheet("padding: 4px;")
        layout.addWidget(self.conn_status_label)

        # -- nodes seen via the MQTT broker (not necessarily in LoRa range) --
        layout.addWidget(QLabel("Node yang terlihat lewat broker MQTT (proxy):"))
        self.mqtt_nodes_table = QTableWidget(0, 4)
        self.mqtt_nodes_table.setHorizontalHeaderLabels(["Node ID", "Gateway", "Channel", "Terakhir terlihat"])
        self.mqtt_nodes_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.mqtt_nodes_table.horizontalHeader().setStretchLastSection(True)
        self.mqtt_nodes_table.verticalHeader().setVisible(False)
        self.mqtt_nodes_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.mqtt_nodes_table.setMaximumHeight(160)
        layout.addWidget(self.mqtt_nodes_table)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Field", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table, 1)

    def set_status(self, text, connected=False):
        color = theme.ACCENT if connected else theme.DANGER
        self.status_label.setText(f"Status: {text}")
        self.status_label.setStyleSheet(f"font-weight: bold; font-size: 14px; padding: 4px; color: {color};")
        self.check_conn_btn.setEnabled(connected)

    # -- MQTT proxy (app-side) status -----------------------------------
    def set_proxy_connected(self, connected: bool):
        color = theme.ACCENT if connected else theme.TEXT_MUTED
        text = "🌉 MQTT Proxy (internet via app): ✅ Terhubung ke broker" if connected \
            else "🌉 MQTT Proxy (internet via app): ❌ Tidak terhubung"
        self.proxy_status_label.setText(text)
        self.proxy_status_label.setStyleSheet(f"padding: 4px; font-weight: 600; color: {color};")

    def upsert_mqtt_node(self, info: dict):
        node_id = info["node_id"]
        is_new = node_id not in self._mqtt_nodes
        self._mqtt_nodes[node_id] = info
        # Re-render sorted by most-recently-seen first.
        rows = sorted(self._mqtt_nodes.values(), key=lambda x: x["ts"], reverse=True)
        self.mqtt_nodes_table.setRowCount(len(rows))
        for row, n in enumerate(rows):
            self.mqtt_nodes_table.setItem(row, 0, QTableWidgetItem(n["node_id"]))
            self.mqtt_nodes_table.setItem(row, 1, QTableWidgetItem(n["gateway_id"]))
            self.mqtt_nodes_table.setItem(row, 2, QTableWidgetItem(n["channel"]))
            self.mqtt_nodes_table.setItem(row, 3, QTableWidgetItem(fmt_timestamp(n["ts"])))

    # -- device's own native connection status ---------------------------
    def show_connection_status(self, status):
        """status: protobuf DeviceConnectionStatus (see bridge.request_connection_status)."""
        parts = []
        if status.HasField("wifi"):
            w = status.wifi
            parts.append(
                f"📶 WiFi: {_yn(w.status.is_connected)}"
                + (f" — SSID '{w.ssid}', RSSI {w.rssi} dBm, IP {_ip_str(w.status.ip_address)}"
                   if w.status.is_connected else "")
            )
            parts.append(f"☁️ MQTT (native WiFi): {_yn(w.status.is_mqtt_connected)}")
        if status.HasField("ethernet"):
            parts.append(f"🔌 Ethernet: {_yn(status.ethernet.status.is_connected)}")
        if status.HasField("bluetooth"):
            parts.append(f"🔵 Bluetooth: {_yn(status.bluetooth.is_connected)}")
        self.conn_status_label.setText("   ·   ".join(parts) if parts else "Tidak ada info koneksi dari perangkat.")

    def populate_from_interface(self, iface):
        rows = []
        my_info = getattr(iface, "myInfo", None)
        metadata = getattr(iface, "metadata", None)
        if my_info is not None:
            rows.extend(flatten(proto_to_dict(my_info)))
        if metadata is not None:
            rows.extend(flatten(proto_to_dict(metadata)))

        node_num = getattr(my_info, "my_node_num", None) if my_info else None
        my_node = None
        if node_num is not None:
            for n in dict(getattr(iface, "nodes", {}) or {}).values():
                if n.get("num") == node_num:
                    my_node = n
                    break
        if my_node:
            rows.extend(flatten(my_node, prefix="node."))

        self.table.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(str(k)))
            self.table.setItem(i, 1, QTableWidgetItem(str(v)))

    def clear(self):
        self.table.setRowCount(0)
        self.conn_status_label.setText("")
        self.check_conn_btn.setEnabled(False)
        self.set_proxy_connected(False)
        self._mqtt_nodes.clear()
        self.mqtt_nodes_table.setRowCount(0)
