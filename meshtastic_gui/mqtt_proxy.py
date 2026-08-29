"""MQTT client-proxy bridge: lets the mesh node reach the internet/MQTT
broker THROUGH this app's own internet connection over the serial/TCP link,
instead of the node needing its own WiFi. This is the same mechanism the
official Android/iOS apps use when "Proxy to client" is enabled in the
node's MQTT module config — meshtastic-python exposes the low-level
primitives (sendMqttClientProxyMessage, the "meshtastic.mqttclientproxymessage"
pubsub event) but does not implement the bridge itself, so this module does.

Protocol reference: pyqtlet2/meshtastic-python source + the open-source
LN4CY/mqtt-proxy project (github.com/LN4CY/mqtt-proxy), which documents the
`{root}/2/e/#` wildcard-subscribe pattern and the loop-prevention rules
followed here (skip our own outbound topic, skip retained-by-default).
"""
import logging
import ssl
import threading
import time

from PySide6.QtCore import QObject, Signal
from pubsub import pub

logger = logging.getLogger(__name__)


class MqttProxy(QObject):
    """Owns a paho-mqtt client that bridges one connected meshtastic node's
    MQTT module config to the real broker, over this machine's internet
    connection. Start once per connection; stop on disconnect."""

    status_changed = Signal(str)   # human-readable state, e.g. "Terhubung ke mqtt.meshtastic.org"
    connected_changed = Signal(bool)  # the thing to trust for a "proxy is up" indicator
    node_seen = Signal(dict)       # {"node_id", "gateway_id", "channel", "ts"} — a node heard via the broker
    log = Signal(str)

    # Small boards (ESP32-C3 etc) have a tiny admin/serial queue. A busy
    # community broker aggregates traffic from many separate physical mesh
    # networks over msh/<root>/2/e/# — far more volume than any single LoRa
    # mesh would ever produce. Blindly forwarding every message down to the
    # device (as an earlier version of this file did) can flood that queue
    # faster than the device can drain it, which is a very plausible cause
    # of the device becoming unresponsive during heavy proxy use. Cap it.
    FORWARD_MIN_INTERVAL_SECS = 0.5  # ~2 msg/s max forwarded to the device

    def __init__(self, parent=None):
        super().__init__(parent)
        self._client = None
        self._iface = None
        self._own_node_id = None
        self._root = "msh"
        self._subscribed_pubsub = False
        self._connected = False
        self._last_forward_ts = 0.0
        self._dropped_since_log = 0
        self._last_drop_log_ts = 0.0

    @property
    def is_connected(self):
        return self._connected

    # -- lifecycle -----------------------------------------------------------
    def start(self, iface, mqtt_config, own_node_id):
        """iface: the live meshtastic interface. mqtt_config: node.moduleConfig.mqtt.
        own_node_id: "!xxxxxxxx" string, used for basic loop prevention."""
        self.stop()  # replace any previous session

        if not mqtt_config.enabled:
            self.log.emit("MQTT proxy: modul MQTT tidak enabled di perangkat, tidak dijalankan.")
            return
        if not mqtt_config.proxy_to_client_enabled:
            self.log.emit("MQTT proxy: 'Proxy to client' tidak diaktifkan di perangkat, tidak dijalankan.")
            return

        address = mqtt_config.address or "mqtt.meshtastic.org"
        port = 8883 if "mqtt.meshtastic.org" in address else 1883
        use_tls = mqtt_config.tls_enabled or "mqtt.meshtastic.org" in address
        self._root = mqtt_config.root or "msh"
        self._iface = iface
        self._own_node_id = own_node_id
        self._last_forward_ts = 0.0
        self._dropped_since_log = 0
        self._last_drop_log_ts = 0.0

        import paho.mqtt.client as mqtt
        client_id = f"MeshtasticGUI-{own_node_id or 'unknown'}"
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if mqtt_config.username and mqtt_config.password:
            client.username_pw_set(mqtt_config.username, mqtt_config.password)
        if use_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            client.tls_set_context(context)

        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        self._client = client

        self.log.emit(f"MQTT proxy: menghubungkan ke {address}:{port} (TLS={'ya' if use_tls else 'tidak'})...")
        try:
            client.connect_async(address, port, keepalive=60)
            client.loop_start()
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"MQTT proxy: gagal konek ke broker: {e}")
            self.status_changed.emit(f"Gagal konek broker: {e}")
            self._client = None
            return

        pub.subscribe(self._on_proxy_message, "meshtastic.mqttclientproxymessage")
        self._subscribed_pubsub = True

    def stop(self):
        if self._subscribed_pubsub:
            try:
                pub.unsubscribe(self._on_proxy_message, "meshtastic.mqttclientproxymessage")
            except Exception:  # noqa: BLE001
                pass
            self._subscribed_pubsub = False

        # Detach immediately so is_running/is_connected reflect the new
        # state right away and nothing else can reach this client anymore.
        client, self._client = self._client, None
        self._iface = None
        if self._connected:
            self._connected = False
            self.connected_changed.emit(False)

        if client is not None:
            # client.loop_stop()/disconnect() block waiting for paho's own
            # network thread to join. stop() runs on the GUI thread (called
            # right from the connection-lost handler) — if that network
            # thread is itself stuck (e.g. the link just died mid-write),
            # calling this synchronously here would freeze/deadlock the
            # whole app. Tear it down on a throwaway daemon thread instead;
            # nothing else holds a reference to `client` anymore, so this is
            # safe to finish fully in the background.
            def _teardown():
                try:
                    client.loop_stop()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    client.disconnect()
                except Exception:  # noqa: BLE001
                    pass

            threading.Thread(target=_teardown, daemon=True, name="mqtt-proxy-teardown").start()

    @property
    def is_running(self):
        return self._client is not None

    # -- broker -> device ------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc, props=None):
        if rc == 0:
            topic = f"{self._root}/2/e/#"
            client.subscribe(topic)
            self.log.emit(f"MQTT proxy: terhubung ke broker, subscribe '{topic}'.")
            self.status_changed.emit("Terhubung ke broker MQTT")
            self._connected = True
            self.connected_changed.emit(True)
        else:
            self.log.emit(f"MQTT proxy: koneksi broker gagal (rc={rc}).")
            self.status_changed.emit(f"Gagal konek broker (rc={rc})")
            self._connected = False
            self.connected_changed.emit(False)

    def _on_disconnect(self, client, userdata, flags, rc=0, props=None):
        self.status_changed.emit("Terputus dari broker MQTT")
        self._connected = False
        self.connected_changed.emit(False)
        if rc != 0:
            self.log.emit(f"MQTT proxy: terputus dari broker (rc={rc}), paho akan reconnect otomatis.")

    def _on_message(self, client, userdata, message):
        # Track for the 'seen via broker' panel regardless of whether we
        # actually forward it down to the device — this is just a UI list,
        # it doesn't touch the device's queue.
        self._track_node(message)
        try:
            # Loop prevention: don't hand the device back its own uplinked
            # traffic, and skip retained state dumps (historical, not new).
            if self._own_node_id and message.topic.endswith(self._own_node_id):
                return
            if message.retain:
                return

            now = time.time()
            if now - self._last_forward_ts < self.FORWARD_MIN_INTERVAL_SECS:
                self._dropped_since_log += 1
                if now - self._last_drop_log_ts > 10:
                    self.log.emit(
                        f"MQTT proxy: {self._dropped_since_log} pesan broker dilewati "
                        f"(rate-limit, melindungi antrian perangkat) dalam 10 detik terakhir."
                    )
                    self._dropped_since_log = 0
                    self._last_drop_log_ts = now
                return
            self._last_forward_ts = now

            iface = self._iface
            if iface is None:
                return
            iface.sendMqttClientProxyMessage(message.topic, message.payload)
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"MQTT proxy: gagal meneruskan pesan broker->device: {e}")

    def _track_node(self, message):
        """Best-effort: peek at the envelope to report which node this
        traffic came from, for the 'nodes seen via the broker' panel. The
        packet header (from/gateway/channel) is readable even when the
        payload itself (packet.encrypted) is not — no decryption needed."""
        try:
            from meshtastic.protobuf import mqtt_pb2
            env = mqtt_pb2.ServiceEnvelope()
            env.ParseFromString(message.payload)
            from_num = getattr(env.packet, "from", 0)
            if not from_num:
                return
            self.node_seen.emit({
                "node_id": f"!{from_num:08x}",
                "gateway_id": env.gateway_id or "-",
                "channel": env.channel_id or "-",
                "ts": time.time(),
            })
        except Exception:  # noqa: BLE001 - tracking is a nice-to-have, never fatal
            pass

    # -- device -> broker (fires on the interface's own reader thread) ----
    def _on_proxy_message(self, proxymessage, interface):
        client = self._client
        if client is None:
            return
        try:
            payload = proxymessage.data if proxymessage.data else proxymessage.text.encode("utf-8")
            client.publish(proxymessage.topic, payload, retain=proxymessage.retained)
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"MQTT proxy: gagal meneruskan pesan device->broker: {e}")
