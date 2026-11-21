#!/usr/bin/env python3
"""Optional MCP stdio server for aria-dl. Python standard library only.

Not installed by install.sh. Run it as a local stdio server:

    python3 examples/mcp_server.py

Stdout is JSON-RPC only (one object per line). Logs go to stderr.
The tool list comes from `aria-dl tools`, so it stays in sync with the CLI.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARIA = os.environ.get("ARIA_DL_BIN", os.path.join(ROOT, "aria-dl"))
SPECS = None


def send(msg):
    data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def read_message():
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if not line.strip():
            continue
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
            while True:
                header = sys.stdin.buffer.readline()
                if header in (b"\r\n", b"\n", b""):
                    break
            return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))
        return json.loads(line.decode("utf-8"))


def tool_specs():
    global SPECS
    if SPECS is None:
        proc = subprocess.run([sys.executable, ARIA, "tools"], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "aria-dl tools failed")
        SPECS = {t["name"]: t for t in json.loads(proc.stdout)["tools"]}
    return SPECS


def mcp_tools():
    out = []
    for spec in tool_specs().values():
        out.append({
            "name": spec["name"],
            "description": spec["description"],
            "inputSchema": spec["input_schema"],
        })
    return out


def build_argv(spec, args):
    args = args or {}
    meta = spec["aria_dl"]
    argv = list(meta["argv"])
    for key in meta.get("positionals") or []:
        if key not in args or args[key] is None:
            continue
        val = args[key]
        if isinstance(val, list):
            argv.extend(str(item) for item in val)
        else:
            argv.append(str(val))
    for key, flag in (meta.get("flags") or {}).items():
        if key not in args or args[key] is None:
            continue
        val = args[key]
        if isinstance(val, bool):
            if val:
                argv.append(flag)
            continue
        argv.extend([flag, str(val)])
    argv.extend(["--json", "--non-interactive"])
    return argv


def call_tool(name, arguments):
    spec = tool_specs().get(name)
    if spec is None:
        return 1, "unknown tool %s" % name
    proc = subprocess.run([sys.executable, ARIA] + build_argv(spec, arguments), capture_output=True, text=True)
    text = proc.stdout if proc.stdout.strip() else proc.stderr
    return proc.returncode, text


def handle(msg):
    method = msg.get("method") or ""
    if method.startswith("notifications/"):
        return None
    mid = msg.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "aria-dl", "version": "0.5.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": mcp_tools()}}
    if method == "tools/call":
        params = msg.get("params") or {}
        code, text = call_tool(params.get("name"), params.get("arguments") or {})
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {"content": [{"type": "text", "text": text}], "isError": code != 0},
        }
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}}


def main():
    while True:
        msg = read_message()
        if msg is None:
            return 0
        try:
            reply = handle(msg)
        except Exception as exc:
            print("aria-dl-mcp: %s" % exc, file=sys.stderr)
            reply = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32000, "message": "internal error"}}
        if reply is not None:
            send(reply)


if __name__ == "__main__":
    sys.exit(main())
