# Upstream Specification: Antigravity (`agy`) Hook Support in `axi-sdk-js`

**Author:** Antigravity Research Agent  
**Ticket:** [cachemoney/agent-flow#11](https://github.com/cachemoney/agent-flow/issues/11)  
**Target Upstream Repository:** [`kunchenguid/axi`](https://github.com/kunchenguid/axi) (`packages/axi-sdk-js`)  
**Date:** September 17, 2026  
**Status:** Complete / Ready for Upstream Implementation  

---

## 1. Executive Summary & Context

Agent Experience Interface (AXI) tooling—including `tasks-axi`, `gh-axi`, `chrome-devtools-axi`, and `lavish-axi`—provides ambient context to AI coding agents on session startup. In these packages, the command `setup hooks` delegates entirely to `axi-sdk-js`'s `installSessionStartHooks()`.

Currently, `axi-sdk-js` (`packages/axi-sdk-js/src/hooks.ts`) injects ambient context into three agent environments:
1. **Claude Code**: Declarative `hooks.SessionStart` entry in `~/.claude/settings.json` (user scope) or `<repo>/.claude/settings.json` (project scope).
2. **Codex CLI**: Declarative `hooks.SessionStart` entry in `~/.codex/hooks.json` (or `<repo>/.codex/hooks.json`), accompanied by `[features].hooks = true` in `~/.codex/config.toml`.
3. **OpenCode**: Generated ambient plugin script in `~/.config/opencode/plugins/` (user scope) or `<repo>/.opencode/plugins/` (project scope) hooking `experimental.chat.system.transform`.

### The Problem
Google Antigravity (`agy`) does **not** possess a native `SessionStart` event in its lifecycle hook configuration (`hooks.json`). Instead, `agy` provides five lifecycle events: `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, and `Stop`. Furthermore, `hooks.json` in `agy` uses a named-group dictionary format rather than a root `hooks` object, and communicates with hook commands via a strict ProtoJSON stdin/stdout contract (`injectSteps`).

### The Solution
As established in Charting Round 1, ambient context for `agy` is delivered via the **`PreInvocation`** lifecycle event. This specification provides the complete technical design, JSON schemas, idempotent state-transition algorithms, full TypeScript diffs, and testing strategies required to add first-class `agy` hook support to `packages/axi-sdk-js/src/hooks.ts` in `kunchenguid/axi`.

---

## 2. Analysis of Existing `axi-sdk-js` Architecture

In `kunchenguid/axi`, `packages/axi-sdk-js/src/hooks.ts` is structured around pure state-computation functions paired with side-effecting file orchestrators:

```
[CLI Process / execPath]
       │
       ▼
inferHookOptions() ─────────► [marker, binaryNames, distEntrypoints]
       │
       ▼
resolvePortableHookCommand() ─► Checks PATH / npm shims; yields short binary or absolute path
       │
       ▼
resolveHookScopeTargets() ──► Resolves paths based on scope: "user" | "project"
       │
       ├─────────────────────────┬─────────────────────────┐
       ▼                         ▼                         ▼
Claude / Codex            Codex Feature Flag           OpenCode
computeSessionStartHookUpdate()  computeCodexConfigUpdate()  installOpenCodeAmbientPlugin()
       │                         │                         │
       ▼                         ▼                         ▼
.claude/settings.json      ~/.codex/config.toml       .opencode/plugins/axi-<marker>.js
.codex/hooks.json
```

### Key Components & Invariants
1. **Marker & Identity Inference (`inferHookOptions`)**:
   Infers identity from `process.argv[1]` (e.g., `.../dist/bin/gh-axi.js` yields marker `gh-axi`).
2. **Portable Command Resolution (`resolvePortableHookCommand`)**:
   Checks whether the executable is available on `PATH` via symlink or npm Windows wrapper shims (`extractNpmShimScriptPath`). If so, emits the clean binary name (e.g., `gh-axi`) instead of machine-dependent absolute paths.
3. **Target Scope Resolution (`resolveHookScopeTargets`)**:
   Accepts `scope: "user" | "project"`.
   - `user`: Config files reside under `home` (`~/.claude/settings.json`, `~/.codex/hooks.json`).
   - `project`: Config files reside under `root` (`<projectDir>/.claude/settings.json`, `<projectDir>/.codex/hooks.json`).
   - Symmetrical exception: Codex's user-level feature flag (`~/.codex/config.toml`) always targets user home, even at project scope.
4. **Pure Functional State Transformation (`computeSessionStartHookUpdate`)**:
   Takes `(current: HookSettings, spec: ManagedHookSpec) => [updated: HookSettings, changed: boolean]`.
   - Idempotent: If the hook is already present with matching command, type, and timeout, returns `[current, false]`.
   - Non-destructive: Retains any foreign hooks, other hook events, and unmanaged groups.
   - Self-repairing: Updates in-place if command path or timeout has drifted.
5. **Clean Uninstallation (`computeSessionStartHookRemoval`)**:
   Filters out only hooks matching `isManagedHook(hook, marker)`. Prunes empty containers, preserving unrelated hooks.
6. **Code Generation Pattern (`installOpenCodeAmbientPlugin`)**:
   Used when an AI tool lacks a declarative JSON hook mechanism. Emits a `.js` plugin containing a managed header (`axi-sdk-js managed opencode plugin: <marker>`), refusing to overwrite unmarked user files.

### Architectural Gaps When Interfacing with Antigravity (`agy`)
Directly writing Claude/Codex-style `{ "hooks": { "SessionStart": [...] } }` into Antigravity's `hooks.json` fails on three distinct fronts:
- **Schema Mismatch**: Antigravity's `hooks.json` root is a map of named hook definitions (`Record<string, AgyNamedHook>`), not a `{ "hooks": ... }` envelope.
- **Event Mismatch**: Antigravity does not recognize `SessionStart`. Unrecognized keys are ignored.
- **Protocol Mismatch**: Antigravity executes hook commands with ProtoJSON on stdin (`conversationId`, `invocationNum`, `workspacePaths`, etc.) and expects ProtoJSON on stdout (`{ "injectSteps": [...] }`). Direct execution of a standard CLI binary that dumps raw plain-text or YAML breaks the parser.
- **Invocation Frequency**: `SessionStart` runs once per session. `PreInvocation` runs before **every model invocation** (every conversation turn). Uncached injection on every turn causes severe token waste and context bloat.

---

## 3. Antigravity (`agy`) Lifecycle Hook Specifications

Primary source: `/home/mezmo/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md`.

### 3.1 Customization Discovery & Paths

Antigravity discovers customizations according to a strict priority hierarchy:
1. **Workspace / Project Root**:
   - Path: `.agents/hooks.json` (also recognizes `.agent/`, `_agents/`, `_agent/`).
   - Discovered by walking up from the current working directory to the Git root.
2. **Global / Machine-Local**:
   - Path: `~/.gemini/config/hooks.json`.
   - Loaded for all workspaces.

Unlike Claude Code, which nests under `.claude/` in both scopes, Antigravity uses **`.agents/hooks.json`** for project scope and **`~/.gemini/config/hooks.json`** for user scope.

### 3.2 Structure of `hooks.json`

`hooks.json` is a JSON object where each top-level key is a **hook name** (e.g., `"gh-axi"`, `"tasks-axi"`), mapping to its event configuration:

```json
{
  "tasks-axi": {
    "enabled": true,
    "PreInvocation": [
      {
        "type": "command",
        "command": "tasks-axi --format=protojson",
        "timeout": 10
      }
    ]
  },
  "lint-checker": {
    "PostToolUse": [
      {
        "matcher": "run_command",
        "hooks": [
          {
            "type": "command",
            "command": "./scripts/lint.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

#### Structural Rules:
- **Merging**: Named hooks from workspace `.agents/hooks.json` and global `~/.gemini/config/hooks.json` are merged. Handlers for the same event type execute sequentially.
- **Event Handler Structure**:
  - `PreToolUse` and `PostToolUse` are **grouped** arrays using `{ "matcher": "...", "hooks": [...] }`.
  - `PreInvocation`, `PostInvocation`, and `Stop` are **flat arrays** of handler objects directly (`[{ "type": "command", "command": "...", "timeout": ... }]`). There is no outer `matcher` wrapper.

### 3.3 The `PreInvocation` Stdin/Stdout Contract

`PreInvocation` executes synchronously before the model is called.

#### Stdin Payload (from `agy` to command):
```json
{
  "invocationNum": 1,
  "initialNumSteps": 0,
  "conversationId": "3b29c0f5-4dc1-4d1a-8c5e-cfc27bc3e9f4",
  "workspacePaths": ["/home/user/projects/my-repo"],
  "transcriptPath": "/home/user/.gemini/antigravity-cli/brain/.../transcript.jsonl",
  "artifactDirectoryPath": "/home/user/.gemini/antigravity-cli/brain/.../artifacts",
  "modelName": "auto"
}
```

#### Stdout Payload (from command to `agy`):
```json
{
  "injectSteps": [
    {
      "ephemeralMessage": "## AXI ambient context: tasks-axi\n- Task 1: In Progress\n- Task 2: Queued"
    }
  ]
}
```

Supported `injectSteps` variants:
- `{"ephemeralMessage": "..."}`: Injected as a transient system prompt for this invocation.
- `{"userMessage": "..."}`: Injected as a simulated user message.
- `{"toolCall": {"name": "...", "args": {...}}}`: Injected as a synthetic tool call.

For ambient session context, **`ephemeralMessage`** is the standard mechanism.

### 3.4 Handling Invocation Frequency (Turn-Frequency Impedance Matching)

Because `PreInvocation` fires on every model turn (`invocationNum: 1, 2, 3, ...`), blindly generating and injecting AXI home views on every turn produces catastrophic context growth.

**Specification Requirement**:
Ambient session context must only be emitted when `invocationNum === 1` (the initial turn of a session). For `invocationNum > 1`, the command must output `{ "injectSteps": [] }` and immediately exit with code 0.

---

## 4. Detailed Target Scope Resolution

`resolveHookScopeTargets` in `packages/axi-sdk-js/src/hooks.ts` must be extended to calculate `agyHooksPath`.

### Path Mapping Rules
| Scope | Target Path | Rationale |
|---|---|---|
| **User** (`scope: "user"`) | `join(home, ".gemini", "config", "hooks.json")` | Standard Antigravity global customization root |
| **Project** (`scope: "project"`) | `join(root, ".agents", "hooks.json")` | Canonical VCS-tracked workspace customization root |

### TypeScript Interface Changes

```typescript
export interface ResolvedHookScopeTargets {
  scope: SessionStartHookScope;
  home: string;
  root: string;
  claudeSettingsPath: string;
  codexHooksPath: string;
  codexConfigPath: string;
  openCodePluginPath: string;
  agyHooksPath: string; // NEW
}

function agyHooksConfigPath(
  scope: SessionStartHookScope,
  home: string,
  root: string,
): string {
  return scope === "project"
    ? join(root, ".agents", "hooks.json")
    : join(home, ".gemini", "config", "hooks.json");
}
```

---

## 5. JSON Schema and Structure for the `PreInvocation` Hook Entry

### 5.1 JSON Schema for Antigravity `hooks.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AntigravityHooksConfig",
  "type": "object",
  "additionalProperties": {
    "type": "object",
    "description": "Named hook definition",
    "properties": {
      "enabled": {
        "type": "boolean",
        "default": true
      },
      "PreInvocation": {
        "type": "array",
        "description": "Flat list of handlers executed before model invocation",
        "items": {
          "$ref": "#/$defs/handler"
        }
      },
      "PostInvocation": {
        "type": "array",
        "items": { "$ref": "#/$defs/handler" }
      },
      "Stop": {
        "type": "array",
        "items": { "$ref": "#/$defs/handler" }
      },
      "PreToolUse": {
        "type": "array",
        "items": { "$ref": "#/$defs/groupedMatcher" }
      },
      "PostToolUse": {
        "type": "array",
        "items": { "$ref": "#/$defs/groupedMatcher" }
      }
    }
  },
  "$defs": {
    "handler": {
      "type": "object",
      "required": ["command"],
      "properties": {
        "type": {
          "type": "string",
          "enum": ["command"],
          "default": "command"
        },
        "command": {
          "type": "string",
          "description": "Shell command to execute"
        },
        "timeout": {
          "type": "integer",
          "minimum": 1,
          "default": 30,
          "description": "Execution timeout in seconds"
        }
      }
    },
    "groupedMatcher": {
      "type": "object",
      "required": ["hooks"],
      "properties": {
        "matcher": { "type": "string" },
        "hooks": {
          "type": "array",
          "items": { "$ref": "#/$defs/handler" }
        }
      }
    }
  }
}
```

### 5.2 Named Hook Keying Convention

In `hooks.json`, each managed entry is keyed by `spec.marker` (e.g., `"tasks-axi"`, `"gh-axi"`, `"chrome-devtools-axi"`, `"lavish-axi"`).

Example configuration generated for `gh-axi`:
```json
{
  "gh-axi": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "gh-axi --format protojson",
        "timeout": 10
      }
    ]
  }
}
```

### 5.3 Command Delivery Strategies: `<binary>` vs Ambient Adapter

We evaluate two architectural strategies for delivering ambient context under Antigravity:

#### Strategy 1: CLI-Native ProtoJSON Output (Recommended Upstream Target)
In this model, the AXI CLI binary itself supports outputting the Antigravity `PreInvocation` ProtoJSON payload when invoked in ambient hook mode.
- Command: `<binary> --format protojson` or `<binary> hook pre-invocation`.
- Behavior:
  1. Reads stdin. If JSON contains `"invocationNum"` and `invocationNum > 1`, outputs `{"injectSteps":[]}` and exits `0`.
  2. If `invocationNum === 1` (or stdin is empty / not a tty): Generates the home view string.
  3. Outputs:
     ```json
     {
       "injectSteps": [
         {
           "ephemeralMessage": "## AXI ambient context: <marker>\n<homeView>"
         }
       ]
     }
     ```
  4. On error: Catches exceptions and exits `0` with `{ "injectSteps": [] }` (or emits diagnostic ephemeral message) so `agy` does not abort the agent loop.

#### Strategy 2: Self-Contained Node Inline Wrapper (Zero CLI Changes Required)
If upstream AXI binaries are not modified to parse stdin ProtoJSON, `axi-sdk-js` can configure a portable Node one-liner or companion script as the `command`. Because Node.js is guaranteed to exist in any environment where `axi-sdk-js` runs, `command` can execute a small Node script:

```json
{
  "gh-axi": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "node -e 'let d=\"\";process.stdin.on(\"data\",c=>d+=c).on(\"end\",()=>{try{let j=JSON.parse(d);if(j.invocationNum>1){process.stdout.write(JSON.stringify({injectSteps:[]}));process.exit(0);}}catch(e){}require(\"child_process\").exec(\"gh-axi\",{timeout:8000},(err,stdout)=>{let text=(stdout||\"\").trim();let steps=text?[{ephemeralMessage:\"## AXI ambient context: gh-axi\\n\"+text}]:[];process.stdout.write(JSON.stringify({injectSteps:steps}));});});'",
        "timeout": 10
      }
    ]
  }
}
```

Alternatively, `axi-sdk-js` can install a managed script `axi-<marker>-agy-hook.mjs` alongside the OpenCode plugin, keeping `command` clean:
```
command: "node ~/.gemini/config/hooks/axi-gh-axi.mjs"
```

#### Recommendation
**Strategy 1** should be adopted as the standard contract in `axi-sdk-js` (`command = `${command} --format protojson``). As a transitional bridge, Strategy 2 can be used if existing CLI packages have not yet cut releases with `--format protojson` support.

---

## 6. Idempotent Update, Uninstall, and Status Semantics

### 6.1 TypeScript Data Types

```typescript
export interface AgyHookHandler {
  type?: "command";
  command: string;
  timeout?: number;
}

export interface AgyNamedHook {
  enabled?: boolean;
  PreInvocation?: AgyHookHandler[];
  PostInvocation?: AgyHookHandler[];
  Stop?: AgyHookHandler[];
  PreToolUse?: unknown[];
  PostToolUse?: unknown[];
  [event: string]: unknown;
}

export type AgyHooksSettings = Record<string, AgyNamedHook>;
```

### 6.2 Pure State Transformation: `computeAgyHookUpdate`

Algorithm requirements:
1. Deep-clone existing `AgyHooksSettings`.
2. Locate or create `settings[spec.marker]`.
3. If `settings[spec.marker].PreInvocation` does not exist, create it as `[]`.
4. Check existing handlers in `PreInvocation` using `isManagedHook(handler, spec.marker)`.
5. If an existing handler has matching `command`, `type: "command"`, and `timeout: spec.timeoutSeconds ?? 10`, return `[settings, false]` (idempotent no-op).
6. If an existing handler has stale command/timeout, update in-place and return `[updated, true]`.
7. If no managed handler exists, push `{ type: "command", command: spec.command, timeout: spec.timeoutSeconds ?? 10 }` and return `[updated, true]`.
8. Never alter or remove foreign named hooks (e.g., `"lint-checker"`, `"safety-gate"`).

```typescript
export function computeAgyHookUpdate(
  settings: AgyHooksSettings,
  spec: ManagedHookSpec,
): [AgyHooksSettings, boolean] {
  const updated = structuredClone(settings);
  let changed = false;

  let hookConfig = updated[spec.marker];
  if (!hookConfig) {
    hookConfig = {};
    updated[spec.marker] = hookConfig;
    changed = true;
  }

  if (!Array.isArray(hookConfig.PreInvocation)) {
    hookConfig.PreInvocation = [];
    changed = true;
  }

  const timeout = spec.timeoutSeconds ?? 10;

  for (const handler of hookConfig.PreInvocation) {
    if (!isManagedHook(handler, spec.marker)) {
      continue;
    }

    const isCorrect =
      handler.command === spec.command &&
      handler.type === "command" &&
      handler.timeout === timeout;

    if (isCorrect && !changed) {
      return [settings, false];
    }

    handler.command = spec.command;
    handler.type = "command";
    handler.timeout = timeout;
    return [updated, true];
  }

  hookConfig.PreInvocation.push({
    type: "command",
    command: spec.command,
    timeout,
  });

  return [updated, true];
}
```

### 6.3 Pure State Transformation: `computeAgyHookRemoval`

Algorithm requirements:
1. Deep-clone `settings`.
2. Inspect `settings[marker]`. If missing, check all named hooks for any handler matching `isManagedHook(handler, marker)`.
3. Filter out managed handlers from `PreInvocation`.
4. If `PreInvocation` is empty, `delete hookConfig.PreInvocation`.
5. If the named hook object has no remaining events or keys, `delete updated[marker]`.
6. Return `[updated, changed]`.

```typescript
export function computeAgyHookRemoval(
  settings: AgyHooksSettings,
  marker: string,
): [AgyHooksSettings, boolean] {
  if (Object.keys(settings).length === 0) {
    return [settings, false];
  }

  const updated = structuredClone(settings);
  let changed = false;

  for (const [hookName, hookConfig] of Object.entries(updated)) {
    if (hookName !== marker && !hookName.includes(marker)) {
      continue;
    }

    if (Array.isArray(hookConfig.PreInvocation)) {
      const remaining = hookConfig.PreInvocation.filter(
        (h) => !isManagedHook(h, marker),
      );
      if (remaining.length !== hookConfig.PreInvocation.length) {
        changed = true;
        if (remaining.length === 0) {
          delete hookConfig.PreInvocation;
        } else {
          hookConfig.PreInvocation = remaining;
        }
      }
    }

    // Clean up empty hook configuration
    const remainingKeys = Object.keys(hookConfig).filter(
      (k) => k !== "enabled",
    );
    if (remainingKeys.length === 0) {
      delete updated[hookName];
      changed = true;
    }
  }

  return changed ? [updated, true] : [settings, false];
}
```

### 6.4 Status Inspection: `hasManagedAgyHookEntry`

```typescript
function hasManagedAgyHookEntry(path: string, marker: string): boolean {
  if (!existsSync(path)) {
    return false;
  }

  try {
    const settings = JSON.parse(readFileSync(path, "utf-8")) as AgyHooksSettings;
    for (const [hookName, hookConfig] of Object.entries(settings)) {
      if (hookName === marker || hookName.includes(marker)) {
        if (
          Array.isArray(hookConfig.PreInvocation) &&
          hookConfig.PreInvocation.some((h) => isManagedHook(h, marker))
        ) {
          return true;
        }
      }
    }
    return false;
  } catch {
    return false;
  }
}
```

---

## 7. Complete TypeScript Implementation Diff

Below is the complete, drop-in implementation diff for `packages/axi-sdk-js/src/hooks.ts`:

```diff
--- a/packages/axi-sdk-js/src/hooks.ts
+++ b/packages/axi-sdk-js/src/hooks.ts
@@ -24,6 +24,20 @@ export interface HookSettings {
   [key: string]: unknown;
 }
 
+export interface AgyHookHandler {
+  type?: "command";
+  command: string;
+  timeout?: number;
+}
+
+export interface AgyNamedHook {
+  enabled?: boolean;
+  PreInvocation?: AgyHookHandler[];
+  [event: string]: unknown;
+}
+
+export type AgyHooksSettings = Record<string, AgyNamedHook>;
+
 export interface ManagedHookSpec {
   marker: string;
   command: string;
@@ -95,6 +109,7 @@ export interface SessionStartHookStatus {
   claude: SessionStartHookAgentStatus;
   codex: SessionStartHookCodexStatus;
   opencode: SessionStartHookAgentStatus;
+  agy: SessionStartHookAgentStatus;
 }
 
 const OPENCODE_PLUGIN_MANAGED_PREFIX = "axi-sdk-js managed opencode plugin:";
@@ -253,6 +268,91 @@ export function computeSessionStartHookRemoval(
   return changed ? [updated, true] : [settings, false];
 }
 
+export function computeAgyHookUpdate(
+  settings: AgyHooksSettings,
+  spec: ManagedHookSpec,
+): [AgyHooksSettings, boolean] {
+  const updated = structuredClone(settings);
+  let changed = false;
+
+  let hookConfig = updated[spec.marker];
+  if (!hookConfig) {
+    hookConfig = {};
+    updated[spec.marker] = hookConfig;
+    changed = true;
+  }
+
+  if (!Array.isArray(hookConfig.PreInvocation)) {
+    hookConfig.PreInvocation = [];
+    changed = true;
+  }
+
+  const timeout = spec.timeoutSeconds ?? 10;
+
+  for (const handler of hookConfig.PreInvocation) {
+    if (!isManagedHook(handler, spec.marker)) {
+      continue;
+    }
+
+    const isCorrect =
+      handler.command === spec.command &&
+      handler.type === "command" &&
+      handler.timeout === timeout;
+
+    if (isCorrect && !changed) {
+      return [settings, false];
+    }
+
+    handler.command = spec.command;
+    handler.type = "command";
+    handler.timeout = timeout;
+    return [updated, true];
+  }
+
+  hookConfig.PreInvocation.push({
+    type: "command",
+    command: spec.command,
+    timeout,
+  });
+
+  return [updated, true];
+}
+
+export function computeAgyHookRemoval(
+  settings: AgyHooksSettings,
+  marker: string,
+): [AgyHooksSettings, boolean] {
+  if (Object.keys(settings).length === 0) {
+    return [settings, false];
+  }
+
+  const updated = structuredClone(settings);
+  let changed = false;
+
+  for (const [hookName, hookConfig] of Object.entries(updated)) {
+    if (hookName !== marker && !hookName.includes(marker)) {
+      continue;
+    }
+
+    if (Array.isArray(hookConfig.PreInvocation)) {
+      const remaining = hookConfig.PreInvocation.filter(
+        (h) => !isManagedHook(h, marker),
+      );
+      if (remaining.length !== hookConfig.PreInvocation.length) {
+        changed = true;
+        if (remaining.length === 0) {
+          delete hookConfig.PreInvocation;
+        } else {
+          hookConfig.PreInvocation = remaining;
+        }
+      }
+    }
+
+    const remainingKeys = Object.keys(hookConfig).filter((k) => k !== "enabled");
+    if (remainingKeys.length === 0) {
+      delete updated[hookName];
+      changed = true;
+    }
+  }
+
+  return changed ? [updated, true] : [settings, false];
+}
+
 export function computeCodexConfigUpdate(content: string): [string, boolean] {
   const newline = content.includes("\r\n") ? "\r\n" : "\n";
   const normalized = content.length === 0 ? "" : content;
@@ -456,6 +556,7 @@ interface ResolvedHookScopeTargets {
   codexConfigPath: string;
   openCodePluginPath: string;
+  agyHooksPath: string;
 }
 
+function agyHooksConfigPath(
+  scope: SessionStartHookScope,
  home: string,
+  root: string,
+): string {
+  return scope === "project"
+    ? join(root, ".agents", "hooks.json")
+    : join(home, ".gemini", "config", "hooks.json");
+}
+
 function resolveHookScopeTargets(
   marker: string,
   options: SessionStartHookScopeOptions,
@@ -478,6 +579,7 @@ function resolveHookScopeTargets(
     openCodePluginPath: join(
       openCodePluginDir(scope, home, root),
       openCodePluginFileName(marker),
     ),
+    agyHooksPath: agyHooksConfigPath(scope, home, root),
   };
 }
 
@@ -741,6 +843,26 @@ export function installSessionStartHooks(
   for (const target of jsonTargets) {
     try {
       mkdirSync(dirname(target), { recursive: true });
@@ -763,6 +885,25 @@ export function installSessionStartHooks(
     options.onError?.(`${target}: ${message}`);
   }
 
+  try {
+    const agyTarget = targets.agyHooksPath;
+    mkdirSync(dirname(agyTarget), { recursive: true });
+    const current = existsSync(agyTarget)
+      ? (JSON.parse(readFileSync(agyTarget, "utf-8")) as AgyHooksSettings)
+      : {};
+    const [updated, changed] = computeAgyHookUpdate(current, {
+      marker,
+      command,
+      timeoutSeconds: options.timeoutSeconds,
+    });
+
+    if (changed) {
+      writeFileSync(agyTarget, `${JSON.stringify(updated, null, 2)}\n`, "utf-8");
+    }
+  } catch (error) {
+    const message = error instanceof Error ? error.message : String(error);
+    options.onError?.(`${targets.agyHooksPath}: ${message}`);
+  }
+
   try {
     mkdirSync(dirname(codexConfigPath), { recursive: true });
@@ -825,6 +966,23 @@ function hasManagedOpenCodePlugin(path: string, marker: string): boolean {
   }
 }
 
+function hasManagedAgyHookEntry(path: string, marker: string): boolean {
+  if (!existsSync(path)) {
+    return false;
+  }
+
+  try {
+    const settings = JSON.parse(readFileSync(path, "utf-8")) as AgyHooksSettings;
+    for (const [hookName, hookConfig] of Object.entries(settings)) {
+      if (hookName === marker || hookName.includes(marker)) {
+        if (
+          Array.isArray(hookConfig.PreInvocation) &&
+          hookConfig.PreInvocation.some((h) => isManagedHook(h, marker))
+        ) {
+          return true;
+        }
+      }
+    }
+    return false;
+  } catch {
+    return false;
   }
 }
 
 /**
  * Reports whether managed SessionStart hooks (Claude Code, Codex, Antigravity)
@@ -871,6 +1029,10 @@ export function sessionStartHookStatus(
     opencode: {
       installed: hasManagedOpenCodePlugin(targets.openCodePluginPath, marker),
       path: targets.openCodePluginPath,
     },
+    agy: {
+      installed: hasManagedAgyHookEntry(targets.agyHooksPath, marker),
+      path: targets.agyHooksPath,
+    },
   };
 }
@@ -911,6 +1073,23 @@ export function uninstallSessionStartHooks(
     options.onError?.(`${target}: ${message}`);
   }
 
+  const agyTarget = targets.agyHooksPath;
+  try {
+    if (existsSync(agyTarget)) {
+      const current = JSON.parse(readFileSync(agyTarget, "utf-8")) as AgyHooksSettings;
+      const [updated, changed] = computeAgyHookRemoval(current, marker);
+
+      if (changed) {
+        writeFileSync(agyTarget, `${JSON.stringify(updated, null, 2)}\n`, "utf-8");
+      }
+    }
+  } catch (error) {
+    const message = error instanceof Error ? error.message : String(error);
+    options.onError?.(`${agyTarget}: ${message}`);
+  }
+
   const pluginPath = targets.openCodePluginPath;
```

---

## 8. Testing Strategy for `packages/axi-sdk-js/test/hooks.test.ts`

The test suite in `kunchenguid/axi` (`packages/axi-sdk-js/test/hooks.test.ts`) runs under Vitest. A robust test plan must cover unit state transitions, target path resolution, scope isolation, and full integration.

### Test Suite Structure

```typescript
describe("computeAgyHookUpdate", () => {
  it("installs a managed PreInvocation hook when hooks.json is empty", () => {
    const [updated, changed] = computeAgyHookUpdate(
      {},
      { marker: "gh-axi", command: "/usr/local/bin/gh-axi" },
    );

    expect(changed).toBe(true);
    expect(updated["gh-axi"]?.PreInvocation).toEqual([
      {
        type: "command",
        command: "/usr/local/bin/gh-axi",
        timeout: 10,
      },
    ]);
  });

  it("preserves foreign named hooks and other lifecycle events", () => {
    const initial: AgyHooksSettings = {
      "lint-checker": {
        PostToolUse: [{ matcher: "run_command", hooks: [] }],
      },
    };

    const [updated, changed] = computeAgyHookUpdate(initial, {
      marker: "tasks-axi",
      command: "tasks-axi",
      timeoutSeconds: 15,
    });

    expect(changed).toBe(true);
    expect(updated["lint-checker"]).toBeDefined();
    expect(updated["tasks-axi"]?.PreInvocation?.[0]).toEqual({
      type: "command",
      command: "tasks-axi",
      timeout: 15,
    });
  });

  it("repairs a stale managed command in place without duplication", () => {
    const initial: AgyHooksSettings = {
      "gh-axi": {
        PreInvocation: [
          { type: "command", command: "/old/bin/gh-axi", timeout: 10 },
        ],
      },
    };

    const [updated, changed] = computeAgyHookUpdate(initial, {
      marker: "gh-axi",
      command: "/new/bin/gh-axi",
      timeoutSeconds: 20,
    });

    expect(changed).toBe(true);
    expect(updated["gh-axi"]?.PreInvocation).toHaveLength(1);
    expect(updated["gh-axi"]?.PreInvocation?.[0]?.command).toBe("/new/bin/gh-axi");
    expect(updated["gh-axi"]?.PreInvocation?.[0]?.timeout).toBe(20);
  });

  it("is an idempotent no-op when the hook entry is already up to date", () => {
    const initial: AgyHooksSettings = {
      "gh-axi": {
        PreInvocation: [
          { type: "command", command: "gh-axi", timeout: 10 },
        ],
      },
    };

    const [updated, changed] = computeAgyHookUpdate(initial, {
      marker: "gh-axi",
      command: "gh-axi",
      timeoutSeconds: 10,
    });

    expect(changed).toBe(false);
    expect(updated).toBe(initial);
  });
});

describe("computeAgyHookRemoval", () => {
  it("removes managed PreInvocation hook and deletes empty hook object", () => {
    const initial: AgyHooksSettings = {
      "gh-axi": {
        PreInvocation: [{ type: "command", command: "gh-axi" }],
      },
      "other-hook": {
        Stop: [{ type: "command", command: "cleanup" }],
      },
    };

    const [updated, changed] = computeAgyHookRemoval(initial, "gh-axi");

    expect(changed).toBe(true);
    expect(updated["gh-axi"]).toBeUndefined();
    expect(updated["other-hook"]).toBeDefined();
  });

  it("is a no-op when marker is not present", () => {
    const initial: AgyHooksSettings = {
      "other-hook": {
        Stop: [{ type: "command", command: "cleanup" }],
      },
    };

    const [updated, changed] = computeAgyHookRemoval(initial, "gh-axi");
    expect(changed).toBe(false);
    expect(updated).toBe(initial);
  });
});

describe("session hook scope for Antigravity (user vs project)", () => {
  let tmp: string;
  let home: string;
  let projectDir: string;
  let execFile: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), "axi-agy-test-"));
    home = join(tmp, "home");
    projectDir = join(tmp, "project");
    mkdirSync(home, { recursive: true });
    mkdirSync(projectDir, { recursive: true });

    const pkgBin = join(tmp, "pkg", "dist", "bin");
    mkdirSync(pkgBin, { recursive: true });
    execFile = join(pkgBin, "gh-axi.js");
    writeFileSync(execFile, "// stub\n", "utf-8");
  });

  afterEach(() => {
    rmSync(tmp, { recursive: true, force: true });
  });

  it("installs to ~/.gemini/config/hooks.json at user scope", () => {
    installSessionStartHooks({
      marker: "gh-axi",
      execPath: execFile,
      homeDir: home,
      scope: "user",
    });

    const agyUserPath = join(home, ".gemini", "config", "hooks.json");
    expect(existsSync(agyUserPath)).toBe(true);

    const config = JSON.parse(readFileSync(agyUserPath, "utf-8"));
    expect(config["gh-axi"]?.PreInvocation?.[0]?.command).toBe(execFile);

    const status = sessionStartHookStatus({ marker: "gh-axi", homeDir: home, scope: "user" });
    expect(status.agy.installed).toBe(true);
    expect(status.agy.path).toBe(agyUserPath);
  });

  it("installs to <project>/.agents/hooks.json at project scope", () => {
    installSessionStartHooks({
      marker: "gh-axi",
      execPath: execFile,
      homeDir: home,
      projectDir,
      scope: "project",
    });

    const agyProjectPath = join(projectDir, ".agents", "hooks.json");
    expect(existsSync(agyProjectPath)).toBe(true);

    const config = JSON.parse(readFileSync(agyProjectPath, "utf-8"));
    expect(config["gh-axi"]?.PreInvocation?.[0]?.command).toBe(execFile);

    // Global user path must NOT be written
    expect(existsSync(join(home, ".gemini", "config", "hooks.json"))).toBe(false);

    const status = sessionStartHookStatus({
      marker: "gh-axi",
      homeDir: home,
      projectDir,
      scope: "project",
    });
    expect(status.agy.installed).toBe(true);
    expect(status.agy.path).toBe(agyProjectPath);
  });

  it("uninstalls cleanly from project scope without touching user scope", () => {
    installSessionStartHooks({
      marker: "gh-axi",
      execPath: execFile,
      homeDir: home,
      scope: "user",
    });
    installSessionStartHooks({
      marker: "gh-axi",
      execPath: execFile,
      homeDir: home,
      projectDir,
      scope: "project",
    });

    uninstallSessionStartHooks({
      marker: "gh-axi",
      homeDir: home,
      projectDir,
      scope: "project",
    });

    const agyProjectPath = join(projectDir, ".agents", "hooks.json");
    const projectConfig = JSON.parse(readFileSync(agyProjectPath, "utf-8"));
    expect(projectConfig["gh-axi"]).toBeUndefined();

    // User scope remains intact
    const agyUserPath = join(home, ".gemini", "config", "hooks.json");
    const userConfig = JSON.parse(readFileSync(agyUserPath, "utf-8"));
    expect(userConfig["gh-axi"]?.PreInvocation?.[0]?.command).toBe(execFile);
  });
});
```

---

## 9. Upstream Integration & PR Roadmap

To land this change smoothly into `kunchenguid/axi`, execute the upstream contribution across two targeted steps:

1. **Pull Request 1: `feat(axi-sdk-js): add Antigravity (agy) PreInvocation hook support`**
   - Apply the TypeScript changes to `packages/axi-sdk-js/src/hooks.ts`.
   - Export `AgyHooksSettings`, `AgyNamedHook`, `AgyHookHandler`, `computeAgyHookUpdate`, and `computeAgyHookRemoval`.
   - Update `packages/axi-sdk-js/test/hooks.test.ts` with the test suite outlined in Section 8.
   - Bump minor version of `axi-sdk-js`.

2. **Pull Request 2: Ambient Hook Format Handling in AXI CLI Runners**
   - Update `runAxiCli` in `packages/axi-sdk-js/src/cli.ts` (or individual tools `tasks-axi`, `gh-axi`, `chrome-devtools-axi`, `lavish-axi`) to detect ProtoJSON stdin / `--format protojson` flag:
     - Check `invocationNum`:
       - If `invocationNum > 1`, output `{"injectSteps":[]}` and exit `0`.
       - If `invocationNum === 1`, format the home view inside `{ "injectSteps": [ { "ephemeralMessage": ... } ] }`.

### Downstream Impact Verification
Once published:
- Running `tasks-axi setup hooks` will configure:
  - Claude Code: `~/.claude/settings.json`
  - Codex CLI: `~/.codex/hooks.json`
  - OpenCode: `~/.config/opencode/plugins/axi-tasks-axi.js`
  - Antigravity: `~/.gemini/config/hooks.json`
- Running `tasks-axi setup hooks --scope project` will configure `.agents/hooks.json`.
- When Antigravity starts a session in that repository or machine, `agy`'s execution engine automatically invokes `tasks-axi` before the first model turn, injecting active tasks directly into the agent's context window.
