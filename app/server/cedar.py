"""Cedar entity model + cedar-agent PDP client for the TinyTodo demo.

The forked TinyTodo server does NOT embed the cedar-policy crate (upstream does).
Instead every authorization decision is delegated to the cedar-agent sidecar over
HTTP (``POST {CEDAR_AGENT_URL}/v1/is_authorized``). cedar-agent loads the policy
set and schema from files at boot (CEDAR_AGENT_POLICIES / CEDAR_AGENT_SCHEMA), so
the *policies* are GitOps-managed in deploy/cedar-policies/ — the server never
sends a policy set on the wire. It only sends the principal/action/resource of the
current request plus the full entity store (static users/teams + the lists created
at runtime), encoded in the Cedar JSON entities format.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error

# ── Static TinyTodo principals, mirrored from upstream
# cedar-policy/cedar-examples/tinytodo entities.json. joblevel:Long, location:String
# match deploy/cedar-policies/schema.cedarschema.json (entity User).
USERS: dict[str, dict] = {
    "kesha": {"joblevel": 5, "location": "ABC17", "teams": ["temp"]},
    "aaron": {"joblevel": 5, "location": "ABC17", "teams": ["interns"]},
    "emina": {"joblevel": 8, "location": "DEF33", "teams": ["admin"]},
    "andrew": {"joblevel": 5, "location": "XYZ77", "teams": ["admin", "temp"]},
}

# Team::"interns" is a member of Team::"temp" (interns are temps); used by the
# Policy 5 reveal (forbid interns CreateList) so aaron is denied but kesha is not.
TEAM_PARENTS: dict[str, list[str]] = {
    "temp": [],
    "admin": [],
    "interns": ["temp"],
}

APPLICATION = "TinyTodo"


def _euid(entity_type: str, eid: str) -> str:
    """Cedar entity-uid literal, e.g. User::\"kesha\"."""
    return f'{entity_type}::"{eid}"'


def _ref(entity_type: str, eid: str) -> dict:
    """Entity reference inside an attribute value (Cedar JSON encoding)."""
    return {"__entity": {"type": entity_type, "id": eid}}


class TinyTodoStore:
    """In-memory list/task store + dynamic share membership.

    A List owns two synthetic Teams — ``<id>.readers`` and ``<id>.editors`` —
    matching the upstream schema (List.readers: Team, List.editors: Team).
    Sharing a list adds the target user as a member (parent) of that team, which
    is how Policy 2/Policy 3 (``principal in resource.readers/editors``) resolve.
    """

    def __init__(self) -> None:
        self._lists: dict[str, dict] = {}
        self._next_list_id = 0

    def create_list(self, owner: str, name: str) -> str:
        list_id = str(self._next_list_id)
        self._next_list_id += 1
        self._lists[list_id] = {
            "name": name,
            "owner": owner,
            "readers": set(),
            "editors": set(),
            "tasks": [],
            "next_task_id": 1,
        }
        return list_id

    def get(self, list_id: str) -> dict | None:
        return self._lists.get(list_id)

    def exists(self, list_id: str) -> bool:
        return list_id in self._lists

    def lists_for(self, user: str) -> list[dict]:
        out = []
        for lid, l in self._lists.items():
            if l["owner"] == user or user in l["readers"] or user in l["editors"]:
                out.append({"id": lid, "name": l["name"], "owner": l["owner"]})
        return out

    def delete_list(self, list_id: str) -> None:
        self._lists.pop(list_id, None)

    def create_task(self, list_id: str, name: str) -> int:
        l = self._lists[list_id]
        task_id = l["next_task_id"]
        l["next_task_id"] += 1
        l["tasks"].append({"id": task_id, "name": name, "state": "unchecked"})
        return task_id

    def update_task(self, list_id: str, task_id: int, state: str) -> bool:
        for t in self._lists[list_id]["tasks"]:
            if t["id"] == task_id:
                t["state"] = state
                return True
        return False

    def delete_task(self, list_id: str, task_id: int) -> bool:
        l = self._lists[list_id]
        before = len(l["tasks"])
        l["tasks"] = [t for t in l["tasks"] if t["id"] != task_id]
        return len(l["tasks"]) != before

    def share(self, list_id: str, role: str, user: str, unshare: bool = False) -> None:
        bucket = self._lists[list_id]["readers" if role == "reader" else "editors"]
        if unshare:
            bucket.discard(user)
        else:
            bucket.add(user)

    # ── Cedar entity store ────────────────────────────────────────────────
    def entities(self) -> list[dict]:
        """Full Cedar entity set: Application, Teams, Users, Lists + list teams.

        Sent inline on every is_authorized call so the file-loaded policies can
        evaluate against current runtime state (list ownership, share membership).
        """
        ents: list[dict] = [
            {"uid": {"type": "Application", "id": APPLICATION}, "attrs": {}, "parents": []}
        ]

        for team, parents in TEAM_PARENTS.items():
            ents.append(
                {
                    "uid": {"type": "Team", "id": team},
                    "attrs": {},
                    "parents": [{"type": "Team", "id": p} for p in parents],
                }
            )

        # Per-list reader/editor teams.
        for lid in self._lists:
            ents.append({"uid": {"type": "Team", "id": f"{lid}.readers"}, "attrs": {}, "parents": []})
            ents.append({"uid": {"type": "Team", "id": f"{lid}.editors"}, "attrs": {}, "parents": []})

        # Users, with static team membership + dynamic per-list share membership.
        for name, u in USERS.items():
            parents = [{"type": "Team", "id": t} for t in u["teams"]]
            parents.append({"type": "Application", "id": APPLICATION})
            for lid, l in self._lists.items():
                if name in l["readers"]:
                    parents.append({"type": "Team", "id": f"{lid}.readers"})
                if name in l["editors"]:
                    parents.append({"type": "Team", "id": f"{lid}.editors"})
            ents.append(
                {
                    "uid": {"type": "User", "id": name},
                    "attrs": {"joblevel": u["joblevel"], "location": u["location"]},
                    "parents": parents,
                }
            )

        # Lists.
        for lid, l in self._lists.items():
            ents.append(
                {
                    "uid": {"type": "List", "id": lid},
                    "attrs": {
                        "name": l["name"],
                        "owner": _ref("User", l["owner"]),
                        "readers": _ref("Team", f"{lid}.readers"),
                        "editors": _ref("Team", f"{lid}.editors"),
                        "tasks": [
                            {"id": t["id"], "name": t["name"], "state": t["state"]}
                            for t in l["tasks"]
                        ],
                    },
                    "parents": [{"type": "Application", "id": APPLICATION}],
                }
            )

        return ents


class CedarClient:
    """Thin HTTP client for the cedar-agent PDP."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def is_authorized(self, principal: str, action: str, resource: str, entities: list[dict]) -> bool:
        body = json.dumps(
            {
                "principal": principal,
                "action": action,
                "resource": resource,
                "context": {},
                "entities": entities,
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/v1/is_authorized",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            answer = json.loads(resp.read())
        # cedar-agent returns {"decision":"Allow"|"Deny","diagnostics":{...}}.
        return str(answer.get("decision", "")).lower() == "allow"

    def healthy(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/v1/policies", method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout):
                return True
        except (urllib.error.URLError, OSError):
            return False


# Action helpers — bare `Action::"..."` (the schema declares actions in the
# empty namespace).
def action(name: str) -> str:
    return _euid("Action", name)


def user(name: str) -> str:
    return _euid("User", name)


def app_resource() -> str:
    return _euid("Application", APPLICATION)


def list_resource(list_id: str) -> str:
    return _euid("List", list_id)
