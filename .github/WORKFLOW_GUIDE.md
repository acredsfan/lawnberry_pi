# LawnBerry Workflow Guide — All Scenarios

This guide maps every type of task to the right agent, skill, or chat mode to use in Copilot CLI. The **LawnBerry Workflow Orchestrator** auto-routes most scenarios, but this reference covers all options.

## Quick Decision Tree

```
START: What are you doing?

1. Debugging a specific failure (mower spins, WiFi drops, test fails)?
   → Use LawnBerry Workflow Orchestrator (/agent)
   → It auto-routes to the right specialist

2. Writing or updating documentation?
   → Use Chat Mode: docs.writer
   OR /agent LawnBerry Docs Maintainer

3. Implementing a feature (sensor, motor, UI element)?
   → Use Chat Mode: sensors.hardware OR webui.feature
   OR /agent LawnBerry Maintainer

4. Writing tests (unit, integration, hardware-in-loop)?
   → Use Chat Mode: tests.software OR tests.hardware-in-loop
   OR /agent Regression Test Planner

5. Refactoring code (renaming, restructuring, typing)?
   → Use Chat Mode: repo.refactor
   OR /agent LawnBerry Maintainer

6. Auditing the whole project (bugs, gaps, drift)?
   → Use Chat Mode: repo.audit-planner
   OR /agent Drift Auditor

7. Validating with real hardware/sensors?
   → Use Chat Mode: tests.hardware-in-loop
   OR /skill sim-hardware-validation (if you need decision logic)
```

---

## Agents (Use `/agent` to invoke)

### 1. **LawnBerry Workflow Orchestrator** ⭐ (START HERE for debugging)
**When:** Multi-step debugging across subsystems, uncertain root cause  
**Auto-routes to specialists based on keywords** (see ORCHESTRATOR-QUICK-START.md)

**Example:** "Mower spins and doesn't move toward waypoints"
```
→ Orchestrator detects: navigation + heading keywords
→ Auto-invokes: /research (BNO085), /fleet (motor+IMU threads), /agent Navigation Hardening
```

**Keywords that trigger auto-routing:**
- `navigation` / `heading` / `spins` / `waypoint` → Navigation Hardening Specialist
- `control` / `lag` / `joystick` → Frontend Flow Specialist
- `test fail` / `regression` → Regression Test Planner
- `WiFi` / `watchdog` / `systemd` → Runtime Audit & Fix
- `motor` / `GPIO` / `safety` → Hardware Safety Reviewer
- `docs` / `drift` → LawnBerry Docs Maintainer

---

### 2. **Navigation Hardening Specialist**
**When:** Mower heading, waypoint navigation, tank turns, obstacle avoidance

**What it does:**
- Audit waypoint progress validation
- Check heading error computation (ZYX convention, compass mapping)
- Stop/fault behavior on obstacle detection
- Interrupted traversal recovery
- Targeted regression coverage for nav flows

**Invocation:**
```
/agent Navigation Hardening Specialist
→ Task: "The mower turns the wrong direction"
```

---

### 3. **Frontend Flow Specialist**
**When:** Control responsiveness, WebSocket lag, state management, UI reactivity

**What it does:**
- Trace WebSocket connect/disconnect flows
- Audit Pinia store state propagation
- Check API contract alignment
- Fix control lag (telemetry polling, batch sizing)
- Validate mission planner → execution flow

**Invocation:**
```
/agent Frontend Flow Specialist
→ Task: "Joystick controls are unresponsive"
```

---

### 4. **Regression Test Planner**
**When:** Test failures, flaky tests, coverage gaps

**What it does:**
- Diagnose test failure root causes
- Plan minimal regression coverage
- Recommend pytest markers and fixtures
- Assess simulation-vs-hardware test scope

**Invocation:**
```
/agent Regression Test Planner
→ Task: "test_mission_planner is failing randomly"
```

---

### 5. **Hardware Safety Reviewer**
**When:** Motor control, blade safety, GPIO, RoboHAT communication, E-stop

**What it does:**
- Review motor PWM logic (dead zone, mixing, direction)
- Check blade safety interlocks
- Validate RoboHAT UART/USB handoff
- Verify watchdog feeding and timeouts
- Audit emergency stop paths

**Invocation:**
```
/agent Hardware Safety Reviewer
→ Task: "Motor commands are being sent but mower doesn't move"
```

---

