"""
Thread-safe bridge between the meshtastic-python interface (which runs its own
reader thread and fires callbacks via pypubsub) and the Qt GUI thread.

All meshtastic device I/O happens off the GUI thread. Results reach the UI
only through Qt signals, which are safe to cross threads with a queued
connection (PySide6 does this automatically for Auto-connections between
objects that live in different threads).
"""
import gc
import time
import traceback

from PySide6.QtCore import QObject, QThread, Signal
from pubsub import pub


def _force_release_stream(port_hint=None):
    """Best-effort cleanup for a meshtastic-python quirk: StreamInterface's
    own close()-on-failed-handshake tries to politely tell the device
    "disconnect" first (_sendDisconnect -> a write over the same broken
    link). When that write also fails, the exception is swallowed and the
    code path that actually closes the OS-level serial handle is never
    reached — the port stays open in exclusive mode for the rest of this
    process's life, so every later connect attempt gets "Access is denied"
    even though nothing in our own app is holding it.

    We reach into the garbage collector for any leftover StreamInterface
    (SerialInterface/TCPInterface) whose stream matches the port we just
    failed to open, and force its handle shut directly."""
    try:
        from meshtastic.stream_interface import StreamInterface
    except ImportError:
        return
    for obj in gc.get_objects():
        if not isinstance(obj, StreamInterface):
            continue
        stream = getattr(obj, "stream", None)
        if stream is None:
            continue
        if port_hint is not None and getattr(stream, "port", None) != port_hint:
            continue
        try:
            stream.close()
        except Exception:  # noqa: BLE001
            pass
        obj.stream = None


class ConnectWorker(QThread):
    """Opens a meshtastic interface off the GUI thread (the constructor blocks
    until the handshake with the device/node completes, which can take a
    few seconds).

    This particular class of hardware (small ESP32 boards especially) can go
    fully unresponsive for a handshake attempt and then work fine moments
    later — the failures are a clean ~30s silence, not "almost connected,
    needs more time", so a bigger timeout doesn't help. What does help in
    practice: just trying again a couple of times before giving up and
    asking for a physical reset."""

    connected = Signal(object)   # emits the live interface instance
    failed = Signal(str)
    retrying = Signal(int, int)  # (attempt_number, max_attempts) — before each retry

    MAX_ATTEMPTS = 3
    RETRY_DELAY_SECS = 3

    def __init__(self, mode, serial_port=None, tcp_host=None, parent=None):
        super().__init__(parent)
        self.mode = mode  # "serial" or "tcp"
        self.serial_port = serial_port
        self.tcp_host = tcp_host

    def run(self):
        last_error = None
        last_trace = ""
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            if attempt > 1:
                self.retrying.emit(attempt, self.MAX_ATTEMPTS)
                time.sleep(self.RETRY_DELAY_SECS)
            try:
                if self.mode == "serial":
                    import meshtastic.serial_interface as si
                    iface = si.SerialInterface(devPath=self.serial_port or None)
                else:
                    import meshtastic.tcp_interface as ti
                    iface = ti.TCPInterface(hostname=self.tcp_host)
                self.connected.emit(iface)
                return
            except Exception as e:  # noqa: BLE001 - surface any failure to the UI
                _force_release_stream(self.serial_port if self.mode == "serial" else None)
                last_error = e
                last_trace = traceback.format_exc(limit=2)
        self.failed.emit(f"{last_error}\n{last_trace}")


