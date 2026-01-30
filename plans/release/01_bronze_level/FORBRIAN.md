# FORBRIAN: Release 01 — Bronze Bootstrapping

## What This Release Actually Is

Think of this release as building the **foundation of a house**. We're not decorating rooms or picking furniture yet — we're pouring the concrete, running the plumbing, and making sure the electrical works. Everything in Release 01 exists to answer one question: **can we reliably capture raw prediction market data and never lose it?**

The Bronze layer is the immutable record of truth. If data doesn't land in Bronze, it didn't happen. Every other layer (Silver for cleaning, Gold for analytics) will read from Bronze. So getting this right means everything built on top of it is automatically trustworthy.

---

## The Architecture (How the Pieces Fit Together)

Here's how to think about the system. Imagine a conveyor belt at a factory:

```
[Prediction Market APIs] → [Our Python Code] → [S3 Bronze Bucket]
         ↑                       ↑                     ↑
   The raw material        The machinery          The warehouse
```

In AWS, the scheduled version looks like this:

```
EventBridge Schedule (the alarm clock)
        ↓
ECS Fargate Task (a disposable worker)
        ↓
prediction-data CLI (the actual code)
        ↓
S3 Bronze (the permanent archive)
        ↓
CloudWatch Logs (the security cameras)
```

Each piece is **stateless** — it wakes up, does its job, writes the result, and disappears. No persistent servers. No databases to maintain. If something crashes, you just run it again and get a new `run_id`. Nothing gets overwritten.

### The Codebase Layout

```
src/prediction_data/
├── cli/                # The command-line interface (how you talk to the system)
│   ├── main.py         # Entry point: 'prediction-data' command
│   └── status.py       # Monitoring commands: coverage, runs, show-run, validate
├── core/               # Shared plumbing that everything else uses
│   ├── http.py         # HTTP client with retries, backoff, rate limiting
│   ├── config.py       # Environment variable loading (pydantic-settings)
│   ├── compression.py  # JSONL serialization + gzip compression
│   ├── logging.py      # Structured JSON logging (CloudWatch-compatible)
│   └── run.py          # RunContext: UUID generation, timing, S3 key formatting
├── bronze/
│   ├── polymarket/
│   │   ├── client.py   # Gamma API + Data API client (markets, events, trades)
│   │   ├── clob.py     # CLOB API client (authenticated trades, unlimited pagination)
│   │   ├── goldsky.py  # Goldsky subgraph client (on-chain order fills, GraphQL)
│   │   └── ingest.py   # All Polymarket ingestion functions
│   └── kalshi/
│       ├── auth.py     # RSA-PSS signature generation (per-request signing)
│       ├── client.py   # Kalshi API client (trades, markets, events)
│       └── ingest.py   # All Kalshi ingestion functions
└── storage/
    ├── s3.py           # S3 upload/download with Bronze key layout validation
    └── manifest.py     # Manifest schema (Pydantic models) for audit trail
```

The key insight: **every platform gets its own client, but they all share the same core plumbing** (HTTP, compression, S3, manifests). This means adding a new prediction market platform someday is mostly about writing a new `client.py` and `ingest.py` — the hard infrastructure problems are already solved.

---

## Sprint-by-Sprint Walkthrough

### Sprint 01: Project Bootstrap

**What:** Set up the Python project, CLI skeleton, configuration, and structured logging.

**Why it matters:** This is the equivalent of setting up a workbench before you start building. You'd be amazed how many projects skip this and end up with dependency hell and no consistent way to run things. We used:

- **pyproject.toml** (not setup.py) — the modern Python packaging standard
- **Typer** for the CLI — it gives you `--help` for free and validates arguments
- **Pydantic Settings** for config — loads from env vars and `.env` files with validation
- **structlog** for logging — outputs JSON in production (for CloudWatch) and colored text locally

**Lesson:** Always invest in your developer experience first. When your CLI has `--help` and your config validates itself, debugging later is 10x easier. The 30 minutes you spend here saves hours later.

