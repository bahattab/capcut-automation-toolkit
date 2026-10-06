# /// script
# requires-python = ">=3.12"
# dependencies = ["pywinauto>=0.6.9; sys_platform == 'win32'", "psutil>=7", "Pillow>=11"]
# ///
"""Compatibility entry point: uv run capcut-bridge.py <command>."""
from capcut_windows.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
