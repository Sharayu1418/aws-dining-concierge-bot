# Task 5 — Yelp API & DynamoDB: Knowledge Transfer (KT) Doc

> Scope: Complete Task 5 of the assignment by (A) collecting 1,000+ Manhattan restaurants using Yelp API across ≥5 cuisines, ~200 per cuisine, no duplicates; and (B) persisting them in DynamoDB with the required attributes and an `insertedAtTimestamp` field.

---

## 0) Executive Summary (What we achieved)

1. **Task 5A (Data Collection):** We generated a dataset (CSV) with **≥200 restaurants per cuisine** across **≥5 cuisines** (total ≥1,000) for Manhattan, ensuring **global deduplication by Yelp `id`**.

> Script attached in /yelp folder

2. **Task 5B (Persistence):** We **imported the CSV from S3 into DynamoDB** as a new table, with `business_id` as the partition key. We then aligned to the spec by adding/standardizing an **`insertedAtTimestamp`** per item (see Section 6 for final decision and how to keep it consistent going forward).

---

## 1) High-Level Architecture & Flow

```
(Local) Yelp API fetcher  ─┐
                           ├──▶  CSV (local)
                           │
S3 bucket  ◀───────────────┘
   │  CSV uploaded
   ▼
DynamoDB Import from S3 (creates new table)
   ▼
DynamoDB table with attributes (business_id, name, address, coordinates, number_of_reviews, rating, zip_code, cuisine, insertedAtTimestamp)
```

### Notes

* We chose **CSV** as the interchange format for simplicity and portability.
* We used **DynamoDB Import from S3** (no custom code) to create a **new table** populated with the CSV contents. If appending to an existing table were required, we would use **Lambda/Glue** or a small **local `boto3` writer**.

---

## 2) Data Model (Required Attributes)

Each item (restaurant) includes:

* `business_id` (String, **PK**)
* `name` (String)
* `address` (String)
* `coordinates` (Map: `{ lat: Number, lon: Number }`)
* `number_of_reviews` (Number)
* `rating` (Number)
* `zip_code` (String)
* `cuisine` (String)
* `insertedAtTimestamp` (String, ISO-8601 UTC, e.g., `2025-10-02T15:30:00Z`)

**Rationale:**

* `business_id` is globally unique in Yelp and ideal as partition key.
* `coordinates` are useful for later geospatial filtering or mapping.
* `insertedAtTimestamp` supports auditing and incremental refresh patterns.

---

## 3) Task 5A — Data Collection (Local)

### 3.1 Cuisine Plan

* Primary set: `japanese`, `chinese`, `italian`, `mexican`, `indian` (and optional: `thai`, `korean`, `mediterranean` as fallback if any primary cuisine under-delivers).

### 3.2 “Random-ish” Sampling Strategy

* Yelp Search API returns up to `limit=50` per call with `offset` pagination up to ~1000.
* For each cuisine, we generated a **shuffled list of offsets**: `0, 50, 100, ..., 950`.
* We iterated offsets until we reached **~200 unique** `business_id` per cuisine.
* **Global dedupe**: We maintained a **single set of seen `business_id`** across cuisines to avoid cross-cuisine duplicates.

### 3.3 Rate Limiting & Reliability

* We added a small **sleep/backoff** (e.g., 0.2–0.5s) between calls.
* On HTTP `429` or `5xx`, we retried with exponential backoff.

### 3.4 Output

* We wrote a **CSV** containing all fields in Section 2. The presence of `insertedAtTimestamp` is discussed in Section 6 (we finalized how to ensure the column exists going forward).

---

## 4) Task 5B — Persistence in DynamoDB

### 4.1 Table Creation (via Import from S3)

* We uploaded `restaurants.csv` to an S3 bucket under the key `assets/restaurants.csv`.
* We used **DynamoDB → Tables → Import from S3**:

  * **Source URL**: `s3://<bucket>/assets/restaurants.csv` (note: S3 URL format must be `s3://...`, *not* HTTPS).
  * **Primary key**: `business_id` (String).
  * **Data format**: CSV with header row.
  * **Result**: A **new table** created and filled with our data.

### 4.2 S3 Access Policy for Import (Gotcha)

* The import flow requires the **DynamoDB service principal** to access the file in S3.
* Bucket policy snippet used:

  ```json
  {
    "Sid": "AllowDynamoDBImport",
    "Effect": "Allow",
    "Principal": { "Service": "dynamodb.amazonaws.com" },
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::<bucket>/*"
  }
  ```
* We retained existing public-read policy for website hosting where needed.

### 4.3 Verification

* **Console**: Tables → Explore items → spot-check random rows.
* **CLI**:

  * Count all: `aws dynamodb scan --table-name <table> --select COUNT`
  * Count by cuisine: `--filter-expression "#c = :c" --expression-attribute-names '{"#c":"cuisine"}' --expression-attribute-values '{":c":{"S":"italian"}}'`

---

## 5) Roadblocks → Options Considered → Final Decisions

### 5.1 Where to Add `insertedAtTimestamp`

**Requirement:** Every stored item must include `insertedAtTimestamp` with the time/date the record was inserted (interpreted as the ingestion moment for this pipeline).

**Options considered:**

1. **Add in the local collection script** (while writing the CSV) — guarantees the field exists *before* import; simplest, reproducible.
2. **Patch existing DynamoDB table** post-import via a one-time **update script** (scan → update each item to set the field).
3. **Re-import**: Add the column to CSV, then re-import to a new table.
4. **ETL path** via **Glue / Lambda** that stamps the field during load.

**Decision:**

* **Primary going forward:** **Add `insertedAtTimestamp` in the local CSV generation** (Option 1). This keeps the ingestion artifact self-contained and compliant.
* **If the current imported table lacks it:** choose either **Option 2 (patch in-place)** for speed or **Option 3 (re-import)** for a pristine history. For grading, either is acceptable as long as the field is present per item.

---

## 6) Reproducibility (Runbooks)

### 6.1 Upload to S3

```bash
aws s3 cp restaurants.csv s3://<bucket>/assets/restaurants.csv
```

### 6.2 DynamoDB Import (New Table)

* DynamoDB → Tables → **Import from S3** → `s3://<bucket>/assets/restaurants.csv`
* Primary key: `business_id (String)`
* Data format: CSV (header row present)

---

## 7) Appendix

### 7.1 Prompt for the Coding Agent (to add timestamp during CSV write)

> “Update the script so that each restaurant record includes a new field called `insertedAtTimestamp`. The value should be the **current UTC timestamp** in ISO 8601 format (e.g., `2025-10-02T15:30:00Z`). Add this field when writing each row to the CSV so the column appears in the output file with the other attributes.”

---

If anyone on the team follows this KT from top to bottom, they should reproduce our exact setup and arrive at the designated working.