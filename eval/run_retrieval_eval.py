import json
from pathlib import Path

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.search_service import search_products


EVAL_FILE = (
    Path(__file__).parent
    / "retrieval_queries.json"
)


def main() -> None:
    with EVAL_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        cases = json.load(file)

    hits = 0

    with SessionLocal() as db:
        print()
        print(
            f"Retrieval evaluation "
            f"(top-k={settings.search_default_top_k})"
        )
        print("=" * 90)

        for index, case in enumerate(
            cases,
            start=1,
        ):
            results = search_products(
                db,
                query=case["query"],
                top_k=(
                    settings.search_default_top_k
                ),
            )

            expected_id = (
                case["expected_product_id"]
            )

            result_ids = [
                str(item["product_id"])
                for item in results
            ]

            hit = (
                expected_id
                in result_ids
            )

            if hit:
                hits += 1

            rank = None

            if hit:
                rank = (
                    result_ids.index(
                        expected_id
                    )
                    + 1
                )

            returned_titles = [
                item["title"]
                for item in results
            ]

            print(
                f"{index:02d}. "
                f"{'HIT ' if hit else 'MISS'} "
                f"| query: {case['query']}"
            )

            print(
                f"    expected: "
                f"{case['expected_title']}"
            )

            print(
                f"    rank: "
                f"{rank if rank is not None else '-'}"
            )

            print(
                f"    returned: "
                f"{returned_titles}"
            )

            print()

    total = len(cases)

    hit_rate = (
        hits / total * 100
        if total
        else 0
    )

    print("=" * 90)

    print(
        f"Hits: {hits}/{total}"
    )

    print(
        f"Top-{settings.search_default_top_k} "
        f"hit rate: {hit_rate:.1f}%"
    )


if __name__ == "__main__":
    main()