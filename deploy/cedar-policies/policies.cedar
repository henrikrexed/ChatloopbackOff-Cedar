// TinyTodo Cedar policies — ACT 1 of the ChatLoopBackOff "Cedar on Kubernetes"
// livestream. Loaded by cedar-agent at startup via CEDAR_AGENT_POLICIES and
// served as the PDP for tinytodo-server (HTTP POST /v1/is_authorized).
//
// This file is the GitOps-managed artifact: a change here -> PR -> Argo CD sync
// -> the cedar-agent pod rolls (kustomize ConfigMap hash) -> new decision live.
//
// Source: cedar-policy/cedar-examples/tinytodo@main (policies.cedar), unmodified
// except that the on-stage demo policy (Policy 5) is intentionally left
// commented so we can enable it live during the stream.

// Policy 0: Any User can create a list and see what lists they own
permit (
    principal,
    action in [Action::"CreateList", Action::"GetLists"],
    resource == Application::"TinyTodo"
);

// Policy 1: A User can perform any action on a List they own
permit (
  principal,
  action,
  resource is List
)
when { resource.owner == principal };

// Policy 2: A User can see a List if they are either a reader or editor
permit (
    principal,
    action == Action::"GetList",
    resource
)
when { principal in resource.readers || principal in resource.editors };

// Policy 3: A User can update a List and its tasks if they are an editor
permit (
    principal,
    action in
        [Action::"UpdateList",
         Action::"CreateTask",
         Action::"UpdateTask",
         Action::"DeleteTask"],
    resource
)
when { principal in resource.editors };

// ── ON-STAGE DEMO CHANGE (keep commented until the GitOps beat) ──────────────
// Policy 5: Interns may not create new task lists. Uncomment this, open a PR,
// merge -> Argo CD syncs -> cedar-agent reloads -> User::"aaron" (an intern)
// is now DENIED CreateList, while non-interns still succeed.
//
// forbid (
//     principal in Team::"interns",
//     action == Action::"CreateList",
//     resource == Application::"TinyTodo"
// );
