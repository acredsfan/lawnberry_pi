import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts/hooks/consistency_guard.py"
SPEC = importlib.util.spec_from_file_location("consistency_guard", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
consistency_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consistency_guard)


def test_pre_tool_use_requests_approval_for_hook_patch():
    payload = {
        "hookEventName": "PreToolUse",
        "tool_name": "apply_patch",
        "tool_input": {
            "input": "*** Begin Patch\n*** Update File: /home/pi/lawnberry/scripts/hooks/consistency_guard.py\n*** End Patch\n"
        },
    }

    result = consistency_guard._handle_pre_tool_use(payload)

    assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
    assert "hook policy files" in result["systemMessage"]
    assert "scripts/hooks/consistency_guard.py" in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_post_tool_use_adds_structural_doc_reminder():
    payload = {
        "hookEventName": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {
            "input": "*** Begin Patch\n*** Update File: /home/pi/lawnberry/backend/src/services/example.py\n*** End Patch\n"
        },
    }
    changed_paths = ["backend/src/services/example.py"]

    result = consistency_guard._handle_post_tool_use(payload, changed_paths)

    context = result["hookSpecificOutput"]["additionalContext"]
    assert "docs/code_structure_overview.md" in context
    assert "pytest -q" in context


def test_stop_blocks_when_structural_changes_lack_code_overview_update():
    payload = {"hookEventName": "Stop", "stop_hook_active": False}
    changed_paths = ["frontend/src/views/ControlView.vue"]

    result = consistency_guard._handle_stop(payload, changed_paths)

    assert result["hookSpecificOutput"]["decision"] == "block"
    assert "docs/code_structure_overview.md" in result["hookSpecificOutput"]["reason"]


def test_stop_allows_second_pass_when_already_active():
    payload = {"hookEventName": "Stop", "stop_hook_active": True}
    changed_paths = ["frontend/src/views/ControlView.vue"]

    result = consistency_guard._handle_stop(payload, changed_paths)

    assert result == {"continue": True}