### 6. **Runtime Audit & Fix**
**When:** SystemD services, WiFi connectivity, config drift, port mismatches

**What it does:**
- Audit runtime contract (ports, startup behavior, env vars)
- Check systemd unit definitions
- Review service interdependencies
- Fix config-vs-code mismatches
- Validate watchdog health checks

**Invocation:**
```
/agent Runtime Audit & Fix
→ Task: "Backend won't start after config changes"
```

---

### 7. **Drift Auditor**
**When:** Documentation drift, config-code mismatch, outdated references

**What it does:**
- Compare docs against actual implementation
- Find stale config files / hardcoded values
- Check hardware connection docs vs actual GPIO
- Audit serial port assignments
- List all drift sites with remediation plan

**Invocation:**
```
/agent Drift Auditor
→ Task: "Docs say BNO085 is on /dev/serial0 but it's actually on /dev/ttyAMA4"
```

---

### 8. **LawnBerry Docs Maintainer**
**When:** Writing/updating maintainer guides, API docs, hardware wiring

**What it does:**
- Update developer-toolkit.md
- Write hardware integration docs
- Create runbooks (startup, deployment, troubleshooting)
- Generate API reference from OpenAPI schema
- Keep docs synchronized with code changes

**Invocation:**
```
/agent LawnBerry Docs Maintainer
→ Task: "Create a troubleshooting guide for WiFi issues"
```

---

### 9. **Code Structure Regenerator**
**When:** Callable interface docs are out of sync with code changes

**What it does:**
- Scan backend/src for new/removed functions
- Scan frontend/src for new/removed exports
- Update docs/code_structure_overview.md
- Regenerate API inventory with signatures

**Invocation:**
```
/agent Code Structure Regenerator
→ Task: "Update code_structure_overview.md after nav refactor"
```

---

### 10. **LawnBerry Maintainer**
**When:** General code changes, bug fixes, refactoring

**What it does:**
- Implement features or bug fixes
- Run tests and linting
- Ensure changes don't break other parts
- Update related files (tests, docs, config)

**Invocation:**
```
/agent LawnBerry Maintainer
→ Task: "Fix the PWM dead zone issue"
```

---

### 11. **Deployment Operations Maintainer**
**When:** SystemD services, HTTPS/TLS, backups, disaster recovery

**What it does:**
- Set up HTTPS certificates
- Configure systemd units
- Plan backup and restore procedures
- Handle remote access (SSH tunneling)
- Document operational runbooks

**Invocation:**
```
/agent Deployment Operations Maintainer
→ Task: "Set up Let's Encrypt on the mower's web server"
```

---

## Skills (Use `/skills` to list; or use a skill in prompts)

Skills are shorter-term guidance than agents. Use when you need a **process checklist** or **specialized hardening pass**.

### Navigation Skills
- `navigation-hardening-pass` — Hardening checklist for navigation work
- `mission-recovery-pass` — Recovery semantics and persistence validation

### Control & Hardware Skills
- `control-camera-regression-review` — Manual control + camera paths (USB, watchdog, responsiveness)
- `hardware-safety-reviewer` — Safety audit for hardware-sensitive changes

### System Skills
- `runtime-audit-and-fix` — Contract alignment (ports, startup, systemd)
- `runtime-contract-audit` — Drift detection across ports, scripts, config
- `subsystem-hardening-orchestration` — Coordinate hardening across nav/mission/control/AI

### Development Skills
- `safe-change-delivery` — Change delivery with re-entry, investigation, sync, validation
- `ai-model-quality-pass` — AI/ML result quality without backend contract breaks
- `sim-hardware-validation` — SIM_MODE validation vs hardware

### Meta Skills
- `maintenance-orchestration` — Choose specialist workflow for multi-step tasks

---

## Chat Modes (Use `shift+tab` to cycle modes)

Chat modes are **opinionated workflows** that guide multi-step work in a specific domain.

### 🧪 Testing

**`tests.software`** — Write unit and integration tests
- Backend pytest tests (mocking, fixtures, async)
- WebSocket integration tests
- No flaky sleeps; deterministic assertions
- **Use when:** "I need to write tests for the mission planner"

**`tests.hardware-in-loop`** — Hardware-in-the-loop validation
- Safe sensor probes (gating by SIM_MODE)
- Verify sensor data is sane
- Don't risk motion; telemetry-only
- **Use when:** "I need to validate that the GPS is streaming correct data"

