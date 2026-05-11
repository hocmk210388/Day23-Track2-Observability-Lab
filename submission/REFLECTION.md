# Day 23 Lab Reflection

> Grader spot-checks **sections 1–5** for substance; **section 6** is weighted highest.

**Student:** _(Mã Khoa Học / 2A202600474)_
**Submission date:** _(2026-05-11)_
**Lab repo URL:** _(URL GitHub public của bạn)_

**Checklist ảnh:** `submission/screenshots/README.md` — ảnh thực tế trong folder là tên `##_lab23.png` (xem bảng ánh xạ trong README).

---

## 1. Hardware + setup output

`00-setup/verify-docker.py` checks **Docker Engine**, **Compose v2**, **free RAM** (warn if low), and whether **lab ports** are already bound (so you know `make up` will attach or conflict). It also writes **`00-setup/setup-report.json`** for checkpoint #1.

Paste output of `python 00-setup/verify-docker.py` (or `python3 …`):

```
Docker:        OK  (28.5.1)
Compose v2:    OK  (2.40.3-desktop.1)
RAM available: 7.36 GB (OK)
Ports free:    BOUND: [8000, 9090, 9093, 3000, 3100, 16686, 4317, 4318, 8888]
Report written: 00-setup/setup-report.json
```

_(If your run shows `Ports free: OK` instead of `BOUND`, that is normal on a clean machine before `make up`.)_

**What I learned:** the script is a cheap gate: it fails fast when Docker Desktop is not running or when ports clash with another course stack, instead of debugging Compose halfway through.

---

## 2. Track 02 — Dashboards & Alerts

### 6 essential panels (screenshot)

Save **`submission/screenshots/07_lab23.png`** (6 panel overview). Nếu ảnh overview của bạn là tên khác (ví dụ `02_lab23.png`), sửa lại đường dẫn cho trùng file. The grader expects the **Day 23 “AI Service Overview”** dashboard with **six panels** populated after **`make load`**: request rate by status, latency quantiles, error rate, GPU util, token throughput, in-flight gauge — so Prometheus labels and the `$model` template variable actually resolve.

### Burn-rate panel

Save **`submission/screenshots/08_lab23.png`** (SLO burn-rate). Should show **error budget** (or availability proxy) and **burn** panels tied to the SLO recording rules, not flat `0/0` from missing denominators.

### Cost & tokens (#9)

Save **`submission/screenshots/09_lab23.png`** — dashboard **Cost and tokens** / ước lượng $/hr sau load.

| When | What | Evidence |
|---|---|---|
| _T0_ | killed `day23-app`         | screenshot `10_lab23.png` (Alertmanager) |
| _T0+90s_ | `ServiceDown` fired   | screenshot `11_lab23.png` (Slack firing) |
| _T1_ | restored app              | — |
| _T1+60s_ | alert resolved        | screenshot `12_lab23.png` (Slack resolved) |

**Narrative:** `make alert` proves the path **Prometheus → Alertmanager → Slack** works end-to-end: firing should be noisy enough to notice, resolve should arrive after the app is healthy again so on-call trust is not destroyed.

### One thing surprised me about Prometheus / Grafana

Recording rules and dashboard variables look simple until cardinality bites: one bad `label` on a counter can multiply series count and make both Prometheus RAM and Grafana queries feel “fine in the demo” but painful at production traffic. The lab made it obvious why burn-rate alerts want pre-aggregated ratios instead of ad-hoc `rate()` on high-cardinality matchers.

---

## 3. Track 03 — Tracing & Logs

### One trace screenshot from Jaeger

Save **`submission/screenshots/13_lab23.png`**. Ideal evidence: root **`POST /predict`** (FastAPI server span) with **three child spans** named **`embed-text` → `vector-search` → `generate-tokens`** (plus the inner `predict` span if present), proving the handler is decomposed for latency attribution.

