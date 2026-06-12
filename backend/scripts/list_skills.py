"""List every skill the generator/verifier supports, grouped by domain.

Run from the backend/ directory:

    python -m scripts.list_skills
"""
from __future__ import annotations

from collections import defaultdict

from app.content.skills import SKILLS


def main() -> None:
    by_domain: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for skill, meta in SKILLS.items():
        by_domain[meta["domain"].value].append((skill, meta))

    print(f"{len(SKILLS)} skills across {len(by_domain)} domains:\n")
    for domain in sorted(by_domain):
        print(f"[{domain}]")
        for skill, meta in by_domain[domain]:
            method = meta["method"]
            extra = f" (template: {meta['template']})" if "template" in meta else ""
            print(f"  - {skill:<24} verify: {method}{extra}")
        print()


if __name__ == "__main__":
    main()
