# WAF Classifier — Changes (April 25, 2026)

---

## Summary of Changes

### Exports
- Excel (.xlsx) + PDF export added to: Review AI Classifications, Drilldown table,
  All Stories, Epic Lineage, Teams story panel, Disputes page
- `per_page=all` added to the history API so All Stories export fetches every
  record, not just the current page

### Charts
- Replaced the two separate "AI Suggested" / "User Submitted" bar charts with a
  single **divergence chart** — shows the delta (AI count − User count) per
  category so the gap is the focus, not raw numbers
- Added the same divergence chart to the **Epic Lineage detail view**

### Portfolio Narrative (Analyze Stories → Summary tab)
- Auto-generated template narrative loads on every Summary tab open
- Optional **✨ AI Narrative** button sends stats to Claude and returns a
  3–4 sentence executive summary

### Teams Page
- Now shows all stories on load — no empty state waiting for a click
- Team pills act as **client-side filters** (all team detail data is pre-fetched
  in parallel on load; no API call per pill click)
- Added **Epic column** to the story table in both All Teams and Single Team modes
- Fixed sort bug (Status column was silently broken; column index was wrong when
  Team column was visible)

### Enterprise Config (all opt-in via .env — zero impact on existing deployments)
- **PortKey AI gateway** support (`AI_GATEWAY=portkey`)
- **Apigee gateway** support (`AI_GATEWAY=apigee`) with OAuth2 client-credentials
  token auto-refresh
- **OIDC / SSO** support (`AUTH_MODE=oidc`) — works with Okta, Azure AD, Ping
  Identity, Keycloak, Google Workspace, or any OIDC-compliant IdP
- Existing direct Anthropic and Bedrock paths completely unchanged
- `.env.example` updated with full documentation for all options

### Housekeeping
- Default baseline CSVs committed (`baselines/gt/`, `baselines/waf/`)
- `waf_classifier.db` added to `.gitignore`

---

## Commits (oldest → newest)

| Hash | Message |
|------|---------|
| `59f14f7` | Add Excel/PDF export + rename Feature Name across test data and UI |
| `d55eff6` | Add Export button to All Stories table in Summary tab |
| `fa4ad11` | Grouped WAF distribution chart + Disputes export |
| `cd2332f` | Add portfolio narrative to Analyze Stories — Summary tab |
| `170e627` | Replace grouped bar with divergence chart for WAF comparison |
| `f50788d` | Add divergence chart to Epic Lineage detail view |
| `3997f73` | Teams page: add Epic column, fix sort, default to All Teams view |
| `595cfb6` | Add default baseline CSVs and ignore waf_classifier.db |
| `a7db544` | feat: enterprise SSO + AI gateway support (PortKey, Apigee, OIDC) |

---

## Files Touched (30 total)

### Backend
| File | What changed |
|------|-------------|
| `app.py` | Wire `init_sso(app)` after Flask init |
| `auth.py` | **New** — OIDC/SSO middleware (login, callback, logout, before_request guard) |
| `config.py` | Add `AI_GATEWAY`, `PORTKEY_*`, `APIGEE_*`, `AUTH_MODE` config blocks |
| `waf_core.py` | `get_client()` extended with PortKey and Apigee routing; token cache for Apigee |
| `routes/analytics.py` | `per_page=all` support; `/api/narrative` POST endpoint |
| `routes/merge.py` | Minor — Feature Name rename |
| `routes/verify.py` | Minor — Feature Name rename |

### Frontend
| File | What changed |
|------|-------------|
| `static/history.html` | Divergence chart; Excel/PDF export (verify, drilldown, all stories); portfolio narrative card; AI Narrative button |
| `static/lineage.html` | Divergence chart on epic detail; Excel/PDF export |
| `static/teams.html` | All-teams default view; client-side pill filtering; Epic column; sort fix; Excel/PDF export |
| `static/disputes.html` | Excel/PDF export |
| `static/dashboard.html` | Feature Name rename |
| `static/home.html` | Feature Name rename |
| `static/index.html` | Feature Name rename |
| `static/merge.html` | Feature Name rename |
| `static/settings.html` | Feature Name rename |
| `static/waf-reference.html` | Feature Name rename |

### Config / Env
| File | What changed |
|------|-------------|
| `.env.example` | Full reference for all 4 AI backend options + OIDC SSO |
| `.gitignore` | Add `waf_classifier.db` |

### Test Data (Feature Name column rename + CSV updates)
| File | What changed |
|------|-------------|
| `test-data/compliance-focus-60.csv` | "Parent Feature" → "Feature Name" |
| `test-data/generate_test_data.py` | "Parent Feature" → "Feature Name" |
| `test-data/ground-truth-maintenance.csv` | "Parent Feature" → "Feature Name" |
| `test-data/merge-samples/sample-story-attributes.csv` | "Parent Feature" → "Feature Name" |
| `test-data/multi-team-product-120.csv` | "Parent Feature" → "Feature Name" |
| `test-data/platform-engineering-80.csv` | "Parent Feature" → "Feature Name" |
| `test-data/synthetic-100-stories.csv` | "Parent Feature" → "Feature Name" |
| `test-data/synthetic-5000-stories.csv` | "Parent Feature" → "Feature Name" |
| `test-data/trend-analysis-480.csv` | "Parent Feature" → "Feature Name" |

### New Files Committed
| File | What it is |
|------|-----------|
| `auth.py` | OIDC SSO middleware |
| `baselines/gt/gt_Default_Baseline.csv` | Default ground-truth baseline |
| `baselines/waf/waf_Default_Baseline.csv` | Default WAF definitions baseline |
