# BLACK_SCHOLES.md
> Polymarket “Black–Scholes-style” Quant Metrics (belief volatility + jumps) from trades (+ optional order book pulls)

This document specifies **exactly what data to fetch from Polymarket** and **exactly what math to implement** to compute the “best” quant metrics for a single Polymarket market/outcome using a Black–Scholes analogue (log-odds diffusion + jumps). It is written for Claude Code to implement end-to-end in a Python backend.

---

## 0) Scope & Philosophy

### What we are modeling
For a binary outcome market, the traded price `p_t ∈ (0, 1)` is interpreted as a **risk-neutral probability** of the outcome resolving YES (or that outcome).

We map probability to **log-odds**:

\[
x_t = \mathrm{logit}(p_t) = \log\left(\frac{p_t}{1-p_t}\right)
\]
\[
p_t = S(x_t) = \frac{1}{1+e^{-x_t}}
\]

The core model is a **jump–diffusion** on log-odds:

\[
dx_t = \mu(t, x_t)\,dt + \sigma_b(t,x_t)\,dW_t + dJ_t
\]

Where:
- `σ_b(t,x)` is the **belief volatility** (diffusive volatility in log-odds).
- `J_t` is a jump process with intensity `λ(t,x)` and jump sizes `z` drawn from some distribution `ν(dz)`.
- `μ(t,x)` is *not* “alpha”; it is constrained so that `p_t = S(x_t)` is (approximately) a martingale under the risk-neutral measure, i.e., **no predictable drift in probability** except what is required by the coordinate transform and jump compensator.

### What data limitations imply
- With **trades only**, we can compute robust **realized variability**, reasonable **belief volatility** at moderate frequency, and workable **jump diagnostics**.
- To do the “cleanest” high-frequency inference (microstructure noise, de-noising, and best jump separation), we would ideally have time-series **top-of-book best bid/ask**. We do **not** have it currently — but we *can fetch it* on demand from Polymarket (REST `GET /book` or websocket market channel `best_bid_ask` / `last_trade_price`).

**Plan**: implement the pipeline for trades-only and optionally **augment with bid/ask pulls** (low-rate sampling) as a second phase.

---

## 1) Data Requirements (Polymarket API)

### 1.1 Market identity & metadata (Gamma API)
Goal: map a human market identifier (id/slug) to **conditionId** and **outcome token ids** (asset_ids). Also need end time/status.

**Fetch**:
- `GET https://gamma-api.polymarket.com/markets/{id}`  (or slug endpoint if used)

From Gamma, store at minimum:
- `market_id` (Gamma market id)
- `slug`
- `question`, `description`
- `conditionId`  ✅ (this is the CLOB market identifier)
- `outcomes[]` (e.g., ["YES", "NO"] or multi)
- `outcomePrices[]` (maps 1:1 to outcomes; *spot* price)
- `clob_token_ids[]` (outcome token ids / asset_ids used by CLOB)
- `active`, `closed`, `resolved` flags (or equivalent)
- `endTime` / `resolveTime` / `event` timing fields if present

Notes:
- The Gamma structure explicitly maps a market to condition id + CLOB token ids.
- Prices in `outcomePrices` are implied probabilities.

### 1.2 Historical trades (CLOB REST)
Goal: obtain the **full trade tape** for the market (condition id), for each outcome token (asset_id).

Polymarket docs indicate trades can be fetched with:
- `GET /data/trades` (CLOB) with filters including `market`, `before`, `after`.

**Important**: The documentation page “Get Trades” is described as requiring L2 headers; however the platform also documents public endpoints. If our backend already can fetch trades “no problem”, proceed using the method you currently use (likely CLOB client with API creds). Persist all raw trades.

**Trade fields to store per record** (from CLOB trade object):
- `trade_id`
- `market` (condition id)
- `asset_id` (token id)
- `side` ("BUY" or "SELL")
- `price` (string -> decimal)
- `size` (string -> decimal)
- `match_time` (timestamp)
- `taker_order_id`, `maker_order_id` (if available)
- `fee_rate_bps` (optional)
- `status` (optional)
- **any** bucketing/aggregation fields such as `bucket_index` or `market_order_id` if present (used to merge multi-part trades)

**Normalization**:
- Parse `match_time` to UTC timestamp (ms precision).
- Parse `price`, `size` as Decimal, then float for calculations if safe.
- Ensure `price` is in (0, 1). If you encounter prices in cents or basis points, normalize to probability.

### 1.3 Optional: order book / spread (CLOB REST or WebSocket)
Even though we don’t currently have historical book data, we can fetch **current** and **forward-going** best bid/ask to build a book time series.

**REST snapshot (simple)**:
- `GET https://clob.polymarket.com/book?market={conditionId}&asset_id={tokenId}`
  - Response includes `bids[]`, `asks[]`, `min_order_size`, `tick_size`, `timestamp`.