### Sprint 02: Core Infrastructure

**What:** HTTP client with retries, S3 storage layer, manifest schema, compression utilities, run_id tracking.

**Why it matters:** These are the building blocks that every ingestion function uses. The HTTP client is the most important — it handles:

- **Exponential backoff with jitter**: If the API rate-limits you (429), you wait 1 second, then 2, then 4, but with a random offset so multiple workers don't all retry at the same instant. Without jitter, you get "thundering herd" — everyone retries at the exact same time and the API falls over again.
- **Run IDs**: Every single invocation gets a UUID4. This is the core of idempotency — if you run the same command twice, you get two separate outputs. Nothing gets overwritten. Ever. This seems paranoid until you realize how many data pipelines break because of accidental overwrites.

**The manifest**: Every run writes a `_manifest.json` alongside the data. Think of it as a receipt: "I fetched 12,345 trades from this API endpoint at this time, and they're stored in these files." Without manifests, you'd have to guess whether a file is complete or partial.

**Lesson:** The `_manifest.json` pattern is used at companies like Netflix, Airbnb, and Uber for exactly this reason. "No manifest = failed run" is a rule worth memorizing. It turns your data lake from a data swamp into something you can actually reason about.

### Sprint 03: Polymarket Integration

**What:** API research, Polymarket client, trades/markets/events ingestion, integration tests.

**Why it matters:** This is where theory meets reality. Polymarket actually has three different APIs:

| API | What it's for | Auth? | Pagination |
|-----|--------------|-------|------------|
| Gamma API | Markets & events catalog | None | Offset-based |
| Data API | Trades (simple) | None | Offset (10k limit!) |
| CLOB API | Trades (authenticated) | HMAC-SHA256 | Cursor-based (unlimited) |

The Data API has a hard 10,000-offset cap — if there are more than 10k trades in a day, you simply can't get them all. That's why the CLOB API exists (Sprint 07 added it). But we started with the Data API because it's simpler and works fine for recent data.

**Bug we hit:** The `raise typer.Exit(code=0)` in CLI success paths was being caught by the exception handler and treated as a failure. The fix was to just remove the redundant exit — the function naturally exits with code 0.

**Lesson:** When you're wrapping APIs, don't try to normalize their quirks away. Store the raw response. If Polymarket returns prices as strings, keep them as strings. Bronze is about preserving exactly what the API gave you. Normalization happens in Silver.

### Sprint 04: Kalshi Integration

**What:** Same pattern as Polymarket but for the Kalshi API with its RSA authentication.

**Why it matters:** Kalshi uses RSA-PSS signatures instead of simple API keys. Every single request needs a fresh cryptographic signature: `sign(timestamp_ms + HTTP_METHOD + path)`. This is more complex than Polymarket's auth but also more secure — even if someone intercepts a request, they can't replay it because the timestamp will be wrong.

The implementation lives in `kalshi/auth.py` and generates three headers per request:
- `KALSHI-ACCESS-KEY`: Your API key ID
- `KALSHI-ACCESS-SIGNATURE`: The RSA-PSS signature (base64-encoded)
- `KALSHI-ACCESS-TIMESTAMP`: Millisecond timestamp

**Lesson:** When you see "RSA signature auth" in API docs, don't panic. The pattern is always: concatenate some fields, sign the result, base64-encode it, put it in a header. The `cryptography` library handles the hard crypto parts.

### Sprint 05: AWS Infrastructure

**What:** CloudFormation templates for S3 bucket, IAM roles, ECS cluster, EventBridge schedules, CloudWatch monitoring.

**Why it matters:** This is Infrastructure as Code (IaC) — instead of clicking around in the AWS console, we define everything in YAML templates. Benefits:

- **Reproducible:** Deploy to dev, staging, prod with one parameter change
- **Auditable:** Git history shows exactly what changed and when
- **Rollback-able:** CloudFormation can undo a bad deployment automatically

