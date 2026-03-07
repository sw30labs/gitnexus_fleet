from pathlib import Path
from rich.console import Console

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLONE_BASE = Path.home() / ".gitnexus_fleet" / "repos"
DASHBOARD_PORT = 8765
MAX_CLONE_WORKERS = 5
MAX_INDEX_WORKERS = 3
STATIC_DIR = Path(__file__).resolve().parent / "static"

console = Console()
