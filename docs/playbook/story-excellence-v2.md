PLAYBOOK · v2

Story Excellence

Epic → Feature → Story

A shared language for Single Family, Multifamily, and Capital Markets — across the full lending lifecycle.

Audience: Product, Engineering, Analytics, QA

Living document — refined every quarter


# 1. Our North Star

One playbook the whole portfolio can rally around — so that any teammate, on any squad, in any line of business, can pick up a backlog item and immediately see what good looks like.

### Three pillars

- Clarity at every level. Epic, Feature, and Story each have their own template, Definition of Ready, and Definition of Done. No more guessing what is expected.

- Lifecycle-wide. The same playbook from loan acquisition through underwriting, servicing, securitization, and investor reporting — end to end.

- Cross-LoB. Single Family, Multifamily, and Capital Markets all use the same shape. Only the business rules and lifecycle stages differ.

This isn't about more rules. It's about removing friction so the team can move faster, together.

# 2. The Three Levels at a Glance

Epic, Feature, and Story share the same shape: each has a template, a Definition of Ready, and a Definition of Done. The difference is scope and horizon.

|  | Epic | Feature | Story |
|---|---|---|---|
| Purpose | Strategic outcome we are willing to fund | Deliverable capability inside an epic | Sprint-sized unit of valuable work |
| Horizon | 1 – 4 quarters | 1 – 3 sprints | Within a single sprint |
| Owner | Business Sponsor + Product | Product Owner | Squad (PO, Devs, Analyst, QA) |
| Sign-off | Portfolio review board | PO + business validation in production | PO + QA at sprint demo |
| Done means | Outcome measured against baseline | Capability live, validated, documented | Acceptance criteria met, deployed |

Each level builds on the one above it. A story is only as clear as the feature it serves; a feature is only as valuable as the epic it advances.

# 3. Lifecycle Coverage

Our lending lifecycle has ten stages. Every epic, feature, and story tags the stages it touches and the lines of business it serves. This makes it easy to answer questions like: “What work is in flight in Servicing right now? Who owns it? What is downstream of this story in CapMkts?”

### Lifecycle stages

- Acquisition — Lender delivery, loan registration, file completeness.

- Underwriting — Eligibility, credit decisioning, documentation review.

- Pricing & Commitments — Pricing, lender commitments, lock management.

- Loan Boarding — Servicing transfer, system of record setup.

- Servicing — Payments, escrow, customer service, statements, modifications.

- Default Mgmt & Loss Mit — Delinquency, workout, foreclosure, REO, claims.

- Securitization & Pooling — Pool formation, allocation, WAC, settlement.

- Investor Reporting — Tape generation, remittance, factor publication.

- Capital Markets Ops — Trading, hedging, debt issuance, portfolio management.

- Risk & Compliance — Risk reporting, regulatory submissions, internal audit.

### Heatmap of activity by line of business

|  | Acq | UW | Price | Board | Svc | Default | Sec | Inv Rpt | CM Ops | Risk |
|---|---|---|---|---|---|---|---|---|---|---|
| Single Family | H | H | H | H | H | H | H | H | M | H |
| Multifamily | H | H | H | H | H | M | M | H | M | H |
| Capital Markets | L | L | M | L | M | L | H | H | H | H |

H = high activity / focus area · M = moderate · L = light

### Why a unified shape matters

Most of our highest-value work crosses two or more lifecycle stages and at least one LoB boundary. A common epic-feature-story shape lets a story written in Servicing flow naturally into Investor Reporting without translation overhead — and lets a CapMkts feature reuse SF and MF data products without re-specifying them.


# 4. Industry Practices We Lean On

We're not reinventing the wheel. The playbook borrows directly from SAFe, Scrum, Mike Cohn's user-story canon, and BDD. These are well-documented practices — easy to onboard new team members and easy to defend in any portfolio or audit conversation.

## 4.1 Epic-level practices

- Lean Business Case (SAFe). A short, structured framing of the epic: hypothesis, leading indicators, MVP outcome, and NFRs. Replaces the 30-page PRD with one page that the portfolio actually reads.

- Hypothesis statement. “We believe [outcome] will result from [change], evidenced by [metric].” Forces the team to commit to a measurable belief, not an output.

- WSJF prioritization (SAFe). Weighted Shortest Job First — cost of delay divided by job size. Keeps the portfolio honest about what to fund first.

- Quarterly Planning Increment cadence. Epics are reviewed, re-cut, or retired every quarter at a big-room planning event. No epic outlives its usefulness.

## 4.2 Feature-level practices

