# syntax=docker/dockerfile:1
#
# tinytodo-client (ACT 1 of the ChatLoopBackOff "Cedar on Kubernetes" livestream).
# Dependency-free Python 3.12 stdlib CLI. The pod runs idle (`sleep infinity`)
# and the operator `kubectl exec`s in to act as kesha/aaron/... on stage:
#   kubectl -n cedar-tinytodo exec deploy/tinytodo-client -- python3 /app/tinytodo.py ...
# so the CLI MUST live at /app/tinytodo.py (TUTORIAL.md `ttc` helper).
#
# Image ref must stay matched to deploy/tinytodo-client.yaml:
#   image: ghcr.io/henrikrexed/tinytodo-client:dev   (command: ["sleep","infinity"])
FROM python:3.12-alpine

LABEL org.opencontainers.image.title="tinytodo-client" \
      org.opencontainers.image.description="TinyTodo CLI driver (ACT 1 livestream demo)" \
      org.opencontainers.image.source="https://github.com/henrikrexed/ChatloopbackOff-Cedar" \
      org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app
COPY tinytodo.py /app/tinytodo.py

RUN addgroup -S app && adduser -S -G app app
USER app

ENV TINYTODO_SERVER_URL=http://tinytodo-server:8080

CMD ["sleep", "infinity"]
