// TinyTodo base policies — human-editable Cedar source of truth.
//
// cedar-agent 0.2.2 loads its --policies file as JSON, NOT raw Cedar. So this
// file is the source the presenter edits; `make gen` (or `python3 gen.py`)
// regenerates the applied artifact `policies.json`. Commit both → Argo CD syncs
// → the kustomize ConfigMap hash rolls the pod → cedar-agent reloads.
//
// Each policy's cedar-agent id comes from the `// @id: <id>` marker above it.
// Source: cedar-policy/cedar-examples/tinytodo.

// @id: policy0
permit (
  principal,
  action in [Action::"CreateList", Action::"GetLists"],
  resource == Application::"TinyTodo"
);

// @id: policy1
// NOTE: upstream TinyTodo uses `resource is List`, but the `is` operator is not
// supported by the older cedar-policy bundled in cedar-agent 0.2.2 (it rejects it
// at load → deny-all). Guarding on the List-only `owner` attribute is semantically
// equivalent here: `List` is the only entity type that declares an `owner`.
permit (principal, action, resource)
when { resource has owner && resource.owner == principal };

// @id: policy2
permit (principal, action == Action::"GetList", resource)
when { principal in resource.readers || principal in resource.editors };

// @id: policy3
permit (
  principal,
  action in [Action::"UpdateList", Action::"CreateTask", Action::"UpdateTask", Action::"DeleteTask"],
  resource
)
when { principal in resource.editors };

// ===========================================================================
// ON-STAGE BEAT — "interns may not create lists".
// Uncomment the policy body below (leave the `// @id:` marker as-is), then run
// `make gen` and commit. Argo CD syncs, cedar-agent reloads, and an intern
// (User::"aaron" in Team::"interns") is DENIED CreateList while others succeed.
// ===========================================================================
// @id: policy5
// forbid (
//   principal in Team::"interns",
//   action == Action::"CreateList",
//   resource == Application::"TinyTodo"
// );