The architecture choice of **EventBridge + ECS Fargate** is deliberate. We could have used:
- A cron job on an EC2 instance (fragile, always-on costs)
- AWS Lambda (15-minute timeout is too short for large backfills)
- Dagster/Airflow (overkill for Bronze-only)

ECS Fargate gives us: run a Docker container, execute one CLI command, exit. You pay only for the seconds it runs. The schedules in EventBridge are the alarm clocks.

**Lesson:** Resist the urge to build complex orchestration early. "EventBridge → ECS → S3" is boring and that's exactly why it works. You can always upgrade to Dagster in Release 2 when you actually need DAGs and sensors. Premature orchestration is one of the biggest time-wasters in data engineering.

### Sprint 06: Validation and Delivery

**What:** End-to-end tests, failure recovery tests, backfill tests, exit criteria verification, operational documentation.

**Why it matters:** This sprint is about proving the system works, not building new features. The tests verify:

- Every ingestion command produces valid gzipped JSONL
- Manifest row counts match actual data
- Failed runs exit with non-zero codes (so monitoring can detect them)
- Retries create new run_ids (no overwrites)
- The CloudFormation templates reference versioned buckets and schedules

**Lesson:** Testing isn't just about writing tests — it's about testing the right things. We test the *contracts*: "Does the output match the Bronze storage contract?" rather than "Does this internal helper return the right value." Contract tests survive refactors; implementation tests break whenever you move code around.

### Sprint 07: Historical Backfill

**What:** CLOB API client with HMAC auth, backfill CLI command for iterating over date ranges.

**Why it matters:** The CLOB API is Polymarket's authenticated trading API. Unlike the Data API (10k offset cap), the CLOB uses cursor-based pagination with no limit. You can walk through millions of historical trades.

The auth is HMAC-SHA256, which is simpler than Kalshi's RSA but still involved:
1. Concatenate: `timestamp + "GET" + "/data/trades"`
2. HMAC-sign with your API secret
3. Base64-encode the result
4. Send it with 5 `POLY_*` headers

The **backfill CLI** (`prediction-data backfill run`) iterates day-by-day over a date range. Key design decision: **continue on failure**. If day 15 out of 30 fails, keep going and report failures at the end. You don't want a 3-day backfill to abort at day 1 because of a transient API hiccup.

**PRD vs reality:** The PRD originally specified timestamp-based backward pagination for the CLOB API. The actual API uses cursor-based forward pagination. We implemented what the API actually does, not what the spec assumed. Always let the API win.

**Lesson:** When building backfill tools, two things matter most: (1) day-by-day isolation so failures don't cascade, and (2) a `--dry-run` flag so you can preview what would happen before doing it for real. These sound simple but they prevent almost every backfill disaster.

### Sprint 08: Order Filled Ingestion

**What:** Goldsky subgraph client for on-chain OrderFilledEvent data, plus a parquet-to-Bronze converter.

**Why it matters:** This is the only on-chain data in the system. While trades come from Polymarket's API, OrderFilledEvents come from the actual Ethereum blockchain via a Goldsky-hosted subgraph (a GraphQL API over indexed blockchain data).

The subgraph uses `id_gt` cursor pagination — a standard pattern in The Graph ecosystem:
```graphql
{
  orderFilledEvents(first: 1000, orderBy: id, where: { id_gt: $cursor, timestamp_gte: $start, timestamp_lte: $end }) {
    id transactionHash orderHash timestamp maker taker ...
  }
}
```

The **parquet backfill** is interesting. We had a monolithic 15 GB parquet file with 313 million historical records. The naive approach (scan the file once per day) would read 15 GB * N days. Instead, we stream through the file exactly once, bucketing rows by date as we go. O(row_groups) instead of O(days * row_groups).

One tricky detail: the parquet file stores asset IDs as float-notation strings like `6.58e+76` due to precision loss in the original export. We resolve these to full-precision token IDs by building a lookup table from the bronze markets data (`clobTokenIds` field).

**Lesson:** When converting between data formats, watch for precision loss. Floating-point numbers can't represent the full range of Ethereum token IDs (77+ digits). This is why blockchain data uses strings for large numbers — and why you should never convert them to floats.