class MeshtasticBridge(QObject):
    """Owns the current interface and republishes pubsub events as Qt signals."""

    node_updated = Signal(dict)          # one node dict from interface.nodes
    text_received = Signal(dict)         # {channel, fromId, toId, text, ts, isDirect}
    connection_established = Signal(dict)  # myInfo-ish summary
    connection_lost = Signal(str)
    connection_status_received = Signal(object)  # protobuf.DeviceConnectionStatus
    message_ack = Signal(int, bool, str)  # (packet_id, success, reason) — did it actually get delivered
    log = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.iface = None
        self._subscribed = False

    # -- pubsub wiring -----------------------------------------------------
    def _subscribe(self):
        if self._subscribed:
            return
        pub.subscribe(self._on_receive, "meshtastic.receive")
        pub.subscribe(self._on_node_updated, "meshtastic.node.updated")
        pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")
        self._subscribed = True

    def attach(self, iface):
        """Call once a ConnectWorker hands back a live interface."""
        self.iface = iface
        self._subscribe()

    def detach(self):
        iface, self.iface = self.iface, None
        if iface is not None:
            port_hint = getattr(getattr(iface, "stream", None), "port", None)
            try:
                iface.close()
            except Exception as e:  # noqa: BLE001
                self.log.emit(f"Error while closing interface: {e}")
                _force_release_stream(port_hint)

    # -- pubsub callbacks (fire on the interface's own reader thread) ------
    def _on_receive(self, packet, interface):
        try:
            decoded = packet.get("decoded", {})
            portnum = decoded.get("portnum")
            if portnum == "TEXT_MESSAGE_APP":
                text = decoded.get("text", "")
                self.text_received.emit({
                    "channel": packet.get("channel", 0),
                    "fromId": packet.get("fromId", "?"),
                    "toId": packet.get("toId", "?"),
                    "text": text,
                    "ts": time.time(),
                    "isDirect": packet.get("toId") not in (None, "^all"),
                })
            else:
                self.log.emit(f"RX {portnum or '?'} from {packet.get('fromId', '?')}")
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"Error handling received packet: {e}")

    def _on_node_updated(self, node, interface):
        try:
            self.node_updated.emit(dict(node))
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"Error handling node update: {e}")

    def _on_connection_established(self, interface, topic=pub.AUTO_TOPIC):
        try:
            my_info = getattr(interface, "myInfo", None)
            node_num = getattr(my_info, "my_node_num", None) if my_info else None
            summary = {"nodeNum": node_num}
            self.connection_established.emit(summary)
            # Seed the node table with whatever the interface already knows.
            for node in dict(getattr(interface, "nodes", {}) or {}).values():
                self.node_updated.emit(dict(node))
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"Error handling connection established: {e}")

    def _on_connection_lost(self, interface, topic=pub.AUTO_TOPIC):
        self.connection_lost.emit("Connection lost")

    # -- outbound actions ----------------------------------------------------
    def send_text(self, text, channel_index=0, destination_id="^all"):
        """Sends with wantAck so we actually learn whether it was delivered
        (see message_ack) instead of only knowing it was handed to the
        radio. For a broadcast this is an "implicit ack" — the firmware
        considers it delivered once it hears a neighbor rebroadcast the
        same packet, not a guarantee every node in range got it, but it's
        a real signal rather than none at all. Returns the packet id so the
        caller can correlate the eventual ack/nak."""
        if not self.iface:
            raise RuntimeError("Not connected")

        # sendText() has no onResponseAckPermitted passthrough to sendData(),
        # so a plain-ACK (no error, no extra payload) response only reaches
        # our callback if the callback is literally named onAckNak — that's
        # a real name-based special case in meshtastic-python's response
        # dispatcher, not a typo.
        def onAckNak(packet):  # noqa: N802 - name is load-bearing, see above
            self._on_text_ack(packet)

        packet = self.iface.sendText(
            text, destinationId=destination_id, channelIndex=channel_index,
            wantAck=True, onResponse=onAckNak,
        )
        return getattr(packet, "id", None)

    def _on_text_ack(self, packet):
        try:
            decoded = packet.get("decoded", {}) or {}
            request_id = decoded.get("requestId")
            routing = decoded.get("routing", {}) or {}
            reason = routing.get("errorReason", "NONE")
            success = reason in (None, "NONE")
            if request_id is not None:
                self.message_ack.emit(request_id, success, reason or "NONE")
        except Exception as e:  # noqa: BLE001
            self.log.emit(f"Error handling message ack: {e}")

    def request_connection_status(self):
        """Asks the local node whether it currently has a live WiFi/Ethernet/
        MQTT/Bluetooth connection (DeviceConnectionStatus admin message).
        Fire-and-forget: the reply arrives later via connection_status_received."""
        if not self.iface:
            raise RuntimeError("Not connected")
        from meshtastic.protobuf import admin_pb2

        p = admin_pb2.AdminMessage()
        p.get_device_connection_status_request = True

        def on_response(packet):
            try:
                status = packet["decoded"]["admin"]["raw"].get_device_connection_status_response
                self.connection_status_received.emit(status)
            except Exception as e:  # noqa: BLE001
                self.log.emit(f"Gagal membaca status koneksi: {e}")

        # meshtastic-python has no public wrapper for this specific admin
        # message (unlike getMetadata()/setOwner()/etc.) — _sendAdmin is the
        # same private helper those public methods use internally.
        self.iface.localNode._sendAdmin(p, wantResponse=True, onResponse=on_response)
