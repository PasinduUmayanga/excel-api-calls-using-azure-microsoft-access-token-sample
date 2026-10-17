"""Convenience launcher: `python main.py` (desktop) or `python main.py --web` (browser)."""

from apirunner.app import main

if __name__ in {"__main__", "__mp_main__"}:
    main()
