---
description: "Ingest a GitHub issue into Firstmate's backlog and brief system"
---

# Ingest GitHub Issue to Firstmate

Bridge a GitHub Issue into Firstmate's multi-agent fleet queue.

## Instructions

1. If an issue number was provided in the prompt, run:
   ```bash
   uv run scripts/gh_firstmate_bridge.py ingest <issue-number> --mode direct-PR
   ```
2. If no issue number was provided, query the tracker first:
   ```bash
   uv run scripts/gh_firstmate_bridge.py list --label ready-for-agent
   ```
   Present the list of open, ready issues to the user and ask which one to ingest and dispatch.
3. Once ingested, report the generated brief location (`data/<task-id>/brief.md`) and confirm whether to dispatch a crewmate or enter away mode (`/afk`).
