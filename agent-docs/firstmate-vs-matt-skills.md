---
title: Firstmate vs. Matt Pocock Skills Workflow Comparison
description: |
  Comprehensive guide comparing Firstmate and Matt Pocock's Skills ecosystems.
  Covers architectural differences, GitHub Issues vs. local backlog, AFK supervision
  mechanisms, and how to integrate both into a unified multi-agent workflow.
when: |
  When designing or running agent workflows combining Firstmate and Matt Pocock's skills.
  When deciding how to manage tasks, GitHub Issues, and backlogs across agents.
  When configuring or utilizing AFK (Away From Keyboard) modes and autonomous agent supervision.
---

# Firstmate vs. Matt Pocock's Skills: Architecture, GitHub Issues, and AFK Deep Dive

A comprehensive analysis of how **Firstmate** (`@repositories/firstmate`) and **Matt Pocock's Skills** (`@repositories/matt_skills`) operate, where their workflows align and diverge, how they handle tasks and issue trackers (specifically GitHub Issues), and how each approaches **AFK (Away From Keyboard)** workflows.

---

## 1. Executive Summary: What Are They?

At the highest level, **Firstmate** and **Matt Pocock's Skills** are not competitors; they operate at different layers of the AI engineering stack:

| Dimension | Firstmate | Matt Pocock's Skills |
| :--- | :--- | :--- |
| **Category** | **Agent Distro & Fleet Supervisor Runtime** | **Cognitive & Engineering Discipline Toolkit** |
| **Metaphor** | Ship & Crew (Captain $\to$ First Mate $\to$ Crewmates) | Senior Engineer's Toolbox (Socratic sparring, specs, TDD) |
| **Core Problem Solved** | "Tab juggling": Babysitting 3+ terminal agents, workspace collisions, managing concurrency, token waste while waiting. | "Misalignment & Ball of Mud": Agents building the wrong thing, messy unmaintainable code, skipping tests, vague jargon. |
| **Execution Model** | **Multi-agent fleet**: Spawns independent autonomous agents in separate terminal multiplexer panes (`tmux`, `zellij`, `herdr`, `orca`). | **Single-agent pair programming**: Structured workflows and prompts within a single session (or sub-agents in supported harnesses). |
| **Workspace Isolation** | **Disposable Git Worktrees** (`treehouse` / `orca`) for every task. | Runs in the current working directory / repo root. |
| **Task / Backlog Store** | **Local file-based queue** (`data/backlog.md` via `tasks-axi`). | **GitHub Issues** (or GitLab / local markdown via `gh` CLI). |
| **AFK Concept** | **Runtime operational posture & background daemon** (`/afk`, tokenless bash watcher, wedge alerts, return briefings). | **Task categorization & contract** (`HITL` vs `AFK` tickets, `ready-for-agent` labels, agent briefs). |

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     THE ORCHESTRATION STACK                             │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ FIRSTMATE (Fleet Supervisor & Process Manager)                    │  │
│  │  - Terminal backends (tmux, zellij, herdr, cmux, orca)            │  │
│  │  - Git Worktree isolation (treehouse)                             │  │
│  │  - Zero-token event-driven bash watcher & wedge alarms            │  │
│  │  - Runtime /afk daemon & PR merge authority gating                │  │
│  └──────────────────────────────────┬────────────────────────────────┘  │
│                                     │ spawns & supervises               │
│                                     ▼                                   │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ MATT POCOCK'S SKILLS (Methodology & Cognitive Tooling)            │  │
│  │  - Alignment & Planning: /grill-me, /to-spec, /wayfinder          │  │
│  │  - Issue Tracking & Triage: GitHub Issues, /triage, /to-tickets   │  │
│  │  - Engineering Rigor: /domain-modeling (CONTEXT.md), /tdd         │  │
│  │  - Verification: /code-review (standards + spec)                  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Architectural Breakdown

