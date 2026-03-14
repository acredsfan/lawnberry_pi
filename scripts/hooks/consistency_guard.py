#!/usr/bin/env python3
"""Workspace hooks that protect consistency-related policy and docs sync."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_POLICY_PREFIXES = (
    ".github/hooks/",
    "scripts/hooks/",
)
STRUCTURAL_PREFIXES = (
    "backend/src/",
    "frontend/src/",
    "scripts/",
    ".specify/scripts/",
)
CODE_OVERVIEW_PATH = "docs/code_structure_overview.md"
DOCS_DRIFT_PATHS = (
    "docs/",
    "spec/",
    "README.md",
    ".specify/memory/AGENT_JOURNAL.md",
)
BACKEND_HINTS = (
    "backend/",
    "tests/",
    "pyproject.toml",
)
FRONTEND_HINTS = (
    "frontend/src/",
    "frontend/package.json",
    "frontend/vite.config.ts",
    "frontend/vitest.config.ts",
    "frontend/playwright.config.ts",
    "frontend/tsconfig.json",
    "frontend/tsconfig.app.json",
)
SCRIPT_HINTS = (
    "scripts/",
    ".specify/scripts/",
)
FILE_MUTATION_TOOLS = {
    "apply_patch",
    "create_file",
    "edit_notebook_file",
    "vscode_renameSymbol",
}
HOOK_FILE_PATTERN = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+?)(?: -> .+)?$")


def _run_git(*args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _get_changed_paths() -> list[str]:
    changed: set[str] = set()
    for args in (
        ("diff", "--name-only", "--cached", "--diff-filter=ACMR"),
        ("diff", "--name-only", "--diff-filter=ACMR"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        changed.update(_run_git(*args))
    return sorted(changed)


def _matches_any(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _normalize_repo_path(raw_path: str | None) -> str | None:
    if not raw_path:
        return None

    path = raw_path.strip()
    if not path:
        return None

    if path.startswith("file://"):
        parsed = urlparse(path)
        path = parsed.path

    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return candidate.as_posix()

    return Path(path.lstrip("./")).as_posix()


def _extract_patch_paths(patch_text: str) -> list[str]:
    paths: list[str] = []
    for line in patch_text.splitlines():
        match = HOOK_FILE_PATTERN.match(line.strip())
        if not match:
            continue
        normalized = _normalize_repo_path(match.group(1))
        if normalized:
            paths.append(normalized)
    return paths


def _extract_tool_paths(tool_name: str, tool_input: object) -> list[str]:
    if tool_name == "apply_patch" and isinstance(tool_input, dict):
        patch_text = tool_input.get("input")
        if isinstance(patch_text, str):
            return _extract_patch_paths(patch_text)

    if tool_name == "run_in_terminal" and isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str):
            paths = []
            for prefix in HOOK_POLICY_PREFIXES:
                if prefix in command:
                    paths.append(prefix)
            return sorted(set(paths))

    paths: list[str] = []

    def _walk(value: object, *, field_name: str | None = None) -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                _walk(nested_value, field_name=key)
            return

        if isinstance(value, list):
            for item in value:
                _walk(item, field_name=field_name)
            return

        if isinstance(value, str) and field_name in {"filePath", "path", "uri"}:
            normalized = _normalize_repo_path(value)
            if normalized:
                paths.append(normalized)

    _walk(tool_input)
    return sorted(set(paths))


def _build_validation_steps(changed_paths: list[str]) -> list[str]:
    steps: list[str] = []

    if any(_matches_any(path, BACKEND_HINTS) for path in changed_paths):
        steps.append("Backend changes detected: run `pytest -q`.")

    if any(_matches_any(path, FRONTEND_HINTS) for path in changed_paths):
        steps.append(
            "Frontend changes detected: run `cd frontend && npm run type-check && npm run test && npm run build`."
        )

    if any(_matches_any(path, SCRIPT_HINTS) for path in changed_paths):
        steps.append("Script or tooling changes detected: run `bash scripts/check_docs_drift.sh`.")

    return steps


def _build_changed_preview(paths: list[str], *, limit: int = 5) -> str:
    preview = ", ".join(paths[:limit])
    if len(paths) > limit:
        preview += ", ..."
    return preview


def _handle_pre_tool_use(payload: dict[str, object]) -> dict[str, object]:
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input")

    if tool_name not in FILE_MUTATION_TOOLS | {"run_in_terminal"}:
        return {"continue": True}

    protected_paths = [
        path
        for path in _extract_tool_paths(tool_name, tool_input)
        if _matches_any(path, HOOK_POLICY_PREFIXES)
    ]
    if not protected_paths:
        return {"continue": True}

    return {
        "continue": True,
        "systemMessage": (
            "Consistency guard is requesting explicit approval because hook policy files are being edited."
        ),
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": (
                "Hook definitions and hook scripts execute automatically, so edits to them should be reviewed "
                f"carefully. Target paths: {_build_changed_preview(protected_paths)}"
            ),
            "additionalContext": (
                "If you change `.github/hooks/**` or `scripts/hooks/**`, re-read the updated hook files and "
                "confirm the policy still matches the repo's expectations before relying on them."
            ),
        },
    }


def _handle_post_tool_use(
    payload: dict[str, object],
    changed_paths: list[str],
) -> dict[str, object]:
    tool_name = str(payload.get("tool_name") or "")
    if tool_name not in FILE_MUTATION_TOOLS | {"run_in_terminal"}:
        return {"continue": True}

    touched_paths = _extract_tool_paths(tool_name, payload.get("tool_input"))
    touched_structural = [
        path for path in touched_paths if _matches_any(path, STRUCTURAL_PREFIXES)
    ]
    touched_hook_policy = [
        path for path in touched_paths if _matches_any(path, HOOK_POLICY_PREFIXES)
    ]

    additional_context: list[str] = []
    if touched_structural and CODE_OVERVIEW_PATH not in changed_paths:
        additional_context.append(
            "Structural code files were edited. Update `docs/code_structure_overview.md` before finishing this task."
        )

    if touched_hook_policy:
        additional_context.append(
            "Hook policy files changed. Re-read the updated hook JSON and scripts before trusting them in the next turn."
        )

    validation_steps = _build_validation_steps(changed_paths)
    if validation_steps:
        additional_context.append("Targeted validation to keep in mind:\n" + "\n".join(f"- {step}" for step in validation_steps))

    if not additional_context:
        return {"continue": True}

    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n\n".join(additional_context),
        },
    }


def _handle_stop(payload: dict[str, object], changed_paths: list[str]) -> dict[str, object]:
    if payload.get("stop_hook_active"):
        return {"continue": True}

    structural_changes = [
        path for path in changed_paths if _matches_any(path, STRUCTURAL_PREFIXES)
    ]
    code_overview_updated = CODE_OVERVIEW_PATH in changed_paths

    if structural_changes and not code_overview_updated:
        return {
            "continue": True,
            "systemMessage": (
                "Consistency guard blocked session stop because structural files changed without updating "
                f"`{CODE_OVERVIEW_PATH}`. Changed paths: {_build_changed_preview(structural_changes)}"
            ),
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "decision": "block",
                "reason": (
                    "Structural code changes require `docs/code_structure_overview.md` to be updated before "
                    "the session ends."
                ),
            },
        }

    validation_steps = _build_validation_steps(changed_paths)
    docs_touched = any(
        path == marker or path.startswith(marker)
        for path in changed_paths
        for marker in DOCS_DRIFT_PATHS
    )
    if not docs_touched and any(
        path.endswith((".py", ".ts", ".tsx", ".vue", ".sh", ".md")) for path in changed_paths
    ):
        validation_steps.append(
            "No docs or spec updates detected yet: consider running `bash scripts/check_docs_drift.sh`."
        )

    if not validation_steps:
        return {"continue": True}

    return {
        "continue": True,
        "systemMessage": (
            "Consistency guard review for changed files:\n"
            + "\n".join(f"- {step}" for step in validation_steps)
        ),
    }


def _dispatch_hook(payload: dict[str, object], changed_paths: list[str]) -> dict[str, object]:
    event_name = payload.get("hookEventName")
    if event_name == "PreToolUse":
        return _handle_pre_tool_use(payload)
    if event_name == "PostToolUse":
        return _handle_post_tool_use(payload, changed_paths)
    if event_name == "Stop":
        return _handle_stop(payload, changed_paths)
    return {"continue": True}


def _emit(payload: dict[str, object], *, exit_code: int = 0) -> None:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.flush()
    raise SystemExit(exit_code)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        payload = {}

    try:
        changed_paths = _get_changed_paths()
    except Exception as exc:  # pragma: no cover - best effort hook behavior
        _emit(
            {
                "continue": True,
                "systemMessage": (
                    "Consistency guard could not inspect Git changes automatically. "
                    f"Please verify your updates manually. Details: {exc}"
                ),
            }
        )

    if not changed_paths:
        _emit({"continue": True})

    _emit(_dispatch_hook(payload, changed_paths))


if __name__ == "__main__":
    main()
