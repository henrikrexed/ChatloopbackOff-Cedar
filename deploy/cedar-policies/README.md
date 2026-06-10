# TinyTodo Cedar policies — ACT 1 PDP artifacts

These two JSON files are mounted into the `cedar-agent` sidecar (see
`../tinytodo-server.yaml`) as its startup `--policies` / `--schema`. They are the
GitOps-managed source of truth: a change here → PR → Argo CD sync → the
kustomize ConfigMap hash rotates → the cedar-agent pod rolls → new decision live.

- `policies.json` — cedar-agent policy set (`[{ "id", "content" }]`); the Cedar
  text lives in each `content`. Upstream TinyTodo Policies 0–3.
- `schema.cedarschema.json` — Cedar JSON schema for TinyTodo.

## cedar-agent 0.2.2 compatibility notes

`permitio/cedar-agent:0.2.2` bundles an older `cedar-policy`. Two upstream forms
do not load on it and were adapted (validated live against the running agent):

- **No `is` operator.** Upstream Policy 1 is `resource is List`. The `is`
  operator postdates this agent, so Policy 1 guards on the List-only `owner`
  attribute (`resource has owner && resource.owner == principal`) instead —
  semantically equivalent for TinyTodo, where only `List` has `owner`.
- **No `enum` entities, no nested `commonTypes`.** `Application` is modelled as a
  plain entity, and the `Task`/`Tasks` types are inlined into `List.tasks`
  (`Set` of `Record`) rather than declared as common types.

## On-stage demo beat — Policy 5 (interns may not create lists)

Kept **out** of `policies.json` on purpose. During the stream, add it as one
object to the array, commit → Argo CD syncs → `User::"aaron"` (an intern) is then
DENIED `CreateList` while non-interns still succeed:

```json
{
  "id": "policy5",
  "content": "forbid (principal in Team::\"interns\", action == Action::\"CreateList\", resource == Application::\"TinyTodo\");"
}
```

Verified on cedar-agent 0.2.2: with Policy 5 active, an intern's `CreateList`
returns `Deny` (reason `policy5`).