**Websocket (best long-term)**:
- Market channel messages include:
  - `last_trade_price` (asset_id, price, side, size, timestamp)
  - `best_bid_ask` (best_bid, best_ask, spread, timestamp) — may require feature flag
  - `price_change` / book update objects that include best_bid and best_ask

**If implementing optional book**:
- Sample at low cadence (e.g., every 5–30 seconds) and store:
  - best_bid, best_ask, spread, mid=(bid+ask)/2, depth@top (sizes)
  - tick_size, min_order_size (from /book)

---

## 2) Data Model & Storage Tables

### 2.1 `pm_market_meta`
Primary key: `(condition_id)`

Columns:
- `condition_id`
- `gamma_market_id`
- `slug`
- `question`
- `outcomes` (json array)
- `asset_ids` (json array)
- `end_ts` (timestamp, nullable)
- `status` (active/closed/resolved etc.)
- `tick_size` (nullable; filled from /book if available)
- `min_order_size` (nullable)

### 2.2 `pm_trades_raw`
Primary key: `trade_id` (or `(trade_id, bucket_index)` if needed)

Columns:
- `trade_id`
- `condition_id`
- `asset_id`
- `side`
- `price`
- `size`
- `match_ts`
- `maker_order_id` (nullable)
- `taker_order_id` (nullable)
- `market_order_id` (nullable)
- `bucket_index` (nullable)
- `fee_rate_bps` (nullable)
- raw JSON payload (optional)

### 2.3 `pm_book_snapshots` (optional)
Primary key: `(condition_id, asset_id, snapshot_ts)`

Columns:
- `condition_id`
- `asset_id`
- `snapshot_ts`
- `best_bid`
- `best_ask`
- `spread`
- `mid`
- `bid_size_top` (optional)
- `ask_size_top` (optional)
- `tick_size`
- `min_order_size`
- raw JSON payload (optional)

---

## 3) Preprocessing: from trades to a clean price series

### 3.1 Choose “price observation” definition
Without continuous book history, trade prices can be noisy. We will build an **aggregate price series** at a chosen cadence Δ (recommended 10s–60s).

For each asset_id (YES token):
1. Bucket trades into fixed time bins `[t_k, t_{k+1})` of width Δ seconds.
2. Compute a representative price per bucket:
   - Prefer **VWAP**:
     \[
     \hat{p}_k = \frac{\sum_i p_i \cdot q_i}{\sum_i q_i}
     \]
     where `q_i = size_i` in that bucket.
   - If no trades in bucket:
     - forward-fill last known \(\hat{p}\) (carry) **only for up to `max_gap`** (e.g., 30 min). Past that, set missing.

3. Optional (if book snapshots exist): prefer mid over vwap:
   - If best_bid and best_ask exist in bucket: \(\hat{p}_k = (bid+ask)/2\)
   - Else fallback to VWAP.

### 3.2 Clamp prices away from 0 and 1
Because logit explodes, define epsilon:
- `eps = 1e-6` (or smaller if you trust data)
- clamp:
  \[
  \tilde{p}_k = \min(1-\epsilon, \max(\epsilon, \hat{p}_k))
  \]

### 3.3 Transform to log-odds
\[
x_k = \log\left(\frac{\tilde{p}_k}{1-\tilde{p}_k}\right)
\]

### 3.4 Compute increments
With uniform sampling:
\[
\Delta x_k = x_{k} - x_{k-1}
\]
\[
\Delta t = \text{bin width in years} = \frac{\Delta \text{seconds}}{365.25 \cdot 24 \cdot 3600}
\]

---

## 4) Core Quant Metrics to Compute (Trades-only baseline)

### 4.1 State metrics
At each timestamp k:
- `p_k` = \(\hat{p}_k\) (representative probability)
- `x_k` = logit(p_k)
- `time_to_resolution` (if end_ts known): \(\tau_k = end\_ts - t_k\)

### 4.2 Realized variability (quadratic variation) in log-odds
On a window `[k-L+1, k]` (rolling) or on the full horizon:
- **Realized variance**:
  \[
  RV^x = \sum_{j=k-L+1}^{k} (\Delta x_j)^2
  \]
- Annualized realized volatility:
  \[
  \hat{\sigma}^{x}_{\text{ann}} = \sqrt{\frac{RV^x}{L\Delta t}}
  \]

Interpretation: volatility of **belief** in log-odds units.

### 4.3 Approximate belief volatility σ_b (diffusion component)
Trade-only cannot perfectly separate diffusion from jumps, but we can robustly estimate the continuous part.

Two recommended approaches:

