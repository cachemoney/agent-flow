# Research: Upstream Specification for backpass Antigravity Transcript Discovery and Invocation

**Target Upstream Repository:** [`kunchenguid/backpass`](https://github.com/kunchenguid/backpass)  
**Related Issue:** [cachemoney/agent-flow#12](https://github.com/cachemoney/agent-flow/issues/12) (blocking [cachemoney/agent-flow#13](https://github.com/cachemoney/agent-flow/issues/13))  
**Author:** Antigravity Research Subagent  
**Date:** 2026-09-17  

---

## 1. Executive Summary & Context

[`kunchenguid/backpass`](https://github.com/kunchenguid/backpass) is an automated memory and skill optimization framework for AI developer workflows. It inspects session histories produced by various agentic harnesses (Claude Code, Codex CLI, Pi, Grok, OpenCode, Cursor, Hermes), normalizes and distills their conversations into unified traces, calculates empirical loss and gradient steps against `AGENTS.md` and repository skills, and proposes targeted prompt and skill improvements via an automated gradient-descent loop.

To expand `backpass` to support the **Antigravity (`agy`)** ecosystem:
1. **Discovery Support:** `backpass` must locate and parse local Antigravity sessions stored on disk under the user's application data directory (defaulting to `~/.gemini/antigravity-cli/brain/`), correlate tool executions, attribute sessions to repository workspaces (supporting Tier 1 and Tier 1.5 association), and feed distilled events into `backpass`'s analysis pipeline.
2. **Invocation Support:** `backpass` must be able to use `agy` as an execution agent for both analysis and synthesis turns, applying one-off model overrides (`--model <id>`), reasoning effort levels (`--effort <low|medium|high>`), and native write permissions (`--dangerously-skip-permissions`) via ephemeral process wrappers without altering global defaults.

This document specifies the exact transcript layout on disk, provides complete implementation code for `src/discovery/adapters/antigravity.js`, details integration into `src/discovery/index.js`, `src/config.js`, `src/discovery/self.js`, `src/acpx.js`, and `src/harness-invoke.js`, and defines a comprehensive test suite.

---

## 2. Antigravity Transcript Structure on Disk

### 2.1 File System and Directory Layout

Antigravity persists each conversation session inside a dedicated workspace under `<appDataDir>/brain/<conversation-id>/`.

- **Default Root:** `~/.gemini/antigravity-cli/brain/`
- **Environment Overrides:** Configurable via `ANTIGRAVITY_DATA_DIR`, `ANTIGRAVITY_HOME`, or `AGY_HOME`.

```
~/.gemini/antigravity-cli/
├── brain/
│   ├── <conversation-uuid-1>/
│   │   ├── .system_generated/
│   │   │   ├── logs/
│   │   │   │   ├── transcript.jsonl        # Compact JSONL transcript (truncated large payloads)
│   │   │   │   ├── transcript_full.jsonl   # Complete, untruncated JSONL transcript
│   │   │   │   └── chunks/                # Streaming chunk buffers
│   │   │   ├── steps/                     # Step artifacts (output.txt, etc.)
│   │   │   ├── subagents/                 # Child subagent registries (<subagent-uuid>.json)
│   │   │   └── worktrees/                 # Isolated git worktrees for subagents
│   │   ├── scratch/                       # Transient scripts and files
│   │   └── .user_uploaded/                # Files uploaded by the user
│   └── <conversation-uuid-2>/
│       └── ...
```

### 2.2 Compact vs. Full Transcript Files

Antigravity writes two parallel JSONL files per session:
1. **`transcript.jsonl` (Compact):** Designed for fast sequential scanning and lightweight reading. When a field (such as tool output or expansive prompt instructions) exceeds the inline limit (approx. 4 KB), it is truncated, and an array field `truncated_fields: ["content", ...]` is stamped on the JSON record.
2. **`transcript_full.jsonl` (Full):** Preserves the complete, untruncated text for every step.

**Discovery & Ingestion Rule:**
- Discovery header inspection (`classify`) uses `transcript.jsonl` to ensure minimal disk I/O and zero unnecessary memory allocations.
- Full session reading (`read`) checks if `transcript_full.jsonl` exists in the same directory. If present, it reads `transcript_full.jsonl` directly (or falls back to `transcript.jsonl` if missing or unreadable), guaranteeing that distilled message traces and tool outputs are complete.

### 2.3 JSONL Step Schema & Lifecycle

Each line in `transcript.jsonl` / `transcript_full.jsonl` is a single serialized JSON object representing an atomic interaction step in the conversation:

```typescript
interface AntigravityStep {
  step_index: number;            // 0-indexed sequential step counter
  source: "USER_EXPLICIT" | "MODEL" | "SYSTEM";
  type: "USER_INPUT" | "PLANNER_RESPONSE" | "GENERIC";
  status: "DONE" | "ERROR" | "CANCELLED";
  created_at: string;            // ISO 8601 UTC timestamp (e.g. "2026-09-18T02:40:22Z")
  content?: string;              // Text payload (user prompt, model message, or tool result)
  thinking?: string;             // Chain-of-thought internal reasoning (omitted from distillation)
  tool_calls?: AntigravityToolCall[]; // Array of tool calls requested in this step
  media?: Array<{ mime_type: string; uri: string }>;
  truncated_fields?: string[];   // Present only in transcript.jsonl when truncation occurred
}

interface AntigravityToolCall {
  name: string;                  // Tool name, e.g. "run_command", "view_file", "replace_file_content"
  args: Record<string, any>;     // Key-value argument dictionary
  toolAction?: string;           // Optional human-readable action label
  toolSummary?: string;          // Optional human-readable summary label
}
```

#### Step Type Roles & Sequencing

1. **`USER_INPUT` (`source: "USER_EXPLICIT" | "SYSTEM"`):**
   - Contains the human request or subagent delegation instructions.
   - The user's prompt text is wrapped in `<USER_REQUEST>...</USER_REQUEST>`.
   - Subsequent system scaffolding may be appended in `<ADDITIONAL_METADATA>`, `<user_information>`, or `<USER_SETTINGS_CHANGE>` tags.
   - Extracting the text inside `<USER_REQUEST>` isolates pure user intent and avoids prompt bloat.

2. **`PLANNER_RESPONSE` (`source: "MODEL"`):**
   - Contains the assistant's turn.
   - If the model is returning conversational text, `content` contains markdown.
   - If the model is invoking tools, `tool_calls` contains an array of `AntigravityToolCall` items (`name` and `args`).
   - If internal reasoning is present, `thinking` contains the CoT log (which backpass filters out as non-distillable noise).

3. **`GENERIC` (`source: "MODEL"`):**
   - Contains the execution result of the preceding tool call.
   - If a `PLANNER_RESPONSE` emitted $N$ tool calls, it is followed by $N$ subsequent `GENERIC` steps in matching order.
   - `content` holds the raw stdout, file contents, or result text.
   - `status: "DONE"` indicates successful completion; `status: "ERROR"` indicates failure.

---

## 3. Implementation Specification: Discovery Adapter

### 3.1 Adapter Module: `src/discovery/adapters/antigravity.js`

This module adheres to the standard `backpass` file-backed discovery adapter contract (`enumerate`, `classify`, `read`).

```javascript
import fs from "node:fs";
import path from "node:path";

import { emptyInteractionSignals, interactionSignals } from "../../interaction.js";
import {
  attachToolResults,
  home,
  listDirs,
  parseJsonLine,
  readHeadLines,
  readJsonl,
  statOrNull,
} from "./shared.js";

const HEADER_LINES = 40;

export const name = "antigravity";

/**
 * Antigravity stores sessions under:
 *   <appDataDir>/brain/<conversation-id>/.system_generated/logs/transcript.jsonl
 *
 * Supported environment overrides:
 *   ANTIGRAVITY_DATA_DIR, ANTIGRAVITY_HOME, AGY_HOME
 */
export function storeRoots() {
  const custom =
    process.env.ANTIGRAVITY_DATA_DIR ||
    process.env.ANTIGRAVITY_HOME ||
    process.env.AGY_HOME;

  const roots = [];
  if (custom) {
    const trimmed = custom.trim();
    roots.push(trimmed.endsWith("brain") ? trimmed : path.join(trimmed, "brain"));
  }
  roots.push(home(".gemini", "antigravity-cli", "brain"));
  return [...new Set(roots)];
}

/**
 * Enumerate session candidate files across all configured brain roots.
 * @param {{ cutoffMs?: number }} [options]
 */
export function enumerate({ cutoffMs } = {}) {
  const out = [];
  for (const root of storeRoots()) {
    if (!fs.existsSync(root)) continue;
    for (const sessionDir of listDirs(root)) {
      const transcriptPath = path.join(sessionDir, ".system_generated", "logs", "transcript.jsonl");
      const stat = statOrNull(transcriptPath);
      if (!stat) continue;
      if (cutoffMs && stat.mtimeMs < cutoffMs) continue;
      out.push({
        key: transcriptPath,
        path: transcriptPath,
        mtimeMs: stat.mtimeMs,
        bytes: stat.size,
      });
    }
  }
  return out;
}

/**
 * Safely unquote arguments that may have been double-serialized as JSON strings.
 */
function cleanArgValue(val) {
  if (typeof val !== "string") return val;
  const trimmed = val.trim();
  if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'"))) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed.slice(1, -1);
    }
  }
  return trimmed;
}

/**
 * Classify a candidate session by inspecting the header lines of transcript.jsonl.
 * Extracts session ID, startedAt, working directory (cwd), model, and interaction signals.
 */
export function classify(candidate) {
  const headLines = readHeadLines(candidate.path, HEADER_LINES);
  if (!headLines.length) return null;

  const sessionDir = path.basename(path.dirname(path.dirname(path.dirname(candidate.path))));
  let id = sessionDir;
  let cwd = null;
  let startedAt = null;
  let model = null;
  let isSubagent = false;

  for (const line of headLines) {
    const step = parseJsonLine(line);
    if (!step) continue;

    if (!startedAt && step.created_at) {
      startedAt = Date.parse(step.created_at);
    }

    if (step.type === "USER_INPUT") {
      const content = step.content || "";
      if (content.includes("<subagent_reminder>")) {
        isSubagent = true;
      }
      // Check for user_information workspace mapping: [URI] -> [CorpusName]
      if (!cwd && content.includes("<user_information>")) {
        const match = content.match(/(\/[^\s\n\r]+)\s*->/);
        if (match && match[1]) {
          cwd = match[1];
        }
      }
      // Check for setting changes reflecting model
      if (!model && content.includes("<USER_SETTINGS_CHANGE>")) {
        const match = content.match(/Model Selection` from \w+ to ([^\n<]+)/);
        if (match) model = match[1].trim();
      }
    }

    if (step.type === "PLANNER_RESPONSE") {
      if (Array.isArray(step.tool_calls)) {
        for (const tc of step.tool_calls) {
          const args = tc.args || {};
          // Direct CWD clues from tool arguments
          if (!cwd) {
            if (args.Cwd) cwd = cleanArgValue(args.Cwd);
            else if (args.SearchDirectory) cwd = cleanArgValue(args.SearchDirectory);
            else if (args.DirectoryPath) cwd = cleanArgValue(args.DirectoryPath);
            else if (args.AbsolutePath) {
              const file = cleanArgValue(args.AbsolutePath);
              cwd = path.dirname(file);
            } else if (args.TargetFile) {
              const file = cleanArgValue(args.TargetFile);
              cwd = path.dirname(file);
            }
          }
        }
      }
    }

    if (cwd) break;
  }

  if (!cwd) return null;

  return {
    id: id || path.basename(candidate.path, ".jsonl"),
    cwd,
    gitBranch: null,
    remotes: [],
    startedAt: startedAt || candidate.mtimeMs,
    model: model || null,
    interactionSignals: isSubagent ? interactionSignals({ originator: "subagent" }) : emptyInteractionSignals(),
  };
}

