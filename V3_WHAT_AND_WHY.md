# GCA V3 — What Was Done and Why

**Governance Continuity Architecture · Group 7 · Assignment 4: Incorporate AI Tools**
*Prepared 6 September 2026*

---

## 1. Purpose of this release

The Assignment 4 deck ("Incorporate AI Tools") moves the project from *architecture* — Craig's Governance Continuity Architecture framing in V2 — to *operations*: how AI actually runs inside that architecture using LLMOps, and how it does so without taking authority away from people.

V2 could show the structure (roles, domains, escalation paths). It could not show the deck's central claim in motion: that an LLM can evaluate a governance signal, propose a route, and be overseen by a human, with every step logged. V3 closes that gap. Everything on slides 1, 2, 4 and 5 of the deck is now something the team can click on during the presentation.

The guiding constraint throughout: **humans decide, AI supports.** No change in V3 lets the model take a decision on a high-stakes domain.

---

## 2. Gap analysis that drove the work

| Deck claim | V2 status | V3 status |
|---|---|---|
| Three-layer model: Data / AI / Human (slide 1) | Implicit only | Dashboard reorganized around the three layers |
| LLMOps loop: Signal → Evaluate → Route → Log → Learn (slide 2) | Signal + Log only | Full loop implemented |
| Stateless · Metered · Logged · HITL (slide 2) | Logged only | All four implemented and visible |
| Person-bound → role-encoded authority (slide 3) | Done in V2 | Unchanged |
| Risk controls: hallucination, authority drift, privacy, adoption (slide 4) | Partially implicit | Controls page maps each risk to the mechanism that enforces it |
| Metrics: Continuity Score, Decision Latency, HITL Compliance, Audit Quality (slide 4) | Continuity Score only | All four on the dashboard, computed from live data |
| 90-Day Pilot Path: Crawl / Walk / Run / Scale (slide 5) | Absent | Pilot tracker with 16 milestones and live Run-phase evidence |

---

## 3. What was built

### 3.1 The AI layer — a real LLMOps loop

