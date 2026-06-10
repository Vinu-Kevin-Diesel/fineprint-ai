"""Quick local runner: analyze a document file straight through the pipeline.

Usage:
    python scripts/run_local.py samples/sample-lease.txt lease
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.extract_text import extract_text  # noqa: E402
from app.llm import analyze_document  # noqa: E402


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/sample-lease.txt")
    domain = sys.argv[2] if len(sys.argv) > 2 else "lease"

    text = extract_text(path.name, path.read_bytes())
    result, model = analyze_document(domain, text)

    print(f"\n=== {path.name}  (domain={domain}, model={model}) ===\n")
    print("SUMMARY:\n " + result.summary + "\n")

    print(f"FINDINGS ({len(result.findings)}):")
    for i, f in enumerate(result.findings, 1):
        print(f"\n  [{i}] ({f.severity.value.upper()} · {f.type.value})  {f.title}")
        print(f"      why: {f.explanation}")
        print(f"      do:  {f.recommendation}")

    print(f"\nCLAUSES EXTRACTED: {len(result.clauses)}")
    for c in result.clauses:
        print(f"  - {c.id} [{c.category}] {c.heading}")


if __name__ == "__main__":
    main()
