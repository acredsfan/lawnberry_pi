# LawnBerry Pi Copilot Customizations Guide

This guide explains the GitHub Copilot customizations that ship with LawnBerry Pi, what they are for,
how to invoke them, and which one to choose for common tasks.

Use this document when you want to work with the repository's built-in Copilot prompts, skills,
agents, chat modes, and hooks without guessing which workflow fits best.

## What lives where

The repository's Copilot customization surfaces live under `.github/`:

- `.github/copilot-instructions.md` — always-on workspace instructions for Copilot in this repo
- `.github/agents/` — custom specialist agents you can pick directly or delegate to
- `.github/prompts/` — reusable slash commands for specific tasks
- `.github/skills/` — on-demand workflows and domain playbooks
- `.github/chatmodes/` — curated chat modes for recurring work styles
- `.github/hooks/` — guardrails that can block or shape unsafe/incomplete actions
- `.github/pull_request_template.md` — PR template used when opening pull requests

## How to use these customizations

### Prompts

Prompts appear as slash commands in chat.

Use them when you already know the task you want to perform, such as:

- triaging a new change
- auditing runtime drift
- delivering a safe code change
- reviewing hardware safety
- tracing a frontend state flow

In VS Code chat:

1. Type `/`
2. Pick the prompt by name
3. Add a short task description in the prompt argument field

### Skills

Skills are workflow packages the agent can load when the task matches them.
They are best for repeatable multi-step work such as:

- maintainer re-entry
- runtime audits
- simulation vs hardware validation
- navigation hardening
- mission recovery

You may also see skills available as slash commands if they are user-invocable.

### Agents

Agents are specialist personas with narrower scope and tool preferences.
Use them when you want a specific specialist to take the lead, or when a prompt tells you which
agent should own the next step.

In VS Code chat, switch agents from the agent picker or invoke a prompt that is already wired to
an agent.

### Chat modes

Chat modes are curated working styles for a class of tasks.
They are useful when you want the whole conversation to stay focused on one kind of work,
such as docs writing, repo audit planning, UI feature work, or hardware-in-loop testing.

### Hooks

Hooks are automatic guardrails. You do not invoke them directly.
They may stop an unsafe or incomplete action and require the agent to finish the workflow properly.

## Start here: recommended entry points

If you are not sure where to begin, use one of these first:

| If you want to... | Best starting point |
| --- | --- |
| Re-enter the repo after time away | `Re-enter And Triage LawnBerry` prompt |
| Coordinate a multi-step task | `LawnBerry Workflow Orchestrator` agent |
| Audit docs/config/runtime drift | `Audit And Align Runtime Contract` prompt |
| Implement a change safely | `Deliver Safe LawnBerry Change` prompt |
| Plan minimal regression coverage | `Plan Regression Validation` prompt |
| Review a risky hardware path | `Review Hardware Safety` prompt |
| Trace a UI/store/API/WebSocket bug | `Trace Frontend Flow` prompt |
| Update repo docs accurately | `Update LawnBerry Docs` prompt |
| Refresh `docs/code_structure_overview.md` | `Regenerate Code Structure Overview` prompt |

## Custom agents

These are the repo's specialist agents in `.github/agents/`.

| Agent | Best for | Typical use |
| --- | --- | --- |
| `LawnBerry Workflow Orchestrator` | Coordinating multi-step work | Start here for cross-cutting tasks that may need investigation, code, docs, and validation |
| `LawnBerry Maintainer` | General repo-aware implementation | Backend/frontend fixes, refactors, tests, doc-aware code changes |
| `LawnBerry Docs Maintainer` | Documentation updates and doc drift | Updating maintainer docs, setup docs, README, testing docs |
| `Drift Auditor` | Runtime/doc/config drift reviews | Ports, startup mismatch, stale docs, source-of-truth comparisons |
| `Deployment Operations Maintainer` | Deployment and operations | systemd, HTTPS/TLS, nginx, backup/restore, remote access |
| `Frontend Flow Specialist` | Stateful frontend behavior | Pinia flows, API contracts, WebSocket flows, auth/control/map state |
| `Hardware Safety Reviewer` | Safety-critical code review | Motors, blade, RoboHAT, watchdog, E-stop, startup sequencing |
| `Regression Test Planner` | Minimal meaningful validation planning | Which tests to run, what coverage is missing, confidence and blind spots |
| `Code Structure Regenerator` | Structure doc synchronization | Updating `docs/code_structure_overview.md` after callable-interface changes |

