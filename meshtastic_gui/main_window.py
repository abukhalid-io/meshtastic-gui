from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QComboBox,
    QPushButton, QRadioButton, QButtonGroup, QLineEdit, QLabel, QMessageBox,
    QStatusBar
)

from .bridge import MeshtasticBridge, ConnectWorker
from .tabs.dashboard_tab import DashboardTab
from .tabs.nodes_tab import NodesTab
from .tabs.messages_tab import MessagesTab
from .tabs.channels_tab import ChannelsTab
from .tabs.settings_tab import SettingsTab
from .tabs.map_tab import MapTab
from .tabs.log_tab import LogTab


def _channel_role_name(ch):
    try:
        return type(ch).Role.Name(ch.role)
    except Exception:  # noqa: BLE001
        return str(ch.role)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meshtastic GUI")
        self.resize(1080, 720)

        self.bridge = MeshtasticBridge(self)
        self.connect_worker = None
        self._connected = False

        self._build_ui()
        self._wire_bridge()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)

        conn_row = QHBoxLayout()

        self.mode_serial = QRadioButton("Serial (USB)")
        self.mode_tcp = QRadioButton("TCP/IP (WiFi)")
        self.mode_serial.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.mode_serial)
        mode_group.addButton(self.mode_tcp)
        self.mode_serial.toggled.connect(self._on_mode_toggled)
        conn_row.addWidget(self.mode_serial)
        conn_row.addWidget(self.mode_tcp)

        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(220)
        conn_row.addWidget(self.port_combo)

        self.refresh_ports_btn = QPushButton("Refresh")
        self.refresh_ports_btn.clicked.connect(self.refresh_ports)
        conn_row.addWidget(self.refresh_ports_btn)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("IP node, mis. 192.168.1.50 atau meshtastic.local")
        self.host_edit.setVisible(False)
        conn_row.addWidget(self.host_edit)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("primary")
        self.connect_btn.clicked.connect(self._on_connect_clicked)
        conn_row.addWidget(self.connect_btn)

        conn_row.addStretch(1)
        root.addLayout(conn_row)

        self.tabs = QTabWidget()
        self.dashboard_tab = DashboardTab()
        self.nodes_tab = NodesTab(actions={
            "favorite": self._favorite_node,
            "unfavorite": self._unfavorite_node,
            "ignore": self._ignore_node,
            "unignore": self._unignore_node,
            "traceroute": self._traceroute_node,
            "request_position": self._request_position_node,
            "remove": self._remove_node,
            "message": self._open_dm_with_node,
        })
        self.messages_tab = MessagesTab(on_send=self._send_text)
        self.channels_tab = ChannelsTab(
            on_refresh=self._get_channels,
            on_import_url=self._import_channel_url,
            on_export_url=self._export_channel_url,
        )
        self.settings_tab = SettingsTab(
            on_set_owner=self._set_owner,
            on_write_config=self._write_config,
            on_reboot=self._reboot,
            on_factory_reset=self._factory_reset,
            on_clean_node_db=self._clean_node_db,
            on_open_channels=lambda: self.tabs.setCurrentWidget(self.channels_tab),
        )
        self.map_tab = MapTab()
        self.log_tab = LogTab()

        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.nodes_tab, "Nodes")
        self.tabs.addTab(self.messages_tab, "Pesan")
        self.tabs.addTab(self.map_tab, "Peta")
        self.tabs.addTab(self.channels_tab, "Channels")
        self.tabs.addTab(self.settings_tab, "Pengaturan")
        self.tabs.addTab(self.log_tab, "Log")
        root.addWidget(self.tabs)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Belum terhubung")

        self.refresh_ports()

    def _on_mode_toggled(self, checked):
        self.port_combo.setVisible(checked)
        self.refresh_ports_btn.setVisible(checked)
        self.host_edit.setVisible(not checked)

    def refresh_ports(self):
        self.port_combo.clear()
        try:
            from serial.tools import list_ports
            ports = list(list_ports.comports())
        except Exception as e:  # noqa: BLE001
            self.log_tab.append(f"Gagal membaca daftar port: {e}")
            ports = []
        if not ports:
            self.port_combo.addItem("(tidak ada port terdeteksi)", None)
            return
        for p in ports:
            self.port_combo.addItem(f"{p.device} - {p.description}", p.device)

    # -------------------------------------------------------------- bridge
    def _wire_bridge(self):
        self.bridge.node_updated.connect(self._on_node_updated)
        self.bridge.text_received.connect(self.messages_tab.add_incoming)
        self.bridge.log.connect(self.log_tab.append)
        self.bridge.connection_established.connect(self._on_connection_established)
        self.bridge.connection_lost.connect(self._on_connection_lost)

    def _on_node_updated(self, node):
        self.nodes_tab.upsert_node(node)
        self.map_tab.upsert_node(node)
        self.messages_tab.update_known_nodes(self.nodes_tab.known_nodes())

    # ---------------------------------------------------------- connect UI
    def _on_connect_clicked(self):
        if self._connected:
            self._disconnect()
            return

        if self.mode_serial.isChecked():
            port = self.port_combo.currentData()
            if not port:
                QMessageBox.warning(self, "Tidak ada port", "Pilih port serial dulu, atau klik Refresh.")
                return
            worker = ConnectWorker(mode="serial", serial_port=port)
        else:
            host = self.host_edit.text().strip()
            if not host:
                QMessageBox.warning(self, "Host kosong", "Isi alamat IP/hostname node dulu.")
                return
            worker = ConnectWorker(mode="tcp", tcp_host=host)

        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Menghubungkan...")
        self.statusBar().showMessage("Menghubungkan ke perangkat...")

        worker.connected.connect(self._on_worker_connected)
        worker.failed.connect(self._on_worker_failed)
        self.connect_worker = worker
        worker.start()

    def _on_worker_connected(self, iface):
        self.bridge.attach(iface)
        self.dashboard_tab.populate_from_interface(iface)
        self._prefill_owner(iface)
        try:
            self.channels_tab.refresh()
        except Exception as e:  # noqa: BLE001
            self.log_tab.append(f"Tidak bisa membaca channel awal: {e}")

        try:
            self.settings_tab.build(iface.localNode)
            self._prefill_owner_settings(iface)
        except Exception as e:  # noqa: BLE001
            self.log_tab.append(f"Tidak bisa membangun halaman pengaturan: {e}")

        self._connected = True
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Disconnect")
        self.dashboard_tab.set_status("Terhubung", connected=True)
        self.statusBar().showMessage("Terhubung")
        self.messages_tab.set_enabled(True)
        self.channels_tab.set_enabled(True)
        self.log_tab.append("Koneksi berhasil dibuka.")

    def _on_worker_failed(self, message):
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Connect")
        self.statusBar().showMessage("Gagal terhubung")
        self.log_tab.append(f"Gagal koneksi: {message}")
        QMessageBox.warning(self, "Gagal terhubung", message.splitlines()[0])

    def _on_connection_established(self, summary):
        self.log_tab.append(f"meshtastic.connection.established: {summary}")

    def _on_connection_lost(self, reason):
        self.log_tab.append(reason)
        if self._connected:
            self._disconnect(silent=True)

    def _disconnect(self, silent=False):
        self.bridge.detach()
        self._connected = False
        self.connect_btn.setText("Connect")
        self.dashboard_tab.set_status("Tidak terhubung", connected=False)
        self.dashboard_tab.clear()
        self.messages_tab.set_enabled(False)
        self.messages_tab.update_known_nodes({})
        self.channels_tab.set_enabled(False)
        self.channels_tab.clear()
        self.settings_tab.clear()
        self.nodes_tab.clear()
        self.map_tab.clear()
        self.statusBar().showMessage("Terputus" if not silent else "Koneksi terputus tak terduga")

    # ----------------------------------------------------------- actions
    def _require_iface(self):
        if not self.bridge.iface:
            raise RuntimeError("Belum terhubung ke perangkat")
        return self.bridge.iface

    def _require_node(self):
        iface = self._require_iface()
        node = getattr(iface, "localNode", None)
        if node is None:
            raise RuntimeError("localNode tidak tersedia dari interface ini")
        return node

    def _send_text(self, text, channel_index, destination_id="^all"):
        try:
            self.bridge.send_text(text, channel_index=channel_index, destination_id=destination_id)
            self.messages_tab.add_outgoing(text, channel_index, destination_id)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal kirim pesan", str(e))

    def _open_dm_with_node(self, node_id):
        self.tabs.setCurrentWidget(self.messages_tab)
        self.messages_tab.select_dm_target(node_id)

    def _prefill_owner(self, iface):
        self._my_user = None
        try:
            node_num = getattr(iface.myInfo, "my_node_num", None)
            for n in dict(getattr(iface, "nodes", {}) or {}).values():
                if n.get("num") == node_num:
                    self._my_user = n.get("user", {}) or {}
                    return
        except Exception as e:  # noqa: BLE001
            self.log_tab.append(f"Tidak bisa membaca nama owner saat ini: {e}")

    def _prefill_owner_settings(self, iface):
        user = getattr(self, "_my_user", None) or {}
        self.settings_tab.prefill_owner(user.get("longName", ""), user.get("shortName", ""))

    def _set_owner(self, long_name, short_name):
        node = self._require_node()
        node.setOwner(long_name=long_name or None, short_name=short_name or None)
        self.log_tab.append(f"Owner diset: long='{long_name}' short='{short_name}'")

    def _write_config(self, config_name):
        node = self._require_node()
        node.writeConfig(config_name)
        self.log_tab.append(f"Config '{config_name}' ditulis ke perangkat.")

    def _reboot(self):
        node = self._require_node()
        node.reboot()
        self.log_tab.append("Perintah reboot dikirim.")

    def _factory_reset(self):
        node = self._require_node()
        node.factoryReset()
        self.log_tab.append("Perintah factory reset dikirim.")

    def _clean_node_db(self):
        node = self._require_node()
        node.resetNodeDb()
        self.log_tab.append("Perintah bersihkan node database dikirim.")

    # -- per-node actions (Nodes tab context menu) --------------------------
    def _favorite_node(self, node_id):
        self._require_node().setFavorite(node_id)
        self.log_tab.append(f"{node_id} dijadikan favorit.")

    def _unfavorite_node(self, node_id):
        self._require_node().removeFavorite(node_id)
        self.log_tab.append(f"{node_id} dibatalkan dari favorit.")

    def _ignore_node(self, node_id):
        self._require_node().setIgnored(node_id)
        self.log_tab.append(f"{node_id} diabaikan.")

    def _unignore_node(self, node_id):
        self._require_node().removeIgnored(node_id)
        self.log_tab.append(f"{node_id} tidak diabaikan lagi.")

    def _remove_node(self, node_id):
        self._require_node().removeNode(node_id)
        self.log_tab.append(f"{node_id} dihapus dari node database.")

    def _traceroute_node(self, node_id):
        iface = self._require_iface()
        iface.sendTraceRoute(node_id, hopLimit=7)
        self.log_tab.append(f"Trace route dikirim ke {node_id} (lihat Log untuk hasil).")

    def _request_position_node(self, node_id):
        iface = self._require_iface()
        iface.sendPosition(destinationId=node_id, wantResponse=True)
        self.log_tab.append(f"Permintaan posisi dikirim ke {node_id}.")

    # -- channels ------------------------------------------------------------
    def _get_channels(self):
        node = self._require_node()
        if not node.channels:
            try:
                node.requestChannels()
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError("Data channel belum diterima dari perangkat, coba Refresh lagi sebentar lagi.")
        result = []
        for ch in node.channels:
            role = _channel_role_name(ch)
            if role == "DISABLED":
                continue
            name = ch.settings.name or ("Default" if role == "PRIMARY" else "")
            result.append({"index": ch.index, "role": role, "name": name})
        return result

    def _import_channel_url(self, url):
        node = self._require_node()
        node.setURL(url)
        self.log_tab.append(f"Channel URL di-import: {url}")

    def _export_channel_url(self):
        node = self._require_node()
        return node.getURL(includeAll=True)

    # ------------------------------------------------------------ lifecycle
    def closeEvent(self, event):
        try:
            self.bridge.detach()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
