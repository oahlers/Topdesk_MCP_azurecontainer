from __future__ import annotations

import sys
import traceback

import server_v36 as s


passed = 0
failed = 0


def run_test(name, func):
    global passed, failed

    print(f"\n{'=' * 70}")
    print(f"TEST: {name}")
    print("=" * 70)

    try:
        result = func()
        print(f"PASS: {result}")
        passed += 1
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        failed += 1


def test_health():
    result = s.health()

    if result.get("status") != "ok":
        raise AssertionError(f"health status = {result.get('status')}")

    return result


def test_known_old_incident():
    result = s.get_incident_by_number("S 2208 005")

    if result.get("number") != "S 2208-005":
        raise AssertionError(
            f"Expected S 2208-005, got {result.get('number')}"
        )

    return (
        f"{result.get('number')} "
        f"{result.get('creationDate')}"
    )


def test_recent_incidents():
    result = s.list_recent_incidents(limit=3)

    if result.get("count", 0) < 1:
        raise AssertionError("No recent incidents returned")

    return f"{result['count']} incidents"


def test_year_2022():
    result = s.find_incidents_by_date_range(
        year=2022,
        limit=10,
    )

    if result.get("totalMatches") != 455:
        raise AssertionError(
            "Expected the previously verified 455 incidents "
            f"for 2022, got {result.get('totalMatches')}"
        )

    return (
        f"{result['count']} shown / "
        f"{result['totalMatches']} total"
    )


def test_year_2021():
    result = s.find_incidents_by_date_range(
        year=2021,
        limit=10,
    )

    if result.get("totalMatches") != 0:
        raise AssertionError(
            f"Expected 0 for 2021, got {result.get('totalMatches')}"
        )

    return "0 incidents, as expected"


def test_oldest_incident():
    result = s.find_incidents_by_date_range(
        sort_order="asc",
        limit=1,
    )

    incidents = result.get("incidents", [])

    if not incidents:
        raise AssertionError("No incidents returned")

    first = incidents[0]

    if first.get("Sagsnummer") != "S 2206-003":
        raise AssertionError(
            "Expected oldest incident S 2206-003, "
            f"got {first.get('Sagsnummer')}"
        )

    return (
        f"{first.get('Sagsnummer')} - "
        f"{first.get('Dato tilføjet (oprettet)')}"
    )


def test_incident_number_formats():
    formats = [
        "S 2208-005",
        "S2208-005",
        "S 2208 005",
        "S2208 005",
        "2208-005",
        "2208 005",
    ]

    for value in formats:
        normalized = s.normalize_incident_number(value)

        if normalized != "S 2208-005":
            raise AssertionError(
                f"{value!r} normalized to {normalized!r}"
            )

    return f"{len(formats)} formats normalized correctly"


def test_knowledge_search():
    result = s.search_knowledge(
        "password",
        limit=3,
    )

    return f"{result.get('count', 0)} results"


def test_categories():
    result = s.list_incident_categories()

    if result.get("count", 0) < 1:
        raise AssertionError("No categories returned")

    return f"{result['count']} categories"


def test_operator_groups():
    result = s.list_operator_groups()

    if result.get("count", 0) < 1:
        raise AssertionError("No operator groups returned")

    return f"{result['count']} operator groups"


def test_operators():
    result = s.find_operators(
        query="",
        limit=3,
    )

    if result.get("count", 0) < 1:
        raise AssertionError("No operators returned")

    return f"{result['count']} operators"


def main():
    print("\nTOPdesk MCP v36 READ-ONLY SMOKE TEST")
    print("No incidents will be created or modified.")

    run_test("Health", test_health)
    run_test("Known historical incident", test_known_old_incident)
    run_test("Incident number normalization", test_incident_number_formats)
    run_test("Recent incidents", test_recent_incidents)
    run_test("2022 date filter", test_year_2022)
    run_test("2021 date filter", test_year_2021)
    run_test("Oldest accessible incident", test_oldest_incident)
    run_test("Knowledge Base search", test_knowledge_search)
    run_test("Incident categories", test_categories)
    run_test("Operator groups", test_operator_groups)
    run_test("Operators", test_operators)

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")
    print(f"TOTAL: {passed + failed}")

    if failed:
        sys.exit(1)

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()