"""CLI: deduplica un file CSV.

Uso:
    python -m sosia clienti.csv --column nome
    python -m sosia clienti.csv --column nome,indirizzo --threshold 0.6
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .dedupe import cluster_duplicates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m sosia",
        description="Trova record duplicati/simili in un file CSV.",
    )
    parser.add_argument("file", type=Path, help="file CSV di input")
    parser.add_argument(
        "--column", "-c", required=True,
        help="colonna (o colonne separate da virgola) su cui confrontare",
    )
    parser.add_argument(
        "--threshold", "-t", type=float, default=0.7,
        help="soglia di similarita' Jaccard in (0,1] (default: 0.7)",
    )
    parser.add_argument(
        "--encoding", default="utf-8-sig",
        help="encoding del file (default: utf-8-sig)",
    )
    args = parser.parse_args(argv)

    if not args.file.exists():
        print(f"errore: file non trovato: {args.file}", file=sys.stderr)
        return 1

    with args.file.open(newline="", encoding=args.encoding) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("errore: CSV vuoto o senza intestazione", file=sys.stderr)
            return 1
        columns = [c.strip() for c in args.column.split(",")]
        missing = [c for c in columns if c not in reader.fieldnames]
        if missing:
            print(
                f"errore: colonne non trovate: {', '.join(missing)}\n"
                f"colonne disponibili: {', '.join(reader.fieldnames)}",
                file=sys.stderr,
            )
            return 1
        rows = list(reader)

    texts = [" ".join(row.get(c, "") or "" for c in columns) for row in rows]
    clusters = cluster_duplicates(texts, threshold=args.threshold)

    if not clusters:
        print(f"Nessun duplicato trovato tra {len(rows)} record "
              f"(soglia {args.threshold}).")
        return 0

    dup_count = sum(len(c) - 1 for c in clusters)
    print(f"{len(rows)} record, {len(clusters)} gruppi di duplicati, "
          f"{dup_count} record ridondanti (soglia {args.threshold})\n")

    for n, cluster in enumerate(clusters, start=1):
        print(f"--- gruppo {n} ({len(cluster)} record) ---")
        for idx in cluster:
            # +2: 1 per l'indice zero-based, 1 per la riga di intestazione
            print(f"  riga {idx + 2}: {texts[idx]}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
