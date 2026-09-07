# Governance Continuity Architecture (GCA) — V3

**The governance operating system for the AI age.**
*MIT Sloan — Group 7 Impact Project*

> AI supports governance continuity — not automated leadership.
> Humans decide. AI supports.

Organizations have operating systems for technology, but not for authority. GCA encodes authority to roles, routes decisions through escalation paths, and uses an LLM to evaluate governance signals — while humans retain authority, judgment, and accountability.

## Three layers

| Layer | What it holds | Where in the app |
|---|---|---|
| **Data** | Roles, decision domains, escalation paths, disruptions, signals | Authority Registry · Decision Domains · Escalation Maps · Disruptions |
| **AI (LLMOps)** | Evaluate relevance → route to accountable role → log everything | Signals (Evaluate) · Controls (call log) |
| **Human** | Authority, judgment, accountability, exception handling | HITL Review · Audit |

## The LLMOps loop

`SIGNAL → EVALUATE → ROUTE → LOG → LEARN`

1. **Signal** — a governance event is detected (automatically on disruption, or manually).
2. **Evaluate** — the LLM scores severity and recommends a route, using only a bounded context: the authority registry, the related domain, and its escalation paths.
3. **Route** — low-stakes signals are routed directly; anything critical/high-risk goes to the HITL queue.
4. **Log** — recommendation, confidence, rationale, tokens, and any human override are persisted.
5. **Learn** — override rationales are reviewable in one place to refine playbooks and prompts.

If `ANTHROPIC_API_KEY` is not set (or the API fails), a deterministic rule-based fallback runs instead, so the pipeline always completes and the demo never blocks.

## Success metrics (dashboard)

- **Continuity Score** — weighted readiness across roles, domains, succession, escalation, signals
- **Decision Latency** — hours from signal detected → accountable human action
- **HITL Compliance** — % of high-risk AI outputs actually reviewed by a human
- **Audit Quality** — % of closed decisions with a logged rationale

## Deploy to Railway

```bash
git add -A
git commit -m "GCA V3 - LLMOps loop, HITL review, pilot tracker"
git push
```

Railway environment variables:

| Variable | Required | Notes |
|---|---|---|
| `SECRET_KEY` | yes | any random string |
| `ANTHROPIC_API_KEY` | no | enables live LLM evaluation; without it the app runs in fallback mode |
| `GCA_MODEL` | no | defaults to `claude-sonnet-4-6` |
| `DATABASE_URL` | auto | set by Railway if you add Postgres |

Existing V2 databases upgrade automatically on first start (missing columns are added).

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...   # optional
python app.py                      # http://localhost:5000
```

## Demo data

8 authority roles · 10 decision domains · 4 escalation paths · 2 active disruptions · 5 governance signals (one already through the full loop) · 16 pilot milestones.

---
*Group 7: Margaret Wood, Ronald C Owens Jr, Arsen Khanguieldyan, Craig Kallin*
