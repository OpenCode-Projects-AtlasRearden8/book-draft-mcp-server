"""MCP server entry point over stdio (JSON-RPC 2.0, minimal protocol subset)."""
import json
import sys

from . import core
from .server import Handlers, SERVER_NAME, SERVER_VERSION, TOOL_DEFS, DraftStore
from .storage import check_leaf_name

__all__ = ["check_leaf_name", "core", "main", "serve"]

PROTOCOL_VERSION = "2025-03-26"


def _reply(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message}}


def serve(stdin, stdout, store=None, today=None):
    store = store or DraftStore()
    handlers = Handlers(store, today)

    def handle(method, params):
        if method == "initialize":
            return {
                "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "capabilities": {"tools": {}},
            }
        if method == "notifications/initialized":
            return None
        if method != "tools/list":
            if method != "tools/call":
                raise LookupError(method)
        if method == "tools/list":
            return {"tools": TOOL_DEFS}
        name = (params or {}).get("name")
        arguments = (params or {}).get("arguments") or {}
        handler_name = "h_" + name
        handler = getattr(handlers, handler_name, None)
        if handler is None or not callable(handler):
            raise KeyError(name)
        return handler(arguments)

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_error(-1, -32700, "Parse error")) + "\n")
            stdout.flush()
            continue
        msg_id = request.get("id", -1)
        method = request.get("method", "")
        if method.startswith("notifications/") or method == "initialized":
            continue
        try:
            result = handle(method, request.get("parameters") or request.get("params") or {})
            if method == "tools/call":
                result = {"content": [{"type": "text",
                                       "text": json.dumps(result, indent=2, default=str)}]}
            stdout.write(json.dumps(_reply(msg_id, result)) + "\n")
        except KeyError as exc:
            stdout.write(json.dumps(_error(msg_id, -32602, "Unknown tool: %s" % exc)) + "\n")
        except LookupError:
            stdout.write(json.dumps(_error(msg_id, -32601, "Method not found")) + "\n")
        except (ValueError, TypeError) as exc:
            if method == "tools/call":
                payload = {"content": [{"type": "text", "text": "Error: %s" % exc}],
                           "isError": True}
                stdout.write(json.dumps(_reply(msg_id, payload)) + "\n")
            else:
                stdout.write(json.dumps(_error(msg_id, -32602, str(exc))) + "\n")
        except Exception as exc:  # keep the stdio loop alive; log to stderr
            print(traceback.format_exc(), file=sys.stderr)
            if method == "tools/call":
                payload = {"content": [{"type": "text", "text": "Error: %s" % exc}],
                           "isError": True}
                stdout.write(json.dumps(_reply(msg_id, payload)) + "\n")
            else:
                stdout.write(json.dumps(_error(msg_id, -32603, str(exc))) + "\n")
        stdout.flush()


def main():
    serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
