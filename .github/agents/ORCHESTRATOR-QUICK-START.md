# LawnBerry Workflow Orchestrator — Quick Start

The enhanced **LawnBerry Workflow Orchestrator** automatically invokes three powerful productivity tips:

- **Tip 2: Fleet Mode** (`/fleet`) — Parallelize independent investigations
- **Tip 4: Specialist Routing** (`/agent`) — Delegate to domain experts
- **Tip 5: Research Mode** (`/research`) — Resolve unfamiliar hardware/protocol questions

## How to Use

### Option 1: Direct Agent Invocation (Recommended)
```bash
/agent
→ Select "LawnBerry Workflow Orchestrator"
→ Describe your task
```

### Option 2: Describe Your Issue Directly
Just describe what you're working on. The orchestrator will automatically:
1. Scan for research triggers (unfamiliar hardware/protocols)
2. Detect parallel work opportunities
3. Route to the right specialist

## Examples

### Example 1: Navigation Bug
```
Task: "The mower spins in circles and doesn't move toward waypoints"

Orchestrator detects:
  ✓ Research trigger: "heading" + "BNO085" keywords
  ✓ Fleet opportunity: Motor behavior + IMU diagnosis + nav controller
  ✓ Specialist: Navigation Hardening Specialist

Action:
  1. /research on BNO085 ZYX convention + motor PWM mixing
  2. /fleet enable for parallel threads
  3. /agent Navigation Hardening Specialist
```

### Example 2: Control System Lag
```
Task: "The mower's joystick is unresponsive and control lags"

Orchestrator detects:
  ✓ No research needed (standard control flow)
  ✓ No parallel decomposition (single subsystem)
  ✓ Specialist: Frontend Flow Specialist

Action:
  1. /agent Frontend Flow Specialist
  2. Specialist audits WebSocket, state management, API latency
```

### Example 3: Multiple System Failures
```
Task: "WiFi keeps dropping, missions fail randomly, sensors timeout"

Orchestrator detects:
  ✓ Research trigger: "watchdog" + "timeout" behavior uncertainty
  ✓ Fleet opportunity: WiFi watchdog + mission flow + sensor I/O (3 threads)
  ✓ Specialists: Runtime Audit & Fix + potentially others

Action:
  1. /research on watchdog escalation + sensor bus contention
  2. /fleet enable for parallel WiFi/mission/sensor audits
  3. /agent Runtime Audit & Fix (takes WiFi thread)
  4. Consolidate findings from parallel threads
```

## Auto-Trigger Keywords

### For Research (`/research`)
- Hardware: `BNO085`, `Victron`, `ZED-F9P`, `RoboHAT`, `RP2040`
- Protocols: `SHTP`, `RTK`, `Game Rotation Vector`, `UART`, `I2C`
- Questions: "Why doesn't X work?", "How does X work?", "Signal corruption"
- Reversals: "I was wrong about X"

### For Fleet Mode (`/fleet`)
- Multiple subsystems: "WiFi drops + missions fail + sensors timeout"
- Multiple failures: "Please debug X, Y, and Z"
- Parallel validation: "Check A independently of B"
- Long sessions: >2 consecutive test failures

### For Specialist Routing (`/agent`)
| Keywords | Specialist |
|----------|-----------|
| `spins`, `heading`, `navigation`, `tank-turn`, `waypoint` | Navigation Hardening Specialist |
| `lag`, `joystick`, `unresponsive`, `WebSocket`, `frontend` | Frontend Flow Specialist |
| `test fail`, `regression`, `coverage`, `flaky` | Regression Test Planner |
| `WiFi`, `watchdog`, `systemd`, `service`, `restart` | Runtime Audit & Fix |
| `motor`, `GPIO`, `safety`, `interlock`, `E-stop`, `blade` | Hardware Safety Reviewer |
| `docs`, `drift`, `README`, `maintenance` | LawnBerry Docs Maintainer |

## Decision Order (Important!)

The orchestrator evaluates in this order:
1. **Research first** — removes domain uncertainty before splitting threads
2. **Fleet second** — parallelizes work based on knowledge gathered
3. **Specialist third** — routes to expert with context from above

This order maximizes information before parallel work begins.

## What You Get

Instead of asking for help with `/ask` (sidebar) or manually invoking `/fleet` and `/agent`:

- **Before:** "I'll investigate navigation... then look at motors... then check tests" (serial)
- **After:** Orchestrator detects keywords → triggers research → enables fleet → routes to specialist (parallel + informed)

## Tips

- **Be specific in your description** — more keywords → better auto-routing
- **Trust the orchestrator's decision** — if it invokes research, wait for findings before continuing
- **Review what it decided** — the orchestrator explains which modes it's enabling and why
- **It's not magic** — it's fast keyword matching + specialist routing, not AI magic

## See Also

- `lawnberry-workflow-orchestrator.agent.md` — Full agent definition
- `.github/copilot-instructions.md` — Project conventions and tools
- `/chronicle tips` — The original 5 tips analysis
