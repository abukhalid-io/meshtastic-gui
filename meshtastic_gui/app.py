"""App bootstrap — shared by main.py (run from source) and the installed
console-script entry point (run after `pip install`)."""
import sys

from PySide6.QtWidgets import QApplication

from . import theme
from .icon import build_app_icon
from .main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Meshtastic GUI")
    app.setStyle("Fusion")
    app.setStyleSheet(theme.stylesheet())

    icon = build_app_icon()
    app.setWindowIcon(icon)

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