**What:** Each governance signal now has an **Evaluate** action. It assembles a bounded context (the authority registry, the related decision domain, and that domain's escalation paths), sends it to the Anthropic Messages API with a governance-specific system prompt, and receives a structured recommendation: severity, recommended role, whether a human checkpoint is required, confidence, and a short rationale grounded in the context.

**Why:** Slide 2 says "LLM scores relevance" and "send to role or HITL." V2 generated signals from hard-coded rules, so there was nothing to demonstrate. A real model call makes the deck's core mechanism observable. Using the *bounded* context, rather than free-form prompting, is also the hallucination control from slide 4: the model can only reason about facts the system gave it.

**Design decisions:**
- **Stateless.** Every evaluation is an independent call with the context rebuilt fresh. Nothing is carried between calls, so the system scales by adding workers — exactly as the deck describes.
- **Registry guard.** If the model recommends a role ID that is not in the authority registry, the recommendation is rejected before it is stored and the rejection is noted in the rationale. This makes "never invent a role" a code-level guarantee, not a prompt-level hope.
- **Rule-based fallback.** If no API key is configured, or the API call fails, a deterministic evaluator runs instead. It follows the escalation path to the first active role, then the successor chain, and applies HITL by policy. Every fallback is flagged as such in the UI and the log. This guarantees the demo cannot block on a network or billing issue, and it is honest about which mode produced each result.
- **Model configurable** via the `GCA_MODEL` environment variable, defaulting to `claude-sonnet-4-6`.

### 3.2 The human layer — HITL review queue

**What:** A new **HITL Review** page holds every AI recommendation that requires a human checkpoint. For each one the reviewer sees the signal, the domain's risk profile, and the AI's proposal with its rationale, then either **accepts** (optionally with a note) or **overrides** (choosing a different role and/or severity, with a *required* written rationale).

**Why:** Slide 2's "HITL — human checkpoint for high stakes" and slide 4's "authority drift" control both depend on a place where a human decision is actually captured. Without it, "humans decide" is a slogan. The override-requires-rationale rule is what makes Audit Quality a real metric rather than a self-reported one.

**Design decisions:**
- **Forced HITL.** A signal is sent to the queue if the model asks for it, *or* if the related domain is critical/high-risk, *or* if the domain is flagged as requiring human judgment, *or* if the evaluated severity is critical. The model's opinion on whether a human is needed is a floor, never a ceiling.
- **Low-stakes signals route directly** (still logged). This preserves the deck's "persistent decision velocity" goal: the checkpoint is applied where it matters, not everywhere.
- **Review history** is shown on the same page, labelled as the LEARN loop: the pattern of overrides is the raw material for revising playbooks and prompts.

### 3.3 Metrics from slide 4, computed live

**What:** Three new metrics join the Continuity Score on the dashboard, the HITL page, and the Pilot page:

- **Decision Latency** — mean hours from `detected_at` to the first accountable human action (HITL review or resolution).
- **HITL Compliance** — percentage of signals that required a human checkpoint and actually received one.
- **Audit Quality** — percentage of closed decisions that carry a logged rationale (human or AI).

**Why:** The deck's closing line on slide 4 is "success is not model accuracy alone; it is trusted, traceable decision flow." These are the measures of trust and traceability. They are computed from stored timestamps and fields, not entered by hand, so they cannot drift from reality.

### 3.4 Metering and logging

**What:** Every LLM call writes a row to a new `AICallLog` table: model, input tokens, output tokens, latency, whether the fallback was used, and any error. The **Controls** page shows the recent call log and cumulative token totals.

**Why:** Slide 2 claims "token use and cost stay forecastable." That claim is only credible if the numbers are visible. Showing them also demonstrates the "Metered" and "Logged" principles literally rather than describing them.

### 3.5 Controls page — risk → control → implementation

**What:** A page that lists the four risks from slide 4 alongside the control the deck proposes *and* the specific mechanism in the app that enforces it (e.g., hallucination → bounded context + registry guard; authority drift → forced HITL on critical domains).

**Why:** Evaluators will ask whether the controls are real. This page answers that in one screen and ties the implementation back to NIST AI RMF language (transparency, accountability, human oversight) that the deck cites.

### 3.6 90-Day Pilot tracker

**What:** A page with the four phases from slide 5 — Crawl (map authority), Walk (route signals), Run (measure), Scale (decide) — each with its milestones as toggleable checkboxes. The current phase is highlighted. Below the phases, the Run-phase evidence (latency, coverage, overrides, trust) is pulled live from the metrics engine.

**Why:** The pilot path is the deck's answer to "how would an organization actually start." Making it a working artifact turns a roadmap slide into something a sponsor could use on day one, and the live evidence panel shows that the system can measure its own pilot.

### 3.7 Dashboard reorganization

**What:** The dashboard now opens with the three layers (Data / AI / Human), each summarising its live state, followed by the four success metrics, then the operational detail that existed in V2.

**Why:** Slide 1 is the mental model the audience will carry. The product should look like the slide.

### 3.8 Backward-compatible schema upgrade

**What:** On startup the app compares its models to the existing database and adds any missing columns, then backfills defaults on pre-V3 rows.

**Why:** The team already has V2 deployed on Railway with data in it. Redeploying V3 must not require dropping the database.

---

## 4. What was deliberately not done

- **No autonomous action.** The model never changes a role's status, resolves a signal, or edits an escalation path. It only proposes.
- **No AI on registry or domain edits.** Authority definitions remain a purely human activity; the AI layer reads the registry, it does not write it.
- **No prompt "learning" automation.** The LEARN step is a human review of override history, not an automatic prompt rewrite. Automating it would undercut the accountability story before the pilot has evidence.
- **No external data connectors.** The Data Layer on slide 1 mentions org charts, decision history, and workforce signals. V3 uses the data already in the system. Connecting HR or ticketing systems is a Scale-phase item, not a pilot item.

---

## 5. How to demonstrate it

1. **Dashboard** — point to the three layers and the four metrics.
2. **Signals** — click **AI Evaluate** on the "Decision stall: Product Roadmap" signal. Show the rationale, confidence, and that it was sent to HITL because the domain is high-risk.
3. **HITL Review** — override it (route to a different role, type a rationale). Show the override appears in history and Audit Quality stays at 100%.
4. **Controls** — show the call log with token counts, and the risk → control mapping.
5. **Pilot** — tick a Walk-phase milestone; point to the live Run-phase evidence.
6. **Audit** — every step above is there with a timestamp and a user.

Set `ANTHROPIC_API_KEY` in Railway before the presentation to run the live model. If it is unset, the same flow runs in fallback mode and every screen says so — which is itself a useful thing to show.

---

## 6. Suggested next steps for the team

- Agree on the two or three decision domains for the pilot (Crawl step 1) and prune the demo data to those.
- Decide who on the team plays "reviewer" during the demo so the HITL step is a human on stage, not a click.
- Add one slide to the deck with a screenshot of the HITL page — it is the clearest single image of "humans decide, AI supports."
