"""CLI: deduplicate a CSV file.

Usage:
    python -m sosia customers.csv --column name
    python -m sosia customers.csv --column name,address --threshold 0.6
    python -m sosia customers.csv --column name --output cleaned.csv
    python -m sosia customers.csv --column name --json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .dedupe import cluster_duplicates


def main(argv: list[str] | None = None) -> int:
    # legacy consoles (e.g. cp1252 on Windows) can't encode every script:
    # degrade unprintable characters to '?' instead of crashing
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        prog="python -m sosia",
        description="Find duplicate/similar records in a CSV file.",
    )
    parser.add_argument("file", type=Path, help="input CSV file")
    parser.add_argument(
        "--column", "-c", required=True,
        help="column (or comma-separated columns) to compare on",
    )
    parser.add_argument(
        "--threshold", "-t", type=float, default=0.7,
        help="Jaccard similarity threshold in (0,1] (default: 0.7)",
    )
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="write a CSV without the redundant records "
             "(keeps the first of each group)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="print the groups as JSON instead of the readable report",
    )
    parser.add_argument(
        "--encoding", default="utf-8-sig",
        help="input file encoding (default: utf-8-sig)",
    )
    args = parser.parse_args(argv)

    if not args.file.exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 1
    if args.output and args.output.resolve() == args.file.resolve():
        print("error: --output cannot be the input file", file=sys.stderr)
        return 1

    with args.file.open(newline="", encoding=args.encoding) as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("error: empty CSV or missing header", file=sys.stderr)
            return 1
        fieldnames = list(reader.fieldnames)
        columns = [c.strip() for c in args.column.split(",")]
        missing = [c for c in columns if c not in fieldnames]
        if missing:
            print(
                f"error: columns not found: {', '.join(missing)}\n"
                f"available columns: {', '.join(fieldnames)}",
                file=sys.stderr,
            )
            return 1
        rows = list(reader)

    texts = [" ".join(row.get(c, "") or "" for c in columns) for row in rows]
    clusters = cluster_duplicates(texts, threshold=args.threshold)

    # the "redundant" records: every member of each group except the first
    redundant = {idx for cluster in clusters for idx in cluster[1:]}

    if args.output:
        with args.output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
            writer.writeheader()
            for i, row in enumerate(rows):
                if i not in redundant:
                    writer.writerow(row)
        print(
            f"{args.output}: wrote {len(rows) - len(redundant)} records "
            f"({len(redundant)} redundant removed)",
            file=sys.stderr,
        )

    if args.as_json:
        payload = {
            "records": len(rows),
            "threshold": args.threshold,
            # +2: 1 for the zero-based index, 1 for the header line
            "groups": [
                {"rows": [i + 2 for i in c], "texts": [texts[i] for i in c]}
                for c in clusters
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if not clusters:
        print(f"No duplicates found among {len(rows)} records "
              f"(threshold {args.threshold}).")
        return 0

    print(f"{len(rows)} records, {len(clusters)} duplicate groups, "
          f"{len(redundant)} redundant records (threshold {args.threshold})\n")

    for n, cluster in enumerate(clusters, start=1):
        print(f"--- group {n} ({len(cluster)} records) ---")
        for idx in cluster:
            # +2: 1 for the zero-based index, 1 for the header line
            print(f"  row {idx + 2}: {texts[idx]}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
