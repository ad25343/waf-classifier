# WAF Classifier — API Reference

Base URL: `http://localhost:8080`

All endpoints return JSON unless otherwise noted.

---

## System

### GET /api/status

Returns current system state.

**Response:**
```json
{
  "api_configured": true,
  "waf_loaded": true,
  "waf_categories": ["KTLO", "Business Maintenance", ...],
  "ground_truth_loaded": true,
  "ground_truth_count": 18,
  "history_count": 42
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
  "categories": ["KTLO", "Business Maintenance", ...],
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
  "categories": {"KTLO": 3, "Business Maintenance": 2, ...}
}
```

---

## Dashboard

### GET /api/dashboard/summary

Returns all dashboard data: KPIs, chart data, and recent classifications.

**Response:**
```json
{
  "total_classifications": 42,
  "approved_count": 15,
  "approval_rate": 35.7,
  "mismatch_count": 8,
  "ground_truth_count": 33,
  "category_distribution": {"KTLO": 12, "Business Maintenance": 8, ...},
  "confidence_distribution": {"High": 25, "Medium": 12, "Low": 5},
  "run_change": {"Run": 22, "Change": 20},
  "color_distribution": {"GRAY": 12, "BLACK": 8, ...},
  "daily_activity": [{"date": "2026-03-01", "count": 5}, ...],
  "recent": [{"id": 42, "story_title": "...", "category": "KTLO", ...}]
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
      "categories": {"KTLO": 5, ...},
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
      "categories": {"KTLO": 10, ...},
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
| `per_page` | int | Results per page (default: 50) |
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

---

## Bulk Verify

### POST /api/bulk-verify

Upload a file and AI-classify every story for side-by-side comparison.

**Request:** `multipart/form-data` with `file` field (CSV or XLSX)

Stories are classified in batches of 10 for efficiency.

**Response:**
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
  "saved": 15
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

### GET /api/epics/summary?epic=Platform+Reliability

Get detailed data for a specific epic including tree structure.

**Response:**
```json
{
  "epic": "Platform Reliability",
  "total": 12,
  "approved": 8,
  "mismatches": 2,
  "categories": {"KTLO": 6, "Technical Maintenance": 4, ...},
  "run_change": {"Run": 10, "Change": 2},
  "features": {
    "Database Health": [
      {"id": 1, "story_title": "...", "category": "KTLO", "color": "GRAY", ...}
    ],
    "API Gateway": [...]
  }
}
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
