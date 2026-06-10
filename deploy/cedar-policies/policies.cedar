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
permit (principal, action, resource is List)
when { resource.owner == principal };

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
