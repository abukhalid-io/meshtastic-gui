from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QComboBox, QLabel
)

from ..utils import fmt_timestamp

BROADCAST = "broadcast"
DIRECT = "direct"


class MessagesTab(QWidget):
    def __init__(self, on_send, parent=None):
        """on_send(text: str, channel_index: int, destination_id: str) -> None,
        called when the user hits Send; the tab does not talk to the
        bridge/interface directly. destination_id is "^all" for broadcast or
        a node id ("!aabbccdd") for a direct message."""
        super().__init__(parent)
        self._on_send = on_send

        layout = QVBoxLayout(self)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Kirim ke:"))
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(260)
        target_row.addWidget(self.target_combo, 1)
        layout.addLayout(target_row)

        self.transcript = QTextEdit()
        self.transcript.setReadOnly(True)
        layout.addWidget(self.transcript)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ketik pesan lalu Enter...")
        self.input.returnPressed.connect(self._send)
        row.addWidget(self.input, 1)

        self.send_btn = QPushButton("Kirim")
        self.send_btn.setObjectName("primary")
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)

        layout.addLayout(row)

        self._populate_broadcast_channels()
        self.set_enabled(False)

    def _populate_broadcast_channels(self):
        for ch in range(8):
            self.target_combo.addItem(f"📢 Broadcast — Channel {ch}", (BROADCAST, ch, "^all"))

    def set_channel_names(self, channels):
        """channels: list of {"index", "role", "name"} (see main_window._get_channels).
        Relabels the 8 fixed broadcast rows with the device's real channel
        names (e.g. 'LongFast') instead of the generic 'Channel N' — this is
        the channel we're actually broadcasting on when we hit Send."""
        names = {c["index"]: c.get("name") for c in channels if c.get("name")}
        for ch in range(8):
            name = names.get(ch)
            label = f"📢 Broadcast — {name} (ch{ch})" if name else f"📢 Broadcast — Channel {ch}"
            self.target_combo.setItemText(ch, label)

    def update_known_nodes(self, nodes: dict):
        """nodes: {node_id: display_label}. Preserves the current selection
        if the target is still present after refresh."""
        current_data = self.target_combo.currentData()

        # Drop old DM entries (everything after the 8 fixed broadcast rows).
        while self.target_combo.count() > 8:
            self.target_combo.removeItem(self.target_combo.count() - 1)

        for node_id, label in nodes.items():
            self.target_combo.addItem(f"💬 {label}", (DIRECT, 0, node_id))

        if current_data:
            for i in range(self.target_combo.count()):
                if self.target_combo.itemData(i) == current_data:
                    self.target_combo.setCurrentIndex(i)
                    break

    def select_dm_target(self, node_id):
        for i in range(self.target_combo.count()):
            data = self.target_combo.itemData(i)
            if data and data[0] == DIRECT and data[2] == node_id:
                self.target_combo.setCurrentIndex(i)
                return
        # Not in the list yet (node seen but not upserted into combo) — add it.
        self.target_combo.addItem(f"💬 {node_id}", (DIRECT, 0, node_id))
        self.target_combo.setCurrentIndex(self.target_combo.count() - 1)

    def set_enabled(self, enabled: bool):
        self.input.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)
        self.target_combo.setEnabled(enabled)

    def _send(self):
        text = self.input.text().strip()
        if not text:
            return
        data = self.target_combo.currentData()
        if not data:
            return
        _kind, channel_index, destination_id = data
        self._on_send(text, channel_index, destination_id)
        self.input.clear()

    def add_outgoing(self, text, channel_index, destination_id="^all"):
        ts = fmt_timestamp(__import__("time").time())
        target = "broadcast" if destination_id in (None, "^all") else destination_id
        self.transcript.append(f'<span style="color:#888">[{ts}] ch{channel_index} → {_escape(target)} </span>'
                                f'<b>Saya:</b> {_escape(text)}')

    def add_incoming(self, msg: dict):
        ts = fmt_timestamp(msg.get("ts"))
        who = msg.get("fromId", "?")
        ch = msg.get("channel", 0)
        direct = " (langsung)" if msg.get("isDirect") else ""
        self.transcript.append(
            f'<span style="color:#888">[{ts}] ch{ch}{direct} </span>'
            f'<b>{_escape(who)}:</b> {_escape(msg.get("text", ""))}'
        )

    def clear(self):
        self.transcript.clear()
        self.set_channel_names([])  # reset to generic "Channel N" labels


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
