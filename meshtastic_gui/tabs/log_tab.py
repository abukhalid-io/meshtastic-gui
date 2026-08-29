from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit, QPushButton, QHBoxLayout

from ..utils import fmt_timestamp
import time


class LogTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        layout.addWidget(self.text)

        row = QHBoxLayout()
        clear_btn = QPushButton("Bersihkan log")
        clear_btn.clicked.connect(self.text.clear)
        row.addWidget(clear_btn)
        row.addStretch(1)
        layout.addLayout(row)

    def append(self, message: str):
        ts = fmt_timestamp(time.time())
        self.text.appendPlainText(f"[{ts}] {message}")