/**
 * Extract the pure user prompt from a USER_INPUT step content string.
 */
function extractUserPrompt(content) {
  if (!content) return "";
  const match = content.match(/<USER_REQUEST>([\s\S]*?)<\/USER_REQUEST>/);
  if (match) return match[1].trim();
  // Strip common Antigravity system scaffolding if USER_REQUEST tags are missing
  return content
    .replace(/<ADDITIONAL_METADATA>[\s\S]*?<\/ADDITIONAL_METADATA>/g, "")
    .replace(/<USER_SETTINGS_CHANGE>[\s\S]*?<\/USER_SETTINGS_CHANGE>/g, "")
    .replace(/<user_information>[\s\S]*?<\/user_information>/g, "")
    .replace(/<user_rules>[\s\S]*?<\/user_rules>/g, "")
    .replace(/<skills>[\s\S]*?<\/skills>/g, "")
    .replace(/<subagents>[\s\S]*?<\/subagents>/g, "")
    .trim();
}

/**
 * Read a full session and normalize it to backpass distiller events.
 * Prefers transcript_full.jsonl to avoid truncation artifacts.
 */
export function read(ref) {
  const fullPath = path.join(path.dirname(ref.path), "transcript_full.jsonl");
  const readPath = fs.existsSync(fullPath) ? fullPath : ref.path;
  const entries = readJsonl(readPath);

  const events = [];
  const pendingToolQueue = [];
  let model = ref.model || null;

  for (const step of entries) {
    if (step.type === "USER_INPUT") {
      const text = extractUserPrompt(step.content);
      if (text) {
        events.push({ kind: "message", role: "user", text });
      }
    } else if (step.type === "PLANNER_RESPONSE") {
      if (step.content && step.content.trim()) {
        events.push({ kind: "message", role: "assistant", text: step.content.trim() });
      }
      if (Array.isArray(step.tool_calls) && step.tool_calls.length > 0) {
        step.tool_calls.forEach((tc, idx) => {
          const callId = `${step.step_index}_${idx}`;
          const cleanArgs = {};
          if (tc.args && typeof tc.args === "object") {
            for (const [k, v] of Object.entries(tc.args)) {
              cleanArgs[k] = cleanArgValue(v);
            }
          }
          events.push({
            kind: "tool",
            name: tc.name,
            input: cleanArgs,
            pendingId: callId,
          });
          pendingToolQueue.push(callId);
        });
      }
    } else if (step.type === "GENERIC") {
      const callId = pendingToolQueue.shift();
      events.push({
        kind: "tool-result",
        id: callId,
        result: step.content || "",
        status: step.status === "ERROR" ? "error" : "completed",
      });
    }
  }

  return { events: attachToolResults(events), model };
}
```

### 3.2 Registration in `src/discovery/index.js` and `src/config.js`

To enable the adapter across discovery and configuration:

1. **`src/discovery/index.js`:**
   ```javascript
   import * as antigravity from "./adapters/antigravity.js";

   export const ADAPTERS = Object.assign(Object.create(null), {
     claude,
     codex,
     pi,
     grok,
     opencode,
     hermes,
     cursor: cursorCli,
     "cursor-ide": cursorIde,
     antigravity,
     agy: antigravity, // alias for CLI ergonomics
   });
   ```

2. **`src/config.js`:**
   Add `"antigravity"` to `ALL_HARNESSES`:
   ```javascript
   export const ALL_HARNESSES = [
     "claude",
     "codex",
     "pi",
     "opencode",
     "grok",
     "cursor",
     "hermes",
     "antigravity",
   ];
   ```

### 3.3 Self-Session Filtering: `src/discovery/self.js`

`backpass` identifies its own synthetic runs by checking if the first user prompt begins with `SELF_SESSION_SENTINEL`. Because `agy` automatically encloses user prompts in `<USER_REQUEST>\n`, `SENTINEL_PATTERN` in `src/discovery/self.js` must be updated to optionally match `<USER_REQUEST>\n`:

```javascript
// In src/discovery/self.js:
const SENTINEL_PATTERN = new RegExp(
  `"(?:text|content|message)":"(?:<USER_REQUEST>\\\\n)?${escapeRegExp(jsonInner(SELF_SESSION_SENTINEL))}`
);
```
This ensures backpass's analysis and synthesis runs with `agy` are cleanly excluded from subsequent training corpora.

---

## 4. Implementation Specification: Model & Effort Overlays in `src/harness-invoke.js`

### 4.1 Invocation Overlays Architecture

When `backpass` invokes an agent for analysis or synthesis (`src/acpx.js` -> `prepareHarnessInvocation`), it must apply:
1. `--model <id>`: A specific model name or alias.
2. `--effort <low|medium|high>`: Reasoning effort (analysis default: `medium`; synthesis default: `high`).
3. `--dangerously-skip-permissions`: Unattended tool approval for synthesis staging writes.

Because Antigravity CLI does not use persistent session-modifying configuration files during one-off command invocations, these flags must be injected as **process argv flags** passed to `agy` via an ephemeral node wrapper script executed through acpx's `--agent <command>` parameter.

### 4.2 Implementation in `src/harness-invoke.js`

Add the `agyInvocation` helper and wire it into `prepareHarnessInvocation`:

```javascript
// In src/harness-invoke.js:

