from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rag.config import DEFAULT_CSV
from rag.filters import interpret_query
from rag.ingest import ingest_csv
from rag.answer import answer_question
from rag.retrieve import retrieve


def _cmd_ingest(args: argparse.Namespace) -> int:
    csv_path = Path(args.csv).resolve()
    if not csv_path.is_file():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 1
    n = ingest_csv(csv_path, reset=args.reset)
    print(f"Indexed {n} documents into Chroma at .chroma/")
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    hits, used = retrieve(args.question, n_results=args.k)
    print("--- Inferred filters ---")
    print(f"  branch: {used.branch}")
    print(f"  reviewer_location: {used.reviewer_location}")
    print(f"  months: {used.months}")
    if used.relaxations:
        print("  relaxations:")
        for r in used.relaxations:
            print(f"    - {r}")
    print(f"--- Retrieved {len(hits)} chunks ---")
    ans = answer_question(args.question, hits, used)
    print(ans)
    return 0


def _cmd_show_filters(args: argparse.Namespace) -> int:
    f = interpret_query(args.question)
    print(f"branch: {f.branch}")
    print(f"reviewer_location: {f.reviewer_location}")
    print(f"months: {f.months}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Disneyland reviews RAG")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="Embed CSV into local Chroma DB")
    pi.add_argument("--csv", type=str, default=str(DEFAULT_CSV))
    pi.add_argument("--reset", action="store_true", help="Delete existing collection first")
    pi.set_defaults(func=_cmd_ingest)

    pa = sub.add_parser("ask", help="Ask a question (retrieval + answer)")
    pa.add_argument("question", type=str)
    pa.add_argument("-k", type=int, default=20, help="Number of chunks to retrieve")
    pa.set_defaults(func=_cmd_ask)

    pf = sub.add_parser("show-filters", help="Debug NL → metadata mapping")
    pf.add_argument("question", type=str)
    pf.set_defaults(func=_cmd_show_filters)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
