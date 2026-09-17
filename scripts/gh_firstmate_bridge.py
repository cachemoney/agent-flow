#!/usr/bin/env python3
"""GitHub Issues to Firstmate Bridge.

Seamlessly connects Matt Pocock's GitHub Issues workflow (e.g. ready-for-agent tickets,
agent briefs, and wayfinder maps) with Firstmate's multi-agent fleet runtime.

Usage:
  uv run scripts/gh_firstmate_bridge.py list [--label <label>] [--repo <owner/repo>]
  uv run scripts/gh_firstmate_bridge.py fetch <issue_number> [--repo <owner/repo>]
  uv run scripts/gh_firstmate_bridge.py ingest <issue_number> [--repo <owner/repo>] [--project <proj>] [--mode <mode>] [--spawn]
  uv run scripts/gh_firstmate_bridge.py status
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def run_cmd(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> str:
    """Run a shell command and return stdout as stripped text."""
    res = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and res.returncode != 0:
        err_msg = res.stderr.strip() or res.stdout.strip()
        raise RuntimeError(f"Command failed ({' '.join(cmd)}): {err_msg}")
    return res.stdout.strip()


def get_default_repo(cwd: Optional[Path] = None) -> Optional[str]:
    """Get the current GitHub owner/repo from git remotes."""
    try:
        out = run_cmd(["git", "config", "--get", "remote.origin.url"], cwd=cwd, check=False)
        if not out:
            return None
        # Support git@github.com:owner/repo.git or https://github.com/owner/repo.git
        match = re.search(r"github\.com[:/]([^/]+/[^/.]+)(?:\.git)?", out)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def fetch_github_issue(issue_number: int, repo: Optional[str] = None) -> Dict[str, Any]:
    """Fetch issue details and comments via gh CLI."""
    cmd = [
        "gh", "issue", "view", str(issue_number),
        "--json", "number,title,body,comments,labels,state,url"
    ]
    if repo:
        cmd.extend(["-R", repo])
    output = run_cmd(cmd)
    return json.loads(output)


def list_github_issues(label: str = "ready-for-agent", repo: Optional[str] = None) -> List[Dict[str, Any]]:
    """List open GitHub issues matching a specific triage label."""
    cmd = [
        "gh", "issue", "list",
        "--state", "open",
        "--json", "number,title,labels,url"
    ]
    if label:
        cmd.extend(["--label", label])
    if repo:
        cmd.extend(["-R", repo])
    output = run_cmd(cmd)
    if not output:
        return []
    return json.loads(output)


def extract_brief_and_intent(issue: Dict[str, Any]) -> tuple[str, str]:
    """Extract Captain's Intent and Firstmate Spec from the issue body and comments.

    Matt Pocock's skills attach an authoritative '## Agent Brief' comment on triage.
    If present, that becomes the spec; otherwise, the issue body is parsed.
    """
    body = (issue.get("body") or "").strip()
    comments = issue.get("comments") or []
    
    agent_brief_content = ""
    for c in reversed(comments):
        c_body = c.get("body", "")
        if "## Agent Brief" in c_body or "### Agent Brief" in c_body:
            agent_brief_content = c_body.strip()
            break

    # Intent: Plain summary of the ask and context
    intent_lines = [
        f"GitHub Issue #{issue['number']}: {issue['title']}",
        f"URL: {issue['url']}",
        "",
        "## Description",
        body if body else "(No description provided in issue body)"
    ]
    intent = "\n".join(intent_lines)

    # Spec: Technical instructions
    if agent_brief_content:
        spec = f"Follow the Agent Brief from issue #{issue['number']}:\n\n{agent_brief_content}"
    else:
        spec = (
            f"Implement the requirements specified in GitHub Issue #{issue['number']}. "
            "Follow repository coding conventions, write automated tests, and ensure all checks pass."
        )

    return intent, spec


def ensure_backlog_entry(data_dir: Path, task_id: str, title: str) -> None:
    """Ensure data/backlog.md has the task registered under ## Queued."""
    backlog_path = data_dir / "backlog.md"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    if not backlog_path.exists():
        initial_content = "# Backlog\n\n## In flight\n\n## Queued\n\n## Done\n"
        backlog_path.write_text(initial_content, encoding="utf-8")
        
    content = backlog_path.read_text(encoding="utf-8")
    if f"- [ ] {task_id}" in content or f"- [x] {task_id}" in content:
        print(f"Task {task_id} already exists in backlog.")
        return

    # Add under ## Queued
    new_line = f"- [ ] {task_id} {title}\n"
    if "## Queued" in content:
        parts = content.split("## Queued", 1)
        updated = parts[0] + "## Queued\n" + new_line + parts[1].lstrip("\n")
    else:
        updated = content + f"\n## Queued\n{new_line}"

    backlog_path.write_text(updated, encoding="utf-8")
    print(f"Added task '{task_id}' to {backlog_path}")


