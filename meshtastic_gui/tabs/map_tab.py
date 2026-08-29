"""Real basemap for node positions, via Leaflet (bundled locally by pyqtlet2 —
no internet needed for the map *library* itself, only for tile *images*).

Works two ways:
  - Online: default tile source is the public OpenStreetMap tile servers.
  - Offline: pick "Custom / offline" and point it at any XYZ tile URL you
    control — a local tile server serving pre-downloaded tiles, an MBTiles
    extraction served over http://localhost, or a file:// path to a folder
    of {z}/{x}/{y}.png tiles. Leaflet doesn't care where tiles come from.

Most Meshtastic nodes never report a GPS position (no GPS hardware, or it's
a stationary base node) — in that case use "Set posisi tetap" below to pin
your own node's location manually (meshtastic-python's setFixedPosition).
"""
import colorsys

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QDoubleSpinBox, QMessageBox
)
from pyqtlet2 import L, MapWidget

from .. import theme
from ..utils import node_display_id, fmt_timestamp

DEFAULT_CENTER = [-2.5, 118.0]  # Indonesia-ish — a sane default before any data
DEFAULT_ZOOM = 5

TILE_PRESETS = {
    "OpenStreetMap (online)": (
        "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        {"attribution": "© OpenStreetMap contributors", "maxZoom": 19},
    ),
}
CUSTOM_LABEL = "Custom / offline (URL manual)..."


def _color_for_id(node_id: str) -> str:
    h = abs(hash(node_id))
    hue = (h % 360) / 360
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 0.95)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def _esc(value) -> str:
    """Leaflet popup content is spliced straight into a JS double-quoted
    string literal by pyqtlet2 — escape what would otherwise break out."""
    return (str(value).replace("\\", "\\\\").replace('"', "'")
            .replace("\n", "<br>"))


