# CLAUDE.md

This file gives Claude Code guidance for working in this repository.

## What this repository is

The backend for OPEN, the Open Pickleball Evaluation Network: a free, open-source, community-governed pickleball rating network. This repository will hold the services and APIs that store players and matches and serve ratings. The rating math itself lives in the separate `engine` repository.

Planned services, from the project roadmap:

- **Results API:** platforms, clubs, and tournaments submit matches.
- **Ratings and stats API:** any app can read OPEN ratings, history, and stats for free.
- **Organizer tools (backend side):** upload results, confirm starting ratings, review flagged matches.

## Current status

The Django project scaffold exists (`config`, with settings read from the environment, plus `apps/accounts` with the custom email-login user model and the first migration, `apps/audit` with the append-only audit log (`AuditEvent`, `record_event`), `apps/public_ids` with OPEN Codes (`PublicCodeModel`, the `IssuedCode` registry, the `PublicCodePath` path parameter), `apps/players` with `Player` and `PlayerPrivacy` and their services (no API, no admin), `apps/clubs` with `Club`, `Organizer`, `OrganizerMember`, and `ClubRole`, the organizer verification services, and their admin (no API), `apps/events` with `Event` and its admin (no API), `apps/partners` with django-oauth-toolkit's swapped Application model `PartnerApplication` and `ClubApplicationGrant`, and their admin (no API, no approval service yet), `apps/matches` with `Match`, `MatchParticipant`, `Game`, and `MatchFlag`, the score validation service `validate_match`, and the creation service `record_match` with duplicate detection (no API, no admin), django-oauth-toolkit's token and revoke views at `/oauth/token/` and `/oauth/revoke_token/`, `config/api.py` with the django-ninja API mounted at `/api/v1/` with the health checks in `config/health.py` as its only operations so far, the Celery app in `config/celery.py`, configured in the Celery section of `config/settings.py` (four queues, django-celery-beat), static files through WhiteNoise, CORS for `/api/` through django-cors-headers, `gunicorn.conf.py` for serving, and `compose.yaml` for local services), and no OPEN rating is live. The work is planned as GitHub issues grouped into outcome milestones (v0.1 MVP through v0.4), epics with sub-issues, native blocked-by links, and the "OPEN backend" org project board. Issue #1 records the plan's decisions and open questions; other issues cite them as "decisions Qn" or "Fn". Read the relevant ones before starting an issue.

## Stack (decided, see issue #1)

- Python 3.13, managed with uv (`uv.lock` committed)
- Django 5.2 LTS (`Django>=5.2,<5.3`, decision Q1), project package `config`, first-party apps under `apps/`
- django-ninja for the API, mounted at `/api/v1/` with OpenAPI docs; every operation has an explicit `operation_id`
- Postgres (psycopg 3), Valkey as cache and Celery broker (decision Q11)
- Celery with django-celery-beat; queues `default`, `ratings`, `email`, `webhooks`
- Settings from environment variables via django-environ; `.env.example` holds placeholders only
- pytest, pytest-django, pytest-cov, factory_boy; ruff, mypy with django-stubs, pre-commit
- gunicorn serves the app (`gunicorn.conf.py`), WhiteNoise serves static files, django-cors-headers handles CORS
- django-oauth-toolkit 3.4 for partner OAuth2 (decisions Q2, Q3), with local type stubs in `typings/oauth2_provider` (`mypy_path`)
- Deployed on DigitalOcean App Platform (M3)

## Ordering rules

