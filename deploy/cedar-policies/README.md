# Cedar PDP artifacts (cedar-agent 0.2.2)

`permitio/cedar-agent:0.2.2` loads its `--policies` and `--schema` startup
files as **JSON**, so these are the cedar-agent JSON artifacts:

- `policies.json` — array of `{ "id", "content" }`. The Cedar policy text lives
  in each `content` field. This is the GitOps-managed artifact: edit it → PR →
  Argo CD sync → the kustomize ConfigMap hash rolls → cedar-agent reloads.
- `schema.cedarschema.json` — the Cedar **JSON** schema for TinyTodo.

Source: `cedar-policy/cedar-examples/tinytodo`. `Application` is modeled as a
plain entity type (rather than the `enum` form) for compatibility with
cedar-agent 0.2.2's bundled cedar-policy.

## On-stage demo beat — enable "interns may not create lists" (Policy 5)

During the stream, add this object to the `policies.json` array, open a PR, and
merge. Argo CD syncs, the ConfigMap hash rolls the pod, cedar-agent reloads, and
an intern (`User::"aaron"` in `Team::"interns"`) is then **DENIED** `CreateList`
while non-interns still succeed:

```json
{
  "id": "policy5",
  "content": "forbid (principal in Team::\"interns\", action == Action::\"CreateList\", resource == Application::\"TinyTodo\");"
}
```

## Smoke check after a sync

- `GET /v1/policies` → returns the base policies (non-empty).
- `kesha create-list groceries` → ALLOW (Policy 0).
- unauthorized action → DENY (a real Cedar decision, not deny-all).
