"""Creates a desktop shortcut/launcher for the installed app.

Run once after installing (`pip install .` / `pipx install ...`):

    meshtastic-gui-shortcut

Windows -> a .lnk on the Desktop.
Linux   -> a .desktop launcher on the Desktop + the app-menu entry
           (~/.local/share/applications), so it also shows up in search.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _find_entry_point() -> Path | None:
    """Best-effort path to the installed `meshtastic-gui` launcher, resolved
    relative to whichever Python is currently running this script (so it
    works the same whether installed via pipx, a venv, or --user)."""
    scripts_dir = Path(sys.executable).parent
    name = "meshtastic-gui.exe" if sys.platform == "win32" else "meshtastic-gui"
    candidate = scripts_dir / name
    return candidate if candidate.exists() else None


def _render_icon(path: Path, fmt: str, size: int = 256):
    """Draws the app icon (see icon.py) straight to a file — no external
    asset needed. Requires a QApplication instance to exist first."""
    from PySide6.QtWidgets import QApplication
    from .icon import build_app_icon

    _ = QApplication.instance() or QApplication([])
    icon = build_app_icon(size)
    if not icon.pixmap(size, size).save(str(path), fmt):
        raise RuntimeError(f"Gagal menyimpan ikon ke {path}")


def install_windows(target_exe: Path, assets_dir: Path):
    ico_path = assets_dir / "icon.ico"
    _render_icon(ico_path, "ICO")

    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    lnk_path = desktop / "Meshtastic GUI.lnk"

    ps_script = (
        "$WshShell = New-Object -ComObject WScript.Shell\n"
        f'$Shortcut = $WshShell.CreateShortcut("{lnk_path}")\n'
        f'$Shortcut.TargetPath = "{target_exe}"\n'
        f'$Shortcut.WorkingDirectory = "{Path.home()}"\n'
        f'$Shortcut.IconLocation = "{ico_path}"\n'
        '$Shortcut.Description = "Meshtastic GUI"\n'
        "$Shortcut.Save()\n"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        check=True,
    )
    print(f"Shortcut dibuat: {lnk_path}")


def install_linux(target_exe: Path, assets_dir: Path):
    png_path = assets_dir / "icon.png"
    _render_icon(png_path, "PNG")

    entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Meshtastic GUI\n"
        "Comment=GUI untuk konfigurasi & chat perangkat Meshtastic\n"
        f'Exec="{target_exe}"\n'
        f"Icon={png_path}\n"
        "Terminal=false\n"
        "Categories=Utility;Network;\n"
    )

    apps_dir = Path.home() / ".local/share/applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    apps_file = apps_dir / "meshtastic-gui.desktop"
    apps_file.write_text(entry)
    apps_file.chmod(0o755)
    print(f"Entry menu aplikasi dibuat: {apps_file}")

    desktop_dir = Path.home() / "Desktop"
    if desktop_dir.is_dir():
        desktop_file = desktop_dir / "meshtastic-gui.desktop"
        desktop_file.write_text(entry)
        desktop_file.chmod(0o755)
        # GNOME/Nautilus refuses to launch untrusted .desktop files by
        # default — mark it trusted so double-click works right away.
        try:
            subprocess.run(
                ["gio", "set", str(desktop_file), "metadata::trusted", "true"],
                check=False, capture_output=True,
            )
        except FileNotFoundError:
            pass
        print(f"Shortcut dibuat: {desktop_file}")
    else:
        print("Folder ~/Desktop tidak ada — dilewati (entry menu aplikasi tetap dibuat).")


def main():
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    target_exe = _find_entry_point()
    if target_exe is None:
        print("Tidak menemukan executable 'meshtastic-gui' yang terinstall.")
        print("Install dulu dengan `pip install .` (atau pipx), baru jalankan `meshtastic-gui-shortcut` lagi.")
        sys.exit(1)

    if sys.platform == "win32":
        install_windows(target_exe, assets_dir)
    elif sys.platform.startswith("linux"):
        install_linux(target_exe, assets_dir)
    else:
        print(f"Platform '{sys.platform}' belum didukung untuk shortcut otomatis.")
        sys.exit(1)


if __name__ == "__main__":
    main()
