# Personal data inventory

This file lists every field in which OPEN stores personal data. It is the source for the privacy policy. [ADR 0009](../adr/0009-personal-data.md) sets the rules.

Personal data means data about an identifiable person, including any data linked to a Player or an Account.

A pull request that adds, changes, or removes a personal data field updates this file in the same pull request. #115 adds a check for it.

## In the code today

| Model and field | Purpose | Who can see it | Retention | Encrypted |
| --- | --- | --- | --- | --- |
| `accounts.User.email` | Login and account email (ADR 0003). | The player, and staff whose role needs it. Never returned by any API except to the Account itself. | Until Account deletion (#116). | No. Login lookups compare it (ADR 0003). |
| `accounts.User.password` | Login. Only Django's salted hash is stored. | Nobody. The hash is not readable as a password. | Until Account deletion (#116). | Hashed, not encrypted. |
| `accounts.User.last_login`, `accounts.User.date_joined` | Account security and support. | Staff whose role needs it. | Until Account deletion (#116). | No. |
| `accounts.User.is_active`, `is_staff`, `is_superuser`, `groups`, `user_permissions` | Access control. Linked to a person, so they count. | Staff whose role needs it. | Until Account deletion (#116). | No. |
| `sessions.Session.session_data` (Django sessions) | Holds the signed-in Account's id and other session values. | Nobody through the app. | Until it expires. A scheduled task removes expired sessions (#116). | No. |
| `admin.LogEntry` (`user`, `object_repr`, `change_message`) | Django admin history. The `object_repr` of an Account is its email address (`User.__str__` returns it). | Staff. | Until Account deletion clears it (#116). | No. |
| `audit.AuditEvent` (`actor_user`, `target_content_type` and `target_object_id`, `before`, `after`, `reason`) | Who changed what. Never holds a personal data field's value (ADR 0009). | Staff whose role needs it. | Kept indefinitely (append-only, ADR 0007). | No. |

### Not personal data

These were checked and hold no personal data on their own:

- `public_ids.IssuedCode` (`code`, `issued_at`): the registry of issued OPEN Codes. It has no link to the record (ADR 0008).
- django-celery-beat's tables (`PeriodicTask`, the schedule tables): periodic task definitions. Task arguments must never carry personal data (`CLAUDE.md`, Settings).
- Django's `auth.Permission`, `auth.Group` (`name`), and `contenttypes.ContentType`.

## Planned

These fields do not exist yet. The issue that adds a field moves its row to the table above.

| Model and field | Purpose | Who can see it | Retention | Encrypted |
| --- | --- | --- | --- | --- |
| Player display name (planned, #19) | The name a Player shows to others. Required. | Every signed-in Account, and Partners except for players aged 13 to 17. | Until Account deletion (#116). | No. It is public within OPEN. |
| Player legal name (planned, #19) | Identity checks and Organizer verification. Optional. | The player, and staff whose role needs it, with an Audit Event each time (#115). Returned only to the player (own profile, data export #39). | Until Account deletion (#116). | Yes (#115). |
| Player birth year and birth month (planned, #19, #114) | Age Group, age divisions, and the 13-and-older rule. Required. Never the day. | The player, and staff whose role needs it, with an Audit Event (#115). Others see an Age Group. Never returned to Partners. | Until Account deletion (#116). | Yes (#115). |
| Player gender division (planned, #19) | Gender divisions and the gender-specific Rating Formats. Men's, women's, or empty. Optional. | Shown only where a division needs it, never as a profile field. | Until Account deletion (#116). | Yes (#115). |
| Player city and region (planned, #19) | A profile detail. Optional. | Set by the player's privacy settings (#19). Most restrictive by default for players aged 13 to 17. | Until Account deletion (#116). | No. |
| Player home club (planned, #20) | A profile detail. | Set by the player's privacy settings (#19). Most restrictive by default for players aged 13 to 17. | Until Account deletion (#116). | No. |
| Player privacy settings (planned, #19) | Who sees the other profile details. | The player, and staff whose role needs it. | Until Account deletion (#116). | No. |
| Player OPEN Code, `public_code` (planned, #19) | The Player's public identifier (ADR 0008). | Public within OPEN. | Kept with the Player in the Ledger. The code is never issued again (ADR 0008). | No. |
| External rating reference: external player ID, external rating, external reliability, attestation (planned, #49, decision F14) | Seed a Player from a standard external rating system. | Set by #49. | Set by #49. | Set by #49. |
| Platform player IDs, `PlatformPlayerLink` (planned, #82) | Map a Partner's player ID to a Player. | Set by #82. Never shared with Partners for players aged 13 to 17. | Set by #82. | Set by #82. |
| Log in with OPEN grants and tokens (planned, #22, #75) | Partner authorizations. Tokens are secrets. | Tokens are never shown. Otherwise set by #75. | Set by #75. | Set by #22 and #75. |
| allauth email addresses and sessions (planned, #30) | Login, email verification, and sessions. Any IP address or user agent it stores goes here when it lands. | Set by #30. | Until Account deletion (#116). Expired sessions are removed by a scheduled task (#116). | Set by #30. |
| Data export files (planned, #39) | The player's copy of their data. | The player only. | Deleted when the download link expires. | Set by #39. |
| Matches and Ratings linked to a Player (planned, #23 onward) | The Ledger and the ratings pipeline. | Display name and current Ratings: every signed-in Account (ADR 0002). Other details: set by the player's privacy settings (#19). | Kept in the Ledger after Account deletion, with the personal data removed (ADR 0002, hard rule 3). | Set by #23. |

## Not collected

[ADR 0009](../adr/0009-personal-data.md) rules these out. Adding one needs a new ADR.

- Payment data, such as cards and billing addresses.
- Street address, postcode, or exact location.
- Full birthdate (the day).
- Raw gender identity.
- Phone number.
