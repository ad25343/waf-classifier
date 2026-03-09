# WAF Classifier — API Reference

Base URL: `http://localhost:8080`

All endpoints return JSON unless otherwise noted. Error responses always return a generic message — full details are logged server-side only.

---

## Error Responses

All endpoints follow this error format:

```json
{ "error": "Human-readable message" }
```

| HTTP Code | Meaning |
|-----------|---------|
| 400 | Bad request (missing file, invalid format) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## System

### GET /api/status

Returns current system state.

**Response:**
```json
{
  "api_configured": true,
  "waf_loaded": true,
  "waf_categories": ["KTLO", "Business Maintenance", "..."],
  "ground_truth_loaded": true,
  "ground_truth_count": 18,
  "history_count": 42
}
```

### GET /api/waf-definitions

Returns structured WAF framework definitions for the reference page.

**Response:**
```json
{
  "loaded": true,
  "definitions": [
    {
      "run_change": "Run",
      "color": "GRAY",
      "category": "KTLO (Keep the Lights On)",
      "description": "Non-discretionary, recurring work...",
      "decision_rule": "Required to meet SLAs, legal...",
      "examples": "Emergency break-fix; Prod outages; ..."
    }
  ]
}
```

---

## Classification

### POST /api/classify

Classify a single story via chat.

**Request:**
```json
{
  "message": "Classify: Fix production DB connection pool exhaustion causing 504 errors",
  "session_id": "optional-session-id",
  "epic": "Platform Reliability",
  "parent_feature": "Database Health"
}
```

**Response:**
```json
{
  "response": "Based on the description...",
  "classification": {
    "category": "KTLO",
    "sub_category": "Production Support",
    "color": "GRAY",
    "confidence": "High",
    "reasoning": "This is operational work...",
    "is_mismatch": false
  },
  "session_id": "abc123",
  "classification_id": 42
}
```

### POST /api/batch-classify

Classify multiple stories at once.

**Request:**
```json
{
  "stories": "Story 1 | Description 1 | Current Tag\nStory 2 | Description 2 | Current Tag"
}
```

**Response:**
```json
{
  "response": "Batch classification results...",
  "classifications": [...]
}
```

### POST /api/approve/{classification_id}

Approve a classification as ground truth.

**Response:**
```json
{
  "success": true,
  "message": "Classification approved and added to ground truth"
}
```

---

## Data Upload

### POST /api/upload-waf

Upload WAF definitions file.

**Request:** `multipart/form-data` with `file` field (CSV, XLSX, JSON, or TXT)

**Response:**
```json
{
  "success": true,
  "categories": ["KTLO", "Business Maintenance", "..."],
  "count": 8
}
```

### POST /api/upload-ground-truth

Upload ground truth examples.

**Request:** `multipart/form-data` with `file` field (CSV or XLSX)

**Response:**
```json
{
  "success": true,
  "count": 18,
  "categories": {"KTLO": 3, "Business Maintenance": 2}
}
```

---

## Dashboard

### GET /api/dashboard/summary

Returns all dashboard data: KPIs, chart data, and recent classifications.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | Optional. Filter to a specific upload batch. Omit for all data. |

**Response:**
```json
{
  "total_classifications": 42,
  "approved_count": 15,
  "approval_rate": 35.7,
  "mismatch_count": 8,
  "ground_truth_count": 33,
  "category_distribution": {"KTLO": 12, "Business Maintenance": 8},
  "confidence_distribution": {"High": 25, "Medium": 12, "Low": 5},
  "run_change": {"Run": 22, "Change": 20},
  "color_distribution": {"GRAY": 12, "BLACK": 8},
  "daily_activity": [{"date": "2026-03-01", "count": 5}],
  "recent": [{"id": 42, "story_title": "...", "category": "KTLO"}]
}
```

### GET /api/dashboard/stories

Paginated, filterable drill-down of individual story records. Used by clickable KPI cards in the Summary tab.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `filter` | string | One of: `mismatches`, `approved`, `category`, `color`, `confidence`, `run_change` |
| `value` | string | Value to filter on (e.g. `KTLO`, `High`, `Run`) |
| `upload_id` | int | Optional. Restrict to a specific upload batch. |
| `page` | int | Page number (default: 1) |
| `per_page` | int | Results per page (default: 100, max: 500) |

**Response:**
```json
{
  "stories": [
    {
      "id": 42,
      "story_title": "Fix connection pool",
      "waf_category": "KTLO",
      "waf_color": "GRAY",
      "run_change": "Run",
      "confidence": "High",
      "was_mismatch": true,
      "approved": false,
      "original_tag": "New Feature",
      "epic": "Platform Reliability",
      "timestamp": "2026-03-01T10:00:00"
    }
  ],
  "total": 42,
  "page": 1,
  "per_page": 100,
  "total_pages": 1
}
```

---

## Historical Analytics

### GET /api/history/sprints

Returns classification data organized into 2-week sprint windows.

**Response:**
```json
{
  "sprints": [
    {
      "label": "Sprint 1 (Feb 17 - Mar 2)",
      "start": "2026-02-17",
      "end": "2026-03-02",
      "total": 15,
      "mismatches": 3,
      "approved": 8,
      "categories": {"KTLO": 5},
      "run_change": {"Run": 8, "Change": 7}
    }
  ]
}
```

### GET /api/history/monthly

Returns monthly rollup with period-over-period comparison.

**Response:**
```json
{
  "months": [
    {
      "month": "2026-03",
      "label": "March 2026",
      "total": 30,
      "mismatches": 5,
      "approved": 18,
      "categories": {"KTLO": 10},
      "prev_total": 12,
      "prev_mismatches": 4
    }
  ]
}
```