def scaffold_and_fill_brief(
    fm_root: Path,
    task_id: str,
    project_name: str,
    mode: str,
    intent: str,
    spec: str,
    is_scout: bool = False,
) -> Path:
    """Scaffold brief using fm-brief.sh and fill {TASK} and {FIRSTMATE_SPEC}."""
    brief_script = fm_root / "bin" / "fm-brief.sh"
    if not brief_script.exists():
        raise FileNotFoundError(f"Firstmate brief script not found at {brief_script}")

    cmd = [str(brief_script), task_id, project_name]
    if is_scout:
        cmd.append("--scout")
    else:
        cmd.extend(["--mode", mode])

    data_dir = fm_root / "data"
    task_dir = data_dir / task_id
    brief_path = task_dir / "brief.md"

    if not brief_path.exists():
        print(f"Scaffolding brief: {' '.join(cmd)}")
        run_cmd(cmd, cwd=fm_root)

    if not brief_path.exists():
        raise RuntimeError(f"Brief was not generated at {brief_path}")

    # Read and fill placeholders
    brief_content = brief_path.read_text(encoding="utf-8")
    
    # Replace {TASK} and {FIRSTMATE_SPEC}
    brief_content = brief_content.replace("{TASK}", intent)
    brief_content = brief_content.replace("{FIRSTMATE_SPEC}", spec)

    # Sanity check: Ensure no lingering placeholders
    if "{TASK}" in brief_content or "{FIRSTMATE_SPEC}" in brief_content:
        raise ValueError("Placeholders {TASK} or {FIRSTMATE_SPEC} still remain in brief.md")

    brief_path.write_text(brief_content, encoding="utf-8")
    print(f"Successfully populated brief at {brief_path}")
    return brief_path


def cmd_list(args: argparse.Namespace) -> None:
    """Handle the 'list' command."""
    repo = args.repo or get_default_repo()
    print(f"Querying GitHub issues (label: {args.label}, repo: {repo or 'current'})...\n")
    issues = list_github_issues(label=args.label, repo=repo)
    if not issues:
        print(f"No open issues found with label '{args.label}'.")
        return

    print(f"Found {len(issues)} issue(s):")
    for iss in issues:
        labels = [l["name"] for l in iss.get("labels", [])]
        print(f"  #{iss['number']}: {iss['title']} [{', '.join(labels)}]")
        print(f"    URL: {iss['url']}")


def cmd_fetch(args: argparse.Namespace) -> None:
    """Handle the 'fetch' command."""
    repo = args.repo or get_default_repo()
    issue = fetch_github_issue(args.issue_number, repo=repo)
    intent, spec = extract_brief_and_intent(issue)
    print(f"Issue #{issue['number']}: {issue['title']}")
    print(f"Status: {issue['state']} | URL: {issue['url']}\n")
    print("--- [Captain's Intent] ---")
    print(intent)
    print("\n--- [Firstmate Spec] ---")
    print(spec)


