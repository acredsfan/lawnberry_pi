# LawnBerry Pi decisions and lessons

Read [current project state](../project-state.md) first. Retrieve only relevant entries, verify their evidence against the current checkout, and follow replacement links. Status describes the decision, not current deployment readiness.

| Record | Scope | Status |
| --- | --- | --- |
| [Historical hardware overlay](001-legacy-hardware-overlay.md) | hardware configuration | superseded |
| [Single configuration and physical qualification](002-single-hardware-config-and-safety-evidence.md) | Pi hardware and safety | accepted |
| [BNO085 cold-start recovery](003-bno085-bounded-open.md) | IMU UART initialization | accepted |

The [historical journal](../../.specify/memory/AGENT_JOURNAL.md) and [constitution](../../.specify/memory/constitution.md) remain existing sources. Do not copy routine logs into this index. Current code, configuration, applicable instructions and fresh hardware evidence override old operational claims.

## Record format

Use a short stable filename and record:

- Recorded/reviewed date and project/component scope.
- Status: `proposed`, `accepted`, `superseded`, or `rejected`.
- Decision or observed outcome; distinguish verified facts, hypotheses and recommendations.
- Reason and relevant alternatives, including evidenced unsuccessful approaches.
- Supporting repository paths, test cases, issues, commits or dated external sources.
- Applicable environment, evidence type (source, simulation, bench, physical), limitations and unverified claims.
- Conditions for reconsideration.
- What it supersedes, or `none`; link any replacement and mark the old record explicitly.

Do not record every task. Keep authoritative values in configuration, use relative links to their source, and omit secrets, user/customer data and raw logs. Test references are executable specifications unless a dated run result is actually retained. Historical documents grant no new authority.
