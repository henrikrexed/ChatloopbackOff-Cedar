# Cedar K8s authorization + admission policies (the cedar-webhook layer)

These are the Cedar policies the **K8s `cedar-webhook`** evaluates — the authorization
and admission webhook the cluster `cedar-livestream-demo` runs as a hostNetwork static
pod (`127.0.0.1:10288`, image `ghcr.io/henrikrexed/cedar-webhook:717b374` built by this
repo's CI). They are a **different Cedar layer** from `deploy/cedar-policies/` (ACT 1),
which is the **TinyTodo application** PDP served by the `permitio/cedar-agent` sidecar:

| Layer | Files | Engine | Governs | Loads via |
|---|---|---|---|---|
| App authz (ACT 1) | `deploy/cedar-policies/policies.cedar` | `cedar-agent` sidecar | TinyTodo app requests (`/v1/is_authorized`) | kustomize ConfigMap → cedar-agent |
| **K8s authz + admission (this dir)** | `cedar-webhook-policies/*.yaml` | `cedar-webhook` static pod | every apiserver request (kubectl/kubelet) | `cedar.k8s.aws/v1alpha1 Policy` CRD → webhook `crd` store |

## What's here (starter set — see "Pending board confirmation" below)

| File | Demo beat (ISI-1086 script) |
|---|---|
| `00-deny-deploybot-secrets.yaml` | **Scenario A headline** — Cedar *denies* what RBAC only grants. RBAC is allow-only; `deploy-bot` is forbidden from reading Secrets even though RBAC permits it. |
| `10-require-owner-label.yaml` | **Unified language** — one Policy doing BOTH authorization (`k8s::Action`) and admission (`k8s::admission::Action`): `owner=<name>` label enforcement on reads and writes. |
| `20-namespace-isolation.yaml` | **ABAC / namespace isolation** — tenant ServiceAccounts confined to their own namespace (scoped to group `tenants` so it never touches system controllers). |

Policy syntax is the upstream `k8s::` / `k8s::admission::` namespace, grounded in
`cedar-policy/cedar-access-control-for-k8s@717b374` (`demo/authorization-policy.yaml`,
`demo/admission-policy.yaml`). Schema reference: that repo's
`cedarschema/k8s-authorization.cedarschema`.

## How these load (prerequisites)

The cluster bootstraps with a `directory`-store-only config plus an inert
`00-bootstrap-noop.cedar` (see `proxmox-clusters/clusters/cedar-livestream-demo/`).
**Post-Running**, the `crd` store is appended and these Policy objects become live:

1. Install the `cedar.k8s.aws/v1alpha1` **Policy CRD** (upstream `config/crd/bases`).
2. Bind the webhook's User identity `system:authorizer:cedar-authorizer` so it can read
   `Policy` objects and issue SARs (ClusterRole + ClusterRoleBinding).
3. Append the `crd` store to the webhook's `cedar-config.yaml` and restart the static pod.
4. `kubectl apply -k cedar-webhook-policies/` (or point a dedicated Argo CD Application at
   this path — do **not** fold it into the ACT 1 `deploy/` Application, which prune+selfHeals
   into the `cedar-tinytodo` namespace; these objects are cluster-scoped).

`validation.enforced: false` on every Policy loads it without validating against the
cluster-generated Cedar schema (matches upstream `demo/*.yaml`). Flip to `true` after
generating this cluster's schema with upstream `cmd/schema-generator`.

> ⚠️ Cedar is the **FIRST** authorizer (`Webhook(cedar) → Node → RBAC`). A broad `forbid`
> here can deny system traffic and wedge the cluster. Every forbid in this set is scoped to a
> named principal or demo group for that reason. Review scoping before enabling new policies.

## Pending board confirmation (ISI-1094)

This is a **starter set** authored from the locked Scenario A headline (deny `deploy-bot`)
and the ISI-1086 script themes; the full script is still in backlog. Confirm/adjust the exact
scenario set, principal/group names (`deploy-bot`, `requires-labels`, `tenants`), and whether
to enable schema validation. These are git-only and reversible.