#### (A) Truncated realized variance (simple & robust)
Define a jump threshold:
- Use median absolute deviation of increments:
  \[
  s = 1.4826 \cdot \mathrm{median}(|\Delta x_k - \mathrm{median}(\Delta x)|)
  \]
- threshold:
  \[
  \theta = c \cdot s \quad \text{with } c \in [5,10]
  \]
Then:
\[
TRV^x = \sum (\Delta x_k)^2 \cdot \mathbf{1}\{|\Delta x_k| \le \theta\}
\]
\[
\hat{\sigma}_{b,\text{ann}} = \sqrt{\frac{TRV^x}{T}}
\]
where `T = (#included)*Δt` in years.

#### (B) Bipower variation (more academic)
Compute bipower variation (BV) as a proxy for continuous variance:
\[
BV = \frac{\pi}{2}\sum_{k=2}^{n}|\Delta x_k||\Delta x_{k-1}|
\]
Annualized:
\[
\hat{\sigma}_{b,\text{ann}} = \sqrt{\frac{BV}{T}}
\]

### 4.4 Jump detection & jump risk metrics
Once σ_b is estimated, mark jumps as increments exceeding a multiple of diffusion scale.

Define expected diffusion std for one step:
\[
\mathrm{sd}_{\Delta} \approx \hat{\sigma}_b \sqrt{\Delta t}
\]
Flag a jump at k if:
\[
|\Delta x_k| > m \cdot \mathrm{sd}_{\Delta}
\]
with `m = 6` (tune 5–10).

Compute:
- Jump count in window: \(N_J\)
- Jump intensity per year:
  \[
  \hat{\lambda} = \frac{N_J}{T}
  \]
- Jump size samples: \(z_i = \Delta x_{k_i}\)
- Jump variance:
  \[
  \widehat{\mathbb{E}}[z^2] = \frac{1}{N_J}\sum_i z_i^2
  \]
- Jump contribution to quadratic variation:
  \[
  JV = \sum_{i=1}^{N_J} z_i^2
  \]

### 4.5 “Variance swap” style fair strikes (model-free estimators)
Even without full parametric calibration, the fair strike for realized log-odds variance on horizon can be approximated by expected realized variance; empirically, use rolling average / EWMA of realized variance:

- EWMA variance forecast:
  \[
  \widehat{K}^{x\text{-var}}_{t,T} \approx \mathrm{EWMA}(RV^x \text{ over matching horizon})
  \]

Also compute corridor variance (swing zone):
- choose probability corridor `[a,b]` (e.g., [0.35, 0.65])
- include increments only when `p_{k-1} ∈ [a,b]`:
  \[
  RV^x_{\text{corr}} = \sum (\Delta x_k)^2 \cdot \mathbf{1}\{p_{k-1}\in[a,b]\}
  \]

### 4.6 Logistic “Greeks” (state sensitivities)
Given `p = S(x)`:
- \[
  \Delta_x = \frac{\partial p}{\partial x} = p(1-p)
  \]
- \[
  \Gamma_x = \frac{\partial^2 p}{\partial x^2} = p(1-p)(1-2p)
  \]

These are useful to interpret why equal log-odds moves matter more near 0.5.

---

## 5) Risk-neutral drift μ(t,x): implementation detail
In this framework, we do NOT estimate an arbitrary drift in p. Instead, enforce that \(p_t\) is (approximately) a martingale.

