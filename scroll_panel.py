# /// script
# requires-python = ">=3.12"
# dependencies = ["pywinauto>=0.6.9; sys_platform == 'win32'", "psutil>=7", "Pillow>=11"]
# ///
"""Windows panel scrolling: x y wheel-steps (not macOS pixel units)."""
import sys
from capcut_windows.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["scroll",*sys.argv[1:]]))
