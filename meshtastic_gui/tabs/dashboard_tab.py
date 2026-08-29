from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView

from .. import theme
from ..utils import proto_to_dict, flatten


class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.status_label = QLabel("Status: Not connected")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 4px;")
        layout.addWidget(self.status_label)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Field", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

    def set_status(self, text, connected=False):
        color = theme.ACCENT if connected else theme.DANGER
        self.status_label.setText(f"Status: {text}")
        self.status_label.setStyleSheet(f"font-weight: bold; font-size: 14px; padding: 4px; color: {color};")

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
