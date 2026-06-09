# Cedar on Kubernetes — live policy tutorial

> **Host-followable script.** Read this top-to-bottom on stream. Every command is
> copy-paste. Each `kubectl apply` of a policy visibly changes what the cluster
> admits — that is the whole show.
>
> **Demo arc (3 lines):**
> 1. Start from an allow-all cluster and watch `deploy-bot` create whatever it wants.
> 2. Add Cedar policies one at a time — deny a principal, carve a single allowed
>    action, then a naming guardrail — re-running the same `kubectl` after each so the
>    decision flips live.
> 3. Tail the OTel collector to prove **every admission decision is traced** (user,
>    allow/deny, policy id), then reset to baseline so the demo is re-runnable.

---

## 0. What is already running (context)

This demo runs on the **`cedar-livestream-demo`** CAPI/Proxmox workload cluster
(Kubernetes v1.35.3). Nothing here builds the cluster or the webhook — they are
pre-baked (ISI-1094). What is live before you start:

- A **Cedar webhook** running as a hostNetwork **static pod on the control-plane
  node**, serving both the authorizer (`/v1/authorize`) and the admission
  endpoint (`/v1/admit`) on `127.0.0.1:10288`.
- The apiserver authorizer chain is **Cedar → Node → RBAC** (Cedar runs first, so
  it can deny what RBAC would otherwise allow).
- A `ValidatingWebhookConfiguration` named `cedar-validating-webhook` routing
  `CREATE/UPDATE/DELETE` on all resources to `/v1/admit` (`failurePolicy: Ignore`).
- The **`crd` policy store**: the webhook reads `cedar.k8s.aws/v1alpha1 Policy`
  objects from the cluster. **This is how we load policies in this tutorial** — you
  `kubectl apply` a `Policy` and the webhook picks it up within a few seconds.
  (A second `directory` store on the node holds only an inert bootstrap policy and
  is not touched here.)
- The observability stack from `cedar-livestream-o11y/` (OTel Collector + LGTM) in
  the `observability` namespace.

### 0.1 Point kubectl at the cluster

```bash
# Use the cedar-livestream-demo workload kubeconfig (path is environment-specific).
export KUBECONFIG=<PATH_TO_CEDAR_LIVESTREAM_DEMO_KUBECONFIG>

kubectl get nodes                       # expect 3 nodes, Ready, v1.35.3
kubectl get pods -A | grep -i cedar     # the cedar webhook static pod, Running 1/1
kubectl get crd policies.cedar.k8s.aws  # the Policy CRD the crd store reads
kubectl get validatingwebhookconfiguration cedar-validating-webhook
```

### 0.2 Set up the demo sandbox (one command block)

We act as different identities with `kubectl --as` (impersonation). For those
requests to reach **admission**, the impersonated user must first pass
**authorization** — so we grant the demo identity ordinary edit rights in a
throwaway namespace. Cedar then does the interesting work at the admission layer.

```bash
kubectl create namespace cedar-demo

# Let deploy-bot pass RBAC in cedar-demo (Cedar authz returns NoOpinion -> RBAC allows),
# so the request reaches the Cedar admission webhook where our policies apply.
kubectl -n cedar-demo create rolebinding demo-deploy-bot \
  --clusterrole=edit --user=deploy-bot
```

> Impersonation (`--as`) requires your own kubeconfig to hold the `impersonate`
> verb. The cluster-admin kubeconfig does.

---

## 1. What Cedar is (one paragraph)

Cedar is an open-source policy language. Every decision is evaluated over four
things — **PARC**: a **Principal** (who is acting — here a Kubernetes `User`,
`Group`, or `ServiceAccount`), an **Action** (what they are trying to do — e.g.
`k8s::admission::Action::"create"`), a **Resource** (what they are acting on — e.g.
`core::v1::ConfigMap`), and a **Context** (extra facts you can test in a
condition). You write small `permit`/`forbid` rules against those four, ship them
as `Policy` objects, and the admission webhook evaluates them on every mutating
request. No rebuilds, no apiserver restarts — policy is just data.

---

## 2. Baseline — allow-all

No demo policies are loaded yet, so admission allows everything. Prove it:

```bash
kubectl --as=deploy-bot -n cedar-demo create configmap app-config \
  --from-literal=stage=test
# Expected: configmap/app-config created
```

```bash
kubectl --as=deploy-bot -n cedar-demo create secret generic app-secret \
  --from-literal=token=abc
# Expected: secret/app-secret created
```

Clean those up so the namespace is empty for the policy steps:

```bash
kubectl -n cedar-demo delete configmap app-config
kubectl -n cedar-demo delete secret app-secret
```

---

## 3. Build the policies step by step

Each step is a single `Policy` object. Apply it, wait a couple of seconds for the
webhook to pick it up, then re-run the **same** `kubectl` and watch the verdict
change.

### Step 3.1 — Deny a principal (deny-by-default for `deploy-bot`)

`deploy-bot` should not be allowed to mutate anything in `cedar-demo`.

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: cedar.k8s.aws/v1alpha1
kind: Policy
metadata:
  name: deny-deploy-bot
spec:
  content: |
    forbid (
      principal is k8s::User,
      action in [
        k8s::admission::Action::"create",
        k8s::admission::Action::"update",
        k8s::admission::Action::"delete"
      ],
      resource
    ) when {
      principal.name == "deploy-bot" &&
      resource.metadata.namespace == "cedar-demo"
    };