- Benefit Hypothesis (SAFe). “By [doing X] for [persona] we will achieve [measurable outcome] by [date].” Pairs the capability with the value commitment.

- Minimum Marketable Feature (MMF). Smallest version that delivers real value to a user — ship it, learn, iterate. Stops feature gold-plating.

- Gherkin acceptance criteria. Given / When / Then format. Testable by construction; integrates cleanly with BDD frameworks for automated conformance testing.

- Feature flags / toggles. Decouple deploy from release. Safer rollouts, easy rollbacks, A/B-style validation when warranted.

## 4.3 Story-level practices

- INVEST criteria (Bill Wake / Mike Cohn). Independent · Negotiable · Valuable · Estimable · Small · Testable. The acid test for a sprint-ready story.

- 3 C's (Ron Jeffries). Card · Conversation · Confirmation. The story is a placeholder for a conversation — write enough to start it, not finish it.

- Connextra format. “As a [persona], I want [capability], so that [outcome].” Keeps the user and the why visible in every story.

- Vertical slicing. Each story delivers thin end-to-end value. Never a horizontal layer alone (e.g. “build the database table”) without the user-facing slice.

- Planning Poker with Fibonacci sizing (Mike Cohn). Relative estimation by the squad — not effort hours assigned by leads. Fast, surfaces hidden complexity.

- BDD (Behavior-Driven Development). Couples Gherkin ACs to automated tests. Acceptance criteria become living documentation.

These practices are listed because they have stood up across thousands of teams and decades of agile delivery. We adopt them as starting points — not religiously — and adapt where the GSE context requires.


# 5. Quality Checkpoints

Three moments to align — before the work begins. If a checkpoint is missed, the item simply waits for the next one. No drama. No blame. Refinement is the gift the team gives itself.

### Portfolio Review (EPIC level)

- Cadence: Quarterly

- Attendees: Business Sponsor, Head of Product, Finance, Risk

- We agree on:

○ Outcome measurable?

○ Funding agreed?

○ LoB and lifecycle stages clear?

○ Major risks named?

### Program Refinement (FEATURE level)

- Cadence: Bi-weekly

- Attendees: Product Owner, Tech Lead, Senior Analyst, QA Lead

- We agree on:

○ Capability stated in business language?

○ Persona named?

○ Acceptance criteria written?

○ Story map drafted?

### Three-Amigos (STORY level)

- Cadence: Weekly

- Attendees: PO, one Dev, one QA, Analyst

- We agree on:

○ Source data accessible?

○ Business rules unambiguous?

○ ACs binary and testable?

○ Traceability tag set?


# 6. Epic — Template, Ready, Done, Examples

## 6.1 Epic template

| Title | Outcome-led, not feature-led. “Same-Day Lender Commitments” not “AUS API Modernization.” |
|---|---|
| Strategic Outcome | The measurable change. What is true after, that wasn’t true before. |
| Lines of Business | Single Family · Multifamily · Capital Markets (any combination). |
| Lifecycle Stages | Which of the 10 lifecycle stages the epic touches. |
| Business Sponsor | Named accountable executive who funds and owns the outcome. |
| Success Metrics | 1–3 metrics with current baseline and target. Agreed with finance and risk. |
| Capacity Envelope | Approximate quarters of effort and number of squads expected to contribute. |
| Major Milestones | Quarter-level checkpoints we will measure against. |
| Cross-Team Dependencies | Other epics, programs, or vendors that must coordinate. |
| Risks & Mitigations | Top 3 risks named upfront — surfaced, not hidden. |

## 6.2 Epic Definition of Ready

- Strategic outcome stated as a measurable change.

- Business sponsor named and engaged.

- Lines of business and lifecycle stages identified.

- Success metrics agreed with finance and risk.

- Capacity envelope confirmed at portfolio review.

- Initial decomposition into features begun.

- Top 3 risks surfaced with named owners.

## 6.3 Epic Definition of Done

- Outcome metric measured against baseline.

- All features delivered or descoped with rationale.

- Business sponsor confirms value realized.

- Retrospective complete; learnings captured in the playbook.

- Run-state ownership transferred to operating team.

## 6.4 Epic examples — one per LoB

SINGLE FAMILY

Same-Day Lender Commitments for Conforming Loans

| Outcome | 80% of conforming SF loans receive a lender commitment same-day, up from 35% baseline. |
|---|---|
| Lifecycle Stages | Acquisition → Underwriting → Commitments |
| Sponsor | SVP, SF Acquisitions |
| Success Metrics | % same-day commits · Lender NPS · Manual review volume |

