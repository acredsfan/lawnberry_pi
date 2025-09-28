<!--
Sync Impact Report:
Version: 1.3.0 → 1.4.0 (Expand agent execution rules: mandatory local workspace edits/search; allow GitHub CLI for git ops)
Modified principles: None renamed
Added sections: Clarified Agent Execution Rules (local edit/search, GH CLI option)
Removed sections: None
Templates requiring updates:
  - .specify/templates/plan-template.md (version reference) ✅ updated
  - .specify/templates/spec-template.md ✅ no change required
  - .specify/templates/tasks-template.md ✅ no change required
Follow-up TODOs: None
-->

# LawnBerry Pi Constitution

## Core Principles

### I. Platform Exclusivity
The LawnBerry Pi system MUST operate exclusively on Raspberry Pi OS Bookworm (64-bit) with Python 3.11.x runtime on Raspberry Pi 5 (primary) or Pi 4B (compatible). No cross-platform dependencies, alternate interpreters, or non-ARM64 Linux distributions are permitted. All development, testing, and deployment MUST assume this target platform exclusively.

### II. Package Isolation (NON-NEGOTIABLE)
AI acceleration dependencies MUST maintain strict isolation: `pycoral`/`edgetpu` are BANNED from the main environment and MUST use dedicated venv-coral. Coral USB acceleration operates in complete isolation from the main system. Hardware acceleration follows constitutional hierarchy: Coral USB (isolated venv-coral) → Hailo HAT (optional) → CPU fallback (TFLite/OpenCV). Package management via uv with committed lock files ensures reproducible builds.

### III. Test-First Development (NON-NEGOTIABLE)
TDD methodology is mandatory: Tests written → User approved → Tests fail → Implementation begins. Red-Green-Refactor cycle strictly enforced. Every feature starts with failing tests that define expected behavior. No implementation code without corresponding test coverage. Hardware simulation (SIM_MODE=1) MUST provide complete test coverage for CI execution without physical hardware dependencies.

### IV. Hardware Resource Coordination
Hardware interfaces are single-owner resources requiring explicit coordination. Camera access is brokered exclusively through `camera-stream.service`; other services MUST subscribe to feeds via IPC and NEVER open the device directly. Sensors, motor controllers, and communication buses require coordination mechanisms (locks, IPC queues, or dedicated daemons) to prevent concurrent access conflicts. Resource ownership must be clearly defined and enforced.

### V. Constitutional Hardware Compliance
Hardware configuration MUST align with `spec/hardware.yaml` requirements. INA3221 power monitoring uses fixed channel assignments: Channel 1 (Battery), Channel 2 (Unused), Channel 3 (Solar Input). GPS supports either ZED-F9P USB with NTRIP corrections OR Neo-8M UART (mutually exclusive). Motor control via RoboHAT RP2040→Cytron MDDRC10 (preferred) or L298N fallback. HAT stacking conflicts (RoboHAT + Hailo HAT) are prohibited without constitutional amendment.

## Technology Stack Requirements

All system components must use approved technologies and interfaces: Picamera2 + GStreamer for camera handling, python-periphery + lgpio for GPIO control, pyserial for UART communication, and systemd for service management. WebUI must maintain retro 1980s aesthetic with constitutional branding assets. No frameworks or libraries outside the approved stack without constitutional amendment and compelling technical justification.

## Development Workflow

Every code change MUST update `/docs` and `/spec` documentation with CI validation preventing drift. No TODOs are permitted unless formatted as `TODO(v3):` with linked GitHub issue for future version planning. All services operate as managed systemd units with automatic startup, monitoring, and graceful shutdown. Service coordination respects camera ownership and hardware resource management protocols.

AI agents MUST maintain an `AGENT_JOURNAL.md` file in the `.specify/memory/` folder, documenting progress, changes made, decisions taken, and any information necessary for seamless handoff to other agents or developers. The journal MUST include timestamps, rationale for major decisions, and current project state to ensure continuity across development sessions.

After completing assigned tasks for a session, the responsible agent MUST execute the repository workflows defined in `.github/workflows/`. Upon successful completion of these workflows, the agent MUST commit any resulting changes (generated artifacts, updated docs/specs, version bumps) to the current working branch with a clear, conventional commit message referencing the workflows run. If workflows fail, the agent MUST document failures and remediation steps in `AGENT_JOURNAL.md` and refrain from committing broken artifacts.

Agent execution rules (MANDATORY):
- Apply code changes directly in the repository.
- If tests or linting are needed, run them in the terminal on Linux/ARM64 (Raspberry Pi OS Bookworm). Do NOT add Windows/macOS-only dependencies or instructions.
- If any dependency is not available on ARM64, STOP and propose a Pi-compatible alternative in `AGENT_JOURNAL.md` (and PR description, if applicable) before proceeding.
- When done, summarize the changes and update `.specify/memory/AGENT_JOURNAL.md` with outcomes, rationale, and next steps.
  
Workspace editing and local context (STRICT):
- Always edit files directly in the local workspace. Do NOT download or fetch files via remote content APIs/tools to modify them. Locate and open files from the checked-out repository tree.
- Prefer local codebase search (editor search, ripgrep) to discover files and symbols. Use repository-aware tools before any remote content fetchers. If a remote fetch is ever necessary, justify it in the journal.

Git operations (OPTIONS):
- You MAY use MCP GitHub tools for commits and PRs if available and part of the workflow.
- You MAY alternatively use the GitHub CLI (`gh`) for git operations when it is installed and authenticated in the workspace. Choose one method per session and document which was used in `AGENT_JOURNAL.md`.
- All PRs MUST use `.github/pull_request_template.md` and include a brief note confirming constitutional compliance.

- For teams using MCP GitHub tools, use `#mcp_github_add_comment_to_pending_review` to perform the push/commit step in accordance with the established review flow after successful workflow completion. If using GitHub CLI, use `gh pr create` with the repository template.

## Governance

This constitution supersedes all other development practices and requirements. Constitutional amendments require formal documentation, approval process, and migration plan for affected systems. All pull requests and code reviews MUST verify constitutional compliance before approval. Complexity deviations require explicit justification with simpler alternatives documented. Development teams MUST use `spec/agent_rules.md` for runtime development guidance and implementation constraints.

**Version**: 1.4.0 | **Ratified**: 2025-09-25 | **Last Amended**: 2025-09-26