## Orchestration prompts

These are the highest-value top-level prompts for most maintainers.

| Prompt | What it does | Use it when |
| --- | --- | --- |
| `Re-enter And Triage LawnBerry` | Rebuilds context and classifies the task | You are returning to the repo or do not know the right next workflow |
| `Audit And Align Runtime Contract` | Audits first, then fixes proven runtime drift | Ports, startup, proxies, docs, systemd, or config disagree |
| `Deliver Safe LawnBerry Change` | Coordinates investigation, implementation, doc sync, and validation | You want one prompt to carry a change end-to-end |
| `Coordinate Hardening Pass` | Routes hardening work to the right subsystem workflow | Navigation, mission recovery, control/camera, or AI needs hardening |

## Specialist prompts

These prompts target a narrower task directly.

| Prompt | What it does | Best fit |
| --- | --- | --- |
| `Audit Runtime Drift` | Read-only drift audit | You want a report before deciding whether to change anything |
| `Update LawnBerry Docs` | Updates docs against implementation truth | Maintainer docs, setup guides, README, runtime docs |
| `Regenerate Code Structure Overview` | Syncs callable-interface documentation | After structural code changes in covered source areas |
| `Plan Regression Validation` | Produces the smallest useful validation plan | Before or after a code change when you want scoped testing |
| `Review Hardware Safety` | Reviews a risky path for fail-safe behavior | Motor, blade, RoboHAT, camera, GPIO, serial, watchdog changes |
| `Trace Frontend Flow` | Traces a UI/store/API/WebSocket flow | Stale state, auth bugs, reconnect issues, contract mismatch |
| `Maintain Runtime Ops Workflow` | Fixes an ops/deployment workflow | systemd, TLS, backups, restore, remote access |
| `Implement LawnBerry Change` | Runs a repo-aware implementation workflow | Focused code changes when you know the seam already |
| `Explore LawnBerry` | Performs fast read-only repo exploration | You want key files, symbols, and next steps without edits |

## Legacy or specification prompts

These prompts are still useful, but they are oriented toward the repo's feature-spec workflow rather
than general day-to-day maintenance.

| Prompt | Purpose |
| --- | --- |
| `Specify` | Create or update a feature specification |
| `Clarify` | Ask targeted clarification questions on a spec |
| `Plan` | Generate implementation planning artifacts |
| `Tasks` | Produce dependency-ordered tasks |
| `Analyze` | Read-only consistency check across spec/plan/tasks |
| `Implement` | Execute the planned implementation tasks |
| `Constitution` | Create or update the project constitution |

## Skills

The repo's skills in `.github/skills/` package repeatable workflows and subsystem playbooks.

### Orchestration skills

| Skill | Purpose |
| --- | --- |
| `maintainer-reentry` | Quick project re-entry using `docs/developer-toolkit.md` |
| `maintenance-orchestration` | Choose the right specialist path for a multi-step maintenance task |
| `runtime-audit-and-fix` | Audit runtime contract drift and align the smallest necessary set of files |
| `safe-change-delivery` | Deliver a change end-to-end with investigation, doc sync, and validation |
| `subsystem-hardening-orchestration` | Route hardening work to the right subsystem pass |
| `maintainer-doc-sync` | Keep maintainer docs and structure docs synchronized with implementation |

