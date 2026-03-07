import subprocess

from .config import CLONE_BASE


class RepoStatus:
    def __init__(self, name: str):
        self.name = name
        self.cloned = False
        self.indexed = False
        self.error = None


def clone_repo(repo: dict, status: RepoStatus, token: str) -> RepoStatus:
    dest = CLONE_BASE / repo["name"]
    clone_url = repo["clone_url"].replace("https://", f"https://{token}@")
    try:
        if dest.exists():
            subprocess.run(
                ["git", "-C", str(dest), "pull", "--ff-only", "-q"],
                check=True, capture_output=True,
            )
        else:
            subprocess.run(
                ["git", "clone", "--depth=1", "-q", clone_url, str(dest)],
                check=True, capture_output=True,
            )
        status.cloned = True
    except subprocess.CalledProcessError as e:
        status.error = f"clone: {e.stderr.decode()[:80] if e.stderr else str(e)}"
    return status


def index_repo(repo: dict, status: RepoStatus) -> RepoStatus:
    if not status.cloned:
        return status
    dest = CLONE_BASE / repo["name"]
    try:
        subprocess.run(
            ["npx", "-y", "gitnexus@latest", "analyze", "--embeddings"],
            cwd=str(dest),
            check=True,
            capture_output=True,
            timeout=300,
        )
        status.indexed = True
    except subprocess.TimeoutExpired:
        status.error = "index: timeout (>5min)"
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode()[:120] if e.stderr else str(e)
        status.error = f"index: {stderr}"
    return status
