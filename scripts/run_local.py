"""Quick local runner: analyze a document file straight through the pipeline.

Usage:
    python scripts/run_local.py samples/sample-lease.txt lease
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extract_rules import extract_ruleset  # noqa: E402
from app.ingest import ingest  # noqa: E402
from app.llm import analyze_document  # noqa: E402
from app.verify import check_consistency  # noqa: E402


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/sample-lease.txt")
    domain = sys.argv[2] if len(sys.argv) > 2 else "lease"

    ingested = ingest(path.name, path.read_bytes())
    result, model = analyze_document(domain, ingested.text)

    print(f"\n=== {path.name}  (domain={domain}, model={model}, read via={ingested.method}) ===\n")
    print("SUMMARY:\n " + result.summary + "\n")

    print(f"FLAGGED BY AI REVIEW ({len(result.findings)}):")
    for i, f in enumerate(result.findings, 1):
        loc = f" @ {f.location}" if f.location else ""
        print(f"\n  [{i}] ({f.severity.value.upper()} · {f.type.value}){loc}  {f.title}")
        if f.source_quote:
            print(f"      quote: “{f.source_quote}”")
        print(f"      why: {f.explanation}")
        print(f"      do:  {f.recommendation}")

    print(f"\nCLAUSES EXTRACTED: {len(result.clauses)}")
    for c in result.clauses:
        print(f"  - {c.id} [{c.category}] {c.heading}")

    # Mode A: formal consistency check (Z3).
    report = check_consistency(extract_ruleset(ingested.text))
    print(f"\n=== FORMAL CONSISTENCY (Z3) — {report.variables} vars, {report.rules} rules ===")
    print(f"consistent: {report.consistent}")
    print(f"\nCONTRADICTIONS ({len(report.contradictions)}):")
    for c in report.contradictions:
        print(f"  - {c.rule_ids}: {c.explanation}")
    print(f"\nUNREACHABLE CLAUSES ({len(report.unreachable)}):")
    for u in report.unreachable:
        print(f"  - [{u.rule_id}] {u.explanation}")
    if report.notes:
        print(f"\nnotes: {report.notes}")


if __name__ == "__main__":
    main()
