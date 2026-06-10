#!/usr/bin/env python3
"""TinyTodo client CLI — the on-stage driver for ACT 1 of the Cedar livestream.

The operator ``kubectl exec``s into the tinytodo-client pod and runs this as
different principals (kesha, aaron, emina, andrew) to show Cedar Allow/Deny
decisions flip as policies are merged via GitOps. The acting principal comes from
``--user`` or the ``TINYTODO_USER`` env var; the server URL from
``TINYTODO_SERVER_URL`` (default http://tinytodo-server:8080).

Examples:
    tinytodo.py --user kesha create-list groceries
    tinytodo.py --user aaron create-list secret-plans      # denied once Policy 5 lands
    tinytodo.py --user kesha get-lists
    tinytodo.py --user kesha create-task 0 "buy milk"
    tinytodo.py --user kesha share 0 --with aaron --role reader
    tinytodo.py --user aaron get-list 0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

SERVER_URL = os.environ.get("TINYTODO_SERVER_URL", "http://tinytodo-server:8080").rstrip("/")
KNOWN_USERS = ["kesha", "aaron", "emina", "andrew"]


def _call(method: str, path: str, *, query: dict | None = None, body: dict | None = None) -> dict:
    url = f"{SERVER_URL}{path}"
    if query:
        from urllib.parse import urlencode

        url = f"{url}?{urlencode(query)}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return {"error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        sys.exit(f"cannot reach tinytodo-server at {SERVER_URL}: {e.reason}")


def _emit(result: dict) -> None:
    if result.get("error") == "Authorization Denied":
        print("DENIED  (Cedar said no)")
    elif "error" in result:
        print(f"ERROR   {result['error']}")
    else:
        print("ALLOWED " + json.dumps(result))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tinytodo", description="TinyTodo CLI (Cedar demo)")
    parser.add_argument(
        "--user",
        default=os.environ.get("TINYTODO_USER", ""),
        help="acting principal (kesha|aaron|emina|andrew); or set TINYTODO_USER",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("users", help="list known demo principals")

    p = sub.add_parser("create-list", help="create a new list")
    p.add_argument("name")

    sub.add_parser("get-lists", help="list the lists you can see")

    p = sub.add_parser("get-list", help="show one list and its tasks")
    p.add_argument("list")

    p = sub.add_parser("delete-list", help="delete a list")
    p.add_argument("list")

    p = sub.add_parser("create-task", help="add a task to a list")
    p.add_argument("list")
    p.add_argument("name")

    p = sub.add_parser("update-task", help="set a task's state")
    p.add_argument("list")
    p.add_argument("task", type=int)
    p.add_argument("--state", default="checked")

    p = sub.add_parser("delete-task", help="remove a task")
    p.add_argument("list")
    p.add_argument("task", type=int)

    p = sub.add_parser("share", help="share a list with another user")
    p.add_argument("list")
    p.add_argument("--with", dest="target", required=True)
    p.add_argument("--role", choices=["reader", "editor"], default="reader")

    p = sub.add_parser("unshare", help="revoke a share")
    p.add_argument("list")
    p.add_argument("--with", dest="target", required=True)
    p.add_argument("--role", choices=["reader", "editor"], default="reader")

    args = parser.parse_args(argv)

    if args.cmd == "users":
        print("known principals: " + ", ".join(KNOWN_USERS))
        return 0

    if not args.user:
        sys.exit("no principal: pass --user <name> or set TINYTODO_USER")
    uid = args.user

    if args.cmd == "create-list":
        _emit(_call("POST", "/api/list/create", body={"uid": uid, "name": args.name}))
    elif args.cmd == "get-lists":
        _emit(_call("GET", "/api/lists/get", query={"uid": uid}))
    elif args.cmd == "get-list":
        _emit(_call("GET", "/api/list/get", query={"uid": uid, "list": args.list}))
    elif args.cmd == "delete-list":
        _emit(_call("DELETE", "/api/list/delete", body={"uid": uid, "list": args.list}))
    elif args.cmd == "create-task":
        _emit(_call("POST", "/api/task/create", body={"uid": uid, "list": args.list, "name": args.name}))
    elif args.cmd == "update-task":
        _emit(_call("POST", "/api/task/update", body={"uid": uid, "list": args.list, "task": args.task, "state": args.state}))
    elif args.cmd == "delete-task":
        _emit(_call("DELETE", "/api/task/delete", body={"uid": uid, "list": args.list, "task": args.task}))
    elif args.cmd == "share":
        _emit(_call("POST", "/api/share", body={"uid": uid, "list": args.list, "role": args.role, "share_with": args.target}))
    elif args.cmd == "unshare":
        _emit(_call("DELETE", "/api/share", body={"uid": uid, "list": args.list, "role": args.role, "unshare_with": args.target}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