### Sprint 09: Monitoring and Status

**What:** Four new CLI commands for inspecting what's in your Bronze layer.

**Why it matters:** Without monitoring, you're flying blind. These commands let you answer the questions that keep data engineers up at night:

| Command | Question it answers |
|---------|-------------------|
| `status coverage` | "Do I have data for every day, or are there gaps?" |
| `status runs` | "What ran recently? Did anything fail?" |
| `status show-run` | "What exactly happened in this specific run?" |
| `status validate` | "Is my data structurally intact, or are there orphaned/broken files?" |

The `validate` command is the paranoid one. It checks:
- Every run directory has a valid `_manifest.json`
- Every file listed in the manifest actually exists in S3
- No orphaned data files exist without a manifest
- No empty runs (row_count = 0) snuck in

If anything is wrong, it exits with a non-zero code — so you can run it in CI or a cron job and alert on failures.

**Implementation detail:** All status commands share the same `--platform` and `--entity` filter options via Typer's annotated types. The `format_table()` utility ensures consistent terminal output across all subcommands. This is a small thing but it matters — users build muscle memory around consistent interfaces.

---

## How to Use the System (The Operator's Guide)

### Running an Ingestion

```bash
# Ingest today's Polymarket trades
prediction-data ingest polymarket-trades --dt 2026-01-30

# Ingest Kalshi markets snapshot
prediction-data ingest kalshi-markets --dt 2026-01-30

# Ingest Polymarket on-chain order fills
prediction-data ingest polymarket-order-filled --dt 2026-01-30
```

Every command prints a `run_id` on success. Save it — it's your receipt.

### Running a Backfill

```bash
# Backfill everything for January
prediction-data backfill run --start-date 2026-01-01 --end-date 2026-01-31

# Just Polymarket trades
prediction-data backfill run --start-date 2026-01-01 --end-date 2026-01-31 \
    --platform polymarket --entity trades

# Preview what would run (no actual API calls or S3 writes)
prediction-data backfill run --start-date 2026-01-01 --end-date 2026-01-07 --dry-run
```

Always run `--dry-run` first for large date ranges. Backfills for a month of trades can take hours due to rate limiting.

### Historical Parquet Backfill (Order Filled)

For order_filled events before the Goldsky subgraph existed, we have a one-time converter:

```bash
# Convert parquet to bronze format for a date range
python scripts/backfill_order_filled_from_parquet.py \
    --start-date 2022-11-01 --end-date 2026-01-31

# Preview first
python scripts/backfill_order_filled_from_parquet.py \
    --start-date 2024-01-01 --end-date 2024-03-31 --dry-run
```

### Checking on Your Data

```bash
# Are there any gaps in the last month?
prediction-data status coverage --start-date 2026-01-01 --end-date 2026-01-31

# What ran recently?
prediction-data status runs --last 10

# What happened on a specific date?
prediction-data status runs --dt 2026-01-15

# Deep-dive into a specific run
prediction-data status show-run <run_id>

# Is my data structurally sound?
prediction-data status validate --start-date 2026-01-01 --end-date 2026-01-31
```

### Monitoring in AWS

Once deployed, the system runs itself. But you should know where to look:

- **CloudWatch Logs:** `/ecs/prediction-data-{env}` — every run writes structured JSON logs
- **CloudWatch Dashboard:** `prediction-data-{env}` — charts for runs, errors, and alarm status
- **CloudWatch Alarms:** Fires if trades haven't run in 10 minutes or markets in 2 hours
- **SNS Alerts:** Email notifications when alarms trigger (configure email in the CloudFormation stack)

To manually check ECS task status:
```bash
# See recent task runs
aws ecs list-tasks --cluster prediction-data-dev --desired-status STOPPED

# Check a specific task's exit code
aws ecs describe-tasks --cluster prediction-data-dev --tasks <task-arn>
```

---

## Lessons Learned and Engineering Wisdom

