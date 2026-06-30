# KoreanOps-RAG Data Dashboard Guide

This guide explains how to open and rebuild the local data dashboard.

## What It Shows

The dashboard is generated from:

- `experiments/project_registry.yaml`

It loads V1, V2, and V3 data with the same registry-driven format:

- project
- scope
- stage
- case ID
- chunking strategy
- Qdrant collection
- OpenSearch index
- local data path
- record counts
- sample rows

It also loads project reports from the same registry as first-class artifacts:

- report role
- project
- scope
- markdown path
- line count
- sample headings or lines

For QASET datasets, the dashboard also shows linked evidence when available:

- question
- reference answer
- gold document IDs
- gold pages
- evidence text
- normalized document snippet
- raw page snippet
- page chunk snippet
- structure chunk snippet

## Open the Current Dashboard

Open this file in a browser:

```powershell
Start-Process "C:\vectorsearch-data\reports\data_dashboard.html"
```

Or paste this path into Chrome/Edge:

```text
C:\vectorsearch-data\reports\data_dashboard.html
```

## Rebuild the Dashboard

From the repo root:

```powershell
cd C:\Users\miin1\OneDrive\Desktop\Github\vectorsearch
uv run koreanops-data-dashboard build
```

The command writes:

```text
C:\vectorsearch-data\reports\data_dashboard.html
```

## Validate the Registry

Use this to confirm that V1, V2, and V3 are registered and to see how many local
artifacts are missing:

```powershell
uv run koreanops-data-dashboard validate
```

Expected output shape:

```text
Validated 3 projects and 23 datasets (... missing local artifacts)
```

Missing artifacts are not always errors. For example, V3 may show missing files
until its local data and QASET artifacts are generated.

## Export Dashboard Inventory JSON

```powershell
uv run koreanops-data-dashboard inventory --output C:\vectorsearch-data\reports\data_dashboard_inventory.json
```

This writes the same standardized dashboard model as JSON.

## How To Use The Dashboard

1. Use `Project` to choose V1, V2, or V3.
2. Use `Scope` to separate `full`, `pilot_1000`, `pilot_100`, `smoke_100`, or `legacy_root`.
3. Use `Stage` to narrow to raw, parsed, normalized, chunked, qaset, oracle, or retrieval results.
4. Select `Stage = report` to inspect registered human-facing reports.
5. Use `Case or chunk` to filter by case ID or chunking strategy.
6. Click an artifact row to inspect path, fields, samples, and status.
7. For QASET rows, use `Linked QASET question` to inspect question-linked evidence.

For V2 office PDF QASET, the linked view can show normalized document, raw page,
page chunk, and structure chunk side by side.

For V3 technical retrieval, current local data is primarily under `pilot_1000`.
Use `Project = ko_dense_technical_v3` and `Scope = pilot_1000` to inspect the
canonical reviewed QASET and pilot chunk/retrieval artifacts. V3 FULL artifacts
should only appear after the full run creates them and the registry is updated.

## Troubleshooting

If the dashboard file is missing, rebuild it:

```powershell
uv run koreanops-data-dashboard build
```

If project data looks stale, rebuild after rerunning the relevant pipeline step.

If model/cache warnings appear in `koreanops-check-env`, load the project env
before model downloads:

```powershell
. .\scripts\project-env.ps1
uv run koreanops-check-env
```