MULTIFAMILY

Unified MF Servicing Visibility Across Sub-Servicers

| Outcome | Single source of truth for MF loan performance refreshed within 24h of sub-servicer activity for 100% of the portfolio. |
|---|---|
| Lifecycle Stages | Servicing → Risk Reporting |
| Sponsor | VP, MF Asset Management |
| Success Metrics | Data freshness SLA · Sub-servicer onboarding cycle time · Exception rate |

CAPITAL MARKETS

T+0 Settlement for Specified MBS Pools

| Outcome | Enable T+0 settlement on 50% of specified pool trades, currently 0%. |
|---|---|
| Lifecycle Stages | Securitization → Investor Reporting |
| Sponsor | MD, Securitization |
| Success Metrics | % T+0 settlement · Settlement fail rate · Dealer satisfaction |


# 7. Feature — Template, Ready, Done, Examples

## 7.1 Feature template

| Title | Capability-led. “Real-Time AUS Decision API.” |
|---|---|
| Capability Statement | One sentence: “This feature enables [persona] to [do X] so that [outcome].” |
| Parent Epic | Linked. Features without an epic are flagged for portfolio review. |
| User / Persona | Lender ops · Asset manager · Trader · Investor · Internal analyst. |
| Acceptance Criteria | 3–5 feature-level ACs that prove the capability is real, not just code. |
| Story Map | High-level list of constituent stories. Proves the feature is decomposable. |
| Cross-Team Dependencies | Other squads, vendors, downstream consumers. |
| Non-Functionals | Performance, audit, compliance, observability requirements. |
| Out of Scope | What this feature explicitly does not do — prevents scope creep mid-flight. |

## 7.2 Feature Definition of Ready

- Capability articulated in business language.

- Linked to a parent epic with a clear contribution.

- Persona / user named.

- 3–5 acceptance criteria written and agreed.

- Decomposed into a story map (titles + sequence).

- Cross-team dependencies surfaced and confirmed.

- Non-functional requirements identified.

## 7.3 Feature Definition of Done

- All component stories closed.

- End-to-end test executed across the full path.

- Non-functionals validated (performance, security, compliance).

- Business validation signed off by Product Owner.

- Live in production environment.

- Documentation, runbook, and lineage updated.

## 7.4 Feature examples

SINGLE FAMILY

Epic: Same-Day Lender Commitments for Conforming Loans

Real-Time AUS Decision API for Lender Integration

Lender systems can submit a borrower file and receive an automated underwriting decision in under 200ms p95 — including credit tier, DTI flag, and condition list.

Feature-level acceptance criteria

- Returns full decision payload < 200ms p95.

- Supports 1,000 concurrent lender connections.

- Decision logic matches the published rule set 100%.

MULTIFAMILY

Epic: Unified MF Servicing Visibility Across Sub-Servicers

Standardized Sub-Servicer Daily Activity File Ingestion

All sub-servicers deliver daily activity in one schema, ingested into the MF data platform with 99.9% completeness within 4 hours of receipt.

Feature-level acceptance criteria

- Schema accepts all 7 active sub-servicers.

- 99.9% file-level completeness with auto-retry.

- Lineage visible end-to-end in the catalog.

CAPITAL MARKETS

Epic: T+0 Settlement for Specified MBS Pools

Same-Day Pool Allocation & WAC Calculation Engine

Operations can allocate eligible loans to a specified pool, compute weighted-average coupon, and lock the pool composition before market close on T+0.

Feature-level acceptance criteria

- Allocation completes < 5 min for pools up to 5,000 loans.

- WAC matches manual reconciliation within 0.005%.

- Audit trail for every allocation decision.


# 8. Story — Template, Ready, Done, Examples

## 8.1 Standard story template

| Title | Outcome-led, written by the analyst or PO. |
|---|---|
| As a / I need / So that | Persona, capability, business outcome. |
| Source Systems / Data | Upstream feeds, tables, APIs the story touches. |
| Business Rules | Explicit GSE definitions used (e.g. UPB, delinquency, WAC). |
| Acceptance Criteria | Binary, testable. “< 2% variance vs source” not “looks right.” |
| DoD Checklist | Reusable list — same for every story. |
| Test Approach | Unit, integration, data quality, performance — what runs and where. |
| Traceability Tag | Epic · Feature · Lifecycle stage · LoB. |

## 8.2 Spike variant

| Question | The one specific question the spike will answer. |
|---|---|
| Timebox | Fixed days. Hard stop, even if work is unfinished. |
| Required Output | Memo, notebook, or decision doc — not code in production. |
| Decision Informed | What downstream choice this enables. |
| LoB / Lifecycle Tag | So findings are reusable across the portfolio. |