### 📚 Documentation

**`docs.writer`** — Generate or update documentation
- Quickstarts, API refs, wiring maps
- Runbooks, FAQs, troubleshooting guides
- Must match code and build cleanly
- **Use when:** "I need to create API documentation for the mission endpoints"

### 💻 Development

**`webui.feature`** — Implement WebUI features
- Aligned FastAPI endpoints + Vue components
- Type-safe request/response
- Integration tests included
- **Use when:** "Add an obstacle threshold slider to the settings page"

**`sensors.hardware`** — Implement sensor/actuator support
- Async I/O, retries, timeouts
- Metrics and health checks
- Safe shutdown
- **Use when:** "Add support for the Victron solar charger via BLE"

**`repo.refactor`** — Safe incremental refactors
- Renaming, imports, typing, logging
- Tests green at each step
- No breaking changes
- **Use when:** "Refactor the navigation module to use better naming"

### 🔍 Code Quality

**`repo.audit-planner`** — Deep codebase audit
- Finds bugs, gaps, style drift
- Outputs multi-PR remediation plan
- Prioritized by risk and effort
- **Use when:** "Audit the entire codebase for issues and create a fix plan"

**`sensors.hardware`** (also covers hardware audit)
- Validates sensor integration
- Checks driver quality, timeouts, fallbacks

---

## How the Orchestrator Decides (Automated)

When you invoke `/agent` → select **LawnBerry Workflow Orchestrator**, it:

1. **Analyzes your task description** for keywords
2. **Detects research needs** (unfamiliar hardware/protocol)
   - If yes: `/research` on the topic
3. **Detects parallel work** (2+ independent subsystems)
   - If yes: `/fleet` mode + describe threads
4. **Routes to specialist** based on subsystem keyword
   - If match found: `/agent [Specialist]`
   - If no match: Continues as generic orchestrator

**Example flow:**
```
Input: "WiFi drops when mower moves, missions fail, sensors timeout"

Orchestrator decision:
  ✓ Research needed? "timeout" + "WiFi" → Research on watchdog escalation
  ✓ Parallel? WiFi watchdog + mission flow + sensor I/O → /fleet enable
  ✓ Specialist? "WiFi" + "watchdog" → Runtime Audit & Fix
  
Action: /research + /fleet + /agent Runtime Audit & Fix
```

---

## Decision Matrix

| Task | Agent | Chat Mode | Skill |
|------|-------|-----------|-------|
| Mower spins indefinitely | Workflow Orchestrator (auto-routes) | — | — |
| Joystick is unresponsive | Workflow Orchestrator (auto-routes to Frontend) | webui.feature | — |
| Test is flaky | Workflow Orchestrator (auto-routes to Regression) | tests.software | — |
| WiFi keeps disconnecting | Workflow Orchestrator (auto-routes to Runtime) | — | runtime-audit-and-fix |
| Motor doesn't move | Workflow Orchestrator (auto-routes to Hardware) | sensors.hardware | hardware-safety-reviewer |
| Docs are out of sync | Drift Auditor | docs.writer | — |
| Write new tests | Regression Test Planner | tests.software | — |
| Implement new feature | LawnBerry Maintainer | sensors.hardware / webui.feature | safe-change-delivery |
| Refactor code | LawnBerry Maintainer | repo.refactor | — |
| Audit whole codebase | Drift Auditor | repo.audit-planner | — |
| Setup HTTPS / backups | Deployment Ops Maintainer | — | — |
| Harden navigation | Navigation Specialist | — | navigation-hardening-pass |
| Plan mission recovery | — | — | mission-recovery-pass |

---

## Getting Help

- **"Which tool should I use?"** → Start here, read the decision tree above
- **"I'm debugging a mower issue"** → Use Workflow Orchestrator (`/agent`)
- **"I'm writing new code"** → Use appropriate Chat Mode (`shift+tab`)
- **"I'm unsure about a change"** → Use a Skill to validate
- **"I need docs updated"** → Use LawnBerry Docs Maintainer (`/agent`) or docs.writer mode

---

## See Also

- `.github/agents/ORCHESTRATOR-QUICK-START.md` — Quick reference for the Orchestrator
- `.github/copilot-instructions.md` — Project conventions, test commands, serial ports
- `docs/developer-toolkit.md` — Maintainer orientation, architecture, key files
