"""Generates the app icon at runtime — a small mesh-network glyph (nodes
connected by radio links) on the Meshtastic-green rounded square. This is an
original mark inspired by the Meshtastic color palette, not a reproduction
of the project's trademarked logo."""
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QColor, QIcon, QPen, QBrush

from . import theme


def build_app_icon(size: int = 256) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    # Rounded square background in Meshtastic green.
    bg_rect = QRectF(0, 0, size, size)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.ACCENT))
    radius = size * 0.22
    p.drawRoundedRect(bg_rect, radius, radius)

    # Mesh glyph: three nodes connected by links, dark on green.
    dark = QColor(theme.ACCENT_TEXT)
    link_pen = QPen(dark)
    link_pen.setWidthF(size * 0.045)
    link_pen.setCapStyle(Qt.RoundCap)
    p.setPen(link_pen)

    top = QPointF(size * 0.5, size * 0.28)
    left = QPointF(size * 0.28, size * 0.68)
    right = QPointF(size * 0.72, size * 0.68)

    p.drawLine(top, left)
    p.drawLine(top, right)
    p.drawLine(left, right)

    node_r = size * 0.09
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(dark))
    for pt in (top, left, right):
        p.drawEllipse(pt, node_r, node_r)

    p.end()
    return QIcon(pix)
