# Personal data inventory

This file lists every field in which OPEN stores personal data. It is the source for the privacy policy. [ADR 0009](../adr/0009-personal-data.md) sets the rules.

Personal data means data about an identifiable person, including any data linked to a Player or an Account.

A pull request that adds, changes, or removes a personal data field updates this file in the same pull request. #115 adds a check for it.

## In the code today

| Model and field | Purpose | Who can see it | Retention | Encrypted |
| --- | --- | --- | --- | --- |
| `accounts.User.email` | Login and account email (ADR 0003). | The player, and staff whose role needs it. Never returned by any API except to the Account itself. | Until Account deletion (#116). | No. Login lookups compare it (ADR 0003). |
| `accounts.User.password` | Login. Only Django's salted hash is stored. | Nobody. The hash is not readable as a password. | Until Account deletion (#116). | Hashed, not encrypted. |
| `accounts.User.last_login`, `accounts.User.date_joined` | Account security and support. | Staff whose role needs it. | Until Account deletion (#116), except on a kept Account row (an Account that has acted, ADR 0007's `PROTECT`, or that has a Player, `players.Player.account`'s `PROTECT`). An Account that verified an Organizer has acted. They are not identifying fields and stay on a kept row. #116 decides whether to reset them. | No. |
| `accounts.User.is_active`, `is_staff`, `is_superuser`, `groups`, `user_permissions` | Access control. Linked to a person, so they count. | Staff whose role needs it. | Until Account deletion (#116), except on a kept Account row: an Account that has acted is kept as a deactivated row with its identifying fields cleared (ADR 0007's `PROTECT`). An Account with a Player cannot be hard-deleted either (`players.Player.account` uses `PROTECT`), nor can an Organizer Member until #116 removes the membership (`clubs.OrganizerMember.account` uses `PROTECT`). Any other Account row may be deleted. #116 decides. | No. |
| `sessions.Session.session_data` (Django sessions) | Holds the signed-in Account's id and other session values. During signup it may briefly hold the signup birth year and month, until the Player is created or the session ends (#114). | Nobody through the app. | Until it expires, or until Account deletion, which deletes the Account's sessions (#116). A scheduled task removes expired sessions (#116). | No. |
| `admin.LogEntry` (`user`, `object_repr`, `change_message`) | Django admin history. No model's `__str__` returns an identifying field (ADR 0009), so `object_repr` holds none, except an Account's: `User.__str__` returns its email address. A Player's, Club's, and Organizer's `object_repr` is its OPEN Code (#19, #20). An Organizer Member or Club Role appears in its parent's `change_message` as its Organizer's or Club's OPEN Code and the role. | Staff. | Every entry tied to an Account (its own, and any for a record that belongs to it) is cleared at Account deletion (#116). | No. |
| `audit.AuditEvent` (`actor_user`, `target_content_type` and `target_object_id`, `before`, `after`, `reason`) | Who changed what. Never holds the value of an identifying personal data field, External IDs and platform player IDs included (ADR 0009). Other values are recorded: Rating and Match changes (ADR 0007), permission changes, privacy setting changes (`privacy.change`, the old and new levels), and Organizer verification (`organizer.verify` and `organizer.unverify`, the old and new `verified_at` and `verified_by`). A Player profile change (`player.profile_change`) records only the changed field names. | Staff whose role needs it, and the player for events about them, through the data export (#39). | Kept indefinitely (append-only, ADR 0007). | No. |
| `players.Player.account` | Links the Player to the one Account that created it (ADR 0002). | Staff whose role needs it. Never returned by the API as a row id. | The Player is kept at Account deletion (`PROTECT`, ADR 0002). #116 decides what the link becomes. | No. |
| `players.Player.display_name` | The name a Player shows to others. Required. | As ADR 0002 sets out: once Ratings are published, for a Player whose Account is active, every signed-in Account. Partners too, except for players aged 13 to 17. | Until Account deletion (#116). | No. It is public within OPEN. |
| `players.Player.legal_name` | Identity checks and Organizer verification. Optional. | The player, and staff whose role needs it, with an Audit Event each time (#115). Returned only to the player (own profile, data export #39). | Until Account deletion (#116). | Not yet. #115 encrypts it. |
| `players.Player.birth_year`, `players.Player.birth_month` | Age Group, age divisions, and the 13-and-older rule (#114). Required. Never the day. | The player, and staff whose role needs it, with an Audit Event (#115). Others see an Age Group. Never returned to Partners. | Until Account deletion (#116). | Not yet. #115 encrypts them. |
| `players.Player.gender_division` | The men's and women's doubles Rating Formats and mixed doubles eligibility. Men's, women's, or empty. Optional. | Not shown as a profile field. A Rating in `doubles_men` or `doubles_women` reveals it (accepted, ADR 0009). | Until Account deletion (#116). | Not yet. #115 encrypts it. |
| `players.Player.city`, `players.Player.region` | Helps signed-in players tell apart players with the same display name, and find players near them. Optional. | Set by `city_region_visibility` in the player's privacy settings. Most restrictive by default for players aged 13 to 17 (#114). | Until Account deletion (#116). | No. |
| `players.Player.public_code` | The Player's OPEN Code, its public identifier (ADR 0008). `Player.__str__` returns it. | Public within OPEN. | Kept with the Player in the Ledger. The code is never issued again (ADR 0008). | No. |
| `clubs.Organizer.name` | The name an Organizer runs events under. It may be a person's name, so it is an identifying field (ADR 0009). | Staff whose role needs it. Later APIs that show it are set by their issues. Never in `__str__`, admin messages, or Audit Events. | Until the Organizer is deleted. For an Organizer that is one person, #116 removes it at Account deletion and decides how to tell such an Organizer apart (ADR 0009). `OrganizerMember.account` uses `PROTECT`, so the Account cannot be hard-deleted while it is a member. | No. |
| `clubs.Organizer.public_code` | The Organizer's OPEN Code (ADR 0008). `Organizer.__str__` returns it. For an Organizer that is one person, it points to that person. | Staff, through the admin. Later APIs that show it are set by their issues. | Kept with the Organizer. #116 decides what happens to an Organizer that is one person. The code is never issued again (ADR 0008). | No. |
| `clubs.Organizer.verified_at`, `clubs.Organizer.verified_by` | Organizer verification: when, and which Account with the `clubs.verify_organizer` permission verified it. Each change records an Audit Event. | Staff whose role needs it. | On the Organizer, until unverified or the Organizer is deleted. The verification Audit Events keep both values (append-only, ADR 0007). `verified_by` uses `PROTECT`. At Account deletion the verifying Account has acted, so its row stays with its identifying fields cleared, and `verified_by` keeps pointing at it (ADR 0009). | No. |
| `clubs.OrganizerMember` (`account`, `role`) | Which Accounts act for an Organizer, and as admin or match manager. | Staff whose role needs it. | Until removed, or at Account deletion (#116). `account` uses `PROTECT`, so #116 removes the membership first. | No. |
| `clubs.ClubRole` (`account`, `role`) | Which Accounts are admins or match managers of a Club. | Staff whose role needs it. | Until removed, or at Account deletion (#116). `CASCADE` covers an Account that is hard-deleted. | No. |
| `players.PlayerPrivacy` (`city_region_visibility`, `match_history_visibility`, `rating_history_visibility`, `stats_visibility`, `home_club_visibility`) | Who sees the other profile details: signed-in players, or only the player. Each starts at signed-in players. There is no setting for the display name or current Ratings (ADR 0002). A change records an Audit Event with the old and new levels. | The player, and staff whose role needs it. | Until Account deletion (#116). | No. |

### Not personal data

These were checked and hold no personal data on their own:

- `public_ids.IssuedCode` (`code`, `issued_at`): the registry of issued OPEN Codes. It has no link to the record (ADR 0008).
- django-celery-beat's tables (`PeriodicTask`, the schedule tables): periodic task definitions. Task arguments must never carry personal data (`CLAUDE.md`, Settings).
- `clubs.Club` (`name`, `city`, `region`, `public_code`): a Club is a place or group, not a person.
- Django's `auth.Permission`, `auth.Group` (`name`), and `contenttypes.ContentType`.

## Planned

These fields do not exist yet. The issue that adds a field moves its row to the table above.

| Model and field | Purpose | Who can see it | Retention | Encrypted |
| --- | --- | --- | --- | --- |
| Player home club (planned, #157) | Shows which club a player plays at (#157). | Set by `home_club_visibility` in the player's privacy settings. Most restrictive by default for players aged 13 to 17 (#114). | Until Account deletion (#116). | No. |
| External rating reference: External ID, external rating, external reliability, attestation (planned, #49, decision F14) | Seed a Player from a standard external rating system. The External ID is an identifying field: an Audit Event never holds its value (ADR 0009). | The entered rating and reliability: the player and moderators only, labeled "self-reported", never shown publicly as the external system's rating (#49). Otherwise set by #49. | Until Account deletion (#116). Otherwise set by #49. | Set by #49. |
| Platform player IDs, `PlatformPlayerLink` (planned, #82) | Map a Partner's player ID to a Player. An identifying field: an Audit Event never holds its value (ADR 0009). | Set by #82. Never shared with Partners for players aged 13 to 17. | Until Account deletion (#116). Otherwise set by #82. | Set by #82. |
| Log in with OPEN grants and tokens (planned, #22, #75) | Partner authorizations. Tokens are secrets. | Tokens are never shown. Otherwise set by #75. | Until Account deletion (#116). Otherwise set by #75. | Set by #22 and #75. |
| allauth email addresses and sessions (planned, #30) | Login, email verification, and sessions. Any IP address or user agent it stores goes here when it lands. | Set by #30. | Until Account deletion (#116). Expired sessions are removed by a scheduled task (#116). | Set by #30. |
| Who confirmed or disputed a Match (planned, #26) | Confirmation of reported scores. | Set by #26. | Kept with the Match in the Ledger (ADR 0002), with the Account's personal data removed at Account deletion (#116). Otherwise set by #26. | Set by #26. |
| OAuth application requests: the applicant Account and contact details (planned, #29) | Partner application review. | Set by #29. | Until Account deletion (#116). Otherwise set by #29. | Set by #29. |
| Recipient addresses sent to the email provider (planned, #35) | Sending account email. | Set by #35. | A copy outside OPEN's database. It follows the email provider's retention, which #35 records and keeps as short as the provider allows. | Set by #35. |
| Uploaded CSV results files (planned, #71) | Organizer result uploads. | Set by #71. | Raw file deleted within 30 days of processing (#71). Its results live on in the Ledger. | Set by #71. |
| MFA authenticators: TOTP secrets, recovery codes, passkeys (planned, #99, #117) | Account security. These are secrets. | Never shown. Otherwise set by #99 and #117. | Until Account deletion (#116). Otherwise set by #99 and #117. | Set by #99 and #117. |
| Login limits and sign-in alerts, including any IP address or device data stored (planned, #100) | Account security. | Set by #100. | Until Account deletion (#116). Otherwise set by #100. | Set by #100. |
| Duplicate External ID flags (planned, #123) | Duplicate detection. | Set by #123. | Until Account deletion (#116). Otherwise set by #123. | Set by #123. |
| Data export files (planned, #39) | The player's copy of their data. | The player only. | Deleted when the download link expires, or at Account deletion (#116), whichever comes first. | Set by #39. |
| Matches and Ratings linked to a Player (planned, #23 onward) | The Ledger and the ratings pipeline. | As ADR 0002 sets out: once Ratings are published, the display name and current Ratings of a Player whose Account is active are visible to every signed-in Account. Partners see them too, except for players aged 13 to 17. Other details: set by the player's privacy settings (#19). | Kept in the Ledger after Account deletion, with the personal data removed (ADR 0002, hard rule 3). | Set by #23. |

## Not collected

[ADR 0009](../adr/0009-personal-data.md) rules these out. Adding one needs a new ADR.

- Payment data, such as cards and billing addresses.
- Street address, postcode, or exact location.
- Full birthdate (the day).
- Raw gender identity.
- Phone number.