- `AUTH_USER_MODEL` is `accounts.User` (issue #3) and is fixed: never swap it. Other apps reference it through `settings.AUTH_USER_MODEL` for foreign keys and `get_user_model()` in code, never by importing `apps.accounts.models.User`.
- `OAUTH2_PROVIDER_APPLICATION_MODEL` is `partners.PartnerApplication` (issue #22, decision Q3) and is fixed like `AUTH_USER_MODEL`: never swap it. Outside `apps/partners`, reference it through `settings.OAUTH2_PROVIDER_APPLICATION_MODEL` for foreign keys and `oauth2_provider.models.get_application_model()` in code (a type-only import under `TYPE_CHECKING` is fine). django-oauth-toolkit's `0001_initial` has foreign keys to that model without depending on it, so `apps/partners/migrations/0001_initial.py` carries `run_before = [("oauth2_provider", "0001_initial")]`, a hand edit to a generated migration (ADR 0010). A test pins the order.
- The engine is pinned as a git dependency on a tag (decision Q4). It is a demonstration package, so its output stays labeled as demonstration ratings.

## Account emails

- An Account's email is its login. Forms (through `clean()`) and the manager normalize it: NFKC, strip, then lowercase one character at a time.
- The normalized email must be ASCII, at most 254 characters, and a valid address. The field validator and the manager enforce these rules. Keep every new check on the normalized value, not the raw input.
- The database enforces the column length, case-insensitive uniqueness (`Lower("email")`), and ASCII. It does not normalize. Raw writes (`save()` without `full_clean()`, `bulk_create`, `update`) skip normalization, so create Accounts through the manager or a form.
- Find an Account by email (an identity lookup, such as login or linking) only through `get_user_model().objects.get_by_natural_key()` (or `aget_by_natural_key()`), which compares with the unique constraint's own `Lower("email")` expression. Do not use `email__iexact` or an exact match on raw input: on Postgres `iexact` compares `UPPER()`, which can match accounts the constraint treats as distinct.

## Audit log

- Write an `AuditEvent` only through `apps.audit.services.record_event()`, inside the same `transaction.atomic()` as the change it records. Record a delete before calling `delete()`. Build `before` and `after` with `snapshot(instance, fields)`, which takes an explicit field list, so a password hash is never captured by accident. `record_event` redacts values under sensitive key names, but never put a secret, token, recovery code, or the value of an identifying personal data field (ADR 0009) in `before`, `after`, or `reason`.
- Audit rows are append-only. In app code the ORM refuses every change or delete. A database trigger (migration `0002_append_only`) refuses `UPDATE`, `DELETE`, and `TRUNCATE` of a non-empty table. Inside a migration, a historical model gets no ORM guard, so only the trigger protects the rows. The trigger does not stop the table's owner or a database superuser, who can disable it. The runtime database role must not own the table: #103 must make sure of that (a comment there asks for it).
- A new action type is a new `AuditAction` value plus its generated migration. The issue that adds a feature records that feature's events, with a test.
- `flush` (and so the teardown of a transactional test) fails once the audit table has a row. Tests that record events should run in a transaction that rolls back (the default `django_db` mark).
- An event's actor is an Account (`actor_user`), a Partner Application (`actor_application`, `record_event(actor_application=...)`), both, or nobody. `actor_user`, `actor_application`, and `target_content_type` use `PROTECT`: an Account or application that has acted cannot be hard-deleted (deactivate an Account; #29 revokes applications), and a content type an event points at cannot be removed. django-oauth-toolkit's `PartnerApplication.user` cascades, so an Account whose application has acted cannot be hard-deleted either. The same holds for an Account or application that submitted a Match (see Matches). Plan account deletion around this.

## Players

- Create a Player only through `apps.players.services.create_player()`, which also creates its `PlayerPrivacy` row. Change profile fields only through `update_profile()` and privacy settings only through `update_privacy()`. Both refuse any actor but the Player's own active Account, and record one Audit Event when a value changes.
- A profile change records only the changed field names, never a value (ADR 0009). A privacy change records the old and new levels of the changed settings.
- `Player.account` uses `PROTECT`, so an Account with a Player cannot be hard-deleted. #116 decides what Account deletion does with it. `MatchParticipant.player` uses `PROTECT` too, so a Player who has played a Match cannot be deleted.
- In tests, build Players with `PlayerFactory` (`apps/players/tests/factories.py`), which goes through `create_player()`. A raw `Player.objects.create()` has no `PlayerPrivacy` row.
- The Player fields are the ones ADR 0009 allows. Adding a personal data field updates `docs/privacy/personal-data-inventory.md` in the same pull request.

## Clubs and organizers

- A verified Organizer's submissions count as confirmed, so verification is a security-sensitive area (hard rule 8). Change `Organizer.verified_at` and `verified_by` only through `apps.clubs.services.verify_organizer()` and `unverify_organizer()`. They refuse any actor but an active Account with the `clubs.verify_organizer` permission that is not a member of that Organizer, and record one Audit Event when the status changes. The `Organizer.save()` docstring lists the writes that skip them; `bulk_create` and `loaddata` skip them too (see Public identifiers).
- While an Organizer is verified, the Account that verified it cannot become its member (`bulk_create` and `QuerySet.update` skip this check). A verified Organizer cannot be deleted: unverify it first (`QuerySet.delete()` skips this check). An Organizer with an Event or a Partner Application cannot be deleted either, even through `QuerySet.delete()` (see Events, Partner applications). A Club with a Match cannot be deleted (`Match.club` uses `PROTECT`).
- `OrganizerMember.account` uses `PROTECT`, so an Account that is a member cannot be hard-deleted. `Organizer.verified_by` uses `PROTECT` while the Organizer is verified; after that, the verify event's actor keeps the Account row (Audit log). `ClubRole.account` cascades.
- Every Organizer's name may be a person's name, so it is an identifying field. #116 carries out what ADR 0009's Retention section decides for memberships, Club Roles, and Organizer names.
- The permission rules that use these roles are #79. Membership and role changes record no Audit Event until #158 lands. Club Application Grant changes record none yet either (a comment on #158 asks it to cover them).

## Events

- An Event's `kind` is the Match Type its matches count as. Its values are the engine's `MatchType` values except `self_reported`, since self-reported matches have no Event (decision F1). Never add a value the engine lacks.
- `Event.weight` (0.01 to 1.00, default 1.00) is stored but not applied to ratings: the engine takes no per-event weight (openpickleball/engine#30). No backend code may apply it (hard rule 2).
- `Event.organizer` and `Event.club` use `PROTECT`, so an Organizer or Club with an Event cannot be deleted. `Match.event` uses `PROTECT`, so an Event with a Match cannot be deleted.
- Event fields override Django's default messages that include the submitted value: an invalid choice, number, or date, and a foreign key that names no row (whose default names the row id).
- A form that edits an Event subclasses `apps.events.admin.EventAdminForm`, and an override of its `clean()` calls `super().clean()`. The form gives `kind` a message without the value (a ModelForm's choice field repeats it), and its `clean()` clears a date that failed, so the model's order check does not compare the other new date with the stored one.
- Event changes record no Audit Event until #125 lands.
- In tests, build Events with `EventFactory` (`apps/events/tests/factories.py`).

## Matches

- `apps/matches` is the match ledger (hard rule 3). A Match is never edited in place or deleted once counted. #26 adds the change service, its Audit Events, and the full delete and edit guard. Until then `Game.match` and `MatchParticipant.match` use `PROTECT`, so the ORM refuses to delete a Match that has games or participants. A Match with neither can still be deleted, and `save()`, `QuerySet.update`, and raw SQL are not guarded. No backend code changes a Match after creating it until #26 lands.
- The database enforces allowed choice values, exactly one submitter (`submitted_by_user` or `submitted_by_application`), each Player once per Match, game numbers 1 to `MAX_GAMES` with each number once per Match, no negative scores, the `played_at` and `external_id` rules below, and one counted Match per fingerprint (see duplicate detection below). `full_clean()` reports each of these with a plain message, except the game number range, which gives Django's generic constraint message. No model or database rule requires a game, contiguous game numbers, or a pending status on creation. The models check only the score range, not the scoring rules (see the next rule). Confirmation and status changes are #26, which (with #79's permitted submitters, decision F4) owns when a Match is created confirmed.
- Every path that submits a Match creates it through `apps.matches.services.record_match()`, never `Match.objects.create()`. `record_match()` calls `validate_match()` before it writes anything, then checks for duplicates and writes the Match, its participants, games, and flags in one transaction. `validate_match()` holds the score validation rules, such as the game scores (the winner reaches the target and wins by 2 or more, or, past the target, wins by exactly 2), team size per format, no player twice, the allowed best-of and game target, 1 to `MAX_GAMES` games that decide the match, and no future `played_on`. It also applies the defaults for a submission (target 11, side-out) and infers a missing best-of. Add a new score validation rule there, never in a submission path.
- `validate_match` raises one `MatchValidationError` that lists every issue it finds as field, code, and message, the shape of the API's `FieldError`.
- Give `validate_match` one canonical reference per player: resolved Players, or codes already passed through `normalize()`. Use one kind for the whole call. The duplicate and both-teams checks compare references by equality, and a call that mixes kinds fails with `mixed_player_references`.
- `validate_match` sets no upper bound on scores and does not read `played_at`. `Game.full_clean()` refuses a score above the field's limit, and `Match.clean()` ties `played_at` to `played_on`.
- Duplicate detection is a security-sensitive area (hard rule 8). `record_match()` refuses an exact duplicate (a Match that is not voided, from any submitter, with the same two teams in either order, the same `played_on`, and the same game scores) and an `external_id` its Partner Application already used (for a Match in any status). Both raise `DuplicateMatchError` with `kind` and the earlier Match's `existing_code`, and the API turns it into a 409 `ErrorResponse` (`config/api_errors.py`). A near duplicate (same teams and date, other scores) is saved with one `MatchFlag(reason=possible_duplicate, duplicate_of=...)` per earlier Match. Advisory locks serialize submissions of one lineup and date, and of one external id, so concurrent submissions are caught too.
- `Match.fingerprint` is the SHA-256 of the teams, date, and scores (`match_fingerprint()`). A partial unique constraint allows one Match per non-blank fingerprint unless it is voided, so the same teams playing the same scores twice on one day count as one match (`sequence` is not in the fingerprint). A Match written outside `record_match()` has a blank fingerprint and escapes the exact check, though a later submission flags it as a near duplicate. The factories set the fingerprint when a Match has participants and games.
- A `MatchFlag` holds a Match for Organizer review (CONTEXT.md, Flagged Match) and is its own row, so review (#40) never edits the Match. #26 and #44 must not count a Match with an open flag. Both links use `PROTECT`, so a flagged Match cannot be deleted.
- `played_at` is stored with `played_at_utc_offset` (minutes east of UTC where the match was played), because Postgres keeps a timestamptz in UTC and drops its offset. Both are set or both empty, and `played_at` shifted by the offset must fall on `played_on` (a check constraint). `clean()` refuses a `played_at` without a time zone. A plain `save()` stores a naive value as UTC, so always pass an aware datetime.
- `external_id` is a Partner Application's own id for the Match. Only an application's Match has one, unique per application. A check constraint refuses leading or trailing whitespace (every character `str.isspace()` matches).
- `location` is a place's name, such as a court or park, never a street address, postcode, or exact location (ADR 0009). Nothing enforces this.
- Choice values follow the engine: `ScoringType` has `open_engine.ScoringType`'s values, `GameTarget` the points in `ALL_GAME_FORMATS`, and `MatchFormat` the two base `RatingFormat` values. `BestOf` is 1, 3, or 5 (decision F15). Import these and the limits (`MAX_GAMES`) from `apps.matches.models`; never redefine them. The match type is not stored: #44 derives it.
- `Match.submitted_by_user`, `submitted_by_application`, `event`, and `club`, and `MatchParticipant.player`, use `PROTECT`. An Account that submitted a Match, an Account whose application submitted one, and a Player who played one cannot be hard-deleted. #116 must plan for this.
- Fields on these models override Django's messages that include the submitted value, including a non-integer foreign key id, whose default message comes from the target's primary key field.
- In tests, build Matches with `MatchFactory` and `DoublesMatchFactory` (`apps/matches/tests/factories.py`), with traits `best_of_1`, `best_of_3`, `best_of_5`, `side_out`, `rally`, and `by_application`. Pass `games=False` or `participants=False` to skip the generated rows.

## Partner applications

- `PartnerApplication` (`apps/partners`) is the OAuth client a Partner uses. Approval is security-sensitive (hard rule 8): only #29's approval service writes `approved_at` and `approved_by`, through `update_fields`. A new application starts unapproved: `save()` refuses a new one that is already approved. `is_sandbox` defaults to true, but staff can change it; #29 and #74 decide how it is enforced. A full `save()` of an existing application never writes the approval fields. An Organizer with an application cannot be deleted (`organizer` uses `PROTECT`). The `save()` docstring lists the writes that skip these rules. An application that submitted a Match cannot be deleted (`Match.submitted_by_application` uses `PROTECT`).
- A new application is always inserted: `save()` refuses `force_update` or `update_fields` on it, so a hand-built instance with another row's pk cannot overwrite that row.
- The client secret is stored hashed: check constraints refuse `hash_client_secret=False` and a blank secret. Any write of `client_secret` must be a raw secret: not blank, and not anything `identify_hasher` recognizes, because django-oauth-toolkit stores such a value as is, and when its hash check fails on it, compares it as plain text. A new raw secret is hashed and replaces the stored one, but a hash-shaped or deferred value is never written back: a full save, or `update_fields` naming `client_secret` (as `update_or_create` always does), leaves it out. The admin shows the generated secret only on the add form. Raw writes (`QuerySet.update`, `bulk_create`, `loaddata`, raw SQL) skip the model's checks; the check constraints still apply.
- Only `/oauth/token/` and `/oauth/revoke_token/` are mounted (`apps/partners/urls.py`). They are plain Django views outside the ninja API: errors use OAuth's JSON format, not `ErrorResponse`, and CORS does not cover them. Until #27, #28, and #29 land, the token endpoint does not check approval, sandbox status, or which scopes each application may have, and no API operation accepts a token.
- `OAUTH2_PROVIDER` in settings turns on every RFC 9700 behavior django-oauth-toolkit offers (tokens hashed at rest, https redirect URIs only). Turning one off makes `check --deploy` report a warning or an error, and `config/tests/test_settings.py` fails on either. Scopes, token lifetimes, and grant types are #28.
- `PartnerApplication.__str__` returns its `client_id`, and `ClubApplicationGrant.__str__` returns the Club's OPEN Code and the `client_id`. The application's `name` is shown only in the admin.
- In tests, build them with `PartnerApplicationFactory` and `ClubApplicationGrantFactory` (`apps/partners/tests/factories.py`).

## Public identifiers

- A model whose records have a public identity (Player, Club, Event, Organizer, Match) inherits `apps.public_ids.models.PublicCodeModel` and sets `public_code_type`. The system check `public_ids.E001` reports a concrete subclass without one. ADR 0008 records the scheme.
- Codes are created only by `save()` (or `objects.create()`), which issues the code, records it in `IssuedCode`, and refuses to change it later. Fixtures (`loaddata`), `bulk_create`, `QuerySet.update`, and raw SQL skip all of this and must not set codes. To copy a record, set `public_code = None`, `pk = None`, and `_state.adding = True` before saving. Saving a deleted record raises.
- Never expose or accept a row id in the API. A path parameter that names a record is `Annotated[str, PublicCodePath(CodeType.X)]`, and the view looks the record up with `get_by_public_code()`. `PublicCodePath` is for path parameters only, not body or response fields. A test fails on any numeric `id`, `pk`, `*_id`, `*Id`, or plural of these in the OpenAPI document, hidden operations included.
- To read a code from other input (such as a CSV column), use `apps.public_ids.codes.normalize()`, then look up the canonical form.

## Personal data

- ADR 0009 sets what OPEN collects. Every model field that holds personal data is listed in `docs/privacy/personal-data-inventory.md`. Add, change, or remove its entry in the same pull request as the field.
- Never store a full birthdate (store birth year and month only), a raw gender, a street address, a phone number, or payment data.
- Only the player sets their own display name, legal name, birth year and month, gender division, and city and region. Others may only remove them (#114, #116).
- Every path that creates a Player refuses anyone under 13, and a new Player always has a birth year and month. Players aged 13 to 17 are left out of all partner sharing. A Player whose birth year and month were removed (#114, #116) is excluded from all partner sharing, permanently.
- The identifying personal data fields are email, display name, legal name, birth year and month, gender division, city and region, an Organizer's name (`clubs.Organizer.name`), External IDs (#49), and platform player IDs (#82). An Audit Event about one of them records the field's name, never its value. Account deletion is wider: it removes all personal data except what ADR 0009's Retention section keeps.
- No model's `__str__` returns an identifying field, so the admin log's `object_repr` and admin messages never hold one (a Player's, a Club's, an Organizer's, an Event's, and a Match's return their OPEN Code, a Match Participant's and a Game's their Match's OPEN Code with the team or game number, and a Partner Application's its `client_id`). `accounts.User.__str__` returns the email, the known exception: #116 clears the admin log entries tied to a deleted Account.

## API

- There is one `NinjaAPI`, `api` in `config/api.py`, mounted at `/api/v1/`. Each app adds its operations to a `Router` in `apps/<app>/api.py`, and `config/api.py` mounts that router. The `config/api.py` docstring shows how. The health checks are the exception: their router is in `config/health.py`. The OAuth endpoints under `/oauth/` are not part of this API (see Partner applications).
- Every operation passes an explicit `operation_id`. It names the method in the generated client, so never change one for a rename. Building the OpenAPI document raises an error for an operation in the document that has none, and a test checks every operation.
- Validation errors, an unparsable body, `Http404`, and `HttpError` come back as `ErrorResponse` (`config/api_errors.py`), and validation errors return 422. With DEBUG off, any other exception goes to Django, which returns its own HTML error page (a 500, or another status for exceptions Django maps, such as 403 for `PermissionDenied`). Raise `HttpError` or `Http404` instead of returning an error body by hand (the readiness check's 503 is not an error: it is a status report with its own documented schema), and use `HttpError(403, ...)`, never Django's `PermissionDenied`. Never declare a different 422 schema on an operation that takes input: building the document raises an error if you do. ADR 0005 records the versioning and error format.
- Never put the submitted value in a validation message. The 422 response returns the message to the client.
- A code path parameter (`PublicCodePath`) that fails returns 404, not 422, which narrows the 422 rule for that parameter (ADR 0008). With the other inputs valid, a malformed code and an unknown one get the same 404. With another input invalid, a well-formed code gets that input's 422 whether or not a record has it, so no response reveals that a record exists.

## Settings

- `config/settings.py` reads its deployment values from the environment (and an optional `.env`). Read a new variable with the helpers there (`_raw`, `_required`, `_list`), not django-environ's `Env` getters: those treat a value starting with `$` as a reference to another variable, which silently swaps secrets and URLs.
- The errors that `config/settings.py` raises for a bad or missing variable name the variable and never echo its value. django-environ's own `.env` reader is the exception: it logs a malformed `.env` line in full.
- With DEBUG off, settings turn on the https redirect, secure cookies, and HSTS (see ADR 0004). The test run applies a fixed set of overrides (the list is `_TEST_OVERRIDES` in `config/test_runner.py`), so tests run over plain http, run Celery tasks eagerly with errors propagated, and need no cache server, no broker, and no `collectstatic`. pytest gets these overrides from `config/settings_test.py`, and `manage.py test` gets them from `config/test_runner.py`. Keep the two sets identical (a test fails if they drift). pytest's set lives in the settings module, so every process that loads it, parallel workers included, gets it; the runner applies its set in spawned parallel workers through `process_setup` (forked workers inherit it).
- `REDIS_URL` takes only the form `redis://[USER:PASSWORD@]HOST[:PORT][/DB]`, or `rediss://` for TLS: a lowercase scheme, a numeric database, and no query string or fragment. Settings refuse at startup a URL that breaks these rules. redis-py lets a query string override settings, certificate verification included, so set connection and TLS options in settings, never in the URL. Percent-encode any URL-reserved character in the password.
- Celery's broker is `REDIS_URL`, the same Valkey database as the cache, so clearing the cache (`RedisCache.clear()` runs FLUSHDB) also drops queued tasks. Settings refuse to start when `CELERY_BROKER_URL`, `CELERY_BROKER_READ_URL`, `CELERY_BROKER_WRITE_URL`, or `CELERY_RESULT_BACKEND` is set to a non-empty value in the environment (or `.env`): Celery would read it ahead of settings and skip the `REDIS_URL` checks. Set broker and TLS options in settings.
- Celery has four queues: `default`, `ratings`, `email`, and `webhooks` (ADR 0006). `CELERY_TASK_ROUTES` routes a task by the start of its name: tasks in `apps.ratings.tasks`, `apps.emails.tasks`, and `apps.webhooks.tasks` go to the matching queue, and every other task goes to `default`. A task given an explicit name outside its module's pattern goes to `default`. Sending to a queue that is not declared raises `QueueNotFound`. A new queue needs a declaration, a route, and the `-Q` list of every worker command (compose, docs, deploy).
- Tasks are acknowledged late, so a crash redelivers them: every task must be safe to run twice. Keep each task's time limit, and any countdown or ETA, below the broker's one-hour visibility timeout, or the task runs twice. Pass ids, not model instances, and keep secrets and personal data out of task arguments and return values (the worker logs return values).
- Static files use WhiteNoise's compressed manifest storage. With DEBUG off, every page that uses `{% static %}` (the admin, `/api/v1/docs`) returns a 500 until `collectstatic` has run, `runserver` and the compose `web` profile included. WhiteNoise sends no CORS header on static files.
- CORS covers `/api/` paths only, for the exact origins in `CORS_ALLOWED_ORIGINS` (empty by default, so no origin is allowed). Settings refuse at startup an entry that is not exactly `scheme://host[:port]`: no wildcard, path, trailing slash, or default port. `CORS_ALLOW_CREDENTIALS` and `CORS_ALLOW_ALL_ORIGINS` stay False, and `CORS_ALLOW_ALL_ORIGINS` is never read from the environment.
- gunicorn reads `PORT` and `WEB_CONCURRENCY` from the process environment only, never from `.env`. gunicorn parses `WEB_CONCURRENCY` itself before `gunicorn.conf.py` runs, so its own error reports a non-integer value. The config turns off gunicorn's control socket.
- Email prints to the console when DEBUG is on and is discarded when DEBUG is off, until #35 adds a real provider. Never let a DEBUG-off environment print or log email: messages carry recipient addresses and, once auth lands, reset tokens.

## Commands

Fill these in as the M0 issues land. A command for a tool or service that has not landed yet fails until its issue does. Every command that loads settings needs the settings variables. That includes `check`, `mypy`, and the pre-commit mypy hook (the django-stubs plugin imports `config.settings`). Copy `.env.example` to `.env` first; process environment values win over it. `migrate`, the tests, `runserver` (which checks migrations at startup), and `celery beat` (which needs the migrations applied) need the Postgres that `DATABASE_URL` names. A Celery worker needs the Valkey that `REDIS_URL` names. `docker compose up -d --wait` starts it and Valkey from `compose.yaml` and waits until both are healthy; the `.env.example` URLs point at them. Docker Compose also reads `.env` and treats a `$` in a value as a variable reference, so wrap a secret key that contains `$` in single quotes. `uv run pytest` runs the suite with coverage and fails when total coverage is below `fail_under` in `pyproject.toml`. The floor counts all of `apps` and `config`, so a narrow run (one file or a `-k` selection) usually fails it even when every test passes: add `--no-cov` to those runs. To build test records, prefer the factory_boy factories (such as `UserFactory` in `apps/accounts/tests/factories.py`), which fill in made-up Faker data. Expected shape:

```bash
cp .env.example .env                      # local settings; never commit .env
uv sync                                   # install from uv.lock
uv run pre-commit install                 # git hooks: ruff, mypy, hygiene checks
uv run python manage.py check             # Django system checks, no database needed
docker compose up -d --wait               # local Postgres and Valkey, healthy
uv run python manage.py migrate
uv run python manage.py runserver
uv run celery -A config worker -Q ratings,email,webhooks,default -l info   # background tasks, every queue
uv run celery -A config beat -l info      # periodic tasks; run one beat only, after migrate
uv run python manage.py collectstatic --noinput   # before serving with DEBUG off
uv run gunicorn                           # serve with gunicorn.conf.py (PORT, WEB_CONCURRENCY)
docker compose --profile web up -d --wait # optional: the app, a worker, and beat in containers, instead of on the host (beat waits for migrate)
docker compose down -v                    # stop and delete local data
uv run pytest                             # tests with coverage (Postgres, not SQLite)
uv run pytest --no-cov apps/accounts      # part of the suite, without the coverage floor
uv run ruff check . && uv run ruff format --check .
uv run mypy .                             # strict; needs the settings variables
uv run python manage.py makemigrations --check --dry-run   # CI fails on missing migrations
uv run pre-commit run --all-files
```

`.github/workflows/ci.yml` runs on every pull request and every push to `main`, in three jobs: `lint` (`ruff check`, `ruff format --check`, and the pre-commit hygiene hooks), `types` (`mypy .`), and `test` (`manage.py check`, `makemigrations --check --dry-run`, and `pytest` with the coverage floor, against a Postgres service). The job names are meant to be required status checks on `main` alongside `sign-off`, so a change that renames a job must also update the `main` ruleset.

## Documentation

- `README.md`: public overview, setup, and contribution pointers.
- `CONTRIBUTING.md`: this repository's contribution workflow (pull requests, DCO, code style, tests, migrations, good first issues). It adds to the org guide.
- `CONTEXT.md`: the domain language (Match, Ledger, Replay, Rating Format, Reliability, and so on). Read it before naming models, endpoints, or fields.
- `docs/adr/`: architecture decision records. Check here before changing a decision, and add a record when you make one.
- `docs/privacy/personal-data-inventory.md`: every personal data field, with purpose, visibility, retention, and encryption (ADR 0009).
- GitHub issue #1: the backend plan's decisions (Q1 to Q16, F1 to F11) and checked package versions.
- Organization-wide policy lives in the `openpickleball/.github` repository: charter, governance, roadmap, contributing guide, security policy, licensing. A local checkout may exist at `../OPEN-pickleball`.
- The reference engine may be checked out at `../OPEN-engine`. Its module docstring in `src/open_engine/engine.py` lists production requirements the backend must meet.

## Hard rules

1. **No real player data, anywhere.** Not in code, fixtures, seed scripts, migrations, logs, issues, pull requests, or screenshots. Use made-up or properly de-identified data. `.gitignore` excludes local data directories and database files; keep it that way.
2. **Do not reimplement rating math.** The backend calls the engine. If a calculation seems wrong or missing, the fix belongs in the engine or the rating spec, not here.
3. **The match ledger is append-only.** Corrections are new records that reference the old one, never in-place edits or deletes of counted matches. Authoritative ratings come from a deterministic replay of the ledger; live updates between replays are provisional and must be labeled as such.
4. **Store replay provenance.** Persist each replay's `as_of` date, config version, and config fingerprint so any published rating can be reproduced.
5. **External ratings are a seed only.** An imported rating initializes a player and needs verified identity and evidence. It can never overwrite an OPEN-earned rating once OPEN matches exist. Show imported reliability separately from OPEN-earned reliability.
6. **Do not name competing rating systems** in code, docs, issues, or comments. Say "standard external rating system" or "external rating".
7. **Charter limits.** No paid tiers, premium features, ads, or payment flows. Players can always export their data. Do not build anything that conflicts with the [mission charter](https://github.com/openpickleball/.github/blob/main/CHARTER.md).
8. **Security-sensitive areas:** score confirmation, organizer verification, duplicate detection, identity linking, and anything that lets one party change another player's rating. Treat bypasses here as security bugs, not feature gaps.

## Contribution conventions

- Every commit needs a DCO sign-off (`git commit -s`). CI (`.github/workflows/dco.yml`) rejects pull requests with unsigned commits. That check runs only on pull requests, so commits pushed straight to `main` must be signed off by hand.
- Founding phase: repository admins may push directly to `main` while the project is getting established. Everyone else, and admins once this phase ends, uses one change per pull request, linked to an issue. Add or update tests and docs when behavior changes.
- `.github/CODEOWNERS` makes the maintainers team the owner of every path. When an app for a security-sensitive area (hard rule 8) or the match ledger lands, give its directory its own entry, owned by the maintainers team, in the same pull request. A test requires every CODEOWNERS path to match a tracked file or a directory that holds one.
- The `.editorconfig` Python settings (indent and line length) must agree with ruff format. A test compares them with ruff's resolved settings, so change both together.
- License: AGPL-3.0-or-later for this repository. API specifications are Apache-2.0 and published separately, so do not place OpenAPI specs here as the canonical copy.
- Before proposing a feature, ask whether it makes the standard more accurate, more trusted, or easier to adopt. If not, it probably belongs in a partner's product.

## Git exception

This section overrides a contributor's global no-commit rule for the `/work-issue` workflow only.

- The workflow may commit (`git commit -s`, with explicit paths) and push, but only on the `issue-<N>-*` branch it creates or resumes.
- After a rebase it may push that branch with `--force-with-lease`. It never force-pushes any other branch.
- It may open a pull request against `main`, edit its description, label it (creating the ready label if it does not exist), and reply to review comments on it.
- It never commits or pushes to `main`, never merges, and never enables auto-merge. A human reviews and merges every pull request.

## Writing style

Docs in this project use plain, short sentences. No emojis and no em dashes. Prefer "player", "match", and "organizer" over generic words like "user" or "entity" (see `CONTEXT.md`).
