# Century & Snooker Scorekeeper: Fouls, Scoring Lock, Seat Order, Nicknames and Club Rates

**Date:** 2026-10-12
**Status:** Conversation design approved; written specification pending user review.
**Product:** Existing single-page GitHub Pages app, with localStorage data and no back-end.

## Goal and scope

Support the way players actually use a phone on the snooker table while keeping current matches, permanent player IDs, lifetime statistics, previous results, Undo/Redo, current-log filters, and club session history intact.

Five accepted requirements:

1. In **both** Afghan Century and Snooker, tap **Foul**, then a ball; subtract that ball's numeric value from the **shooter**. Do not award foul points to the opponent, even in Snooker.
2. Prevent stray taps with optional **Scoring Lock**, without burdening normal scoring with confirmations.
3. **Swap Seats** changes only visual scoreboard positions, never turn order, scoring data, player IDs, or results.
4. Add editable regular-player nicknames; use **Sid** for Sadam and **Hekmo** for Hekmat where an existing matching profile is unambiguous.
5. Add two sections (Normal and VIP) to each of two saved club price presets, plus an editable Custom rate.

## Existing-code constraints

The live app implements century and snooker logic, persistent settings/states, 40-step scoring Undo/Redo timelines, profile IDs and guest match references, history/results/stats, a current-log player filter, a timestamp-based club timer, and a responsive landscape/table view in one index.html. These are the integration boundaries, not features to rewrite. Retain existing versioned localStorage keys and perform backward-compatible migrations for new properties and keys. Keep all data local; no online sync or cloud accounts.

### Component and state responsibilities

- **Scoring engine:** canonical participant index, active turn, Century score/visit/free-red passes, Snooker score/break/phase, participant matchRefs, results, log and timelines.
- **Display seats:** persisted permutation of participant indices for the active game/frame, separate from the engine and its Undo/Redo snapshots.
- **Regular player profiles:** immutable ID and canonical name with an optional display nickname. Guest identities remain temporary.
- **Club rate presets:** namespaced by club ID and section ID; timer active session captures immutable billing settings at start.
- **Scoring Lock:** device-local UI preference and interaction guard independent of scores and timer.

## 1. Foul-by-ball mode

Normal unlocked workflow: tap **Foul** to enter a visibly distinct foul-selection mode, then tap any ball, including red, to choose the deduction. A second tap on Foul cancels without changing game state. Choosing a ball records one undoable foul action and exits foul mode. Hide/remove the old four-penalty picker. In foul mode, ball buttons must not call regular potting handlers, and ball eligibility for a normal pot does not restrict foul choices. Show clear pending-foul feedback.

**Century values:** Red 10, Yellow 2, Green 3, Brown 4, Blue 5, Pink 6, Black 7. Deduct selected value from the current player's score, log who fouled and how many points were lost, reset visit, and end turn according to the unchanged canonical rotation. Do not consume or award free-red passes from foul selection. Protected/unprotected red **miss** behavior stays separate and unchanged. A red foul is -10.

**Snooker house-rule values:** Red 1, Yellow 2, Green 3, Brown 4, Blue 5, Pink 6, Black 7. Deduct the selected number from the current shooter's own score; credit **nothing** to the opponent; log and end the break/turn. The selected ball is not potted or removed. Retain the existing Snooker ball-on/clearance transition for a foul and the existing respotted-black frame-resolution behavior, while replacing awarded foul points with shooter deduction. Negative scores may occur. Best break is not reduced retrospectively; free-ball play remains distinct. A red foul is -1. This is the user's custom house rule, not official Snooker scoring.

## 2. Accidental-touch protection

Provide an easily found **Scoring Lock** in portrait and table/landscape modes. One deliberate tap locks. Unlock via a continuous roughly 700-ms hold, with visible progress and accessible keyboard equivalent; releasing too early does not unlock. The locked state survives reload/rotation until deliberately changed.

Block actions that mutate scoring, active player, results, fouls, misses, free-ball selection, concession, new-game resets, Undo and Redo while locked. Keep scores/history readable and allow timer/settings access. Show clear locked feedback if the user attempts a scoring action. Keep destructive-action confirmations when unlocked; do **not** add confirmation dialogs to normal scoring.

Implement guards in the mutation/action layer as well as disabling or blocking controls, to prevent a tap routed through an unexpected handler from changing scores. Scoring Lock does not pause or change club time.

## 3. Visual-only seat swaps

Represent displayOrder as a valid permutation, e.g., [1,0,2] displays canonical person 2 in visual slot 1, canonical person 1 in slot 2, and canonical person 3 in slot 3. Old state loads with [0,1,2,...]. The Swap Seats interface picks two visible seats and exchanges only the permutation entries, including during active matches. Render player cards using the mapped canonical indices; data attributes on cards must still target canonical indices.

The swap must not modify or reorder the scoring arrays, participant matchRefs, score, best visit/break, free-red passes, current active participant, current visit, frame phase, or lifetime result attribution. After a turn ends, the next participant is computed by the original canonical rotation. Active-player highlight follows the person when cards move. Display-only seat labels/colors follow visual position rather than serving as identity.

