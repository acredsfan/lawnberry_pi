#!/usr/bin/env python3
"""
Universal Session Serializer.
Captures dirty Git files, diff size, and current task.md checklist.
"""
import subprocess
import os
import sys
from pathlib import Path

def get_git_state() -> dict:
    try:
        # Works on Windows and Linux if git is in PATH
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], shell=True, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        status = subprocess.check_output(["git", "status", "--short"], shell=True, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        diff = subprocess.check_output(["git", "diff", "--stat"], shell=True, stderr=subprocess.DEVNULL).decode("utf-8").strip()
        return {
            "branch": branch,
            "dirty_files": [line.strip() for line in status.split("\n") if line.strip()],
            "diff_stat": diff
        }
    except Exception:
        return {"branch": "unknown", "dirty_files": [], "diff_stat": "Git is unavailable or repository is not initialized."}

def get_checklist() -> str:
    # Looks for a task.md file in the current working directory or system state
    task_file = Path("task.md")
    if not task_file.exists():
        return "No task.md file found. Create a task.md file at root to track active work items."
    
    try:
        content = task_file.read_text(encoding="utf-8")
        lines = content.splitlines()
        # Extract uncompleted [ ] and in-progress [/] items
        active_items = []
        for line in lines:
            if "[ ]" in line or "[/]" in line:
                active_items.append(line.strip())
        
        if not active_items:
            return "All tasks are marked completed [x]! Ready for next instructions."
        return "\n".join(active_items[:15])  # Cap at 15 items to conserve token budget
    except Exception as e:
        return f"Error reading task.md: {str(e)}"

def main():
    git = get_git_state()
    checklist = get_checklist()
    
    print("==================== AGENT WORKSPACE INTEGRITY SESSION ====================")
    print(f"Active Git Branch: {git['branch']}")
    print("Modified & Dirty Files:")
    if git["dirty_files"]:
        for file in git["dirty_files"]:
            print(f"  {file}")
    else:
        print("  None (Workspace is clean)")
    print("\nGit Diff Stat Summary:")
    print(git["diff_stat"] or "  None")
    print("\nActive Checklist Items (task.md):")
    print(checklist)
    print("===========================================================================")

if __name__ == "__main__":
    main()