### 1. Immutability is your best friend

Every run creates a new `run_id` directory. Nothing is ever overwritten. This sounds wasteful (you'll have duplicate data) but it means:
- Retries are always safe
- You can debug by comparing two runs
- You never have to answer "did someone corrupt the data?"

Deduplication is a Silver problem. Bronze just captures everything.

### 2. Manifests turn a data lake into a data warehouse

Without manifests, S3 is just a pile of files. With manifests, every file has provenance: who created it, when, from what API, with how many rows. This is the difference between a filing cabinet (organized, labeled) and a box of papers (good luck finding anything).

### 3. Start with the simplest thing that works

We started with the Data API (no auth, simple pagination) even though we knew the CLOB API was better for backfills. This let us ship working ingestion in Sprint 03 and add the CLOB client in Sprint 07 when we actually needed it. The worst thing you can do is build a complex auth system before you've even proven the basic pipeline works.

### 4. APIs lie (or at least surprise you)

- The PRD said the CLOB API used timestamp-based pagination. It uses cursor-based. We adapted.
- Kalshi's docs say the field is `side`. The API returns `taker_side`. Our integration tests caught this.
- Polymarket's parquet export stores Ethereum token IDs (77+ digit integers) as floats, turning them into `6.58e+76`. We built a resolution table from markets data.

Always write integration tests that hit the real API (behind a `pytest -m integration` flag). Unit tests with mocked responses can't catch API changes.

### 5. Design for failure from day one

The HTTP client retries on 429/5xx with exponential backoff. The backfill CLI continues on per-day failures. The status validate command catches orphaned files and broken manifests. None of this is glamorous, but it's what separates a toy project from a production system.

### 6. Infrastructure as Code, always

Every AWS resource is defined in a CloudFormation template in `infrastructure/`. Deploying to a new environment is:
```bash
aws cloudformation deploy --template-file infrastructure/s3-bronze-bucket.yaml \
    --stack-name prediction-bronze-bucket --parameter-overrides Environment=prod
```
Not "click these 47 things in the AWS console and hope you remember what you did."

### 7. Test the contracts, not the implementation

Our tests verify: "Does the S3 key match `bronze/{platform}/{entity}/dt={date}/run_id={uuid}/`?" They don't verify: "Does this internal helper parse the date string correctly." The contract tests survived every refactor. The implementation tests would have broken constantly.

---

## Technologies Used (and Why)

| Tech | Why we chose it |
|------|----------------|
| **Python 3.11+** | Ecosystem (boto3, httpx, pyarrow), team familiarity, async support |
| **httpx** | Modern async HTTP client, better API than requests, built-in retry support |
| **Typer** | CLI framework that gives `--help`, validation, and subcommands for free |
| **Pydantic** | Data validation with type hints — catches config/manifest errors at parse time |
| **structlog** | Structured logging that outputs JSON for CloudWatch and colored text for humans |
| **boto3** | AWS SDK — it's the only real option for S3 in Python |
| **pyarrow** | Fast parquet reading with streaming (row group iteration) for the 15 GB backfill |
| **cryptography** | RSA-PSS signatures for Kalshi auth — don't roll your own crypto |
| **ECS Fargate** | Serverless containers — no servers to manage, pay per second of execution |
| **EventBridge Scheduler** | Modern AWS scheduling — replaced older EventBridge Rules approach |
| **CloudFormation** | AWS-native IaC — no extra tools needed (Terraform would also work) |

---

## What's Next (Release 02 Preview)

Release 02 adds the **Silver layer**: Apache Iceberg tables that deduplicate, clean, and type-cast the raw Bronze data. Bronze remains untouched — Silver reads from it. The key additions will be:
- Iceberg table definitions
- Manifest-driven processing (Silver reads Bronze manifests to know what's new)
- Data quality gates (schema validation, null checks)
- Canonical IDs (mapping market IDs across platforms)
- Dagster for orchestration (now we actually need DAGs)

But that's a future problem. For now, Bronze is law.
