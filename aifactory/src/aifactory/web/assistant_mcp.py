"""Stdio MCP transport for the guide gate; no shell or arbitrary file access.

The dashboard fixes the HAIFA home and repository scope at process startup. Tool
arguments are passed as an argv array to the existing gate, never to a shell.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from aifactory.web import assistant_gate as gate

TOOL_NAME = "guide"
TOOL = {
    "name": TOOL_NAME,
    "description": (
        "Read HAIFA factory data. Pass argv WITHOUT ./guide. Examples: "
        '["repos"], ["factory", "REPO_ID", "task", "runs", "TASK_ID"], '
        '["sql", "REPO_ID", "SELECT * FROM task_runs LIMIT 10"]. ' + gate.USAGE
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"argv": {"type": "array", "items": {"type": "string"}}},
        "required": ["argv"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
}


def dispatch(message: dict[str, Any], home: Path, repo_id: str | None) -> dict[str, Any]:
    """Handle one MCP request; startup scope cannot be changed by a tool call."""
    method = message.get("method")
    params = message.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    if method == "initialize":
        requested = params.get("protocolVersion")
        supported = ("2024-11-05", "2025-03-26", "2025-06-18")
        return {
            "protocolVersion": requested if requested in supported else supported[-1],
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "haifa-guide", "version": "1"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [TOOL]}
    if method != "tools/call" or params.get("name") != TOOL_NAME:
        raise ValueError("only the guide tool is available")
    args = params.get("arguments")
    if not isinstance(args, dict) or set(args) != {"argv"}:
        raise ValueError("guide requires only argv; the repository scope is fixed")
    argv = args["argv"]
    if not isinstance(argv, list) or not all(isinstance(word, str) for word in argv):
        raise ValueError("argv must be an array of strings")
    code, output = gate.execute(argv, home, repo_id=repo_id)
    return {"content": [{"type": "text", "text": output}], "isError": code != 0}


def serve(home: Path, repo_id: str | None, source: TextIO, target: TextIO) -> None:
    """MCP uses one JSON-RPC message per line on stdio, including on Windows."""
    for line in source:
        message: Any = None
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
                raise ValueError("expected a JSON-RPC 2.0 object")
            if "id" not in message:  # initialized/cancelled notifications have no reply
                continue
            reply = {"result": dispatch(message, home, repo_id)}
        except (ValueError, TypeError) as exc:
            reply = {"error": {"code": -32602, "message": str(exc)}}
        except Exception:  # noqa: BLE001 - never disclose internal errors or secrets
            reply = {"error": {"code": -32603, "message": "guide data request failed"}}
        request_id = message.get("id") if isinstance(message, dict) else None
        target.write(json.dumps({"jsonrpc": "2.0", "id": request_id, **reply}) + "\n")
        target.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--repo")
    args = parser.parse_args()
    serve(args.home, args.repo, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
