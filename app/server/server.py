"""TinyTodo server (forked for cedar-agent delegation).

A small stdlib HTTP server holding lists/tasks in memory. Every mutating or
reading request is authorized by asking the cedar-agent sidecar
(``CEDAR_AGENT_URL``, default http://127.0.0.1:8180). The action/resource mapping
mirrors upstream cedar-policy/cedar-examples/tinytodo:

    POST   /api/list/create   {uid,name}              -> CreateList  on Application
    GET    /api/lists/get?uid=                         -> GetLists    on Application
    GET    /api/list/get?uid=&list=                    -> GetList     on List
    DELETE /api/list/delete   {uid,list}               -> DeleteList  on List
    POST   /api/task/create   {uid,list,name}          -> CreateTask  on List
    POST   /api/task/update   {uid,list,task,state}    -> UpdateTask  on List
    DELETE /api/task/delete   {uid,list,task}          -> DeleteTask  on List
    POST   /api/share         {uid,list,role,share_with}    -> EditShare on List
    DELETE /api/share         {uid,list,role,unshare_with}  -> EditShare on List
    GET    /healthz

Authorization-denied responses return HTTP 200 with {"error":"Authorization Denied"}
(upstream behaviour) so the client can render Allow/Deny without HTTP error noise.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import cedar

CEDAR_AGENT_URL = os.environ.get("CEDAR_AGENT_URL", "http://127.0.0.1:8180")
LISTEN_ADDR = os.environ.get("TINYTODO_ADDR", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("TINYTODO_PORT", "8080"))

STORE = cedar.TinyTodoStore()
PDP = cedar.CedarClient(CEDAR_AGENT_URL)

DENIED = {"error": "Authorization Denied"}


class Denied(Exception):
    pass


class BadRequest(Exception):
    pass


def _authorize(uid: str, action: str, resource: str) -> None:
    if not uid or uid not in cedar.USERS:
        raise BadRequest(f"unknown principal: {uid!r}")
    allowed = PDP.is_authorized(
        cedar.user(uid), cedar.action(action), resource, STORE.entities()
    )
    if not allowed:
        raise Denied()


def handle(method: str, path: str, query: dict, body: dict) -> tuple[int, dict]:
    def q(name: str) -> str:
        return (query.get(name, [""])[0] or body.get(name, "")) if query else body.get(name, "")

    if path == "/healthz":
        return 200, {"status": "ok", "cedar_agent": PDP.healthy()}

    if path == "/api/list/create" and method == "POST":
        uid, name = body.get("uid", ""), body.get("name", "")
        _authorize(uid, "CreateList", cedar.app_resource())
        list_id = STORE.create_list(uid, name)
        return 200, {"id": list_id, "name": name, "owner": uid}

    if path == "/api/lists/get" and method == "GET":
        uid = q("uid")
        _authorize(uid, "GetLists", cedar.app_resource())
        return 200, {"lists": STORE.lists_for(uid)}

    if path == "/api/list/get" and method == "GET":
        uid, list_id = q("uid"), q("list")
        if not STORE.exists(list_id):
            return 404, {"error": "no such list"}
        _authorize(uid, "GetList", cedar.list_resource(list_id))
        l = STORE.get(list_id)
        return 200, {"id": list_id, "name": l["name"], "owner": l["owner"], "tasks": l["tasks"]}

    if path == "/api/list/delete" and method == "DELETE":
        uid, list_id = body.get("uid", ""), body.get("list", "")
        if not STORE.exists(list_id):
            return 404, {"error": "no such list"}
        _authorize(uid, "DeleteList", cedar.list_resource(list_id))
        STORE.delete_list(list_id)
        return 200, {"deleted": list_id}

    if path == "/api/task/create" and method == "POST":
        uid, list_id, name = body.get("uid", ""), body.get("list", ""), body.get("name", "")
        if not STORE.exists(list_id):
            return 404, {"error": "no such list"}
        _authorize(uid, "CreateTask", cedar.list_resource(list_id))
        task_id = STORE.create_task(list_id, name)
        return 200, {"list": list_id, "task": task_id, "name": name}

    if path == "/api/task/update" and method == "POST":
        uid, list_id = body.get("uid", ""), body.get("list", "")
        task_id, state = body.get("task"), body.get("state", "")
        if not STORE.exists(list_id):
            return 404, {"error": "no such list"}
        _authorize(uid, "UpdateTask", cedar.list_resource(list_id))
        ok = STORE.update_task(list_id, int(task_id), state)
        return (200, {"updated": ok}) if ok else (404, {"error": "no such task"})

    if path == "/api/task/delete" and method == "DELETE":
        uid, list_id, task_id = body.get("uid", ""), body.get("list", ""), body.get("task")
        if not STORE.exists(list_id):
            return 404, {"error": "no such list"}
        _authorize(uid, "DeleteTask", cedar.list_resource(list_id))
        ok = STORE.delete_task(list_id, int(task_id))
        return (200, {"deleted": ok}) if ok else (404, {"error": "no such task"})

    if path == "/api/share" and method in ("POST", "DELETE"):
        uid, list_id = body.get("uid", ""), body.get("list", "")
        role = body.get("role", "reader")
        if role not in ("reader", "editor"):
            raise BadRequest("role must be 'reader' or 'editor'")
        if not STORE.exists(list_id):
            return 404, {"error": "no such list"}
        _authorize(uid, "EditShare", cedar.list_resource(list_id))
        unshare = method == "DELETE"
        target = body.get("unshare_with" if unshare else "share_with", "")
        if target not in cedar.USERS:
            raise BadRequest(f"unknown user: {target!r}")
        STORE.share(list_id, role, target, unshare=unshare)
        return 200, {"list": list_id, "role": role, "user": target, "unshared": unshare}

    return 404, {"error": "not found"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: D401 - quieter, structured-ish log
        sys.stderr.write("tinytodo-server %s\n" % (fmt % args))

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            raise BadRequest("invalid JSON body")

    def _respond(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        try:
            body = self._read_body() if method in ("POST", "DELETE") else {}
            query = parse_qs(parsed.query)
            status, payload = handle(method, parsed.path, query, body)
            self._respond(status, payload)
        except Denied:
            self._respond(200, DENIED)
        except BadRequest as e:
            self._respond(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001 - surface PDP/connectivity errors
            self._respond(502, {"error": f"server error: {e}"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_DELETE(self):
        self._dispatch("DELETE")


def main() -> None:
    sys.stderr.write(
        f"tinytodo-server listening on {LISTEN_ADDR}:{LISTEN_PORT}, "
        f"PDP={CEDAR_AGENT_URL} (reachable={PDP.healthy()})\n"
    )
    ThreadingHTTPServer((LISTEN_ADDR, LISTEN_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