Save seat layout across reload and orientation changes for the **current** match; a new game/frame starts with natural seat order. Seat swaps are undone by swapping again, not by scoring Undo/Redo. Undo/Redo restores the prior scoring state without restoring/rearranging the presentation permutation. Validate and recover invalid permutations, especially after legitimate player-count changes outside a progressed match. Never silently discard a participant's progressed match state merely to change seats.

## 4. Nicknames and stable identity

Extend regular profiles with an optional nickname field; retain each profile's canonical name and immutable ID. A nonempty nickname is the displayed name in the scoreboard, stats, Current Log tabs, player selectors and subsequent new result displays; fallback to canonical name. Guest names remain editable for that match and do not receive permanent lifetime records.

For existing regular profiles exactly named **Sadam** and **Hekmat** (case-insensitive, trimmed), default absent nicknames to **Sid** and **Hekmo** respectively, only when each matching identity is unambiguous. Do not create new profile IDs, conflate similarly named profiles, or infer a person from a legacy name-only completed result. Allow future edits and clearing the nickname.

Save new log entries with a stable canonical player reference/index alongside human-readable text so changing nickname or seat does not break the player-specific Current Log filters. Show older log entries unchanged. Attribute older unstructured entries conservatively by known stable identity/unique name evidence; when ambiguous, leave them under **All**. Do not rewrite historic result names or snapshots in order to display a new nickname. Linked regular profile stats continue to aggregate using player ID, including games against guests.

## 5. Club Timer: saved Normal/VIP rates

Preset table (all AFN per hour):

| Club ID | Club label | Section ID | Section | Initial rate |
| --- | --- | --- | --- | ---: |
| qball | Qball | normal | Normal | 200 |
| qball | Qball | vip | VIP | 300 |
| vip-club | VIP | normal | Normal | 150 |
| vip-club | VIP | vip | VIP | 250 |

The club called **VIP** and the **VIP section** are distinct: make the selector and final receipt explicit, e.g. “VIP club — VIP section.” Provide a saved rate editor for each of the four combinations, plus **Custom** for other clubs. Club + section selection preloads the saved hourly price; each rate may be edited for later sessions.

Preserve existing exact-minute, upward 30-minute, and upward whole-hour billing; currency, Start/Pause/Resume/End; timestamps; elapsed-time persistence; previous session receipts. Snapshot club/section/rate/currency/rounding when a session is started. Calculate current estimates and final receipts using that immutable active-session snapshot, not mutable preset settings. Do not allow silently switching active-session club/rate; ask the user to end the session first. Rates must be finite, nonnegative, and greater than zero when starting.

Migrate clubTimer.v1 settings, running/paused sessions and past receipts without deleting them. For an older active session with no snapshot, take a one-time snapshot of its prior settings. Historical receipts must keep their saved prices after future preset edits.

## 6. UI and integration design

- **Scoring view:** recognizable Foul mode, Scoring Lock state, Swap Seats entry, compact portrait and short-phone landscape displays; keep MISS/END TURN and scores prominent.
- **Regular roster/settings:** existing profile ID/name plus editable Nickname; keep guest and color settings. Do not permit settings changes that silently replace a player mid-progressed match.
- **Timer sheet:** club selector, section selector, four editable presets, Custom pricing, existing billing method/controls/receipt history.
- **Action log/history:** preserve All view and name/person filters. New typed actor fields support nickname changes; old logs still render unchanged.
- **Accessibility and safety:** escaped user-controlled labels (nickname/club), keyboard unlock alternative, no accidental double-invocation on pointer/touch, and no global timer rerender that resets an in-progress form edit.

## 7. Tests and migration verification

Create failing tests before implementing each behavior, then verify passing tests and manually examine relevant UI.

1. **Century:** all foul values including red -10, no opponent award/free-red change, one timeline entry, turn order, Undo/Redo.
2. **Snooker:** all foul values including red -1, opponent untouched, no ball pot/removal, correct break/phase/turn, negative score and respotted-black cases, Undo/Redo.
3. **Foul mode:** enter/cancel/choose, normal pot disabled while selecting, ordinary pot works again afterward.
4. **Scoring Lock:** short hold does not unlock; sufficient hold and keyboard interaction do; protected actions never mutate; reload and orientation retention.
5. **Seat order:** 2/3/4 participants, swap during active turn, next canonical turn unchanged, Undo/Redo after swap, correct log IDs and result attribution, reload.
6. **Nicknames:** matching-profile migration, user edits and clearing, guest/regular name collisions, old unstructured logs and historical results remain intact, aggregate stats by ID.
7. **Club prices:** all four preset rates, custom edit, distinct VIP club versus VIP section, rate/rounding frozen at start, no retroactive receipt changes, migration of paused/running prior sessions.
8. **Regression:** Century red passes and protection, standard Snooker pot/clearance rules other than explicitly changed fouls, player-profile persistence, current-log filtering, club timer after phone lock, responsive landscape controls.

Check JavaScript parsing, full relevant tests, saved-state migration, and browser interaction if browser access is available. Compare changes against latest GitHub main to avoid overwriting parallel changes; use git history to roll back. Publish only after tests pass; independently verify the specific Pages deployment workflow before claiming it is live.

## Out of scope

No backend, multi-device synchronization, official-rule foul logic, automatic referee, payments, full UI rewrite, guest lifetime profiles, or inference of historical profile IDs based only on names.