const VALID_AGY_EFFORTS = new Set(["low", "medium", "high"]);

function agyInvocation({ requestedModel, requestedEffort, writeAccess = false, notes, cleanups, dispose }) {
  if (process.platform === "win32") {
    throw new UserError(
      `cannot apply ${describeOverride(requestedModel, requestedEffort) || "file-write flags"} through acpx --agent on Windows`,
      "pin pi, claude, codex, or opencode, or omit the model and effort override",
    );
  }

  const extra = [];
  if (writeAccess) {
    // Auto-approve tool executions in the staging workspace without human prompting
    extra.push("--dangerously-skip-permissions");
  }
  if (requestedModel) {
    extra.push("--model", requestedModel);
  }
  if (requestedEffort) {
    const normalized = requestedEffort.toLowerCase();
    if (!VALID_AGY_EFFORTS.has(normalized)) {
      throw new UserError(
        `agy requires reasoning effort to be one of "low", "medium", or "high" (got "${requestedEffort}")`,
        "set effort to low, medium, or high, or omit the effort override",
      );
    }
    extra.push("--effort", normalized);
  }

  const real = resolveOnPath("agy");
  if (!real) {
    throw new UserError(
      `cannot apply ${describeOverride(requestedModel, requestedEffort) || "file-write flags"} as agy process flags because agy was not found on PATH`,
      "install the agy CLI, or pin a different agent / omit the model and effort override",
    );
  }

  const { nodeCommand, dir } = writeArgvWrapper({ realCommand: real, extraArgs: extra, binName: "agy" });
  cleanups.push(() => fs.rmSync(dir, { recursive: true, force: true }));

  return {
    env: undefined,
    acpxModel: null,
    setEffortKey: null,
    sessionMode: null,
    sessionModeRequired: false,
    acpxAgentCommand: nodeCommand,
    requiredBuiltinAgent: null,
    notes,
    dispose,
  };
}
```

Wire into `prepareHarnessInvocation`:
```javascript
// In prepareHarnessInvocation() in src/harness-invoke.js:
    if (agent === "pi") {
      invocation = overlay
        ? piInvocation({ requestedModel, requestedEffort, notes, cleanups, dispose })
        : baseInvocation({ notes, dispose });
    } else if (agent === "grok") {
      invocation = grokInvocation({ requestedModel, requestedEffort, writeAccess, notes, cleanups, dispose });
    } else if (agent === "antigravity" || agent === "agy") {
      invocation = agyInvocation({ requestedModel, requestedEffort, writeAccess, notes, cleanups, dispose });
    } else if (agent === "claude" || agent === "codex" || agent === "opencode") {
...
```

Update `src/acpx.js`:
```javascript
// In src/acpx.js:
const ACPX_AGENT_NAMES = {
  grok: "grok-build",
  antigravity: "agy",
};
```

---

## 5. Testing Strategy

### 5.1 Discovery Test Suite: `test/discovery/antigravity.test.js`

Add a test suite verifying all behaviors using synthetic fixtures and real Antigravity structures:

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import * as antigravity from "../../src/discovery/adapters/antigravity.js";
import { statOrNull } from "../../src/discovery/adapters/shared.js";
import { distill } from "../../src/distill.js";

function candidateFor(file) {
  const stat = statOrNull(file);
  return { key: file, path: file, mtimeMs: stat.mtimeMs, bytes: stat.size };
}

function writeMockSession(rootDir, sessionId, lines) {
  const logDir = path.join(rootDir, sessionId, ".system_generated", "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const filePath = path.join(logDir, "transcript.jsonl");
  fs.writeFileSync(filePath, lines.map((l) => JSON.stringify(l)).join("\n") + "\n");
  return filePath;
}

test("antigravity adapter classifies session with Cwd from run_command", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "agy-test-"));
  const sessionId = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
  const file = writeMockSession(tmp, sessionId, [
    {
      step_index: 0,
      source: "USER_EXPLICIT",
      type: "USER_INPUT",
      status: "DONE",
      created_at: "2026-09-18T00:00:00Z",
      content: "<USER_REQUEST>\nFix bug in parser\n</USER_REQUEST>",
    },
    {
      step_index: 1,
      source: "MODEL",
      type: "PLANNER_RESPONSE",
      status: "DONE",
      created_at: "2026-09-18T00:00:05Z",
      tool_calls: [
        {
          name: "run_command",
          args: { CommandLine: "npm test", Cwd: "\"/workspace/repo\"" },
        },
      ],
    },
  ]);

  const candidate = candidateFor(file);
  const desc = antigravity.classify(candidate);

  assert.ok(desc);
  assert.equal(desc.id, sessionId);
  assert.equal(desc.cwd, "/workspace/repo");
  assert.equal(desc.startedAt, Date.parse("2026-09-18T00:00:00Z"));
});

test("antigravity adapter reads full session, unquotes args, and folds tool results", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "agy-test-read-"));
  const sessionId = "b2c3d4e5-f6a7-8901-bcde-f12345678901";
  const file = writeMockSession(tmp, sessionId, [
    {
      step_index: 0,
      source: "USER_EXPLICIT",
      type: "USER_INPUT",
      status: "DONE",
      created_at: "2026-09-18T00:00:00Z",
      content: "<USER_REQUEST>\nRun test suite\n</USER_REQUEST>",
    },
    {
      step_index: 1,
      source: "MODEL",
      type: "PLANNER_RESPONSE",
      status: "DONE",
      created_at: "2026-09-18T00:00:02Z",
      tool_calls: [
        {
          name: "run_command",
          args: { CommandLine: "npm test", Cwd: "\"/repo/app\"" },
        },
      ],
    },
    {
      step_index: 2,
      source: "MODEL",
      type: "GENERIC",
      status: "DONE",
      created_at: "2026-09-18T00:00:04Z",
      content: "PASS 14 tests passing",
    },
    {
      step_index: 3,
      source: "MODEL",
      type: "PLANNER_RESPONSE",
      status: "DONE",
      created_at: "2026-09-18T00:00:06Z",
      content: "All tests passed successfully.",
    },
  ]);

  const { events } = antigravity.read({ path: file });
  assert.equal(events.length, 3);

  const [userMsg, toolCall, assistantMsg] = events;
  assert.equal(userMsg.kind, "message");
  assert.equal(userMsg.role, "user");
  assert.equal(userMsg.text, "Run test suite");

  assert.equal(toolCall.kind, "tool");
  assert.equal(toolCall.name, "run_command");
  assert.deepEqual(toolCall.input, { CommandLine: "npm test", Cwd: "/repo/app" });
  assert.equal(toolCall.result, "PASS 14 tests passing");
  assert.equal(toolCall.status, "completed");

  assert.equal(assistantMsg.kind, "message");
  assert.equal(assistantMsg.role, "assistant");
  assert.equal(assistantMsg.text, "All tests passed successfully.");

  // Verify distillation
  const meta = { harness: "antigravity", id: `antigravity-${sessionId}`, rawPath: file };
  const distilled = distill(events, meta);
  assert.ok(distilled.trace.includes("### turn 1 · user"));
  assert.ok(distilled.trace.includes("Run test suite"));
  assert.ok(distilled.trace.includes("tool: run_command"));
  assert.ok(distilled.trace.includes("PASS 14 tests passing"));
});

test("antigravity adapter honors ANTIGRAVITY_HOME env override", () => {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), "agy-home-"));
  process.env.ANTIGRAVITY_HOME = tmpHome;
  try {
    writeMockSession(path.join(tmpHome, "brain"), "sess-123", [
      { step_index: 0, type: "USER_INPUT", content: "hello" },
    ]);
    const candidates = antigravity.enumerate();
    assert.equal(candidates.length, 1);
    assert.ok(candidates[0].path.includes("sess-123"));
  } finally {
    delete process.env.ANTIGRAVITY_HOME;
  }
});
```

### 5.2 Harness Invocation Test Suite: `test/harness-invoke.test.js`

Add tests verifying argument synthesis and execution via `prepareHarnessInvocation`:

```javascript
test("agy invocation applies model, effort, and dangerously-skip-permissions", () => {
  const prevPath = process.env.PATH;
  const binDir = fs.mkdtempSync(path.join(os.tmpdir(), "fake-agy-bin-"));
  const fakeAgy = path.join(binDir, "agy");
  const logFile = path.join(binDir, "agy.log");

  fs.writeFileSync(
    fakeAgy,
    `#!${process.execPath}
const fs = require("node:fs");
fs.appendFileSync(${JSON.stringify(logFile)}, JSON.stringify(process.argv.slice(2)) + "\\n");
process.exit(0);
`,
  );
  fs.chmodSync(fakeAgy, 0o755);

  process.env.PATH = `${binDir}${path.delimiter}${prevPath}`;

  try {
    const invocation = prepareHarnessInvocation({
      agent: "agy",
      model: "gemini-3.8-pro",
      effort: "high",
      writeAccess: true,
    });

    assert.ok(invocation.acpxAgentCommand);
    assert.equal(invocation.acpxModel, null); // carried in process wrapper

    // Spawn the generated wrapper command
    const parts = invocation.acpxAgentCommand.split(" ").map((s) => s.replace(/^'|'$/g, ""));
    const { spawnSync } = await import("node:child_process");
    spawnSync(parts[0], parts.slice(1), { stdio: "ignore" });

    const logged = JSON.parse(fs.readFileSync(logFile, "utf8").trim());
    assert.ok(logged.includes("--dangerously-skip-permissions"));
    assert.ok(logged.includes("--model"));
    assert.ok(logged.includes("gemini-3.8-pro"));
    assert.ok(logged.includes("--effort"));
    assert.ok(logged.includes("high"));

    invocation.dispose();
  } finally {
    process.env.PATH = prevPath;
  }
});

test("agy invocation rejects invalid effort levels", () => {
  assert.throws(
    () => prepareHarnessInvocation({ agent: "agy", effort: "extreme" }),
    /agy requires reasoning effort to be one of "low", "medium", or "high"/,
  );
});
```

---

## 6. Upstream Delivery & PR Plan

### 6.1 Proposed Pull Request

1. **Title:** `feat(discovery,invoke): add Antigravity (agy) transcript discovery and invocation support`
2. **Branch Name:** `feature/antigravity-support` (upstream PR branch against `kunchenguid/backpass:main`)
3. **Changed Files:**
   - `src/discovery/adapters/antigravity.js` (new)
   - `src/discovery/index.js` (register `antigravity` and `agy`)
   - `src/config.js` (add to `ALL_HARNESSES`)
   - `src/discovery/self.js` (support `<USER_REQUEST>\n` sentinel prefix)
   - `src/acpx.js` (alias `antigravity -> agy`)
   - `src/harness-invoke.js` (implement `agyInvocation`)
   - `test/discovery/antigravity.test.js` (new discovery test suite)
   - `test/harness-invoke.test.js` (extended invocation tests)
   - `test/fixtures/antigravity-session.jsonl` (golden fixture)

### 6.2 Verification Checklist

Before submission, run the standard `backpass` CI validation matrix:
- [ ] `pnpm run check`
- [ ] `pnpm test`
- [ ] `pnpm run lint`
- [ ] `pnpm run format:check`
- [ ] `pnpm run typecheck`
