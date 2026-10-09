#!/usr/bin/env python3
"""Direito ao esquecimento: tirar um pedido apagado também do histórico do Iceberg.

O DELETE no MongoDB só remove a linha da visão atual da tabela; os snapshots
anteriores continuam com ela (é o time travel). Este script faz o resto, via
Athena: OPTIMIZE (reescreve os arquivos aplicando o delete) + VACUUM com a
retenção pedida (expira snapshots e apaga arquivos inalcançáveis/órfãos) e
verifica que nenhum snapshot retido devolve o pedido. Ver backend/rtbf_side.py.

    # só verificar (leitura)
    ./backend/venv/bin/python stream-processing/forget_order.py PED-AOVIVO-001

    # expurgar agora (destrutivo: apaga o time travel anterior da tabela inteira)
    ALLOW_LAKE_PURGE=1 ./backend/venv/bin/python stream-processing/forget_order.py \\
        PED-AOVIVO-001 --purge --retention-seconds 1

Em produção a retenção é a política de RTBF: com a retenção padrão do Athena
(432000 s, 5 dias) e um VACUUM agendado, o apagamento se completa em até
retenção + intervalo do agendamento.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import athena_side  # noqa: E402
import rtbf_side  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("order_id")
    parser.add_argument("--purge", action="store_true", help="roda OPTIMIZE + VACUUM (exige ALLOW_LAKE_PURGE=1)")
    parser.add_argument("--retention-seconds", type=int, default=rtbf_side.RETENCAO_PADRAO_S)
    args = parser.parse_args()

    try:
        if args.purge:
            if not rtbf_side.expurgo_habilitado():
                print("RECUSADO: o expurgo apaga o time travel da tabela inteira. Use ALLOW_LAKE_PURGE=1.")
                for passo in rtbf_side.passos(args.retention_seconds):
                    for sql in passo["sql"] or []:
                        print(f"    {sql}")
                return 2
            resultado = rtbf_side.expurgar(args.order_id, args.retention_seconds)
        else:
            resultado = rtbf_side.verificar(args.order_id)
    except rtbf_side.PreCondicao as exc:
        print(f"PRÉ-CONDIÇÃO: {exc}")
        return 3
    except athena_side.AwsUnavailable as exc:
        print(f"AWS indisponível: {exc}")
        return 4
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado.get("apagado_do_lake") else 1


if __name__ == "__main__":
    raise SystemExit(main())