_(Tuỳ chọn rubric #13 — GenAI tags: **`submission/screenshots/02_lab23.png`** hoặc tab Tags trên cùng trace nếu bạn gộp một ảnh.)_

### Log line correlated to trace

Source: `docker compose logs app` (prefix `day23-app |` is from Compose; the payload is one JSON object per line).

**`trace_id` to match in Jaeger:** `1057a6832b057b58f100f1a30143ce7c`

```json
{"model": "llama3-mock", "input_tokens": 4, "output_tokens": 54, "quality": 0.667, "duration_seconds": 0.2439, "trace_id": "1057a6832b057b58f100f1a30143ce7c", "event": "prediction served", "level": "info", "timestamp": "2026-05-11T05:08:06.736152Z"}
```

**Why this matters:** the same `trace_id` in logs and in Jaeger/Loki is the minimum viable “correlation contract” between pillars — without it, you only have three disconnected UIs.

### Tail-sampling math

The collector uses `tail_sampling` in `03-tracing-and-logs/otel-collector/otel-config.yaml` with **`decision_wait: 30s`** (it waits up to ~30s after the last span in a trace before deciding keep/drop) and three sibling policies:

1. **`keep-errors`** — `status_code: [ERROR]` → any trace that ends with an error span is **retained** (for debugging).
2. **`keep-slow`** — `latency: threshold_ms: 2000` → traces whose end-to-end latency is **≥ 2000 ms** are **retained**.
3. **`probabilistic-1pct`** — `sampling_percentage: 1` → among traces that are **not** already kept by (1) or (2), roughly **1%** are kept at random.

Interpreting the policies as an **OR** over “reasons to keep” (the usual intent of this lab stack: keep all bad/slow signal, subsample the healthy bulk), the **healthy + fast** traffic is the only traffic that depends on the 1% rule.

**Worked example (healthy, fast traces only):**  
If the app emits **N = 1,000** successful traces per minute, each faster than 2s, then only the probabilistic gate applies. Expected retained traces ≈ **0.01 × 1,000 = 10** per minute (binomial noise applies; long-run average ~1%).

**Forced-failure trace:** `POST /predict` with `"fail": true` returns 503 and marks the server span path as **error** → policy (1) matches → that trace should be **kept regardless of the 1% sampler**, so you can still find it in Jaeger even when almost all healthy traces are dropped.

**“Healthy trace dropped”:** a normal 200 response with latency &lt; 2s has **no** error match and **no** slow match, so it is subject to **~99% drop** at the collector (only ~1% exported to Jaeger). That is the cost control story: you keep full fidelity for incidents and tails, and you pay much lower storage for the happy path.

---

## 4. Track 04 — Drift Detection

Run: `make drift` (or `python 04-drift-detection/scripts/drift_detect.py`). Outputs: `04-drift-detection/reports/drift-summary.json`, `04-drift-detection/reports/drift-report.html`.

### PSI scores

Paste `04-drift-detection/reports/drift-summary.json`:

```json
{
  "prompt_length": {
    "psi": 3.461,
    "kl": 1.7982,
    "ks_stat": 0.702,
    "ks_pvalue": 0.0,
    "drift": "yes"
  },
  "embedding_norm": {
    "psi": 0.0187,
    "kl": 0.0324,
    "ks_stat": 0.052,
    "ks_pvalue": 0.133853,
    "drift": "no"
  },
  "response_length": {
    "psi": 0.0162,
    "kl": 0.0178,
    "ks_stat": 0.056,
    "ks_pvalue": 0.086899,
    "drift": "no"
  },
  "response_quality": {
    "psi": 8.8486,
    "kl": 13.5011,
    "ks_stat": 0.941,
    "ks_pvalue": 0.0,
    "drift": "yes"
  }
}
```

At least two features exceed the lab’s PSI drift threshold (`psi > 0.2` → `drift: yes`): **`prompt_length`** and **`response_quality`**, matching the intentional shift in `drift_detect.py` (mean prompt length and Beta parameters for quality).

### Evidently-style HTML report (#17)

Open **`04-drift-detection/reports/drift-report.html`** in a browser (double-click the file, or `file:///...`).

- If **Evidently** loads successfully in your environment, you get the full Evidently UI.
- If Evidently fails on import (some `pydantic` / `evidently` combinations), the script still writes a **tabular HTML fallback** with the same PSI / KL / KS columns so the report **renders** for a screenshot.

**Screenshot checkpoint:** save as **`submission/screenshots/17_lab23.png`** (báo cáo Evidently / HTML fallback trong trình duyệt — nếu bạn lưu drift ở file khác, sửa tên cho khớp).

### Which test fits which feature? (#18)

Rubric #18 asks: for **`prompt_length`**, **`embedding_norm`**, **`response_length`**, **`response_quality`**, pick the drift test you would run **in production** (PSI / KL / KS / MMD) and justify it by **feature type** (continuous scalar vs bounded score vs high‑dim vector, etc.).

#### Summary table

| Feature | Test I’d use in production | Why (feature type) |
|---|---|---|
| **`prompt_length`** | **PSI** | One‑dimensional continuous input; PSI is the standard ops metric for “reference vs current” bin stability. |
| **`embedding_norm`** | **PSI** on this scalar; **MMD** if we had full embedding vectors | Here we only store a **norm** (1D). With **768‑dim** (or similar) embeddings, **MMD** detects shift in distribution **jointly** across dimensions without hand‑picked bins. |
| **`response_length`** | **KS** (two‑sample) as gate; **PSI** on dashboard | KS answers “did the **entire** CDF change?” with a p‑value; PSI is easier for weekly drift scorecards. |
| **`response_quality`** | **KL** (binned) + **PSI** headline | Bounded score in **[0, 1]** with **shape** change (Beta shift): KL is sensitive to mass moving between tails; PSI stays the single number ops can alert on. |

#### Tie‑in to **this** run (`drift-summary.json`)

- **`prompt_length`** — PSI **3.46**, KS p‑value **0.0** → both PSI and KS scream drift; I’d still **alert on PSI** in prod (stable thresholds, cheap to recompute) and use KS in offline RCA.
- **`embedding_norm`** — PSI **0.019**, KS p‑value **0.134** → **no** practical drift; PSI/MMD would be “monitor only,” no page.
- **`response_length`** — PSI **0.016**, KS p‑value **0.087** → borderline noise; **KS** is useful here so we don’t over‑rotate on a tiny PSI when the effect size is nil.
- **`response_quality`** — PSI **8.85**, KL **13.5**, KS p‑value **0.0** → I’d ship **PSI** to paging and use **KL** in model‑quality reviews (“where did probability mass move?”). **MMD** is less natural here because the feature is **already** a 1D summary; MMD shines on **raw** embedding tensors or multi‑modal feature spaces.

#### When **MMD** is the right default (cross‑cutting)

Use **MMD** (or learned embedding + MMD) when the monitored object is **high‑dimensional** and binning each dimension is meaningless (e.g. full text embeddings, spectrograms). For **scalar** norms and lengths, **PSI / KS / KL** stay interpretable and cheaper at production cadence.

---

## 5. Track 05 — Cross-Day Integration

**Dashboard (#20):** Grafana auto-provisions **`Cross-Day Stack (Day 23 integrative)`** (UID `day23-cross-day`) from `02-prometheus-grafana/grafana/dashboards/cross-day-stack.json` into folder **AICB Day 23**. After `make up` (or `docker compose restart grafana`), open **Dashboards → AICB Day 23** and select that title. Six panels: Day **16**, **17**, **18**, **19**, **20**, **22**.

**Evidence (#20):** screenshot the full dashboard as **`submission/screenshots/20_lab23.png`** — all **six** panels visible in one frame. Rubric allows **real data or “No Data”** per panel.

**Rubric #19 (prior-day source connected):** chạy stub trên host **`python 05-integration/monitor-day19-vector-store.py`** (port **9101**) và/hoặc **`python 05-integration/monitor-day20-llama-cpp.py`** (**9102**); Prometheus jobs **`day19-stub`** / **`day20-stub`** scrape `host.docker.internal` (xem `05-integration/README.md`). **Minh chứng chính theo rubric:** ảnh Grafana cross-day ở trên — có ít nhất một panel Day 16–22 **có số** (ví dụ Day **19** = `day19_qdrant_collections`, Day **20** = `day20_llamacpp_tokens_per_second`). **Minh chứng phụ (tuỳ chọn):** ảnh **Prometheus → Status → Targets** với `day19-stub` / `day20-stub` **UP** → lưu **`submission/screenshots/20_2_lab23.png`**. Ảnh panel theo ngày (nếu bạn chụp riêng): ví dụ **`16_lab23.png`**, **`17_lab23.png`**, **`19_lab23.png`**, **`20_3_lab23.png`** — giữ đúng tên file trong folder; chỉnh câu này nếu ý nghĩa từng ảnh khác với bảng trong `screenshots/README.md`.

### Which prior-day metric was hardest to expose? Why?

**Day 18 — Spark “active applications”** is usually the hardest: Spark metrics are historically tied to the **Spark UI** / internal sink, not a single Prometheus textfile you can scrape without an **extra exporter**, auth to the cluster, and stable job labels. Compared to Day 19/20 (often a plain `/metrics` HTTP endpoint) or Day 16 (`node_exporter`), Spark needs more glue work, so it is the first panel I’d stub or defer in a time-boxed lab.

**Integration takeaway:** the cross-day dashboard is valuable even when half the panels read **No Data**, because it documents **where telemetry would land** once each prior-day service exposes a scrape contract — the hard part is agreeing that contract, not drawing the Grafana panel.

---

## 6. The single change that mattered most (#22)

The **one** change that moved this lab from “toys that light up” to “something an on-call could actually use” was **fixing the OpenTelemetry trace model end-to-end**: **`FastAPIInstrumentor().instrument_app(app)` at import time** (not from `lifespan`, where Starlette forbids `add_middleware`), **`async` `/predict`** so spans stay on the asyncio context with the server span, resolving the **tracer** via **`get_tracer()` after the provider exists** (avoiding stale `from instrumentation import tracer` bindings), and **emitting the same `trace_id` in structured JSON logs** as in the span context. Before that alignment, Jaeger showed orphan one-span traces and logs could not be joined to traces; after it, **`POST /predict`** becomes the honest root of latency, internal steps become **attributable children**, and Loki/Grafana can pivot on **`trace_id`**. That is exactly the “three pillars, one timeline” idea from the deck: metrics tell you *that* SLO is burning, traces tell you *where* time went, logs tell you *what* the model decided — but only if the ID is consistent.

Everything else (tail sampling at the collector, Prometheus burn-rate rules, drift PSI thresholds) is **downstream policy** on top of that spine. Tail sampling (~**1%** healthy, keep **errors** and **slow**) is what makes the spine **affordable** at student traffic levels without lying about incident coverage; without the correlation spine first, sampling would only preserve disconnected fragments. So if I had only one PR to ship from this week, it would be **trace + log correlation with a correct FastAPI parent span** — all other dashboards become easier to trust once a single request has a single coherent story.

---

## Checklist nộp bài (tổng hợp)

| Checkpoint | File / lệnh |
|---|---|
| #1 `setup-report.json` | Commit `00-setup/setup-report.json` *(và/hoặc bản copy trong `submission/` nếu khóa học yêu cầu)* — chạy lại `python 00-setup/verify-docker.py` trước khi nộp. |
| #4 active gauge | `04_lab23.png` hoặc `04_2_lab23.png` *(tùy ảnh bạn chụp)* |
| #7–9 dashboards | `07_lab23.png`, `08_lab23.png`, `09_lab23.png` |
| #10–11 alerts / Slack | `10_lab23.png`, `11_lab23.png`, `12_lab23.png` |
| #12–13 Jaeger | `13_lab23.png` (+ `02_lab23.png` nếu tách #13 GenAI) |
| #14–15 reflection | §3 + dòng log JSON *(đã có trong file này)* |
| #16–18 drift | `04-drift-detection/reports/drift-summary.json` + `drift-report.html` + `17_lab23.png` |
| #19–20 cross-day | `20_lab23.png` *(+ `20_2_lab23.png` Targets; `16_lab23.png` / `19_lab23.png` / `20_3_lab23.png` nếu nộp thêm panel)* |
| Gate | `make verify` (stack bật, drift đã chạy, `REFLECTION.md` > 500 ký tự) |
| Git | Push repo public URL đã điền ở đầu file. |
