"""Entry point for running from source (no install needed): `python main.py`.
Once installed (`pip install .`), use the `meshtastic-gui` command instead —
see meshtastic_gui/app.py for the actual bootstrap."""
from meshtastic_gui.app import main

if __name__ == "__main__":
    main()
