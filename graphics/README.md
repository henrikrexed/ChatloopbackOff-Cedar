# Cedar livestream — explainer graphics

Three explainer slides that form the visual backbone the host shows on stream.
The point of the stream is to **explain what Cedar is and why it matters** — these
are explainer slides, not marketing posters.

Each graphic is provided as a layered **SVG** source (editable) and a **PNG** poster
(1920×1080, stream-resolution). Render PNGs from SVGs with:

```
node /tmp/svgrender/render.js   # uses @resvg/resvg-js
```

| # | File | Caption (one line) |
|---|------|--------------------|
| 1 | `01-what-is-cedar-parc.{svg,png}` | **What is Cedar** — every authorization question is one PARC tuple (Principal · Action · Resource · Context) that resolves to a single Allow or Deny. |
| 2 | `02-architecture-admission-webhook.{svg,png}` | **The architecture** — Cedar runs as a Kubernetes validating admission webhook; a write request is checked against policy before it's persisted, and every decision emits an OTel span. |
| 3 | `03-the-library.{svg,png}` | **The library** — under the webhook, Cedar is a small, embeddable, formally-verified engine: feed it policy text + entities, get back a decision plus diagnostics. |

## Palette (consistent with the Cedar livestream visual pack)

- Console `#0B1220` · Chrome `#1C2738` — neutral backdrops
- **Lens `#36C5B0`** — Cedar accent (the through-line color)
- Signal `#F5A623` — default request flow / data
- Iris `#A78BFA` — OTel telemetry path
- Bone `#E8ECF2` — primary text · `#9AB0BD` muted
- Deny `#FF6B6B` — used sparingly, only for deny states
- Type: Inter (display) + JetBrains Mono (code)

## Accuracy notes

Terminology verified against the Cedar research brief (ISI-1085):
- CNCF **Sandbox**, accepted **2025-10-08**, Apache-2.0, created by AWS.
- Action namespaces `k8s::Action` (authz) and `k8s::admission::Action` (admission).
- "Deny trumps allow"; not Turing-complete by design → analyzable.
- Formally verified: Rust impl differentially tested against a Lean theorem-prover model.
- Admission flow matches the ISI-1094 CAPI cluster + admission webhook pre-bake.

If any Cedar semantics need to change, edit the SVG (text is live, not outlined) and re-render.
