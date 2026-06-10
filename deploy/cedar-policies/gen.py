#!/usr/bin/env python3
"""Convert the human-editable policies.cedar into cedar-agent's policies.json.

cedar-agent 0.2.2 loads --policies as JSON (an array of {"id","content"}), not
raw Cedar text. policies.cedar is the source of truth the presenter edits; this
script regenerates policies.json so a policy change is one command + a commit.

Policy ids come from a `// @id: <id>` marker line above each policy. A policy
whose body is fully commented out (the on-stage Policy 5 beat) is skipped until
its body is uncommented. No cedar toolchain required — this is a text pass, so
it runs anywhere `make gen` runs.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "policies.cedar"
OUT = HERE / "policies.json"

ID_RE = re.compile(r"^\s*//\s*@id:\s*(\S+)\s*$")
COMMENT_RE = re.compile(r"^\s*//")


def parse(text: str):
    policies = []
    pending_id = None
    auto = 0
    buf: list[str] = []

    def flush():
        nonlocal pending_id, auto, buf
        content = " ".join(" ".join(buf).split())
        content = content.replace("( ", "(").replace(" )", ")")
        if not content:
            buf = []
            return
        pid = pending_id if pending_id is not None else f"policy{auto}"
        policies.append({"id": pid, "content": content})
        auto += 1
        pending_id = None
        buf = []

    for line in text.splitlines():
        m = ID_RE.match(line)
        if m:
            pending_id = m.group(1)
            continue
        if COMMENT_RE.match(line) or not line.strip():
            continue
        buf.append(line.strip())
        if line.rstrip().endswith(";"):
            flush()
    flush()
    return policies


def main() -> int:
    policies = parse(SRC.read_text())
    rendered = json.dumps(policies, indent=2) + "\n"
    if "--check" in sys.argv:
        current = OUT.read_text() if OUT.exists() else ""
        if current != rendered:
            sys.stderr.write(
                "policies.json is stale — run `make gen` (or python3 gen.py) and commit.\n"
            )
            return 1
        print("policies.json is up to date.")
        return 0
    OUT.write_text(rendered)
    print(f"Wrote {len(policies)} policies to {OUT.relative_to(HERE.parent)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
