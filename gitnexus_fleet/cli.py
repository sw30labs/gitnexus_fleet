import os
import sys
import time
import subprocess
import threading
import webbrowser
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    TaskProgressColumn, TimeElapsedColumn,
)
from rich.panel import Panel
from rich.rule import Rule
from rich import box
from rich.prompt import Prompt, Confirm

from .config import (
    console, PROJECT_ROOT, CLONE_BASE,
    DASHBOARD_PORT, MAX_CLONE_WORKERS, MAX_INDEX_WORKERS,
)
from .github import GitHubAPI
from .mcp import GitNexusMCP
from .repos import RepoStatus, clone_repo, index_repo
from .server import DashboardHandler, run_server


def print_header():
    console.print()
    console.print(Panel(
        "[bold cyan]GitNexus Fleet Scanner[/bold cyan]\n"
        "[dim]Clone · Index · Analyze · Query[/dim]",
        box=box.DOUBLE_EDGE,
        border_style="cyan",
        padding=(0, 4),
    ))
    console.print()


def print_repo_table(repos: list[dict]):
    t = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan", show_lines=False)
    t.add_column("#",          style="dim",   width=4)
    t.add_column("Repository", style="white", min_width=30)
    t.add_column("Language",   style="yellow")
    t.add_column("Last push",  style="dim")
    t.add_column("Visibility", style="green")

    for i, r in enumerate(repos, 1):
        lang   = r.get("language") or "—"
        pushed = (r.get("pushed_at") or "")[:10]
        vis    = "[dim]private[/dim]" if r["private"] else "public"
        t.add_row(str(i), r["name"], lang, pushed, vis)

    console.print(t)
    console.print(f"  [dim]Total: {len(repos)} repositories[/dim]\n")


def _run_phase(label, repos, statuses, worker_fn, max_workers, token=None):
    """Run clone or index phase with progress display."""
    console.print(Rule(f"[bold cyan]{label}[/bold cyan]"))
    if "Index" in label:
        console.print("  [dim]Embeddings are off by default for speed.[/dim]\n")

    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30, style="cyan", complete_style="green"),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        overall = progress.add_task(f"[cyan]{label}[/cyan]", total=len(repos))
        tasks = {}
        for r in repos:
            tasks[r["name"]] = progress.add_task(
                f"  [dim]{r['name'][:40]}[/dim]", total=1
            )

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            if token is not None:
                futures = {
                    pool.submit(worker_fn, r, statuses[r["name"]], token): r
                    for r in repos
                }
            else:
                futures = {
                    pool.submit(worker_fn, r, statuses[r["name"]]): r
                    for r in repos
                }
            for future in as_completed(futures):
                r  = futures[future]
                st = future.result()
                ok = st.cloned if token is not None else st.indexed
                if ok:
                    progress.update(tasks[r["name"]], completed=1,
                                    description=f"  [green]✓[/green] {r['name'][:40]}")
                else:
                    extra = f" [dim]{st.error or ''}[/dim]" if token is None else ""
                    progress.update(tasks[r["name"]], completed=1,
                                    description=f"  [red]✗[/red] {r['name'][:40]}{extra}")
                progress.advance(overall)


