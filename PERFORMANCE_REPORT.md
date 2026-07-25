# SLMC Performance Report

**Package:** SLMC-0.1.0  
**Benchmark:** `scripts/catalog_performance.py`  
**Evidence:** `docs/slmc/evidence/performance/`

## Method

The benchmark creates a fresh independent catalog database, inserts synthetic Movies and aliases through bounded SQL transactions, builds the FTS index, then repeatedly measures exact title, title-plus-year, alias, FTS candidate and insertion operations. It records database size, integrity/FK results and duplicate-source prevention.

The synthetic data validates indexed catalog mechanics. It does not measure live Wikipedia latency, operator browser throughput, physical media import or production storage hardware.

## 10,000 Movies / 50,000 aliases

- database size: **17,354,752 bytes**;
- data insertion: **0.435 s**;
- FTS rebuild: **0.181 s**;
- representative median lookups: approximately **0.74–1.06 ms**;
- integrity: **ok**;
- foreign-key violations: **0**;
- duplicate source prevention: confirmed.

## 100,000 Movies / 500,000 aliases

- database size: **202,215,424 bytes**;
- data insertion: **4.1618 s**;
- FTS rebuild: **2.3264 s**;
- exact-title median: **1.0325 ms**;
- exact-title p95: **21.29 ms**;
- exact-title maximum observed: **991.7 ms** outlier;
- title-and-year median: **0.9079 ms**;
- title-and-year p95: **1.048 ms**;
- alias median: **0.9027 ms**;
- alias p95: **1.168 ms**;
- FTS candidate median: **0.8609 ms**;
- FTS candidate p95: **1.0604 ms**;
- single insertion median: **0.0281 ms**;
- single insertion p95: **1.3148 ms**;
- integrity: **ok**;
- foreign-key violations: **0**;
- duplicate source prevention: confirmed by unique constraint.

## Interpretation

The indexed design supports routine local-first recognition lookups without full-table scans or loading the catalog into memory. The 100,000/500,000 run demonstrates representative large-catalog mechanics, not a guarantee for all hardware. The exact-title p95 was affected by a large outlier; title/year, alias and FTS p95 remained near one millisecond in this run.

## Reproduction

```bash
python scripts/catalog_performance.py --movies 10000 --aliases-per-movie 5 --output docs/slmc/evidence/performance/slmc-performance-10k.json
python scripts/catalog_performance.py --movies 100000 --aliases-per-movie 5 --output docs/slmc/evidence/performance/slmc-performance.json
```

Use a disposable data directory. Runtime benchmark databases are intentionally excluded from the integration archive.
