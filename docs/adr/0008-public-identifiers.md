# 0008. Public identifiers: OPEN Codes

- Status: Accepted
- Date: 2026-11-14

## Context

Players, clubs, events, organizers, and matches need public identifiers that partners, exports, webhooks, and URLs can use (issue #92). Partner mappings, player data exports, and partner databases will store them, so an identifier must never change once issued. The scheme must be fixed before the first Player migration (#19).

The default primary key is a `BigAutoField`. If the row number were the public identifier, anyone could list every player by counting, which works against profile visibility and opt-out. It would also reveal how many players and matches exist.

Players and organizers will read codes aloud and type them. A typo must be rejected, not resolved to another player.

## Decision

- `BigAutoField` stays the internal primary key and the foreign key target. Row ids never appear in the API: no path, query, body, or response carries one. A test walks the OpenAPI document and fails on any integer field named `id`, `pk`, or `*_id`.
- Each public record gets an OPEN Code in a `public_code` column, from the abstract model `apps.public_ids.models.PublicCodeModel`. The column is unique (a database constraint and index) and not editable.
- Format: a type prefix, a hyphen, then the body in groups of 4 characters joined by hyphens. The canonical form is uppercase. Examples (made up): player `P-7K3M-QX9H`, club `C-4HWT-2N8Z`, match `M-9QF6-RD2K-X3BP`.
- Alphabet: Crockford base32, `0123456789ABCDEFGHJKMNPQRSTVWXYZ` (no I, L, O, or U).
- Prefixes: `P` player, `C` club, `E` event, `G` organizer, `M` match.
- Lengths, not counting the prefix: 8 characters (7 random plus 1 check) for players, clubs, events, and organizers; 12 characters (11 random plus 1 check) for matches.
- Check character: Luhn mod 32 over the prefix and the random characters. It catches every single-character substitution, and so a code moved to another type. It catches most swaps of two neighboring characters.
- Generation: the random characters come from `secrets`, never from the row id or the time.
- Registry: every issued code is stored in `IssuedCode`, with a unique constraint. A code is never issued again, even after its record is deleted or opted out. The ORM refuses to change or delete a registry row.
- Collisions: on create, a new code is inserted into the registry inside a savepoint. A unique-constraint collision is retried with a fresh code, up to 5 attempts, then `PublicCodeExhausted` is raised. The record insert runs in the same transaction, so a failed insert also rolls back its registry row.
- A code never changes. `save()` refuses a changed code on an existing record, and refuses a code set by hand on a new one.
- Input normalization, in order: refuse anything that is not ASCII or is longer than 64 characters; uppercase; drop spaces and hyphens; check the prefix (the endpoint's prefix may be omitted, any other prefix is refused); map I and L to 1 and O to 0; refuse characters outside the alphabet; verify the length and the check character. The result is the canonical form.
- API: a path parameter is `Annotated[str, PublicCodePath(CodeType.X)]`. A malformed code and a well-formed code that matches no record both return the same 404 `ErrorResponse`. Neither returns a 422, so a client cannot learn which codes are well formed.

### Collision math

A code with 7 random characters carries 35 bits: about 34 billion codes. With 1 million players issued, a new code hits an existing one about 1 time in 34,000. The retry absorbs that. Five collisions in a row would mean something is wrong. Match codes carry 55 random bits (about 3.6 times 10^16 codes).

### Longer codes later

If a type ever needs more codes, it gets a new, longer length. Existing codes stay valid and are never rewritten. Normalization then accepts every length that type has ever issued. The column's `max_length` is 32 to leave room.

### External IDs

A standard external rating system uses 6-character player IDs. An OPEN Code has a prefix and 8 or 12 characters, so an external ID never has its shape and is refused as malformed, never looked up.

## Consequences

- Partners can store codes forever, and a code cannot be guessed by counting.
- `bulk_create`, `QuerySet.update`, and raw SQL skip code generation and the no-change rule. `bulk_create` without a code fails, because the column is NOT NULL with no default. Create records through `save()` or `objects.create()`.
- The registry grows forever. Its rows are small.
- There is no database trigger on the registry. Raw SQL can delete its rows, so the ORM guard protects only app code.
- Lookups compare the canonical form exactly, so normalization must run first. The path parameter type does that.

## Alternatives considered

- **UUIDs.** Long, hard to read aloud or type, with no check character.
- **Hashids or Sqids of the row id.** Reversible with the salt, and they still leak counts and order.
- **No check character.** A typo could resolve to another player.
- **No registry.** A deleted record's code could be issued again and point a partner's stored mapping at someone else.
- **A pattern in the OpenAPI schema.** Ninja would enforce it with a 422, which tells a client which codes are well formed.