Using Itô’s lemma for \(p=S(x)\) for the diffusion part:
\[
dp = S'(x)\,dx + \frac{1}{2}S''(x)\sigma_b^2 dt + \dots
\]
For a pure diffusion (no jumps), to make \(E[dp]=0\):
\[
S'(x)\mu dt + \frac{1}{2}S''(x)\sigma_b^2 dt = 0
\]
So:
\[
\mu(t,x) = -\frac{1}{2}\frac{S''(x)}{S'(x)}\sigma_b^2(t,x)
\]
Now compute:
- \(S'(x)=p(1-p)\)
- \(S''(x)=p(1-p)(1-2p)\)

Thus:
\[
\mu(t,x) = -\frac{1}{2}(1-2p)\sigma_b^2(t,x)
\]

**With jumps**, there is an additional compensator term:
\[
\mu(t,x) = -\frac{1}{2}(1-2p)\sigma_b^2(t,x) - \lambda \cdot \frac{\mathbb{E}[S(x+z)-S(x)]}{S'(x)}
\]
In practice, if we are not fitting a full jump distribution, we can:
- Either ignore the compensator for μ and treat μ as the diffusion-only expression, OR
- Approximate the compensator empirically using observed jump size samples `z_i`:
  \[
  \mathbb{E}[S(x+z)-S(x)] \approx \frac{1}{N_J}\sum_i (S(x+z_i)-S(x))
  \]
Then plug into formula.

**Recommendation for v1**: implement diffusion-only μ and report it as “martingale drift (diffusion-only)”.

---

## 6) Optional Upgrade: add order book snapshots (recommended)

Even if we cannot backfill historical book, we can start collecting now.

### 6.1 What to fetch
- `GET /book` for (conditionId, asset_id)
  - store best bid/ask from top of `bids[0]`, `asks[0]`
  - store tick_size and min_order_size
- Or websocket market channel events:
  - `best_bid_ask` if available
  - `last_trade_price` for a stream of trades
  - `price_change` events include best_bid and best_ask fields in the PriceChange objects

### 6.2 How it changes the pipeline
- Replace trade VWAP representative price with **midprice** when available:
  \[
  \hat{p}_k = \frac{bid_k + ask_k}{2}
  \]
- Compute spread metrics:
  - absolute spread: `ask-bid`
  - relative spread: `(ask-bid)/mid`
- Use spread to set a “noise floor” and more conservative jump thresholds during illiquidity:
  - if spread is wide, increase jump threshold `m` or increase Δ (sample slower)

### 6.3 Additional metrics enabled
- Liquidity regime: spread percentiles, time spent wide vs tight
- Toxicity proxies: jump frequency conditional on wide spread (picked-off risk)
- Better separation of diffusion vs microstructure

---

## 7) Implementation Blueprint (Claude Code)

### 7.1 Functions / modules to implement
1. `fetch_market_meta(condition_id | gamma_id | slug) -> MarketMeta`
2. `fetch_trades(condition_id, after_ts=None, before_ts=None, asset_id=None) -> List[Trade]`
3. `build_price_series(trades, bin_seconds=30, method="VWAP", max_gap_seconds=1800) -> DataFrame[t, p]`
4. `transform_to_logodds(df) -> DataFrame[t, p, x, dx]`
5. `estimate_sigma_b(df, window, method="TRUNCATED_RV"|"BIPOWER") -> Series[sigma_b_ann]`
6. `detect_jumps(df, sigma_b_ann, m=6) -> jump_flags, jump_sizes`
7. `compute_metrics(df, sigma_b, jumps, windows=[1h,1d,7d]) -> MetricsObject`
8. Optional:
   - `fetch_book_snapshot(condition_id, asset_id) -> BookSnapshot`
   - `collect_book_timeseries(...)`

### 7.2 Numerical precision requirements
- Use `Decimal` when parsing API numeric strings.
- Convert to float for vectorized computations only after scaling and clamping.
- Clamp `p` to `[eps, 1-eps]` before logit.

### 7.3 Sampling guidance (very important)
- Default `Δ = 30 seconds`.
- If market is illiquid (few trades/hour), increase to `Δ = 5 minutes`.
- If very liquid, you may reduce to `Δ = 10 seconds`, but microstructure noise increases.
- Always allow the caller to override cadence.

### 7.4 Handling sparse bins
- Forward-fill up to `max_gap_seconds`.
- Beyond that, leave missing (do not create artificial flat periods).

### 7.5 Annualization constants
- `seconds_per_year = 365.25 * 24 * 3600`
- `Δt_years = bin_seconds / seconds_per_year`

---

## 8) Outputs: what to report per market

At minimum:
- Current `p`, `x`, time-to-resolution τ
- Rolling windows (e.g., 1h / 1d / 7d):
  - realized variance `RV^x`
  - realized vol `sqrt(RV^x/T)`
  - belief vol estimate `σ_b_ann`
  - jump count `N_J`, jump intensity `λ`, mean |jump|, jump variance `E[z^2]`, jump QV share `JV/(RV^x + JV)`
- Corridor variance / volatility for `[0.35, 0.65]` (configurable)
- Logistic greeks: `Δ_x`, `Γ_x`

Optional if book is collected:
- Spread statistics: mean/median/p90, time above thresholds
- Vol conditional on spread regimes

---

## 9) Validation & sanity checks
- Ensure `p` stays in (0,1) and logit isn’t exploding.
- Plot (internally) `p_t`, `x_t`, and `|Δx|` histogram.
- Check that “diffusion-only martingale drift” μ(t,x) averages near 0 in p-space:
  - empirically verify that \(\mathbb{E}[\Delta p]\) is near zero after filtering obvious jumps at chosen cadence.

---

## 10) API references (for implementation)
- Gamma market metadata: `https://gamma-api.polymarket.com/markets/{id}`
- CLOB endpoints host: `https://clob.polymarket.com`
  - `GET /data/trades` (filtered by `market`, `before`, `after`, etc.)
  - `GET /book` (order book summary snapshot)
  - websocket market channel messages (last_trade_price, best_bid_ask, etc.)

(Exact field names and access requirements should be implemented per the current Polymarket docs in the repo.)
