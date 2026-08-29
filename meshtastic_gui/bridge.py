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
    few seconds)."""

    connected = Signal(object)   # emits the live interface instance
    failed = Signal(str)

    def __init__(self, mode, serial_port=None, tcp_host=None, parent=None):
        super().__init__(parent)
        self.mode = mode  # "serial" or "tcp"
        self.serial_port = serial_port
        self.tcp_host = tcp_host

    def run(self):
        try:
            if self.mode == "serial":
                import meshtastic.serial_interface as si
                iface = si.SerialInterface(devPath=self.serial_port or None)
            else:
                import meshtastic.tcp_interface as ti
                iface = ti.TCPInterface(hostname=self.tcp_host)
            self.connected.emit(iface)
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            _force_release_stream(self.serial_port if self.mode == "serial" else None)
            self.failed.emit(f"{e}\n{traceback.format_exc(limit=2)}")


class MeshtasticBridge(QObject):
    """Owns the current interface and republishes pubsub events as Qt signals."""

    node_updated = Signal(dict)          # one node dict from interface.nodes
    text_received = Signal(dict)         # {channel, fromId, toId, text, ts, isDirect}
    connection_established = Signal(dict)  # myInfo-ish summary
    connection_lost = Signal(str)
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
        if not self.iface:
            raise RuntimeError("Not connected")
        self.iface.sendText(text, destinationId=destination_id, channelIndex=channel_index)