### Firstmate: The Agent Distro & Fleet Supervisor
Firstmate is **not** a model, not a skill library, and not an MCP server. It is an **Agent Distro**:
- **One Liaison**: You talk only to the **First Mate**. It acts as your chief of staff.
- **The Crew**: Autonomous workers (**Crewmates**) run in dedicated background terminal windows (default `tmux`, but supports `herdr`, `zellij`, `cmux`, `orca`).
- **Disposable Worktrees**: Every task runs in its own git worktree (`treehouse`). Three agents can touch the same repo simultaneously without Git conflicts or dirtying your primary working copy.
- **Strict Boundaries**: The First Mate is **read-only** over your projects. It does not write project code. Only Crewmates write code in their worktrees behind explicit delivery modes (`no-mistakes`, `direct-PR`, `local-only`) and merge authority (`yolo` vs captain approval).
- **Zero-Token Supervision**: When crewmates are busy coding or running builds, Firstmate doesn't spin LLM tokens polling them. A bash watcher sleeps on file events (`state/<id>.status`) and wakes the First Mate only when an agent finishes, fails, or needs a decision.

### Matt Pocock's Skills: Engineering Rigor for AI Agents
Matt Pocock's skills are focused on **how agents think, plan, and write software**:
- **Combatting Misalignment**: Agents often build the wrong thing because prompts are underspecified. [`/grill-me`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/productivity/grill-me/SKILL.md) and [`/grill-with-docs`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/grill-with-docs/SKILL.md) grill the human with deep, branching questions before any code is written.
- **Domain Modeling & Ubiquitous Language**: Agents get verbose and invent jargon. [`/domain-modeling`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/domain-modeling/SKILL.md) forces the agent to establish and maintain a [`CONTEXT.md`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/CONTEXT.md) and Architectural Decision Records (ADRs).
- **Tracer Bullets & Deep Modules**: [`/to-spec`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/to-spec/SKILL.md) and [`/to-tickets`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/to-tickets/SKILL.md) turn plans into actionable, atomic, dependency-linked tickets.
- **Feedback Loops**: Instead of "vibe coding", [`/tdd`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/tdd/SKILL.md) enforces a strict Red-Green-Refactor cycle, and [`/code-review`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/code-review/SKILL.md) evaluates PRs along two parallel axes: Coding Standards and Spec Conformance.
- **Wayfinding**: [`/wayfinder`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/wayfinder/SKILL.md) charts large, ambiguous efforts into decision tickets on a tracker map, exploring the "fog of war" one decision at a time.

---

## 3. Issue & Task Storage: Does Firstmate Support GitHub Issues?

