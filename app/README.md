# TinyTodo app (ACT 1) — Cedar-agent-delegated fork

This is the application demoed in **ACT 1** of the ChatLoopBackOff "Cedar on
Kubernetes" livestream: a tiny todo-list service whose **every** authorization
decision is made by [Cedar](https://www.cedarpolicy.com/), evaluated by a
[`cedar-agent`](https://github.com/permitio/cedar-agent) sidecar.

It is **forked** from
[`cedar-policy/cedar-examples/tinytodo`](https://github.com/cedar-policy/cedar-examples/tree/main/tinytodo):
the data model (Users/Teams/Lists, the actions, the Cedar schema) and
the Python client UX are preserved. The one architectural change is the whole
point of the demo:

> **Upstream embeds the `cedar-policy` crate and authorizes in-process.**
> **This fork delegates every decision to cedar-agent over HTTP** —
> `POST {CEDAR_AGENT_URL}/v1/is_authorized` — so the policy set lives outside the
> app, in `deploy/cedar-policies/`, and is swapped via GitOps with no rebuild.

> **Implementation note (divergence from upstream):** upstream's server is Rust.
> This fork reimplements the server in dependency-free Python so the image is
> small, reproducible, and trivially multi-arch — and so the authorization path
> is one obvious HTTP call the audience can read on screen. Semantics (entity
> model, actions, allow/deny behaviour) are unchanged. If the board wants a Rust
> fork instead, that is a swap of `server/` only — the deploy contract (port
> 8080, `CEDAR_AGENT_URL`, image names) stays the same.

## Layout

```
app/
  server/
    server.py    # stdlib HTTP server; in-memory lists/tasks; calls the PDP
    cedar.py     # entity model + Cedar JSON entity builder + cedar-agent client
  client/
    tinytodo.py  # CLI the operator kubectl-execs in to act as kesha/aaron/...
```

Both are pure Python 3.12 stdlib — **no pip dependencies**.

## How a request is authorized

1. The client sends an action (e.g. `create-list`) as a principal (`--user kesha`).
2. The server maps it to a Cedar query — principal `User::"kesha"`, action
   `Action::"CreateList"`, resource `Application::"TinyTodo"` (or `List::"<id>"`).
3. The server sends that query **plus the full entity store** (static
   users/teams + every list created at runtime, in Cedar JSON entities format) to
   cedar-agent. It does **not** send a policy set — cedar-agent already loaded the
   policies and schema from files (`CEDAR_AGENT_POLICIES`, `CEDAR_AGENT_SCHEMA`),
   which is what makes policy changes a pure GitOps/ConfigMap concern.
4. cedar-agent replies `{"decision":"Allow"|"Deny"}`. On `Deny` the server returns
   `{"error":"Authorization Denied"}` and the client prints `DENIED`.

Because Cedar is **deny-by-default**, with an empty policy set every action is
denied — that is the tutorial's "no policy first" starting state.

## Principals (from upstream `entities.json`)

| User   | joblevel | team(s)       | notes                                   |
|--------|----------|---------------|-----------------------------------------|
| kesha  | 5        | temp          | not an intern → keeps CreateList         |
| aaron  | 5        | interns       | intern → denied CreateList by Policy 5   |
| emina  | 8        | admin         |                                          |
| andrew | 5        | admin, temp   |                                          |

`Team::"interns"` is a member of `Team::"temp"`.

## Run locally (without Kubernetes)

```bash
# 1. start a cedar-agent with the demo policies + schema
docker run --rm -p 8180:8180 \
  -v "$PWD/../deploy/cedar-policies:/cedar:ro" \
  -e CEDAR_AGENT_POLICIES=/cedar/policies.json \
  -e CEDAR_AGENT_SCHEMA=/cedar/schema.cedarschema.json \
  permitio/cedar-agent:0.2.2

# 2. start the server
CEDAR_AGENT_URL=http://127.0.0.1:8180 python3 server/server.py

# 3. drive it
TINYTODO_SERVER_URL=http://127.0.0.1:8080 python3 client/tinytodo.py --user kesha create-list groceries
```

## Configuration

| Component | Env var              | Default                      |
|-----------|----------------------|------------------------------|
| server    | `CEDAR_AGENT_URL`    | `http://127.0.0.1:8180`      |
| server    | `TINYTODO_PORT`      | `8080`                       |
| server    | `TINYTODO_ADDR`      | `0.0.0.0`                    |
| client    | `TINYTODO_SERVER_URL`| `http://tinytodo-server:8080`|
| client    | `TINYTODO_USER`      | (unset; or pass `--user`)    |

Images (`ghcr.io/henrikrexed/tinytodo-server:dev`, `tinytodo-client:dev`) are
built by a separate CI ticket; see the repo's GitHub Actions.
