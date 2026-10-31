"""Entry point for the packaged Swangz app (PyInstaller). Opens the window; `Swangz run claude` etc. also work."""
import sys

from swangz_client.cli import main

if __name__ == "__main__":
    sys.exit(main())
