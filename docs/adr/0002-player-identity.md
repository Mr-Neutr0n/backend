# 0002. Player identity: no unclaimed players, and opt-out

- Status: Proposed
- Date: 2026-11-14

## Context

Issue #1 left a question open (decision Q9): partner and CSV submissions may name people who have never signed up for OPEN. Its default was a short decision record (ADR) on unclaimed Player records, how a person claims one, and what opt-out means for matches with other players. The Player model (#19) depends on the answer. Issue #18 asks:

- How is an unclaimed Player record created and matched?
- How does a person claim a record, and how are false claims handled?
- What does opt-out mean: which views hide the player, what happens to their Rating, and what happens to their matches with other players?
- What is the minimum personal data stored for an unclaimed player?

Earlier decisions already narrowed this. Partners send OPEN Codes or their own player IDs that are mapped (#82) or linked through Log in with OPEN (#75). An unmapped ID fails that match, and partner submissions never create unclaimed players (decision F5). CSV uploads use OPEN Codes only for now. An unknown code fails that row, and no Player is found or created from a name (decision F13). That left organizer rosters as the only remaining source of unclaimed records.

The engine supports Player records with no Account (`Player.account_user_id` is optional, and `RatingEngine.link_account` links one later). The backend does not have to use that.

Unclaimed records bring hard problems. The person never agreed to have a record. Their age is unknown, so OPEN cannot tell whether they are a minor (#93). Someone else can claim the record falsely. Two records for one person must be merged, and the Ledger is append-only (hard rule 3), so a merge cannot rewrite past Matches.

Opt-out must also fit the Ledger and the Replay. For the Matches already in the Ledger, a Replay must give the same Ratings for every other player whether or not someone opts out.

## Decision

### No unclaimed Player records

- For now, OPEN has no unclaimed Player records. Every Player is created by one Account and belongs to it (#124). An Account has at most one Player.
- Deleting an Account (#116) removes its personal data but keeps the Player and its Matches in the Ledger. #116 decides how.
- Nobody else creates a Player: not Partners, not CSV uploads, not Organizers, not moderators.
- So there is nothing to claim, no false-claim process, and no unclaimed personal data.

### How submissions name players

- Partner and bulk submissions never create a Player.
- They name a player only by OPEN Code (ADR 0008), by a confirmed platform mapping (#82), or by a Log in with OPEN link (#75).
- CSV uploads use OPEN Codes only for now (decision F13).
- A name never finds or creates a Player.
- An unknown or unmapped ID fails that Match, or that CSV row.

### Opt-out is a pause

Opt-out is a pause, not a deletion. Deleting an Account and its personal data is #116. While a player is opted out:

- Every lookup path answers for them exactly as for an unknown OPEN Code. This covers the public profile (the same 404), single and batch rating lookups, rating history (#53), and any other partner read. A batch lookup reports them the same way it reports an unknown code.
- Other players' match history, and Match detail looked up by a Match's OPEN Code, show them as "Private player". This is the same label used for players hidden by their privacy settings (#31, #56), so it does not single out an opt-out.
- No stats about them are published: no summaries of their own, no percentile, and no rankings. In other players' stats (partner and head-to-head summaries, #56) they show as "Private player". Their Matches still count in those players' totals.
- The rating card shows their Rating as not available (#96).
- They are left out of webhooks (decision F9).
- Opting out and opting back in must invalidate cached public responses about them (#54).
- Their past Matches stay in the Ledger (hard rule 3) and keep counting for the other players in them. For those Matches, a Replay gives the same Ratings for everyone else.
- Their own Rating is still computed in Replays, since the other players' math needs it. It is never published to others. They can still see it, and their export includes it.
- A new Submission that names them fails for that Match. Every submission path must check this: Partner, bulk, CSV, Organizer, and self-submission. The error depends on how the Submission names them:
  - By OPEN Code: the same error as an unknown OPEN Code.
  - By a platform player ID resolved through a mapping (#82) or a link (#75): the same error as an unmapped ID.
  - In their own self-submission: a plain refusal that says they are opted out. They already know.
- A Submission that names them and has not entered the Ledger when they opt out also fails. This covers a Submission pending Confirmation and a Flagged Match awaiting review. It never enters the Ledger, even if it is confirmed or approved later.
- They cannot confirm a pending Submission. It fails anyway.
- An opt-out does not block corrections of Matches already in the Ledger (new records that reference the old one, hard rule 3). It does not block moderator or Organizer review of those Matches either. The pause stops new play, not fixes to the record that other players' Ratings depend on.
- They can still dispute a Match already in the Ledger.
- They can still see and export their own data (the charter).
- They can opt back in at any time. Opting back in restores visibility and lets new Matches count. OPEN does not add refused Submissions back automatically. After opting back in, a Submission is judged like any other. OPEN keeps no record of opt-out periods beyond the Audit Events.
- `opted_out_at` (#19) holds only the start of the current opt-out. Opting back in clears it. Audit Events record both the opt-out and the opt-in, each with its time.

### Personal data

No unclaimed players exist, so there is no minimum data set for one. Personal data for Players is set by #93.

## Consequences

- A league needs every player to sign up and create a Player before its results are uploaded. #124 already says this.
- #19's criterion "A player can exist without a user (unclaimed)" no longer applies. Every Player is created with a link to its Account, and an Account has at most one Player. What happens to that link when an Account is deleted is for #116.
- #19's "claimed status" task is dropped. There is no claimed status field.
- #93's question about unknown ages for unclaimed players does not arise.
- #93's "Unclaimed players" rule becomes: only the player sets birth year, birth month, gender, and legal name, on their own Player.
- #116's retention for unclaimed records has nothing to act on.
- #124's out-of-scope items "Claiming an existing unclaimed record" and "Organizer-created players from a roster" are settled. Neither is planned.
- The opt-out check must run on every read path: profile, match history, Match detail, rating lookups, rating history, rankings, stats (#56), partner APIs, webhooks, the rating card, and cached public responses. It must also run on every submission path, and on every Submission still waiting for Confirmation or review. A missed path leaks the player or records a Match they refused.
- A Partner that knows its mapping was confirmed can infer, from the unmapped-ID error, that the player opted out or the mapping was removed. This signal is accepted.
- A Match refused during an opt-out may leave a league result unrecorded for the other players in it. That is the cost of a real pause.
- Adding unclaimed records later needs a new record that supersedes this one in part. It must first decide how records are created and matched, how a person claims one, how false claims and merges are handled, and the minimum data stored.

## Alternatives considered

- **Organizer-created unclaimed records with claim codes.** An Organizer could add a roster and hand each person a code to claim their record. This brings consent, unknown ages, false claims, and merges, with no answer yet for any of them.
- **Claim by request and approval.** A person asks for a record and a moderator approves. It has the same problems, plus moderator load and a social engineering target.
- **Partner or CSV creation from names.** Already refused by decisions F5 and F13. Names cause mismatches.
- **Opt-out that keeps accepting Matches (hidden but rated).** The player's results would keep feeding the Ledger after they asked to stop. That is not a pause.
- **Opt-out that freezes the Rating.** This needs engine support. The backend must not change the rating math (hard rule 2).
- **Deleting Matches on opt-out.** This breaks the append-only Ledger (hard rule 3) and changes other players' Ratings.
