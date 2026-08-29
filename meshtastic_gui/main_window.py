from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QComboBox,
    QPushButton, QRadioButton, QButtonGroup, QLineEdit, QLabel, QMessageBox,
    QStatusBar
)

from .bridge import MeshtasticBridge, ConnectWorker
from .debug_server import DebugServer
from .mqtt_proxy import MqttProxy
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


def _modem_preset_name(node):
    """When a channel's settings.name is empty, every other Meshtastic client
    (the phone app, the MQTT topic path itself — 'msh/ID/2/e/LongFast/...')
    falls back to displaying the radio's modem preset, e.g. 'LongFast'. We
    were instead showing a generic 'Default' placeholder, which looked like
    the channel had no real name at all."""
    try:
        from meshtastic.protobuf import config_pb2
        raw = config_pb2.Config.LoRaConfig.ModemPreset.Name(node.localConfig.lora.modem_preset)
        return "".join(word.capitalize() for word in raw.split("_"))
    except Exception:  # noqa: BLE001
        return None


class MainWindow(QMainWindow):
    # Extra full connect-attempt rounds (each with its own internal retries —
    # see ConnectWorker) the app will try on its own before finally giving up
    # and telling the user to power-cycle the device.
    AUTO_RECONNECT_MAX_ROUNDS = 2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meshtastic GUI")
        self.resize(1080, 720)

        self.bridge = MeshtasticBridge(self)
        self.mqtt_proxy = MqttProxy(self)
        self.connect_worker = None
        self._connected = False
        self._auto_reconnect_rounds_left = 0

        self._build_ui()
        self._wire_bridge()
        self.mqtt_proxy.log.connect(self.log_tab.append)
        self.mqtt_proxy.status_changed.connect(lambda s: self.log_tab.append(f"[MQTT proxy] {s}"))
        self.mqtt_proxy.connected_changed.connect(self.dashboard_tab.set_proxy_connected)
        self.mqtt_proxy.connected_changed.connect(lambda b: self.debug_server.set_state(mqtt_proxy_connected=b))
        self.mqtt_proxy.node_seen.connect(self.dashboard_tab.upsert_mqtt_node)
        self.mqtt_proxy.node_seen.connect(self._on_mqtt_node_seen)

        # -- local debug/control server (see debug_server.py) --------------
        # Lets an external tool read live state / trigger connect-disconnect
        # via plain HTTP instead of screenshotting the GUI and simulating
        # clicks, which is slow and gets confused by other windows.
        self.debug_server = DebugServer(port=8765, parent=self)
        original_log_append = self.log_tab.append

        def _append_and_mirror(msg):
            original_log_append(msg)
            self.debug_server.append_log(msg)

        self.log_tab.append = _append_and_mirror

        original_transcript_append = self.messages_tab.transcript.append

        def _append_transcript_and_mirror(html):
            original_transcript_append(html)
            # toPlainText() right here is still on the GUI thread (append()
            # only ever gets called from here) — safe, unlike calling it
            # from the HTTP handler's own thread would be.
            self.debug_server.set_state(transcript=self.messages_tab.transcript.toPlainText())

        self.messages_tab.transcript.append = _append_transcript_and_mirror

        self.debug_server.command_requested.connect(self._on_debug_command)
        self.debug_server.send_requested.connect(self._on_debug_send)
        self.debug_server.set_state(connected=False, mqtt_proxy_connected=False, node_count=0)
        self.debug_server.start()

    def _on_debug_command(self, command):
        if command == "connect" and not self._connected:
            self._on_connect_clicked()
        elif command == "disconnect" and self._connected:
            self._disconnect()

    def _on_debug_send(self, text, channel_index, destination_id):
        self._send_text(text, channel_index, destination_id)

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
        self.dashboard_tab = DashboardTab(on_check_connection_status=self._check_connection_status)
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
        self.map_tab = MapTab(on_set_fixed_position=self._set_fixed_position)
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
        self.bridge.connection_status_received.connect(self.dashboard_tab.show_connection_status)
        self.bridge.message_ack.connect(self.messages_tab.show_ack)

    def _on_node_updated(self, node):
        self.nodes_tab.upsert_node(node)
        self.map_tab.upsert_node(node)
        self.messages_tab.update_known_nodes(self.nodes_tab.known_nodes())
        self.debug_server.set_state(node_count=len(self.nodes_tab._nodes))

    def _on_mqtt_node_seen(self, info):
        """A node was heard via the MQTT broker (see mqtt_proxy.node_seen).
        Only add a stub row if we don't already know this node for real
        (via LoRa/local NodeDB) — never clobber real name/model/etc. with
        this bare, MQTT-only sighting."""
        node_id = info.get("node_id")
        if not node_id or self.nodes_tab.has_node(node_id):
            return
        stub = {
            "num": int(node_id[1:], 16),
            "lastHeard": info["ts"],
            "user": {"id": node_id, "hwModel": "🌐 via MQTT (bukan LoRa)"},
        }
        self.nodes_tab.upsert_node(stub)

    # ---------------------------------------------------------- connect UI
    def _build_connect_worker(self):
        """Returns a fresh ConnectWorker using the current mode/port-or-host
        fields, or None (with a warning shown) if they're not filled in."""
        if self.mode_serial.isChecked():
            port = self.port_combo.currentData()
            if not port:
                QMessageBox.warning(self, "Tidak ada port", "Pilih port serial dulu, atau klik Refresh.")
                return None
            return ConnectWorker(mode="serial", serial_port=port)
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Host kosong", "Isi alamat IP/hostname node dulu.")
            return None
        return ConnectWorker(mode="tcp", tcp_host=host)

    def _start_connect_worker(self, worker, status_text="Menghubungkan ke perangkat..."):
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Menghubungkan...")
        self.statusBar().showMessage(status_text)

        worker.connected.connect(self._on_worker_connected)
        worker.failed.connect(self._on_worker_failed)
        worker.retrying.connect(self._on_worker_retrying)
        self.connect_worker = worker
        worker.start()

    def _on_connect_clicked(self):
        if self._connected:
            self._disconnect()
            return

        self._auto_reconnect_rounds_left = self.AUTO_RECONNECT_MAX_ROUNDS
        worker = self._build_connect_worker()
        if worker is None:
            return
        self._start_connect_worker(worker)

    def _on_worker_retrying(self, attempt, max_attempts):
        text = f"Percobaan koneksi {attempt}/{max_attempts}..."
        self.statusBar().showMessage(text)
        self.log_tab.append(f"Menyambung ulang (percobaan {attempt}/{max_attempts})...")

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
        self._auto_reconnect_rounds_left = 0
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Disconnect")
        self.dashboard_tab.set_status("Terhubung", connected=True)
        self.statusBar().showMessage("Terhubung")
        self.messages_tab.set_enabled(True)
        self.channels_tab.set_enabled(True)
        self.map_tab.set_enabled(True)
        if self._my_node_id:
            self.map_tab.set_my_node_id(self._my_node_id)
        self.log_tab.append("Koneksi berhasil dibuka.")
        self.debug_server.set_state(
            connected=True, my_node_id=self._my_node_id,
            firmware_version=getattr(getattr(iface, "metadata", None), "firmware_version", None),
        )

        # The device just did a lot of work for us in one burst (NodeDB
        # dump, channels, settings/config reads) — starting the MQTT proxy
        # immediately piles broker traffic on right on top of that. In
        # practice the connection has been dying within ~1s of the proxy's
        # first forwarded message, right when it's least settled. Give it a
        # few seconds of breathing room first.
        self.log_tab.append("Menunggu perangkat stabil sebelum menyalakan MQTT proxy...")
        QTimer.singleShot(5000, lambda: self._start_mqtt_proxy_if_still_this_session(iface))

    def _start_mqtt_proxy_if_still_this_session(self, iface):
        if not self._connected or self.bridge.iface is not iface:
            return  # disconnected or reconnected to a different session already
        try:
            self.mqtt_proxy.start(iface, iface.localNode.moduleConfig.mqtt, self._my_node_id)
        except Exception as e:  # noqa: BLE001
            self.log_tab.append(f"Tidak bisa menjalankan MQTT proxy: {e}")

    def _on_worker_failed(self, message):
        rounds_left = getattr(self, "_auto_reconnect_rounds_left", 0)
        if rounds_left > 0:
            self._auto_reconnect_rounds_left = rounds_left - 1
            self.log_tab.append(
                f"Gagal koneksi (akan dicoba otomatis lagi, {rounds_left} percobaan tersisa): {message.splitlines()[0]}"
            )
            self.statusBar().showMessage("Gagal, mencoba ulang otomatis...")
            self.debug_server.set_state(connected=False, last_error=message.splitlines()[0])
            QTimer.singleShot(2000, self._retry_connect_worker)
            return

        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Connect")
        self.statusBar().showMessage("Gagal terhubung")
        self.log_tab.append(f"Gagal koneksi: {message}")
        self.debug_server.set_state(connected=False, last_error=message.splitlines()[0])
        QMessageBox.warning(
            self, "Gagal terhubung",
            message.splitlines()[0] + "\n\nSudah dicoba berkali-kali otomatis. "
            "Coba cabut-colok USB perangkatnya, lalu klik Connect lagi.",
        )

    def _retry_connect_worker(self):
        if self._connected:
            return  # something else already reconnected us
        worker = self._build_connect_worker()
        if worker is None:
            return
        self._start_connect_worker(worker, status_text="Menyambung ulang otomatis...")

    def _on_connection_established(self, summary):
        self.log_tab.append(f"meshtastic.connection.established: {summary}")

    def _on_connection_lost(self, reason):
        self.log_tab.append(reason)
        if self._connected:
            self._disconnect(silent=True)
            self._auto_reconnect_rounds_left = self.AUTO_RECONNECT_MAX_ROUNDS
            self.log_tab.append("Koneksi terputus tak terduga, mencoba menyambung ulang otomatis...")
            QTimer.singleShot(2000, self._retry_connect_worker)

    def _disconnect(self, silent=False):
        self.mqtt_proxy.stop()
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
        self.map_tab.set_enabled(False)
        self.map_tab.clear()
        self.statusBar().showMessage("Terputus" if not silent else "Koneksi terputus tak terduga")
        self.debug_server.set_state(connected=False, mqtt_proxy_connected=False, node_count=0)

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
            packet_id = self.bridge.send_text(text, channel_index=channel_index, destination_id=destination_id)
            self.messages_tab.add_outgoing(text, channel_index, destination_id, packet_id=packet_id)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal kirim pesan", str(e))

    def _open_dm_with_node(self, node_id):
        self.tabs.setCurrentWidget(self.messages_tab)
        self.messages_tab.select_dm_target(node_id)

    def _prefill_owner(self, iface):
        self._my_user = None
        self._my_node_id = None
        try:
            node_num = getattr(iface.myInfo, "my_node_num", None)
            for n in dict(getattr(iface, "nodes", {}) or {}).values():
                if n.get("num") == node_num:
                    self._my_user = n.get("user", {}) or {}
                    self._my_node_id = (self._my_user or {}).get("id") or f"!{node_num:08x}"
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

        # WiFi and Bluetooth share the ESP32's single 2.4GHz radio — running
        # both at once adds RF contention and extra peak current draw, which
        # is exactly what tends to brown out small boards (SuperMini-class)
        # once WiFi is also active. Keep them mutually exclusive.
        if config_name == "network" and node.localConfig.network.wifi_enabled:
            if node.localConfig.bluetooth.enabled:
                node.localConfig.bluetooth.enabled = False
                node.writeConfig("bluetooth")
                self.log_tab.append("WiFi diaktifkan -> Bluetooth otomatis dimatikan (satu radio 2.4GHz, hindari brownout).")
        elif config_name == "bluetooth" and node.localConfig.bluetooth.enabled:
            if node.localConfig.network.wifi_enabled:
                node.localConfig.network.wifi_enabled = False
                node.writeConfig("network")
                self.log_tab.append("Bluetooth diaktifkan -> WiFi otomatis dimatikan (satu radio 2.4GHz, hindari brownout).")

        node.writeConfig(config_name)
        self.log_tab.append(f"Config '{config_name}' ditulis ke perangkat.")

    def _check_connection_status(self):
        self.bridge.request_connection_status()
        self.log_tab.append("Meminta status koneksi (WiFi/Ethernet/Bluetooth/MQTT) ke perangkat...")

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

    def _set_fixed_position(self, lat, lon, alt=0):
        node = self._require_node()
        node.setFixedPosition(lat, lon, alt)
        self.log_tab.append(f"Posisi tetap diset: {lat:.6f}, {lon:.6f}")

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
        preset_name = _modem_preset_name(node)
        result = []
        for ch in node.channels:
            role = _channel_role_name(ch)
            if role == "DISABLED":
                continue
            name = ch.settings.name
            if not name and role == "PRIMARY":
                name = preset_name or "Default"
            result.append({"index": ch.index, "role": role, "name": name or ""})
        self.messages_tab.set_channel_names(result)
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
            self.mqtt_proxy.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.bridge.detach()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.debug_server.stop()
        except Exception:  # noqa: BLE001
            pass
        super().closeEvent(event)
