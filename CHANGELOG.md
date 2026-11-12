# Changelog

## Unreleased

- `backend/lake_probe.py`: mede o circuito MongoDB → processor → Iceberg → Athena (p50/p95, timeouts, bytes escaneados); teste live `LIVE_LAKE=1`.
- `POST /api/demo/{op}` só afirma o commit no MongoDB (`propagacao: "aguardando_confirmacao"`); `/preflight` ganha `modo` e `resumo`.
- README: status GA do `$iceberg`, catálogos, particionamento e limites; DELETE deixa de ser apresentado como direito ao esquecimento.
- ADRs 0001–0005 em `docs/adr/`.

- Reorganização: `config.py` saiu da raiz para `scripts/` (só os scripts o usam).
- Atualiza dependências compatíveis e pisos de segurança; alinha metadados de versão entre aplicação e frontend.

- UI: layout MongoDB 2026 "Dark Stage v4" (tokens mais escuros, Special Gothic / Source Code Pro locais, motivos de escada e grade, movimento escalonado).

## 1.1.0

- Reset único, redação de erros, escritas idempotentes de demo e suíte adversarial (tag `v1.1.0`, commit `e43ea69`).

## 1.0.0 (2026-09-30)

First public release.

- Repository rebuilt with a clean, single-commit history.
- English README and repository description, with screenshots captured against a real Atlas cluster.
- MIT license.
- Internal notes, presentation decks, test-output snapshots, and tooling configuration removed from the repository.