def main():
    print_header()

    # ── Token ────────────────────────────────────────────────────────────────
    load_dotenv(PROJECT_ROOT / ".env.gitnexus")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    openai_api_key = os.environ.get("OPENAI_API_KEY", "").strip()

    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key

    if not token:
        token = Prompt.ask("[cyan]GitHub Personal Access Token[/cyan]", password=True)
    if not token:
        console.print("[red]No token provided. Exiting.[/red]")
        sys.exit(1)

    # ── Fetch repos ──────────────────────────────────────────────────────────
    console.print("[cyan]Fetching repository list from GitHub...[/cyan]")
    try:
        gh   = GitHubAPI(token)
        user = gh.get_user()
        repos = gh.get_all_repos()
    except requests.HTTPError as e:
        console.print(f"[red]GitHub API error: {e}[/red]")
        sys.exit(1)

    console.print(f"  Authenticated as [bold]{user['login']}[/bold] "
                  f"([dim]{user.get('name', '')}[/dim])\n")
    print_repo_table(repos)

    if not Confirm.ask(f"[cyan]Clone and index all {len(repos)} repos?[/cyan]", default=True):
        console.print("[yellow]Aborted.[/yellow]")
        sys.exit(0)

    CLONE_BASE.mkdir(parents=True, exist_ok=True)

    # ── Check gitnexus ───────────────────────────────────────────────────────
    console.print("\n[cyan]Checking gitnexus...[/cyan]")
    try:
        subprocess.run(["npx", "-y", "gitnexus@latest", "--version"],
                       capture_output=True, check=True, timeout=60)
        console.print("  [green]✓[/green] gitnexus available\n")
    except Exception as e:
        console.print(f"  [red]✗ gitnexus not available: {e}[/red]\n"
                      "  Install Node.js and try again.")
        sys.exit(1)

    # ── Initialize statuses ──────────────────────────────────────────────────
    statuses = {}
    for r in repos:
        statuses[r["name"]] = RepoStatus(r["name"])

    # ── Phase 1: Clone ───────────────────────────────────────────────────────
    _run_phase("Phase 1 — Cloning", repos, statuses, clone_repo,
               MAX_CLONE_WORKERS, token=token)

    cloned_count = sum(1 for s in statuses.values() if s.cloned)
    console.print(f"\n  Cloned [bold green]{cloned_count}[/bold green] / {len(repos)} repos\n")

    # ── Phase 2: Index ───────────────────────────────────────────────────────
    cloned_repos = [r for r in repos if statuses[r["name"]].cloned]
    _run_phase("Phase 2 — Indexing", cloned_repos, statuses, index_repo,
               MAX_INDEX_WORKERS)

    indexed_count = sum(1 for s in statuses.values() if s.indexed)
    console.print(f"\n  Indexed [bold green]{indexed_count}[/bold green] / {len(cloned_repos)} repos\n")

    if indexed_count == 0:
        console.print("[red]No repos were indexed. Cannot start dashboard.[/red]")
        sys.exit(1)

    # ── Phase 3: Start MCP + Dashboard ───────────────────────────────────────
    console.print(Rule("[bold cyan]Phase 3 — Dashboard[/bold cyan]"))

    console.print("  Starting MCP server...", end="")
    mcp_client = GitNexusMCP()
    mcp_client.start()
    if mcp_client.ready:
        console.print(" [green]ready[/green]")
    else:
        console.print(" [red]failed — queries may not work[/red]")

    DashboardHandler.mcp_client = mcp_client
    DashboardHandler.statuses = statuses

    console.print("  Starting dashboard server...", end="")
    t = threading.Thread(target=run_server, args=(DASHBOARD_PORT,), daemon=True)
    t.start()
    time.sleep(0.5)
    console.print(f" [green]ready[/green]")

    url = f"http://localhost:{DASHBOARD_PORT}"
    console.print(f"\n  [bold green]Dashboard:[/bold green] {url}\n")
    webbrowser.open(url)

    # ── Summary table ────────────────────────────────────────────────────────
    summary = Table(box=box.SIMPLE, header_style="bold cyan", show_lines=False, padding=(0, 1))
    summary.add_column("Repository", style="white")
    summary.add_column("Cloned",     style="green", justify="center")
    summary.add_column("Indexed",    style="green", justify="center")
    summary.add_column("Note",       style="dim")
    for name, st in statuses.items():
        cloned_sym  = "[green]✓[/green]" if st.cloned  else "[red]✗[/red]"
        indexed_sym = "[green]✓[/green]" if st.indexed else "[red]✗[/red]"
        note = st.error or ""
        summary.add_row(name, cloned_sym, indexed_sym, note[:60])
    console.print(summary)

    console.print(Panel(
        f"[bold]Fleet scanner running[/bold]\n\n"
        f"  Dashboard  →  {url}\n"
        f"  MCP tools  →  query · impact · context · cypher\n\n"
        f"  [dim]Press Ctrl+C to stop[/dim]",
        border_style="green",
        box=box.ROUNDED,
        padding=(1, 4),
    ))

    # ── Keep alive ───────────────────────────────────────────────────────────
    def shutdown(sig, frame):
        console.print("\n[yellow]Shutting down...[/yellow]")
        mcp_client.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        time.sleep(1)