### How Matt Pocock's Skills Handle GitHub Issues
In Matt Pocock's ecosystem, **GitHub Issues is a first-class, primary citizen**:
- Configured via [`/setup-matt-pocock-skills`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/setup-matt-pocock-skills/SKILL.md) and specified in [`docs/agents/issue-tracker.md`](file:///home/mezmo/Work/vibe/agent-flow/docs/agents/issue-tracker.md).
- **Issue Creation**: `gh issue create --title "..." --body "..."`.
- **Specs & Tickets**: [`/to-spec`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/to-spec/SKILL.md) publishes full markdown specifications as GitHub issues. [`/to-tickets`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/to-tickets/SKILL.md) creates child issues linked to parent specs.
- **Native Dependency Graph**: [`wayfinder`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/wayfinder/SKILL.md) and [`to-tickets`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/to-tickets/SKILL.md) use GitHub's native issue dependencies API:
  ```bash
  gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-id>
  ```
- **Triage State Machine**: Issues transition across 5 canonical labels (`needs-triage` $\to$ `needs-info` $\to$ `ready-for-agent` / `ready-for-human` $\to$ `wontfix`).
- **Agent Briefs**: When an issue reaches `ready-for-agent`, [`/triage`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/triage/SKILL.md) posts an authoritative `## Agent Brief` comment directly on the GitHub Issue.

### How Firstmate Handles Tasks & Backlog
**Firstmate does NOT natively use GitHub Issues as its task backlog.**

Instead, Firstmate uses an internal, local file-based queue:
1. **Local Backlog Store**: Backlog items live in [`data/backlog.md`](file:///home/mezmo/Work/vibe/agent-flow/repositories/firstmate/.tasks.toml) within the Firstmate home directory (`FM_HOME`).
2. **The `tasks-axi` CLI**: Firstmate delegates task mutations to `tasks-axi` (`bin/fm-tasks-axi.sh`), configured in `.tasks.toml`:
   ```toml
   backend = "markdown"

   [markdown]
   path = "data/backlog.md"
   archive = "data/done-archive.md"
   done_keep = 10
   ```
3. **Task Lifecycle**: Tasks have internal states (`Queued`, `In flight`, `Done`, `Archived`). When Firstmate spawns a worker, `bin/fm-spawn.sh` atomically moves the item in `data/backlog.md` to *In flight*. When a task finishes, `bin/fm-teardown.sh` moves it to *Done*.
4. **How Firstmate Uses GitHub**:
   - Firstmate **does** use the `gh` CLI (`gh auth login`, `gh-axi`), but **exclusively for Pull Requests and Git operations**:
     - Cloning repos into `projects/<repo>`.
     - Monitoring PRs (`gh pr view`).
     - Polling PR mergeability and CI check statuses.
     - Executing guarded PR merges (`bin/fm-pr-merge.sh`).
   - Firstmate has no built-in polling loop or background sync for GitHub Issues.

### Can You Connect Firstmate to GitHub Issues?
**Yes, easily**, through three practical integration patterns:

1. **Intake Bridge (Prompt-Level)**:
   You tell Firstmate:
   > *"Ahoy! Look at GitHub issue #42 in project xyz (`gh issue view 42`), file a task for it, and dispatch a crewmate to implement it."*
   Firstmate will fetch the issue body via `gh`, generate a task brief (`bin/fm-brief.sh`), write a backlog item in `data/backlog.md`, and spawn a crewmate.
2. **Scout-to-Issue Workflow**:
   Firstmate supports **Scout tasks** (investigation/research tasks that output `data/<id>/report.md`). A scout or Firstmate script can be instructed to post its findings or open a ticket directly back to GitHub Issues using `gh issue comment` or `gh issue create`.
3. **Pluggable `tasks-axi` Backend**:
   Firstmate's backlog architecture abstracts storage via `tasks-axi` (`config/backlog-backend`). If a custom `tasks-axi` adapter or wrapper is pointed at GitHub Issues or Linear, Firstmate will read and transition those items directly.

---

## 4. AFK (Away From Keyboard) Deep Dive: How Both Support It

Both workflows emphasize "Away From Keyboard" (AFK) operation, but they mean very different things:

| Aspect | Firstmate `/afk` | Matt Pocock's Skills AFK |
| :--- | :--- | :--- |
| **What is it?** | A **runtime operational mode & supervision daemon**. | A **work categorization & contract boundary**. |
| **Mechanism** | Bash sub-supervisor daemon (`bin/fm-afk-start.sh`) running on file-event watcher. | Ticket labeling (`ready-for-agent`, `wayfinder:task (AFK)`, `wayfinder:research`). |
| **Token Consumption** | **Zero tokens** while agents work. LLM is not called until an alert or return. | Standard token consumption per session or subagent execution. |
| **Human Escalation** | **Wedge alarm** (macOS Notification Center / terminal bell) triggers if an agent gets stuck. | Agent halts in chat and waits for human input. |
| **Return Experience** | **Return Briefing**: On typing any message, Firstmate summarizes everything completed, decisions waiting, blockers, and cost. | You review the closed tickets, PRs, or Git branches manually. |

### How Firstmate's `/afk` Works
In Firstmate, `/afk` is a core engineering feature designed to let you physically step away from your machine while multiple agents code:
1. **Mandate Clauses**: You invoke `/afk [your words]` (e.g., `/afk heading to lunch, merge auth-fix if green, do not touch payments`).
2. **Away Contract**: Firstmate writes a durable record (`state/.afk-contract`). It announces that it is in hold-for-return mode.
3. **Zero-Token Daemon**: A background bash daemon runs. It manages the watcher. If a crewmate outputs progress or runs tests, bash consumes the logs. No tokens are burned.
4. **Wedge Alarms**: If a crewmate crashes, gets stuck in an infinite loop, or hits an unrecoverable blocker, the away daemon fires an active desktop alert (`docs/wedge-alarm.md`).
5. **The Return Catch-up**: You don't type `/back`. You simply type any normal message. Firstmate automatically detects your return, shuts down the daemon, runs `bin/fm-afk-return.sh`, and gives you a structured briefing:
   - Supervisor health during your absence.
   - What was finished and shipped.
   - Any PRs waiting for your review.
   - Any open blockers or questions that need your decision.
   - Token/monetary cost incurred.

### How Matt Pocock's Skills Handle AFK
In Matt Pocock's skills, AFK is about **spec completeness and autonomy contracts**:
1. **HITL vs. AFK Classification**:
   - **HITL (Human In The Loop)**: Tasks that *require* the human's taste, intent, or decision. Examples: `/grill-me`, `/domain-modeling`, prototype reviews. The agent is strictly forbidden from answering its own questions.
   - **AFK (Away From Keyboard)**: Tasks that are sufficiently specified for an agent to execute autonomously. Examples: `/research` (spawns background subagents on throwaway branches), `/tdd` implementation.
2. **`ready-for-agent` Contract**:
   When an issue is triaged with [`/triage`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/triage/SKILL.md), marking it `ready-for-agent` requires an **Agent Brief**. This brief contains:
   - Target files and interfaces.
   - Definition of done.
   - Test criteria.
   - Out-of-scope boundaries.
   An AFK runner or agent can pick up this ticket and run with zero human steering.
3. **Wayfinder Parallel AFK Burns**:
   In [`/wayfinder`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/wayfinder/SKILL.md), when charting a map, any `research` tickets are marked AFK. The charting session fires parallel subagents to burn down all research tickets in the background while leaving you free.

---

## 5. Detailed Comparison Matrix

| Capability | Firstmate | Matt Pocock's Skills |
| :--- | :--- | :--- |
| **Primary Focus** | Orchestrating and supervising multiple concurrent coding agents. | Guiding agent reasoning, architecture, testing, and alignment. |
| **Agent Roles** | Captain (User), First Mate (Supervisor), Crewmates (Workers), Second Mates (Remote/Persistent). | User + Agent (Pair programming), Subagents (Research, Dual-Axis Review). |
| **Issue Tracker** | Local Markdown (`data/backlog.md` via `tasks-axi`). | GitHub Issues (default via `gh`), GitLab, or Local Markdown. |
| **PR Management** | Full automated tracking, CI polling, merge authority (`bin/fm-pr-merge.sh`). | Code review subagents (`/code-review`), relies on standard `gh pr` commands. |
| **Test Discipline** | Delegates testing to repo's test suite or `no-mistakes` validation pipeline. | Strict Test-Driven Development ([`/tdd`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/tdd/SKILL.md) red-green-refactor loop). |
| **Code Architecture** | Enforces worktree isolation and prevents cross-project writes. | Enforces deep modules ([`/codebase-design`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/codebase-design/SKILL.md)), refactoring audits ([`/improve-codebase-architecture`](file:///home/mezmo/Work/vibe/agent-flow/repositories/matt_skills/skills/engineering/improve-codebase-architecture/SKILL.md)). |
| **Domain Knowledge** | `data/captain.md`, `data/learnings.md`, `data/projects.md`. | `CONTEXT.md` (Ubiquitous language dictionary), `docs/adr/` (ADRs). |
| **Away Mode** | `/afk` daemon with tokenless bash watcher, desktop alerts, return catch-up. | Categorizes tickets as AFK vs HITL; attaches structured agent briefs. |
| **Harness Support** | Claude Code, Grok, Pi, Oh My Pi, Codex, OpenCode, Cursor Agent CLI. | Claude Code, Codex, and any model/harness supporting skills/prompts. |

---

## 6. How to Combine Both: The Ideal Hybrid Workflow

Because Firstmate is an **orchestration runtime** and Matt Pocock's skills are **cognitive disciplines**, they complement each other cleanly. Here is the blueprint for running them together:

```
                      PLANNING & SPECIFICATION (HITL)
                                    │
                                    │ Human + Agent (Matt Pocock Skills)
                                    │ • /wayfinder charts unknown terrain
                                    │ • /grill-with-docs aligns intent & updates CONTEXT.md
                                    │ • /to-spec & /to-tickets publish to GitHub Issues
                                    ▼
                          GITHUB ISSUES / SPEC
                    ┌────────────────────────────────┐
                    │ Issue #101: Auth Seam Refactor │
                    │ - Labels: ready-for-agent      │
                    │ - Agent Brief attached         │
                    └───────────────┬────────────────┘
                                    │
                                    │ Human triggers Firstmate
                                    ▼
                      FLEET ORCHESTRATION (FIRSTMATE)
                    ┌────────────────────────────────┐
                    │ First Mate ingests Issue #101  │
                    │ Creates brief in FM_HOME       │
                    │ Spawns Crewmate in worktree    │
                    └───────────────┬────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    ▼                                ▼
       FIRSTMATE /afk SUPERVISION         CREWMATE EXECUTION (WORKTREE)
     ┌────────────────────────────┐     ┌───────────────────────────────┐
     │ Captain types: /afk        │     │ Crewmate loads Matt's Skills: │
     │ - Bash watcher sleeps      │     │ • /tdd (Red-Green-Refactor)   │
     │ - Zero tokens burned       │     │ • /codebase-design (Deep Mod) │
     │ - Wedge alarm on failure   │     │ • /code-review (Dual Axis)    │
     │ - Briefing on return       │     │ Pushes PR -> CI Runs          │
     └────────────────────────────┘     └───────────────┬───────────────┘
                                                        │
                                                        ▼
                                              FIRSTMATE PR LIFECYCLE
                                        ┌───────────────────────────────┐
                                        │ Firstmate detects passing PR  │
                                        │ Merges if YOLO, else alerts   │
                                        │ Closes GitHub Issue #101      │
                                        └───────────────────────────────┘
```

### The 4-Step Synthesis Recipe

1. **Plan in GitHub Issues (Using Matt Pocock's Skills)**:
   - Run `/wayfinder` or `/grill-with-docs` to sharpen the requirements and domain model in `CONTEXT.md`.
   - Run `/to-spec` and `/to-tickets` to publish tracer-bullet issues directly to GitHub Issues with native dependency links.
   - Run `/triage` so the issues have `ready-for-agent` labels and complete Agent Briefs.
2. **Dispatch Fleet (Using Firstmate)**:
   - Tell Firstmate: *"Ahoy! Ingest the open `ready-for-agent` issues from GitHub for project X and dispatch crewmates."*
   - Firstmate assigns each issue to a crewmate running in an isolated `treehouse` git worktree.
3. **Equip Crewmates with Matt's Engineering Skills**:
   - Ensure the project or crewmate harnesses have Matt's skills installed (e.g. via `skills.sh add mattpocock/skills`).
   - In Firstmate's brief instructions, instruct the crewmates to use `/tdd` for all feature logic and run `/code-review` before finalizing their commits.
4. **Step Away with `/afk`**:
   - Type `/afk` in Firstmate.
   - Walk away. The bash sub-supervisor monitors all panes with zero token waste.
   - If a crewmate gets stuck, your desktop alarm rings.
   - When you return, Firstmate gives you a complete briefing of all merged PRs, green checks, and closed GitHub issues.
