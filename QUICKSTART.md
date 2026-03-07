**Option 1**
Create a .env.gitnexus file with your token:
    GITHUB_TOKEN=ghp_yourtoken
    
    Then run:
    ```bash
    python gitnexus_fleet.py
    ```

**Option 2**
You need Node.js installed, then:

```bash
# Install globally
npm install -g gitnexus

# Go to any repo you have locally
cd ~/your-project

# Index it
npx gitnexus analyze

# Optional: start the web UI connected to your local index
gitnexus serve
# Then open gitnexus.vercel.app — it auto-detects the local server
```

That's it. The index lives in `.gitnexus/` inside the repo.

---

**Option 3— Hook it into Claude Code**

If you're already using Claude Code, this is one command:

```bash
claude mcp add gitnexus -- npx -y gitnexus@latest mcp
```

After that, Claude Code gets the full 7-tool MCP interface — impact analysis, context lookups, Cypher queries — on any repo you've indexed.

---

**Good test repo to start with**

Pick something you know well so you can validate what the graph tells you. A medium-sized Python or TypeScript project with real call chains is more interesting than a toy app — the clustering and process tracing are where it shines. If you want a public repo to experiment on, something like **FastAPI** or **LangChain** itself would be revealing.