"""Fill a local development database with made-up records (#41).

It runs only with DJANGO_DEBUG on. The seeding code imports factory_boy
and Faker, which are development dependencies, so it is imported only
after that check: this module stays importable in a production install,
where Django's command discovery loads it.
"""

from argparse import ArgumentParser
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

MIN_PLAYERS = 4
DEFAULT_PLAYERS = 20
_DEV_DEPENDENCIES = ("factory", "faker")


def _is_dev_dependency(name: str | None) -> bool:
    if name is None:
        return False
    return any(
        name == package or name.startswith(f"{package}.")
        for package in _DEV_DEPENDENCIES
    )


class Command(BaseCommand):
    help = (
        "Add made-up Clubs, verified Organizers, Events, Players, and "
        "confirmed Matches for local development. Runs only with "
        "DJANGO_DEBUG on."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--players",
            type=int,
            default=DEFAULT_PLAYERS,
            help=(
                f"How many Players to create (default {DEFAULT_PLAYERS}, "
                f"at least {MIN_PLAYERS})."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev_data runs only with DJANGO_DEBUG on. "
                "It writes made-up data for local development."
            )
        players: int = options["players"]
        if players < MIN_PLAYERS:
            raise CommandError(
                f"--players must be at least {MIN_PLAYERS}, "
                "so a doubles match has enough players."
            )
        try:
            from apps.devdata import seed
        except ModuleNotFoundError as error:
            if not _is_dev_dependency(error.name):
                raise
            raise CommandError(
                "seed_dev_data needs the development dependencies "
                "(factory_boy and Faker). Run `uv sync` to install them."
            ) from error

        summary = seed.seed(players=players)
        self.stdout.write(
            f"Added {summary.players} players, {summary.clubs} clubs, "
            f"{summary.organizers} verified organizers, {summary.events} "
            f"events, and {summary.matches} confirmed matches."
        )
