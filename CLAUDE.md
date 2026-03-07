# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

GitNexus Fleet is a Python orchestrator that:
1. Authenticates with GitHub and fetches all repos owned by the user
2. Shallow-clones them into `~/.gitnexus_fleet/repos/`
3. Indexes each repo using the `gitnexus` npm package (`npx gitnexus@latest analyze --embeddings`), which creates a KuzuDB graph database in each repo's `.gitnexus/` directory
4. Starts an MCP stdio client connected to `gitnexus@latest mcp`
5. Serves a local web dashboard on port 8765 that proxies queries to the MCP server

## Running

```bash
pip install -r requirements.txt

# Either:
python run.py
# Or:
python -m gitnexus_fleet
```

Requires: Python 3, Node.js (for `npx gitnexus`), and a `GITHUB_TOKEN` in `.env.gitnexus` or environment.

## Package Structure

```
gitnexus_fleet/          # package
├── __init__.py          # auto-installs missing pip dependencies at import time
├── __main__.py          # python -m entry point
├── config.py            # constants (CLONE_BASE, DASHBOARD_PORT, worker counts), shared Rich console
├── github.py            # GitHubAPI — thin wrapper around GitHub REST API v3
├── mcp.py               # GitNexusMCP — thread-safe MCP stdio client (JSON-RPC over stdin/stdout)
├── nlq.py               # Natural language query layer — uses OpenAI Responses API to translate
│                        #   questions into MCP tool calls, then summarizes raw results
├── repos.py             # RepoStatus data class, clone_repo(), index_repo()
├── server.py            # DashboardHandler (BaseHTTPRequestHandler) + run_server()
├── cli.py               # Rich TUI helpers + main() orchestration (the entry point)
└── static/
    └── dashboard.html   # self-contained HTML/CSS/JS dashboard (no build step)
```

## Architecture

**Execution flow** (`cli.main()`):
1. Load `.env.gitnexus` via python-dotenv
2. Fetch repos from GitHub API (`github.GitHubAPI`)
3. **Phase 1** — Clone repos in parallel (`ThreadPoolExecutor`, 5 workers) via `repos.clone_repo`
4. **Phase 2** — Index repos in parallel (3 workers, 5-min timeout each) via `repos.index_repo`
5. **Phase 3** — Start MCP server (`mcp.GitNexusMCP`) + HTTP dashboard (`server.DashboardHandler`), open browser

**Server state passing**: `DashboardHandler` uses class-level attributes (`mcp_client`, `statuses`) set by `cli.main()` before the server thread starts.

**NLQ pipeline** (`nlq.py`, used by `/api/ask`):
1. `translate_question()` sends the user's natural language question to OpenAI with a system prompt describing the available MCP tools and graph schema, getting back a `{"tool", "args", "explanation"}` JSON object
2. The tool call is executed against the MCP server
3. `summarize_result()` sends the raw result back to OpenAI for a human-friendly summary
4. Requires `OPENAI_API_KEY` in `.env.gitnexus` or environment

**Dashboard API endpoints**:
- `GET /` — serves `dashboard.html`
- `GET /api/repos` — clone/index status of all repos
- `GET /api/health` — MCP readiness check
- `POST /api/query` — natural language search via MCP `query` tool
- `POST /api/impact` — dependency impact analysis via MCP `impact` tool
- `POST /api/context` — symbol context lookup via MCP `context` tool
- `POST /api/cypher` — raw Cypher queries via MCP `cypher` tool
- `POST /api/list_repos` — list indexed repos via MCP `list_repos` tool
- `POST /api/ask` — NLQ endpoint: translates question → tool call → summarized answer (requires OpenAI key)

## KuzuDB Graph Schema

The `gitnexus analyze` command builds a graph with:
- **Nodes**: `Function`, `Class`, `File`, `Community`
- **Edges**: `CodeRelation` with `type` property: `CALLS`, `IMPORTS`, `CONTAINS`, `EXTENDS`, `IMPLEMENTS`
- **Node properties**: `name`, `filePath`, `language`, `kind`, `signature`
- **Community properties**: `heuristicLabel`, `size`, `cohesion`

## Configuration Constants (config.py)

- `PROJECT_ROOT` — resolved path two levels up from config.py (the repo root)
- `CLONE_BASE` — `~/.gitnexus_fleet/repos/`
- `DASHBOARD_PORT` — `8765`
- `MAX_CLONE_WORKERS` — `5`
- `MAX_INDEX_WORKERS` — `3`
- `STATIC_DIR` — resolved absolute path to `gitnexus_fleet/static/`

## Important Notes

- `.env.gitnexus` contains credentials — never commit real tokens
- Dependencies auto-install at runtime if missing (via `__init__.py`)
- Embeddings are **on** by default during indexing (`--embeddings` flag in `repos.index_repo`); remove the flag to skip them for faster indexing
- If `OPENAI_API_KEY` is set, gitnexus uses OpenAI's `text-embedding-3` instead of local `snowflake-arctic-embed-xs`
- The `/api/ask` NLQ feature requires `OPENAI_API_KEY`; all other endpoints work without it
- The dashboard is a single self-contained HTML file with inline CSS/JS — no build tooling needed
- MCP communication is JSON-RPC 2.0 over stdio, with a threading lock for concurrent access
