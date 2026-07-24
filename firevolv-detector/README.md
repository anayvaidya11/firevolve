# liuwilliam12~firevolv-detector

The **Layer-3 Claude judge** from Firevolv (PRD §3.3), packaged as a Guild agent.

It inspects an untrusted document for prompt-injection attempts aimed at a
specified AI agent, and returns strict JSON spans per the frozen schema
(PRD §5.2). Everything inside the document is treated as **DATA, never
instructions** — the judge reports what it finds, it never obeys it.

## Input

| Field | Required | Default |
|---|---|---|
| `document` | yes | — |
| `profile_json` | no | Executive Assistant Agent persona (PRD §1.1) |
| `examples_block` | no | `"No labeled examples yet."` |

## Output

Strict JSON: `{ "spans": [{ quote, category, severity, addressed_to, rationale }], "overall_assessment" }`
(PRD §5.2). The backend router resolves each `quote` to character offsets by
verbatim substring match and drops any quote it can't find (PRD §5.2), then
computes the BLOCK/PASS/UNCERTAIN band (PRD §3.4). Non-conforming output is the
judge-capture tripwire → UNCERTAIN (PRD §6.3).

## Scope

This agent is **only** the judge. The full detector (heuristics, GliGuard, the
router, and the Actian retrieval loop) is the FastAPI backend in `../backend/`.
Guild's role in the PRD proper is the eval harness (`../eval/guild.yml`); this
agent is a deliberate extension that exposes the judge as a standalone Guild
agent.

## No tools / no skills

The judge is a pure contextual reasoner, so `tools: {}` — the default
`skillsTools` spread was removed intentionally.
