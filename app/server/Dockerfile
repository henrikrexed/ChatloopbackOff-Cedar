# syntax=docker/dockerfile:1
#
# tinytodo-server (ACT 1 of the ChatLoopBackOff "Cedar on Kubernetes" livestream).
# Dependency-free Python 3.12 stdlib HTTP server; every authz decision is
# delegated to the cedar-agent sidecar at CEDAR_AGENT_URL (default
# http://127.0.0.1:8180). No pip deps -> alpine + stdlib only, trivially multi-arch.
#
# Build context is app/server/ so server.py + cedar.py (the `import cedar`) sit
# together in /app. Image ref must stay matched to deploy/tinytodo-server.yaml:
#   image: ghcr.io/henrikrexed/tinytodo-server:dev   (containerPort 8080)
FROM python:3.12-alpine

LABEL org.opencontainers.image.title="tinytodo-server" \
      org.opencontainers.image.description="Cedar-agent-delegated TinyTodo server (ACT 1 livestream demo)" \
      org.opencontainers.image.source="https://github.com/henrikrexed/ChatloopbackOff-Cedar" \
      org.opencontainers.image.licenses="Apache-2.0"

WORKDIR /app
COPY server.py cedar.py /app/

RUN addgroup -S app && adduser -S -G app app
USER app

ENV TINYTODO_ADDR=0.0.0.0 \
    TINYTODO_PORT=8080 \
    CEDAR_AGENT_URL=http://127.0.0.1:8180
EXPOSE 8080

ENTRYPOINT ["python3", "/app/server.py"]
