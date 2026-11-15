"""partners' first migration runs before django-oauth-toolkit's.

django-oauth-toolkit's 0001 has foreign keys to the swapped Application
model but no dependency on it, so only ``run_before`` orders the two.
"""

from django.db.migrations.loader import MigrationLoader

PARTNERS_FIRST = ("partners", "0001_initial")
OAUTH_FIRST = ("oauth2_provider", "0001_initial")


def _forward_plan() -> list[tuple[str, str]]:
    loader = MigrationLoader(None, ignore_no_migrations=True)
    plan: list[tuple[str, str]] = []
    for node in loader.graph.leaf_nodes():
        for key in loader.graph.forwards_plan(node):
            if key not in plan:
                plan.append(key)
    return plan


def test_partners_runs_before_oauth2_provider() -> None:
    plan = _forward_plan()

    assert plan.index(PARTNERS_FIRST) < plan.index(OAUTH_FIRST)


def test_oauth2_provider_depends_on_partners() -> None:
    loader = MigrationLoader(None, ignore_no_migrations=True)

    assert PARTNERS_FIRST in loader.graph.node_map[OAUTH_FIRST].parents
