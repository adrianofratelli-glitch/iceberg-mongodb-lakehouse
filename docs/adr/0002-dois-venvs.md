# ADR 0002 — Dois ambientes Python

- Status: aceita (2026-08, registrada em 2026-11-12)

## Contexto
Os scripts de demo (`scripts/`) só precisam do pymongo e são rodados por quem
apresenta. O backend precisa de FastAPI, uvicorn e boto3.

## Decisão
`.venv/` na raiz com `requirements.txt` para `scripts/`; `backend/venv/` com
`backend/requirements*.txt` para a API, a sonda `backend/lake_probe.py` e
`stream-processing/rebuild_table.py`. Os dois leem o mesmo `.env` da raiz e
`DATABASE_NAME` no ambiente vence o `.env`.

## Consequências
- Quem só roda a CLI da demo não instala boto3 nem FastAPI.
- Script que fala com Athena precisa do venv do backend (está nos comandos do
  README).
- No CI e na imagem Docker as duas listas são instaladas juntas.