### GET /api/history/timeline

Paginated, filterable timeline of all classifications.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `page` | int | Page number (default: 1) |
| `per_page` | int | Results per page (default: 50, max: 500) |
| `from_date` | string | Start date (YYYY-MM-DD) |
| `to_date` | string | End date (YYYY-MM-DD) |
| `category` | string | Filter by WAF category |
| `color` | string | Filter by WAF color |
| `team` | string | Filter by team |
| `confidence` | string | Filter by confidence level |
| `mismatch_only` | bool | Only show mismatches |

**Response:**
```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "per_page": 50,
  "pages": 1
}
```

### POST /api/history/import

Import classifications from CSV or Excel file.

**Request:** `multipart/form-data` with `file` field

**Response:**
```json
{
  "success": true,
  "imported": 25
}
```

### GET /api/history/export

Export all classifications as CSV.

**Response:** CSV file download

### GET /api/history/export-xlsx

Export formatted Excel workbook with 3 sheets: Summary, Monthly Rollups, Raw Data.

**Response:** XLSX file download with conditional formatting (green = approved, red = mismatch)

### GET /api/history/uploads

List all previous upload batches.

**Response:**
```json
{
  "uploads": [
    {
      "id": 1,
      "filename": "sprint-backlog.csv",
      "row_count": 120,
      "imported_count": 120,
      "uploaded_at": "2026-03-01T10:00:00"
    }
  ]
}
```

### POST /api/history/uploads/{upload_id}/reload

Reload a previous upload batch into the verify/review view.

**Response:**
```json
{
  "success": true,
  "results": [...],
  "filename": "sprint-backlog.csv",
  "total": 120
}
```

---

## Bulk Verify

### POST /api/bulk-verify

Upload a file and AI-classify every story. Small files (≤200 stories) return results synchronously. Large files (>200 stories) return a job ID for async polling.

**Request:** `multipart/form-data` with `file` field (CSV or XLSX)

**Rate limit:** 5 requests per IP address per minute. Exceeding this returns HTTP 429.

Stories are classified in batches of 50 using 5 concurrent threads.

**Response (synchronous, ≤200 stories):**
```json
{
  "results": [
    {
      "row": 0,
      "story_title": "Fix connection pool",
      "description": "...",
      "original_tag": "New Feature",
      "ai_category": "KTLO",
      "ai_sub_category": "Production Support",
      "ai_color": "GRAY",
      "ai_confidence": "High",
      "is_mismatch": true,
      "epic": "Platform Reliability",
      "parent_feature": "Database Health"
    }
  ],
  "total": 25
}
```

**Response (async, >200 stories):**
```json
{
  "async": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_stories": 5000,
  "message": "Processing started"
}
```

### GET /api/bulk-verify/status/{job_id}

Poll the status of an async bulk-verify job.

**Response (in progress):**
```json
{
  "status": "running",
  "stories_processed": 1250,
  "total_stories": 5000,
  "batches_done": 25,
  "total_batches": 100,
  "pct": 25
}
```

**Response (complete):**
```json
{
  "status": "done",
  "results": [...],
  "total": 5000
}
```

**Response (failed):**
```json
{
  "status": "error",
  "error": "Verification failed. Please try again."
}
```

### POST /api/bulk-verify/save

Save selected verified classifications to the database.

**Request:**
```json
{
  "rows": [
    {
      "story_title": "Fix connection pool",
      "description": "...",
      "category": "KTLO",
      "sub_category": "Production Support",
      "color": "GRAY",
      "confidence": "High",
      "is_mismatch": true,
      "epic": "Platform Reliability",
      "parent_feature": "Database Health"
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "saved": 15,
  "upload_id": 3
}
```

---

## Epic Lineage

### GET /api/epics

List all epics with story counts.

**Response:**
```json
{
  "epics": [
    {"epic": "Platform Reliability", "count": 12},
    {"epic": "Customer Onboarding", "count": 8}
  ]
}
```

### GET /api/epics/summary

Get detailed data for all epics including health scores, mismatch counts, and story tree.

**Query Parameters:**
| Param | Type | Description |
|-------|------|-------------|
| `upload_id` | int | Optional. Filter to a specific upload batch. |

**Response:**
```json
[
  {
    "epic": "Platform Reliability",
    "total_stories": 12,
    "approved": 8,
    "mismatches": 2,
    "health_score": 82,
    "dominant_color": "GRAY",
    "colors": {"GRAY": 8, "BLACK": 4},
    "categories": {"KTLO": 6, "Technical Maintenance": 4},
    "run_change": {"Run": 10, "Change": 2},
    "features": [
      {
        "name": "Database Health",
        "stories": [
          {
            "id": 1,
            "title": "Fix connection pool",
            "category": "KTLO",
            "color": "GRAY",
            "confidence": "High",
            "mismatch": true,
            "original_tag": "New Feature",
            "run_change": "Run"
          }
        ]
      }
    ]
  }
]
```

### POST /api/epics/assign

Bulk assign epic and parent feature to classification IDs.

**Request:**
```json
{
  "ids": [1, 2, 3],
  "epic": "Platform Reliability",
  "parent_feature": "Database Health"
}
```

**Response:**
```json
{
  "success": true,
  "updated": 3
}
```

### GET /api/epics/autocomplete?q=plat

Get autocomplete suggestions for epic and feature names.

**Response:**
```json
{
  "epics": ["Platform Reliability", "Platform Migration"],
  "features": ["Platform Security", "Platform Monitoring"]
}
```