### Subsystem and validation skills

| Skill | Purpose |
| --- | --- |
| `runtime-contract-audit` | Read-only runtime drift audit across code, docs, config, and services |
| `sim-hardware-validation` | Keep simulation-safe validation separate from real hardware claims |
| `navigation-hardening-pass` | Harden navigation feedback, stop/fault behavior, and edge-case coverage |
| `mission-recovery-pass` | Define and implement safe mission persistence and restart semantics |
| `control-camera-regression-review` | Review manual-control and camera changes conservatively |
| `ai-model-quality-pass` | Improve AI quality behind the existing backend contract |

## Chat modes

The repository also includes chat modes under `.github/chatmodes/` for persistent conversation style.

| Chat mode | Good for |
| --- | --- |
| `docs.writer` | Documentation writing and cleanup |
| `repo.audit-planner` | Repo audits and planning investigation work |
| `repo.refactor` | Refactor-oriented conversations |
| `sensors.hardware` | Hardware and sensor-focused work |
| `tests.hardware-in-loop` | Hardware-in-loop validation discussions |
| `tests.software` | Software-only testing and regression work |
| `webui.feature` | Frontend/UI feature discussions |

## Hooks and guardrails

The repo currently includes this hook:

| Hook file | What it does |
| --- | --- |
| `.github/hooks/consistency-stop.json` | Enforces workflow consistency and can block incomplete finish states |

Practical takeaway: if Copilot says a hook stopped it, treat that as a guardrail, not a bug. The
agent usually needs to complete a required step such as validation or explicit task completion.

## Typical workflows

### 1. I am new or returning and want the fastest safe start

Use:

1. `Re-enter And Triage LawnBerry`
2. If the task spans multiple areas, continue with `Deliver Safe LawnBerry Change`
3. If you only need a report first, switch to `Explore LawnBerry` or `Audit Runtime Drift`

### 2. Something about ports, startup, or docs feels wrong

Use:

1. `Audit And Align Runtime Contract`
2. If you only want a report, use `Audit Runtime Drift`
3. If service units, TLS, or operations are involved, use `Maintain Runtime Ops Workflow`

### 3. I need to implement a normal code change safely

Use:

1. `Deliver Safe LawnBerry Change`
2. For focused implementation without orchestration overhead, use `Implement LawnBerry Change`
3. Then use `Plan Regression Validation` if you want a separate validation recommendation

### 4. I am touching a risky hardware path

Use:

1. `Review Hardware Safety`
2. If the work will also change code, continue with `Deliver Safe LawnBerry Change`
3. Keep simulation-safe validation explicit before making any real-hardware claims

### 5. The bug lives in the frontend state flow

Use:

1. `Trace Frontend Flow`
2. If the fix will span stores, API, docs, and tests, escalate to `Deliver Safe LawnBerry Change`

### 6. I need a hardening pass, not a one-off fix

Use `Coordinate Hardening Pass` and name the leading subsystem:

- navigation
- mission recovery
- control/camera
- AI

## How these pieces fit together

The shortest mental model is:

- **Prompts** are the easiest user entry points
- **Agents** are the specialists that do the work
- **Skills** are repeatable workflows and playbooks the agent can load
- **Chat modes** shape the whole conversation style
- **Hooks** enforce guardrails when the workflow would otherwise end incorrectly
- **Workspace instructions** provide the default repo rules all of the above should follow

## Recommended default for most users

If you only remember one thing, remember this:

1. start with `Re-enter And Triage LawnBerry` when the task is fuzzy
2. use `Deliver Safe LawnBerry Change` for most non-trivial code work
3. use `Audit And Align Runtime Contract` when docs/runtime/service behavior disagree
4. use `Coordinate Hardening Pass` for subsystem-level reliability work

That sequence covers most day-to-day LawnBerry maintenance without needing to memorize the full
customization matrix.
