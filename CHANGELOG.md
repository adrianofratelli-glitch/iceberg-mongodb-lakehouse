# Changelog

## Unreleased

## 1.2.0 (2026-10-09)

- RTBF: README no longer claims DELETE alone erases from the lake; new *Direito ao esquecimento* panel, `GET/POST /api/esquecimento/{id}` and `stream-processing/forget_order.py` (OPTIMIZE + VACUUM with retention, then snapshot-by-snapshot check). Purge guarded by `ALLOW_LAKE_PURGE=1`.
- CDC responses only confirm the MongoDB write; the lake side stays "aguardando confirmação" until the row is read back from Athena.
- Preflight: `modo`/`resumo` (MongoDB-only mode when AWS is unavailable), largest-document check against the 16 MB change-event limit, missing lake configuration.

- UI: layout MongoDB 2026 "Dark Stage v4" (tokens mais escuros, Special Gothic / Source Code Pro locais, motivos de escada e grade, movimento escalonado).

## 1.0.0 (2026-09-30)

First public release.

- Repository rebuilt with a clean, single-commit history.
- English README and repository description, with screenshots captured against a real Atlas cluster.
- MIT license.
- Internal notes, presentation decks, test-output snapshots, and tooling configuration removed from the repository.
