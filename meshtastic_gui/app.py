"""App bootstrap — shared by main.py (run from source) and the installed
console-script entry point (run after `pip install`)."""
import sys

from PySide6.QtWidgets import QApplication

from . import theme
from .icon import build_app_icon
from .main_window import MainWindow


def _fix_windows_taskbar_icon():
    """Without this, Windows groups the running process under its own
    'Application User Model ID' and — since nothing set one — falls back to
    showing python.exe's generic icon in the taskbar, even though the window
    itself already carries our icon. Must run before QApplication exists."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "meshtastic-gui.desktop.app"
        )
    except Exception:  # noqa: BLE001
        pass


def main():
    _fix_windows_taskbar_icon()
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
