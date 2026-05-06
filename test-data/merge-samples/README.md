# Merge Sample Data

Three test fixture sets for exercising the File Merger and the upload paths. Each set ships in its own subdirectory with **four files**:

```
{set-name}/
├── epics.csv         (or epic-shaped file)
├── features.csv      (or feature-shaped file)
├── stories.csv       (or story-shaped file)
└── consolidated.csv  ← single-file equivalent (Story → Feature → Epic flattened by name-based join)
```

Use the three E/F/S files for the **3-file Merge flow** (`/merge`); use `consolidated.csv` for the **single-file upload path** (`/history`).

## The three sets

### `jira-realistic/` — multi-LoB, complete columns, with seeded edge cases

Realistic Jira-export shape with the columns you'll actually see in production:

| Field | Epic | Feature | Story |
|---|---|---|---|
| ID, Name (Summary) | ✅ | ✅ | ✅ |
| Description | ✅ | ✅ | ✅ |
| WAF Category, WAF Color, Run/Change | ✅ | ✅ (Color via Feature) | derived |
| Block, Sponsor, Status, ATP Link, Assignee | ✅ | partial | partial |
| Team of Teams, Team | — | ✅ | ✅ |
| Story Points, Resolved Date | — | — | ✅ |

Contains:
- **9 epics** spanning Compliance, Privacy, Cloud, Observability, API platform — covers all canonical WAF categories plus four **alias-test wrenches** (`Audit & Compliance`, `Lift and Shift`, `BAU Maintenance`, `Innovation Bet`) that deliberately use non-canonical names so the alias system has to map them.
- **15 features** including 1 orphan (points to an Epic Name not in the file).
- **31 stories** including 2 orphans (no feature, or non-existent feature) and 5 stories under the alias-wrench features.

Use this set to exercise the full pipeline end-to-end: column mapping, name-based join, orphan flagging, missing-WAF / missing-R/C surfacing, alias resolution, and AI classification.

### `clean-simple/` — happy path with a simpler 5-column schema

Smaller-schema fixture (`Epic Id`, `Epic Name`, `Epic Desc`, `Block`, `WAF`) with WAF Color encoded inline as `COLOR - Category`. Everything joins cleanly — no orphans, no edge cases.

Counts: 20 epics, 31 features, 76 stories.

Use this set when you want to verify the merge engine itself is working end-to-end on tidy data without fighting realistic noise.

### `edge-cases-simple/` — same simple schema, with intentional issues

Same shape as `clean-simple/` but seeded with the bug-class scenarios the merge feature has to handle: orphan stories, orphan features, non-canonical WAF colors that need alias mapping, malformed rows.

Counts: 4 epics, 8 features, 18 stories.

Use this set when you want to verify orphan handling, the Missing-WAF / Missing-R/C UI, and how the alias system reacts to garbage input.

## Quick reference — which file maps to which app path

| You want to test… | Use these files |
|---|---|
| 3-file Merge (`/merge`) | `{set}/epics.csv` + `{set}/features.csv` + `{set}/stories.csv` |
| Single-file Upload (`/history`) | `{set}/consolidated.csv` |
| Alias system | `jira-realistic/` (has 4 alias wrenches) |
| Orphan handling | `jira-realistic/` or `edge-cases-simple/` |
| Domain Editor + Story Quality | any `consolidated.csv` (then go to `/history` → Story Quality) |
