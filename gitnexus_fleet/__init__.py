import sys
import subprocess


def _pip_install(*packages):
    subprocess.run(
        [sys.executable, "-m", "pip", "install", *packages, "--break-system-packages", "-q"],
        check=True,
    )


try:
    import rich  # noqa: F401
except ImportError:
    print("Installing rich...")
    _pip_install("rich")

try:
    import requests  # noqa: F401
except ImportError:
    print("Installing requests...")
    _pip_install("requests")

try:
    import dotenv  # noqa: F401
except ImportError:
    print("Installing python-dotenv...")
    _pip_install("python-dotenv")
