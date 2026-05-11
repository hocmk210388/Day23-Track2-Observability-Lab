# 05 — Integration with Days 16-22

Day 23 is the **integrative day** for Phase 2 Track 2. This track wires the observability stack to artifacts from prior days.

## What gets monitored from where

| Source day | What | How |
|---|---|---|
| 16 cloud infra | EC2/EKS hosts | `node_exporter` scrape (configure target in `prometheus.yml`) |
| 17 data pipeline | Airflow DAG | `airflow_dag_run_duration` via `statsd_exporter` |
| 18 lakehouse | Spark / Delta | Spark UI metrics → Prometheus |
| 19 vector store | Qdrant | scrape `host.docker.internal:6333/metrics` |
| 20 model serving | llama.cpp | scrape `host.docker.internal:8080/metrics` |
| 21 (skipped) | — | not yet authored as of 2026-05 |
| 22 alignment | DPO model | push `dpo_eval_pass_rate` gauge via `monitor-day22-alignment.py` |

### Rubric #19 — “at least 1 prior-day source connected” (stub OK)

1. **Pull latest `prometheus.yml` + `docker-compose.yml`** (Prometheus scrapes `host.docker.internal:9101` / `:9102`).
2. **Restart Prometheus** so it loads the new jobs:  
   `docker compose up -d prometheus`  
   (or `docker compose restart prometheus`).
3. On the **host** (same machine as Docker Desktop), from the repo root, in **two terminals**:
   - `python 05-integration/monitor-day19-vector-store.py`  → stub metrics on **:9101** (`day19_qdrant_collections`, …)
   - `python 05-integration/monitor-day20-llama-cpp.py`       → stub metrics on **:9102** (`day20_llamacpp_tokens_per_second`, …)  
   Use your lab env: `conda activate …` then `python` if needed.
4. Check Prometheus **Targets** (`http://localhost:9090/targets`) — `day19-stub` / `day20-stub` should be **UP**.
5. Grafana → **Cross-Day Stack** dashboard → **Refresh** — Day **19** and/or **20** panels should show **numbers**, not only “No Data”.
6. **Screenshot** that view for rubric **#19** (and it still satisfies **#20** six-panel layout).

If a target stays **DOWN**, confirm Windows Firewall allows Python to listen on 9101/9102 and that Docker can reach `host.docker.internal` (Compose adds `extra_hosts: host-gateway` for Prometheus).

## Run

If you have prior days running locally:

```bash
# In .env:
DAY19_QDRANT_URL=http://host.docker.internal:6333
DAY20_LLAMACPP_METRICS_URL=http://host.docker.internal:8080/metrics

# Then enable the prometheus.yml job stanzas (uncomment the blocks)
make restart
```

If you don't have prior days running, the integration scripts will **stub** the metrics so the cross-day dashboard still renders.

## Cross-day dashboard

The same definition is **auto-loaded** with the stack as:

`02-prometheus-grafana/grafana/dashboards/cross-day-stack.json`

In Grafana: folder **AICB Day 23**, title **Cross-Day Stack (Day 23 integrative)** (UID `day23-cross-day`). After `make up` or `docker compose restart grafana`, open **Dashboards → browse → AICB Day 23**.

`full-stack-dashboard.json` in this folder is the **source copy** kept next to the integration scripts; edit either and sync if you change panel queries.

## Submission checkpoint (15 pts)

- 5 pts: at least 1 prior-day source actually scraped (or stub script running)
- 5 pts: cross-day dashboard renders with all 6 panels (data or "No Data")
- 5 pts: REFLECTION.md describes which prior-day metric was hardest to expose