## 8.3 Story Definition of Ready

- Template fully populated (no empty fields).

- Acceptance criteria are binary and testable.

- Source systems confirmed accessible by the squad.

- Business rules unambiguous and signed off by analyst.

- Linked to a parent feature.

- Three-amigos review complete (PO + Dev + QA).

- Sized — pointed by the squad, not assigned a number.

## 8.4 Story Definition of Done

- All acceptance criteria met and demonstrated.

- Code reviewed and merged; unit tests passing.

- Data quality checks passing where applicable.

- Non-functional checks passing (performance, security, audit).

- Business owner accepts in sprint demo.

- Documentation, lineage, and runbook updated.

- Deployed to the target environment.

## 8.5 Story examples

SF · ORIGINATION

Return AUS decision with credit tier and DTI flag in <200ms p95

As a Lender Operations user, I need an AUS decision returned synchronously so that I can issue a same-day commitment.

Acceptance criteria: p95 latency < 200ms · Credit tier returned in all 4 buckets · DTI flag returned where DTI > 43%.

MF · SERVICING

Ingest Wells Fargo MF daily remittance file with 99.9% completeness

As an MF Asset Manager, I need WF daily remittance reflected in the platform so that delinquency reporting is accurate within 24h.

Acceptance criteria: File parsed end-to-end · 99.9% record-level completeness · Mismatches routed to exception queue with alert.

CAPMKTS · SECURITIZATION

Calculate weighted-average coupon for same-day pool with mixed coupons

As a Securitization Operations user, I need WAC computed in real time on a draft pool so that I can validate before locking.

Acceptance criteria: WAC computed for pools up to 5,000 loans in <30 sec · Matches manual recon within 0.005% · Audit log per calculation.

SPIKE · CROSS-LOB

Investigate prepayment speed anomaly in Q1 2026 SF 30Y 5.5% pools

Question: Why did CPR diverge 18% from model on a specific cohort? Required output: memo plus notebook with hypotheses tested.

Acceptance criteria: Timebox: 1 sprint · Decision informed: whether to re-tune model or treat as transient.


# 9. Traceability — Epic → Feature → Story

Every story tags its parent feature and epic. Anyone reading a story can trace the strategic intent in two clicks. Below is one full example.

### Epic: T+0 Settlement for Specified MBS Pools

Feature: Same-Day Pool Allocation & WAC Calculation Engine

• Story: Calculate WAC for same-day pool with mixed coupons

• Story: Real-time UPB validation against source system at allocation

• Story: Settlement instruction generation API

Feature: T+0 Investor Reporting Pipeline

• Story: T+0 trade tape ingestion

• Story: Same-day investor remittance email generation


# 10. Team Commitments

What each role brings to the playbook. These are commitments, not job descriptions — they describe what each role is on the hook for so the system works.

| Business Sponsor | Names the outcome, funds the epic, and reviews progress at the portfolio level. Stays out of sprint mechanics. |
|---|---|
| Product Owner | Owns features end-to-end. Ensures stories meet Definition of Ready before sprint planning. Runs three-amigos. Accepts in demo. |
| Senior Analyst | Owns business-rule clarity and source-system accessibility. Writes acceptance criteria with the PO. Validates outputs against source. |
| Tech Lead | Owns architectural integrity across stories within a feature. Surfaces cross-feature dependencies early. |
| Squad (Devs + QA) | Collectively owns Definition of Done. Accepts ready stories with confidence; respectfully returns un-ready stories for refinement. |


# 11. Quick Reference

Pin this above your monitor. Same shape at every level — only the criteria differ.

| EPIC | FEATURE | STORY |
|---|---|---|
| READY | READY | READY |
| • Outcome measurable • Sponsor named • LoB + lifecycle clear • Metrics agreed • Capacity confirmed • Risks surfaced | • Capability stated • Linked to epic • Persona named • ACs agreed • Story map drafted • Dependencies surfaced | • Template complete • ACs binary + testable • Sources accessible • Rules unambiguous • Linked to feature • Three-amigos done |
| DONE | DONE | DONE |
| • Outcome measured • Features delivered • Sponsor confirms value • Retro complete • Run-state transferred | • Stories closed • E2E tested • Non-functionals met • PO signed off • Live in prod • Docs updated | • ACs met • Code reviewed • DQ checks pass • Demo accepted • Docs updated • Deployed |

Golden Rule: ready stories make happy sprints — and ready epics make happy quarters.