def cmd_ingest(args: argparse.Namespace) -> None:
    """Handle the 'ingest' command."""
    fm_root = Path(args.fm_root).resolve()
    repo = args.repo or get_default_repo()
    issue = fetch_github_issue(args.issue_number, repo=repo)

    task_id = args.task_id or f"gh-{issue['number']}"
    project_name = args.project
    if not project_name:
        # Fallback to repo name or current directory name
        if repo and "/" in repo:
            project_name = repo.split("/")[1]
        else:
            project_name = Path.cwd().name

    intent, spec = extract_brief_and_intent(issue)
    data_dir = fm_root / "data"

    # Step 1: Register in backlog
    ensure_backlog_entry(data_dir, task_id, issue["title"])

    # Step 2: Scaffold and populate brief
    brief_path = scaffold_and_fill_brief(
        fm_root=fm_root,
        task_id=task_id,
        project_name=project_name,
        mode=args.mode,
        intent=intent,
        spec=spec,
        is_scout=args.scout,
    )

    # Step 3: Post comment to GitHub if requested
    if args.comment:
        comment_body = (
            f"⚓ **Firstmate Intake**: Task `{task_id}` created.\n"
            f"- **Mode**: `{args.mode}`\n"
            f"- **Brief**: `{brief_path.relative_to(fm_root)}`\n"
            "A crewmate is being staged for execution."
        )
        run_cmd(["gh", "issue", "comment", str(issue["number"]), "--body", comment_body], check=False)
        print(f"Posted confirmation comment to GitHub issue #{issue['number']}.")

    # Step 4: Spawn crewmate if requested
    if args.spawn:
        spawn_script = fm_root / "bin" / "fm-spawn.sh"
        if not spawn_script.exists():
            print(f"Cannot spawn: {spawn_script} not found.", file=sys.stderr)
            return
        spawn_cmd = [str(spawn_script), task_id, project_name, "--mode", args.mode]
        if args.yolo:
            spawn_cmd.append("--yolo")
        print(f"Launching crewmate: {' '.join(spawn_cmd)}")
        run_cmd(spawn_cmd, cwd=fm_root)
        print(f"Crewmate for task {task_id} spawned successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Issues to Firstmate Bridge")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List GitHub issues ready for agents")
    p_list.add_argument("--label", default="ready-for-agent", help="Triage label to filter by")
    p_list.add_argument("--repo", help="Target GitHub repo (e.g. owner/repo)")
    p_list.set_defaults(func=cmd_list)

    # fetch
    p_fetch = subparsers.add_parser("fetch", help="Fetch and parse a GitHub issue")
    p_fetch.add_argument("issue_number", type=int, help="GitHub issue number")
    p_fetch.add_argument("--repo", help="Target GitHub repo (e.g. owner/repo)")
    p_fetch.set_defaults(func=cmd_fetch)

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest GitHub issue into Firstmate")
    p_ingest.add_argument("issue_number", type=int, help="GitHub issue number")
    p_ingest.add_argument("--repo", help="Target GitHub repo (e.g. owner/repo)")
    p_ingest.add_argument("--project", help="Firstmate project name under projects/")
    p_ingest.add_argument("--task-id", help="Custom task ID (default: gh-<number>)")
    p_ingest.add_argument("--mode", choices=["no-mistakes", "direct-PR", "local-only"], default="direct-PR", help="Delivery mode")
    p_ingest.add_argument("--scout", action="store_true", help="Ingest as a scout task (investigation report)")
    p_ingest.add_argument("--spawn", action="store_true", help="Immediately spawn the crewmate after ingestion")
    p_ingest.add_argument("--yolo", action="store_true", help="Enable merge autonomy for spawned task")
    p_ingest.add_argument("--comment", action="store_true", default=True, help="Post confirmation comment on GitHub")
    p_ingest.add_argument("--no-comment", action="store_false", dest="comment", help="Do not post comment to GitHub")
    p_ingest.add_argument("--fm-root", default="repositories/firstmate", help="Path to Firstmate repo root")
    p_ingest.set_defaults(func=cmd_ingest)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
