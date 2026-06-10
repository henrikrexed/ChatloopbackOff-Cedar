# Cedar PDP artifacts (cedar-agent 0.2.2)

`permitio/cedar-agent:0.2.2` loads its `--policies` and `--schema` startup
files as **JSON**, so the applied artifacts are JSON. To keep policies
human-editable, the Cedar text is the source of truth and the JSON is generated:

| File | Role |
|------|------|
| `policies.cedar` | **Source of truth.** Human-readable Cedar. Edit this. |
| `gen.py` / `Makefile` | Converter. `make gen` regenerates `policies.json`. |
| `policies.json` | **Generated, applied** artifact — array of `{ "id", "content" }`. Do not hand-edit. |
| `schema.cedarschema.json` | Cedar **JSON** schema for TinyTodo (stable; not live-edited). |

`Application` is modeled as a plain entity type (rather than the `enum` form)
for compatibility with cedar-agent 0.2.2's bundled cedar-policy. Source of the
policies/schema: `cedar-policy/cedar-examples/tinytodo`.

## Editing policies (the GitOps loop)

1. Edit `policies.cedar`. Each policy gets its cedar-agent id from the
   `// @id: <id>` marker line above it.
2. Run `make gen` (pure Python text pass — no cedar toolchain needed).
3. Commit `policies.cedar` **and** the regenerated `policies.json`.
4. Argo CD syncs → the kustomize ConfigMap hash rolls the pod → cedar-agent
   reloads → the decision changes live on stage.

`make check` (used in CI) fails if `policies.json` is out of date with
`policies.cedar`.

## On-stage demo beat — enable "interns may not create lists" (Policy 5)

`policies.cedar` already contains Policy 5, **commented out**. During the stream,
uncomment its body (leave the `// @id: policy5` marker as-is), run `make gen`,
and commit:

```cedar
// @id: policy5
forbid (
  principal in Team::"interns",
  action == Action::"CreateList",
  resource == Application::"TinyTodo"
);
```

After sync, an intern (`User::"aaron"` in `Team::"interns"`) is **DENIED**
`CreateList` while non-interns still succeed.

## Schema note

`schema.cedarschema.json` is committed as JSON directly. The schema is stable
during the demo (it is not part of the live-edit beat), and converting the
human-readable `.cedarschema` to cedar-agent JSON requires the `cedar` CLI,
which is intentionally kept out of the on-stage path.

## Smoke check after a sync

- `GET /v1/policies` → returns the base policies (non-empty).
- `kesha create-list groceries` → ALLOW (Policy 0).
- unauthorized action → DENY (a real Cedar decision, not deny-all).
