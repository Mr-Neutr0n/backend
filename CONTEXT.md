# OPEN backend: domain language

The shared vocabulary for this repository. Use these terms in models, endpoints, fields, tests, and docs. Where a term comes from the reference engine, the engine name is given in `code` so the two stay aligned. If the engine renames something, update this file.

## People and accounts

**Player**:
A person who plays matches and has ratings. Every Player is created by one Account and belongs to it. Deleting the Account (#116) keeps the Player and its Matches. Once Ratings are published, the display name and current Ratings of a Player whose Account is active are always visible to every signed-in Account, and the Player cannot hide them. Authenticated partner applications see them too, except for players aged 13 to 17 (ADR 0009). There are no unclaimed Player records, and no Submission creates a Player (ADR 0002). Engine: `Player`. Backend: `players.Player`.
_Avoid_: user, member, athlete.

**Account**:
A registered OPEN login. An Account creates its own Player, and has at most one. The engine allows a Player with no Account, but the backend never creates one. #116 decides what a deleted Account leaves behind (ADR 0002). Engine: `Player.account_user_id`, `RatingEngine.link_account`. Backend: `accounts.User`, keyed on email.
_Avoid_: profile (a profile is the view of a Player that others see behind authentication).

**Display Name**:
The name a Player shows to others. As ADR 0002 sets out, once Ratings are published, the Display Name of a Player whose Account is active is visible to every signed-in Account. Partners see it too, except for players aged 13 to 17 (ADR 0009).
_Avoid_: username, nickname.

**Legal Name**:
A Player's full legal name, private, used only for identity checks and Organizer verification. Encrypted once #115 lands, and never returned to Partners (ADR 0009).
_Avoid_: real name.

**Age Group**:
A band derived from a Player's birth year and month, shown in their place. OPEN stores birth year and month, never the day, and applies age limits as if the player were born on the last day of the month (ADR 0009).
_Avoid_: age, birthdate.

**Privacy Setting**:
A Player's choice of who sees one of their other profile details (city and region, match history, rating history, stats, home club): every active signed-in Account, or only the player. While the player's own Account is inactive, nobody sees them. Display Name and current Ratings have no Privacy Setting (ADR 0002). Backend: the `*_visibility` fields of `players.PlayerPrivacy`.
_Avoid_: visibility flag, opt-out.

**Gender Division**:
The gender division a Player enters for divisions and gender-specific Rating Formats: men's, women's, or none. OPEN stores no other gender data (ADR 0009).
_Avoid_: gender, sex.

**Organizer**:
A verified person or body that submits results on behalf of an event, club, league, or tournament. An Organizer submission counts as confirmed.

**Partner**:
An app, league platform, club, or tournament that integrates with OPEN through the APIs. Partners use OPEN for free.
_Avoid_: customer, client, vendor.

**External ID**:
A Player's identifier in another system, keyed by source. Used for identity matching, never as the OPEN primary key. Engine: `Player.external_ids`.

**OPEN Code**:
The public identifier OPEN issues to a Player, Club, Event, Organizer, or Match, such as `P-7K3M-QX9H`. A type prefix, random characters, and a check character. It never changes and is never issued again. APIs, exports, and URLs use it; row ids never appear in the API. An External ID comes from another system and is only used for matching; an OPEN Code is OPEN's own. Backend: `public_code`, `public_ids.PublicCodeModel` (ADR 0008).
_Avoid_: OPEN ID, player ID, row id.

## Matches and results

**Match**:
One completed contest between two teams, with one or more game scores. Singles teams have one player; doubles teams have two. Every Match has a `match_id` unique to its source, used for duplicate protection. Engine: `Match`.
_Avoid_: game (a game is one scored unit inside a Match), result.

**Game**:
One scored unit inside a Match, such as 11-8. Must be valid for the Match's Game Format. Engine: `Match.games`.

**Game Format**:
How each game is scored: side-out or rally scoring, points to win, win-by margin, and an optional cap. Recorded on every Match. Engine: `GameFormat`.

**Match Type**:
Where the result came from, which affects its weight: `tournament`, `league`, `rec_verified`, or `self_reported`. Engine: `MatchType`.

**Confirmation**:
Agreement that a reported score is correct. A self-reported Match needs at least one player from each team to confirm it, unless a verified Organizer submitted it. Engine: `Match.confirmed_by`.

**Submission**:
A request to add a Match through the Results API. A Submission becomes a Match in the Ledger only after it passes validation, duplicate checks, and Confirmation.
_Avoid_: upload (an upload is a batch of Submissions).

**Flagged Match**:
A Match held for Organizer review because it looks like an outlier, a possible duplicate, or otherwise suspicious.

**Ledger**:
The append-only, ordered record of every counted Match. Order is date, time, sequence, then `match_id`. The Ledger is the source of truth for ratings. Engine: `ledger_order`.
_Avoid_: history table, log.

## Ratings

**Rating**:
A number on the 2.0 to 8.0 scale for one Player in one Rating Format. Engine: `RatingState.rating`.

**Rating Format**:
The kind of play a rating covers: `singles`, `doubles`, `mixed_doubles`, `doubles_men`, `doubles_women`. Category formats also update the overall `doubles` rating. Engine: `RatingFormat`.

**RD (rating deviation)**:
How uncertain a Rating is. Grows with inactivity and shrinks with play. Engine: `RatingState.rd`.

**Reliability**:
A 0 to 100% score shown with every Rating, earned through OPEN matches, opponent and partner variety, and recent play. It cannot be chosen or converted from another system. Engine: `reliability()`.

**Seed**:
A Player's starting Rating before any OPEN matches, either provisional or imported from an External Rating Snapshot.

**External Rating Snapshot**:
A verified rating from a standard external rating system, with its source, date, and evidence. Used only as a Seed. Once OPEN matches exist, a new snapshot cannot overwrite the Rating. Engine: `ExternalRatingSnapshot`.
_Avoid_: naming the external system.

**Imported Reliability**:
The external system's reliability, shown separately and clearly labeled until OPEN-earned Reliability exceeds it.

**Replay**:
Rebuilding all Ratings from Seeds plus the full Ledger as of a date. Same Ledger, Seeds, config, and date always give the same result. Replays run on a published schedule and produce the authoritative Ratings. Engine: `replay()`.

**Replay Info**:
The provenance stored with every Replay: as-of date, config version, config fingerprint, and match counts. Engine: `ReplayInfo`.

**Live Update**:
A rating change applied when a Match arrives, between Replays. Live Updates are provisional and labeled with how many have occurred since the last Replay. Engine: `RatingEngine.record`, `RatingState.live_updates_since_replay`.

**Frozen**:
A player in a Match dated on or before their imported baseline. Their rating is used for the prediction but does not move. Reported on every match result. Engine: `MatchResult.frozen`.

**Clamped**:
A player whose change was cut short by the rating floor or ceiling. Engine: `MatchResult.clamped`.

**Shadow Mode**:
Running the engine on real results without publishing or relying on its Ratings. OPEN is in shadow mode until validation results are published and the governing board is seated.

## Records

**Audit Event**:
One recorded sensitive action: who did it (an Account, or nobody), what it changed (the target), the values before and after (for an identifying personal data field, only its name, ADR 0009), and a reason. Audit Events are append-only. They record moderation, manual edits, account security changes, privacy changes, a player's own profile changes, and partner application requests and decisions; they are not part of the Ledger and never feed ratings. Backend: `audit.AuditEvent`.
_Avoid_: log entry (Django's admin `LogEntry` is a different thing), history.

## Governance terms

**Rating Spec**:
The published, versioned definition of how OPEN ratings are calculated. Only the governing board changes the official spec.

**Conformance**:
Meeting the board's published requirements for showing an OPEN rating. Only conforming tools may display one.