class MapTab(QWidget):
    def __init__(self, on_set_fixed_position, parent=None):
        """on_set_fixed_position(lat: float, lon: float, alt: int) -> None"""
        super().__init__(parent)
        self._on_set_fixed_position = on_set_fixed_position

        self._nodes = {}     # node_id -> node dict
        self._markers = {}   # node_id -> L.circleMarker
        self._my_node_id = None
        self._has_fit_once = False

        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Sumber peta:"))
        self.tile_combo = QComboBox()
        self.tile_combo.addItems(list(TILE_PRESETS.keys()) + [CUSTOM_LABEL])
        self.tile_combo.currentIndexChanged.connect(self._on_tile_source_changed)
        top.addWidget(self.tile_combo)

        self.tile_url_edit = QLineEdit()
        self.tile_url_edit.setPlaceholderText(
            "mis. http://localhost:8080/{z}/{x}/{y}.png atau file:///D:/tiles/{z}/{x}/{y}.png"
        )
        self.tile_url_edit.setVisible(False)
        top.addWidget(self.tile_url_edit, 1)

        self.apply_tile_btn = QPushButton("Terapkan")
        self.apply_tile_btn.setVisible(False)
        self.apply_tile_btn.clicked.connect(self._apply_custom_tile)
        top.addWidget(self.apply_tile_btn)
        layout.addLayout(top)

        self.map_widget = MapWidget()
        # pyqtlet2 loads its map.html from a file:// URL. QtWebEngine treats
        # local-file pages as untrusted by default and blocks them from
        # fetching remote resources — which silently kills every tile
        # request, leaving Leaflet's JS/markers working but the basemap
        # permanently blank. Explicitly allow it for this one page.
        try:
            from PySide6.QtWebEngineCore import QWebEngineSettings
            # NOTE: pyqtlet2's MapWidget exposes `.page` as a @property
            # (not QWebEngineView's own `.page()` method) — no parens here.
            self.map_widget.page.settings().setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
        except Exception:  # noqa: BLE001 - tiles just won't load if this ever fails
            pass
        layout.addWidget(self.map_widget, 1)
        self.map = L.map(self.map_widget)
        self.map.setView(DEFAULT_CENTER, DEFAULT_ZOOM)
        self._tile_layer = None
        self._set_tile_layer(*TILE_PRESETS["OpenStreetMap (online)"])

        self.hint_label = QLabel(
            "Belum ada node dengan posisi GPS — ini normal, kebanyakan node Meshtastic tidak "
            "punya modul GPS. Klik-kanan node di tab Nodes untuk 'Minta posisi', atau set posisi "
            "tetap untuk node kamu sendiri di bawah."
        )
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        fixed_row = QHBoxLayout()
        fixed_row.addWidget(QLabel("Set posisi tetap node saya — Lat:"))
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-90, 90)
        self.lat_spin.setDecimals(6)
        fixed_row.addWidget(self.lat_spin)
        fixed_row.addWidget(QLabel("Lon:"))
        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(-180, 180)
        self.lon_spin.setDecimals(6)
        fixed_row.addWidget(self.lon_spin)
        self.set_fixed_btn = QPushButton("Terapkan")
        self.set_fixed_btn.setObjectName("primary")
        self.set_fixed_btn.clicked.connect(self._apply_fixed_position)
        fixed_row.addWidget(self.set_fixed_btn)
        layout.addLayout(fixed_row)

        self.set_enabled(False)

    # -- tile source ---------------------------------------------------------
    def _set_tile_layer(self, url, options):
        if self._tile_layer is not None:
            self.map.removeLayer(self._tile_layer)
        self._tile_layer = L.tileLayer(url, options)
        self._tile_layer.addTo(self.map)

    def _on_tile_source_changed(self, _index):
        text = self.tile_combo.currentText()
        is_custom = text == CUSTOM_LABEL
        self.tile_url_edit.setVisible(is_custom)
        self.apply_tile_btn.setVisible(is_custom)
        if not is_custom:
            self._set_tile_layer(*TILE_PRESETS[text])

    def _apply_custom_tile(self):
        url = self.tile_url_edit.text().strip()
        if not url:
            return
        self._set_tile_layer(url, {"maxZoom": 19, "attribution": "Custom tile source"})

    # -- lifecycle -------------------------------------------------------
    def set_enabled(self, enabled: bool):
        for w in (self.lat_spin, self.lon_spin, self.set_fixed_btn):
            w.setEnabled(enabled)

    def clear(self):
        for marker in self._markers.values():
            self.map.removeLayer(marker)
        self._markers.clear()
        self._nodes.clear()
        self._my_node_id = None
        self._has_fit_once = False
        self.hint_label.setVisible(True)
        self.map.setView(DEFAULT_CENTER, DEFAULT_ZOOM)

    def set_my_node_id(self, node_id):
        self._my_node_id = node_id
        # If we already drew our own marker under the "not yet known" color,
        # refresh it now that we know it's "us".
        if node_id in self._nodes:
            self._draw_marker(node_id, self._nodes[node_id])

    # -- node data ---------------------------------------------------------
    def upsert_node(self, node: dict):
        node_id = node_display_id(node)
        self._nodes[node_id] = node
        self._draw_marker(node_id, node)

    def _draw_marker(self, node_id, node):
        pos = node.get("position", {}) or {}
        lat, lon = pos.get("latitude"), pos.get("longitude")
        if lat is None or lon is None:
            return

        user = node.get("user", {}) or {}
        name = user.get("longName") or user.get("shortName") or node_id
        is_me = node_id == self._my_node_id
        color = theme.ACCENT if is_me else _color_for_id(node_id)
        radius = 10 if is_me else 7

        marker = self._markers.get(node_id)
        if marker is None:
            marker = L.circleMarker([lat, lon], {
                "radius": radius, "color": color, "fillColor": color,
                "fillOpacity": 0.85, "weight": 2,
            })
            marker.addTo(self.map)
            self._markers[node_id] = marker
        else:
            marker.setLatLng([lat, lon])

        battery = (node.get("deviceMetrics", {}) or {}).get("batteryLevel")
        last_heard = fmt_timestamp(node.get("lastHeard"))
        lines = [f"<b>{_esc(name)}</b>" + (" (saya)" if is_me else ""), _esc(node_id)]
        if battery is not None:
            lines.append(f"Baterai: {_esc(battery)}%")
        lines.append(f"Terakhir: {_esc(last_heard)}")
        marker.bindPopup("<br>".join(lines))

        self.hint_label.setVisible(False)
        self._maybe_fit_bounds()

    def _maybe_fit_bounds(self):
        if self._has_fit_once:
            return
        coords = []
        for node in self._nodes.values():
            pos = node.get("position", {}) or {}
            if pos.get("latitude") is not None and pos.get("longitude") is not None:
                coords.append([pos["latitude"], pos["longitude"]])
        if not coords:
            return
        self._has_fit_once = True
        if len(coords) == 1:
            self.map.setView(coords[0], 15)
        else:
            self.map.fitBounds(coords)

    # -- set fixed position ---------------------------------------------
    def _apply_fixed_position(self):
        lat, lon = self.lat_spin.value(), self.lon_spin.value()
        if lat == 0 and lon == 0:
            QMessageBox.warning(self, "Koordinat kosong", "Isi lat/lon dulu (0,0 bukan lokasi valid).")
            return
        try:
            self._on_set_fixed_position(lat, lon, 0)
            QMessageBox.information(self, "Berhasil", "Posisi tetap dikirim ke perangkat.")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal", str(e))
