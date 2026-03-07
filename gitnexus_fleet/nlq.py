import json
import os

import requests

TRANSLATE_PROMPT = """\
You translate natural language questions about code repositories into structured tool calls.

Available tools:
1. query — Natural language search across code. Args: {"query": "search terms"}
2. impact — Find what uses a symbol (upstream) or what a symbol uses (downstream). Args: {"target": "symbolName", "direction": "upstream|downstream|both"}
3. context — Get full 360° context for a symbol (callers, callees, file, community). Args: {"name": "symbolName"}
4. cypher — Run a raw Cypher query against the KuzuDB code graph. Args: {"query": "MATCH ..."}

Graph schema:
- Nodes: Function, Class, File, Community
- Edges: CodeRelation with type property: CALLS, IMPORTS, CONTAINS, EXTENDS, IMPLEMENTS
- Node properties: name, filePath, language, kind, signature
- Community properties: heuristicLabel, size, cohesion

Respond with ONLY a JSON object (no markdown fences):
{"tool": "tool_name", "args": {...}, "explanation": "brief explanation of what you're querying"}\
"""

SUMMARIZE_PROMPT = """\
You are a code intelligence assistant. The user asked a question about their codebase, \
a tool was executed against their code graph, and you are given the raw result.

Provide a clear, concise answer to the user's question based on the raw data. \
Use bullet points for lists. Reference specific file paths and symbol names from the data. \
If the data is empty or insufficient, say so honestly.\
"""


def _call_responses_api(instructions: str, user_input: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set — add it to .env.gitnexus")

    resp = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-5.3-chat-latest",
            "instructions": instructions,
            "input": user_input,
        },
        timeout=30,
    )
    resp.raise_for_status()

    data = resp.json()
    output_text = ""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text += content.get("text", "")
    return output_text


def translate_question(question: str) -> dict:
    """Translate a natural language question into a tool call dict."""
    text = _call_responses_api(TRANSLATE_PROMPT, question)
    text = text.strip()
    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    # Model sometimes duplicates the JSON object — use raw decoder to grab just the first one
    decoder = json.JSONDecoder()
    result, _ = decoder.raw_decode(text.strip())
    return result


def summarize_result(question: str, tool_name: str, raw_result: str) -> str:
    """Summarize raw MCP tool output into a human-friendly answer."""
    # Truncate very large results to stay within context
    truncated = raw_result[:8000]
    if len(raw_result) > 8000:
        truncated += "\n... (truncated)"

    return _call_responses_api(
        SUMMARIZE_PROMPT,
        f"Question: {question}\n\nTool used: {tool_name}\n\nRaw result:\n{truncated}",
    )
