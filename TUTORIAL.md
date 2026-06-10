# Cedar on Kubernetes — live policy tutorial

> **Two acts.** This stream has two halves, both showing "policy is just data you
> ship with Git":
>
> - **[ACT 1 — TinyTodo app authorization](#act-1--tinytodo-app-authorization-gitops-policy-reveal)**
>   (jump to the bottom): a real app whose every decision is made by a Cedar PDP
>   (`cedar-agent`). We start with **no policy** (the app denies everything), then
>   add `permit` rules one at a time **via Git → Argo CD sync** and watch access
>   open up — ending with a `forbid` rule revealed live.
> - **ACT 2 — Cluster admission** (sections 0–5 below): the same idea at the
>   Kubernetes admission layer, where Cedar policies gate `kubectl` itself.
>
> On stream, run **ACT 1 first**, then ACT 2. The sections below (0–5) are ACT 2.

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

---

# ACT 1 — TinyTodo app authorization (GitOps policy reveal)

> **Run this act first on stream.** It tells the cleanest version of the story:
> a normal app that asks Cedar "is this allowed?" for every action, where the
> answer is controlled entirely by files in Git. We start locked down, then
> **merge `permit` policies one at a time** and watch the app come to life, and
> finish by **revealing a `forbid`** that denies one principal live.

## A1.0 What is running

The TinyTodo app lives in the **`cedar-tinytodo`** namespace and is delivered by
**Argo CD**, which watches `deploy/` in this repo (`argocd/application.yaml`):

- **`tinytodo-server`** — the app, with a **`cedar-agent` sidecar** in the same
  pod. The server makes **no authorization decision itself**: for every request it
  asks the sidecar over HTTP (`POST 127.0.0.1:8180/v1/is_authorized`). See
  [`app/`](app/) for the source.
- The sidecar loads its **policies and schema from files** —
  `deploy/cedar-policies/policies.json` and `schema.cedarschema.json` — mounted
  from a kustomize **ConfigMap whose name is content-hashed**. So when we change
  `policies.cedar`, run `make gen`, and merge it, kustomize generates a new
  ConfigMap name → the pod rolls → cedar-agent reloads with the new policy.
  **That is the GitOps beat.**
- **`tinytodo-client`** — an idle pod we `kubectl exec` into to act as the demo
  principals **kesha, aaron, emina, andrew**.

```bash
kubectl -n cedar-tinytodo get pods            # tinytodo-server (2/2) + tinytodo-client (1/1)
kubectl -n argocd get application cedar-tinytodo   # SYNCED / Healthy
```

A tiny client helper (use it for every command below):

```bash
# Run the TinyTodo CLI inside the client pod, as a chosen principal.
ttc() { kubectl -n cedar-tinytodo exec deploy/tinytodo-client -- python3 /app/tinytodo.py "$@"; }
ttc users     # -> known principals: kesha, aaron, emina, andrew
```

## A1.1 Start with NO policy — Cedar denies everything

Cedar is **deny-by-default**: with an empty policy set, every action is denied.
Put the app in that state by emptying the policy file, then committing it so Argo
syncs it (this *is* the first GitOps action of the demo):

```bash
# In deploy/cedar-policies/policies.cedar, comment out / remove all permit rules
# (leave the file present but with no active policy), then:
git commit -am "demo: start ACT 1 from an empty policy set"
git push          # open PR -> merge -> Argo CD syncs -> cedar-agent reloads (~30s)
```

> **Tip:** to keep the reveal snappy on camera, do the empty-policy commit
> **before** going live, or run the build-up on a demo branch and point the Argo
> `Application.spec.source.targetRevision` at it. `main`'s resting state already
> has Policies 0–3 active (the *end* state of this act) with Policy 5 commented.

Now everything is denied — even creating your own list:

```bash
ttc --user kesha create-list groceries
# DENIED  (Cedar said no)
ttc --user kesha get-lists
# DENIED  (Cedar said no)
```

"The app is wired to Cedar, and Cedar has nothing that says *yes* — so it's *no*."

## A1.2 Policy 0 — anyone can create and list their own lists

Uncomment **Policy 0** in `deploy/cedar-policies/policies.cedar`:

```cedar
// Policy 0: Any User can create a list and see what lists they own
permit (
    principal,
    action in [Action::"CreateList", Action::"GetLists"],
    resource == Application::"TinyTodo"
);
```

```bash
git commit -am "feat(policy): allow CreateList + GetLists"
git push    # PR -> merge -> Argo sync -> pod rolls
kubectl -n cedar-tinytodo rollout status deploy/tinytodo-server   # wait for the new ConfigMap
```

Re-run the **same** commands — they flip to allowed:

```bash
ttc --user kesha create-list groceries
# ALLOWED {"id": "0", "name": "groceries", "owner": "kesha"}
ttc --user kesha get-lists
# ALLOWED {"lists": [{"id": "0", "name": "groceries", "owner": "kesha"}]}
```

But kesha still can't add a task to her own list — no policy permits it yet:

```bash
ttc --user kesha create-task 0 "buy milk"
# DENIED  (Cedar said no)
```

## A1.3 Policy 1 — owners get full control of their lists

Uncomment **Policy 1** (`when { resource.owner == principal }`). Commit, push,
merge, wait for the rollout — then:

```bash
ttc --user kesha create-task 0 "buy milk"
# ALLOWED {"list": "0", "task": 1, "name": "buy milk"}
ttc --user kesha get-list 0
# ALLOWED {... "tasks": [{"id": 1, "name": "buy milk", "state": "unchecked"}]}
```

This decision used **data, not just rules**: cedar-agent evaluated
`resource.owner == principal` against the list's `owner` attribute the server sent.

## A1.4 Policy 2 — readers/editors can view a shared list

aaron can't see kesha's list yet:

```bash
ttc --user aaron get-list 0
# DENIED  (Cedar said no)
```

kesha shares it (owner action, allowed by Policy 1), then uncomment **Policy 2**
(`principal in resource.readers || principal in resource.editors`), commit/merge/roll:

```bash
ttc --user kesha share 0 --with aaron --role reader
# ALLOWED {"list": "0", "role": "reader", "user": "aaron", "unshared": false}

ttc --user aaron get-list 0
# ALLOWED {... shows kesha's list}
```

A reader still can't edit:

```bash
ttc --user aaron create-task 0 "sneak this in"
# DENIED  (Cedar said no)
```

## A1.5 Policy 3 — editors can modify tasks

Re-share aaron as an **editor** and uncomment **Policy 3**
(editors may `UpdateList`/`CreateTask`/`UpdateTask`/`DeleteTask`):

```bash
ttc --user kesha share 0 --with aaron --role editor
ttc --user aaron create-task 0 "added as editor"
# ALLOWED {...}
```

You now have layered, data-driven authorization — ownership, read sharing, edit
sharing — all from four small `permit` rules shipped as files.

## A1.6 The reveal — `forbid` interns from creating lists (Policy 5)

The finale. `deploy/cedar-policies/policies.cedar` keeps **Policy 5** commented
for exactly this moment. aaron is an **intern** (`Team::"interns"`); kesha is not.
First show both can still create lists:

```bash
ttc --user aaron create-list intern-list      # ALLOWED (Policy 0)
ttc --user kesha create-list kesha-list        # ALLOWED (Policy 0)
```

Uncomment **Policy 5** and ship it:

```cedar
// Policy 5: Interns may not create new task lists.
forbid (
    principal in Team::"interns",
    action == Action::"CreateList",
    resource == Application::"TinyTodo"
);
```

```bash
git commit -am "feat(policy): forbid interns from creating lists"
git push    # PR -> merge -> Argo sync -> roll
kubectl -n cedar-tinytodo rollout status deploy/tinytodo-server
```

Re-run — the **same** action now flips for the intern, while everyone else is
unaffected. `forbid` always wins over `permit`:

```bash
ttc --user aaron create-list another-intern-list
# DENIED  (Cedar said no)      <- Policy 5 forbids interns
ttc --user kesha create-list another-kesha-list
# ALLOWED {...}                <- kesha is temp, not an intern
```

"One `forbid` rule, merged like any other change, instantly denied a whole class
of principals — no redeploy of the app, no restart of the API. Policy is data."

## A1.7 Reset (re-runnable)

Revert `policies.cedar` to `main`'s resting state (Policies 0–3 active, Policy 5
commented) and let Argo sync, or restart the server to drop the in-memory lists:

```bash
git checkout main -- deploy/cedar-policies/policies.cedar && git commit -am "demo: reset ACT 1 policies" && git push
kubectl -n cedar-tinytodo rollout restart deploy/tinytodo-server   # clears lists/tasks
```