EOF
```

```bash
kubectl get policies.cedar.k8s.aws          # deny-deploy-bot is listed
sleep 3                                       # let the webhook reload the crd store
kubectl --as=deploy-bot -n cedar-demo create configmap app-config \
  --from-literal=stage=test
# Expected: Error from server (Forbidden): admission webhook "vpolicy.cedar.k8s.aws"
#           denied the request: ... (policy deny-deploy-bot)
```

Show that a different identity is unaffected (you, cluster-admin, are not `deploy-bot`):

```bash
kubectl -n cedar-demo create configmap admin-config --from-literal=stage=test
# Expected: configmap/admin-config created
kubectl -n cedar-demo delete configmap admin-config
```

### Step 3.2 — Allow a specific Action on a Resource kind

Now soften it: `deploy-bot` may **create ConfigMaps**, but still nothing else.
We re-apply the **same policy name**, so this replaces 3.1 in place.

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: cedar.k8s.aws/v1alpha1
kind: Policy
metadata:
  name: deny-deploy-bot
spec:
  content: |
    forbid (
      principal is k8s::User,
      action in [
        k8s::admission::Action::"create",
        k8s::admission::Action::"update",
        k8s::admission::Action::"delete"
      ],
      resource
    ) when {
      principal.name == "deploy-bot" &&
      resource.metadata.namespace == "cedar-demo"
    } unless {
      action == k8s::admission::Action::"create" &&
      resource is core::v1::ConfigMap
    };
EOF
sleep 3
```

ConfigMap create now succeeds:

```bash
kubectl --as=deploy-bot -n cedar-demo create configmap app-config \
  --from-literal=stage=test
# Expected: configmap/app-config created
```

…but a Secret is still denied — the exception was scoped to ConfigMaps only:

```bash
kubectl --as=deploy-bot -n cedar-demo create secret generic app-secret \
  --from-literal=token=abc
# Expected: Error from server (Forbidden): ... denied the request (deny-deploy-bot)
```

### Step 3.3 — A Context-based condition (naming guardrail)

A separate org-wide rule: nobody may create or update a ConfigMap in `cedar-demo`
whose **name begins with `prod`** — a condition tested against the resource.

```bash
cat <<'EOF' | kubectl apply -f -
apiVersion: cedar.k8s.aws/v1alpha1
kind: Policy
metadata:
  name: forbid-prod-named-configmaps
spec:
  content: |
    forbid (
      principal,
      action in [
        k8s::admission::Action::"create",
        k8s::admission::Action::"update"
      ],
      resource is core::v1::ConfigMap
    ) when {
      resource.metadata.namespace == "cedar-demo" &&
      resource.metadata.name like "prod*"
    };
EOF
sleep 3
```

A normally-named ConfigMap is fine (3.2 lets `deploy-bot` create ConfigMaps):

```bash
kubectl --as=deploy-bot -n cedar-demo create configmap dev-flags \
  --from-literal=debug=true
# Expected: configmap/dev-flags created
```

A `prod*` name is denied — the `forbid` overrides the allow from 3.2:

```bash
kubectl --as=deploy-bot -n cedar-demo create configmap prod-flags \
  --from-literal=debug=false
# Expected: Error from server (Forbidden): ... denied the request
#           (forbid-prod-named-configmaps)
```

You now have three layered policies doing principal-, action/kind-, and
condition-based control:

```bash
kubectl get policies.cedar.k8s.aws
# deny-deploy-bot
# forbid-prod-named-configmaps
```

---

## 4. Every decision is traced

The Cedar webhook emits one OTel span per admission review, carrying
`k8s.user`, `k8s.resource.kind`, `admission.allowed`, `admission.reason`, and
`cedar.policy.id`. It exports to the existing collector at
`otel-collector.observability:4317` (see `cedar-livestream-o11y/README.md`). We do
**not** open Grafana — we read the raw spans straight off the collector.

**One-time prep (do before the stream, not on camera):** the collector already
ships a `debug` exporter; add it to the traces pipeline so spans print to the
collector log, then re-apply the bundle.

```bash
# In cedar-livestream-o11y/otelcol/config.yaml, add `debug` to the traces exporters:
#   traces:
#     exporters: [otlp/lgtm, spanmetrics, debug]
kubectl apply -k cedar-livestream-o11y/
kubectl -n observability rollout restart deploy/otel-collector
```

**On stream:** tail the collector and trigger a decision in a second terminal.

```bash
# terminal 1
kubectl -n observability logs deploy/otel-collector -f
```

```bash
# terminal 2 — produces one denied admission span
kubectl --as=deploy-bot -n cedar-demo create configmap prod-flags \
  --from-literal=debug=false
```

In terminal 1 you will see the span with its attributes — `k8s.user=deploy-bot`,
`admission.allowed=false`, and the `cedar.policy.id` that decided it. Point at it:
"every allow and every deny is a trace — full audit trail, no extra wiring."

---

## 5. Reset to baseline (re-runnable)

```bash
# Drop the demo policies -> admission returns to allow-all
kubectl delete policy deny-deploy-bot forbid-prod-named-configmaps --ignore-not-found

# Remove the sandbox
kubectl delete namespace cedar-demo --ignore-not-found

# (If you enabled it for §4) revert the `debug` exporter edit in
# cedar-livestream-o11y/otelcol/config.yaml and re-apply:
#   kubectl apply -k cedar-livestream-o11y/
#   kubectl -n observability rollout restart deploy/otel-collector
```

The cluster, the webhook, and the bootstrap policy are untouched — run the
tutorial again from §0.2 any time.
