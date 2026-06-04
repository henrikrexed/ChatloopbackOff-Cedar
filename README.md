# ChatLoopBackOff — Cedar on Kubernetes (livestream assets)

Build assets for the 60-min CNCF Cedar episode. This repo's CI builds the Cedar
authorization + admission webhook container image consumed by the CAPI/Proxmox
demo cluster `cedar-livestream-demo`.

## What CI produces

`.github/workflows/build-cedar-webhook.yml` checks out upstream
[`cedar-policy/cedar-access-control-for-k8s`](https://github.com/cedar-policy/cedar-access-control-for-k8s)
at the pinned immutable commit **`717b3745015f78c80e3d63d83cc97947bd2f4d20`**
(short `717b374`) and builds it with upstream's own multi-stage `Dockerfile`
(binary `cmd/cedar-webhook/main.go`, `ENTRYPOINT /cedar-webhook`, exposes
`10288`/`10289`). It pushes to GHCR:

```
ghcr.io/henrikrexed/cedar-webhook:717b374
ghcr.io/henrikrexed/cedar-webhook:latest
```

> Upstream was **archived/deprecated on 2025-10-15** — demo only, do not deploy
> to production. Pinning by full SHA keeps the build reproducible on stream day
> even though the source repo is frozen.

## Why this image ref is load-bearing

The CAPI manifest pins it exactly in
`proxmox-clusters/clusters/cedar-livestream-demo/control-plane.yaml`:

```yaml
image: ghcr.io/henrikrexed/cedar-webhook:717b374
```

If you change the image name or tag here, update that manifest in the same
change or the control-plane static pod won't pull.

## Running the build

- Push to `main` (touching the workflow) or trigger **Actions → build-cedar-webhook
  → Run workflow** (`workflow_dispatch`).
- After it succeeds, make the GHCR package **public** (or grant the cluster a
  pull secret) so the kubelet on the CP node can pull it at boot.

## Not built here

TLS material (`cedar-ca`, `cedar-authorizer-server`, `apiserver-client`) is
**not** baked into the image — it is delivered to the cluster out of band as the
`cedar-webhook-certs` Secret. The webhook's serving cert **must** be named
`cedar-authorizer-server.crt/.key` (hardcoded in upstream
`internal/server/options/options.go@717b374`; there is no CLI override).
