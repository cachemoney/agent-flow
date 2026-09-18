# Agent Flow

Unified meta-repository workspace integrating Firstmate fleet supervision, Antigravity (`agy`), and the AXI plugin ecosystem.

## Language

**Harness**:
The host runtime environment executing an AI agent process (e.g. `agy`, `claude`, `codex`, `opencode`).
_Avoid_: Agent runner, model wrapper

**AXI Plugin**:
A command-line tool built according to the Agent eXperience Interface specification providing token-efficient TOON output, contextual suggestions, and session hooks.
_Avoid_: MCP server, skill script

**Ambient Context**:
Real-time state (backlog status, active PRs, browser sessions) surfaced into an agent session before user or turn execution.
_Avoid_: System prompt, environment variable

**Session Lock**:
The exclusive file lock (`state/.lock`) proving single-process ownership of a Firstmate supervisor instance.
_Avoid_: Mutex, pidfile

**Supervision Wake**:
The protocol by which background fleet events return control to an idle or waiting supervisor agent.
_Avoid_: Polling loop, cron job

**Transcript Store**:
On-disk JSONL or event logs recorded by an agent harness during interactive or headless sessions.
_Avoid_: Chat history, session dump
