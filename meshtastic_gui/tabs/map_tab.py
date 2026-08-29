"""A lightweight offline 'mesh map' — plots nodes that have reported a GPS
position on a simple 2D canvas (equirectangular projection, no tile imagery
needed/possible without internet). This mirrors the spirit of the Android
app's Map tab: see where your nodes are relative to each other at a glance."""
import math

from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from .. import theme
from ..utils import node_display_id, fmt_timestamp

MARGIN = 40
MARKER_R = 9


def _color_for_id(node_id: str) -> QColor:
    h = abs(hash(node_id))
    hue = h % 360
    c = QColor()
    c.setHsv(hue, 200, 255)
    return c


class MapCanvas(QWidget):
    node_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(320)
        self._nodes = {}  # node_id -> node dict (must have position.lat/lon)
        self._marker_positions = {}  # node_id -> QPointF (screen space, updated on paint)

    def set_nodes(self, nodes: dict):
        self._nodes = nodes
        self.update()

    def _positioned_nodes(self):
        out = []
        for node_id, node in self._nodes.items():
            pos = node.get("position", {}) or {}
            lat, lon = pos.get("latitude"), pos.get("longitude")
            if lat is None or lon is None:
                continue
            out.append((node_id, node, lat, lon))
        return out

    def paintEvent(self, event):  # noqa: N802 - Qt override
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.PANEL))

        points = self._positioned_nodes()
        self._marker_positions = {}

        if not points:
            p.setPen(QColor(theme.TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignCenter, "Belum ada node dengan data posisi GPS.")
            p.end()
            return

        lats = [pt[2] for pt in points]
        lons = [pt[3] for pt in points]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        # Guard against a single point / degenerate span.
        lat_span = max(lat_max - lat_min, 1e-4)
        lon_span = max(lon_max - lon_min, 1e-4)

        w = max(self.width() - 2 * MARGIN, 10)
        h = max(self.height() - 2 * MARGIN, 10)
        # Latitude compression so shapes aren't wildly distorted at higher latitudes.
        lat_mid_rad = math.radians((lat_min + lat_max) / 2)
        lon_scale = max(math.cos(lat_mid_rad), 0.15)

        def to_screen(lat, lon):
            x = MARGIN + ((lon - lon_min) * lon_scale) / (lon_span * lon_scale) * w
            y = MARGIN + (1 - (lat - lat_min) / lat_span) * h
            return QPointF(x, y)

        # Links: draw a faint line from every node to every other (mesh feel) —
        # skip if too many nodes to stay legible.
        if len(points) <= 25:
            pen = QPen(QColor(theme.BORDER))
            pen.setWidthF(1)
            p.setPen(pen)
            screen_pts = [to_screen(lat, lon) for _, _, lat, lon in points]
            for i in range(len(screen_pts)):
                for j in range(i + 1, len(screen_pts)):
                    p.drawLine(screen_pts[i], screen_pts[j])

        font = QFont()
        font.setPointSize(8)
        p.setFont(font)

        for node_id, node, lat, lon in points:
            pt = to_screen(lat, lon)
            self._marker_positions[node_id] = pt
            color = _color_for_id(node_id)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(pt, MARKER_R, MARKER_R)

            user = node.get("user", {}) or {}
            label = user.get("shortName") or node_id[-4:]
            p.setPen(QColor(theme.TEXT))
            text_rect = QRectF(pt.x() - 30, pt.y() + MARKER_R + 2, 60, 16)
            p.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)

        p.end()

    def mousePressEvent(self, event):  # noqa: N802 - Qt override
        click = event.position() if hasattr(event, "position") else event.pos()
        cx, cy = click.x(), click.y()
        for node_id, pt in self._marker_positions.items():
            if (pt.x() - cx) ** 2 + (pt.y() - cy) ** 2 <= (MARKER_R + 4) ** 2:
                self.node_clicked.emit(node_id)
                return


class MapTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Peta node (offline, posisi relatif — bukan citra satelit)"))
        top.addStretch(1)
        layout.addLayout(top)

        self.canvas = MapCanvas()
        self.canvas.node_clicked.connect(self._on_node_clicked)
        layout.addWidget(self.canvas, 1)

        self.detail_label = QLabel("Klik sebuah node di peta untuk lihat detail singkat.")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self._nodes = {}

    def clear(self):
        self._nodes = {}
        self.canvas.set_nodes({})
        self.detail_label.setText("Klik sebuah node di peta untuk lihat detail singkat.")

    def upsert_node(self, node: dict):
        node_id = node_display_id(node)
        self._nodes[node_id] = node
        self.canvas.set_nodes(self._nodes)

    def _on_node_clicked(self, node_id):
        node = self._nodes.get(node_id, {})
        user = node.get("user", {}) or {}
        pos = node.get("position", {}) or {}
        name = user.get("longName", node_id)
        lat, lon = pos.get("latitude"), pos.get("longitude")
        alt = pos.get("altitude")
        last_heard = fmt_timestamp(node.get("lastHeard"))
        parts = [f"{name} ({node_id})", f"Posisi: {lat:.5f}, {lon:.5f}"]
        if alt is not None:
            parts.append(f"Altitude: {alt} m")
        parts.append(f"Terakhir terdengar: {last_heard}")
        self.detail_label.setText(" · ".join(parts))
