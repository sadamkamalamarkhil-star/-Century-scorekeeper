# CueScore — Century and Snooker

A static scorekeeper with player profiles, game history, seat arrangement, and a club session timer.

## Run locally

From this directory:

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

Open the served app in a modern browser. No application dependencies or build step are required.

## Scoring rules

- Century: in the default shooter protection mode, a missed red below **70% of the target** leaves the shooter's score unchanged and grants one free-red pass to every other player. At or above 70%, it deducts 10. For target 100, 65 is protected and 70 is not. Leader mode uses the same threshold for the highest score; manual protection remains an explicit override. Choosing **Foul**, then red, is a separate −10 foul.
- Regular Snooker: a foul awards the opponent at least 4 points, or the higher value of the selected ball or a known ball on, up to 7. Select the highest-value ball involved, including a nominated colour. The fouling player's score stays unchanged. Historical records retain their original scores.

## Preserve and transfer phone data

Use **Backup & transfer** in Settings, or open `backup.html` on the same site and browser that contains your scores.

1. On your phone, open the existing GitHub Pages app in the browser where you scored the games. If you normally use the installed app, use that same browser/profile.
2. Open Backup & transfer and export a JSON backup. It includes current scoreboards, game results, profiles, settings, undo/redo, seat layout, scoring lock, timer history, and supported older storage keys.
3. Keep that original backup. At the destination site, open Backup & transfer, choose the file, review its summary, and explicitly restore it. Restore replaces this device's CueScore state and downloads a safety backup of its previous state first.

The backup page must first be deployed at the original site for step 2 to work. Opening a local HTML file or a different site cannot read the phone's existing data. Do not clear the phone's browser data before exporting. Only data still present in that browser can be recovered; this tool cannot reconstruct previously deleted games.

Backup/restore is a manual transfer. **This version does not provide live shared storage or club invitations.** Publishing the same static files on another host does not synchronize devices. No phone history has been bundled into this repository.

## Invited club sharing: deployment requirement

The requested shared version needs an authenticated backend with persistent storage: one club dataset for invited members, saved results/profiles/timer sessions, a shared active scoreboard, and conflict detection for simultaneous edits. Invite-only access must be enforced on server reads and writes. Phone history should be imported once from its backup, preserving record IDs and checking duplicates, before club members start using it.

ChatGPT Sites publication and its database/access configuration require Sites deployment capabilities. This repository currently contains the static app and manual transfer tools. A cloud database and invite-only server authorization must be implemented and deployed before shared club sync is available. The existing GitHub Pages site and its browser data are independent of a future Sites deployment.

## Browser regression tests

Development tests use Python Playwright and system Chromium. Install the development package if it is not already available:

```sh
python3 -m pip install -r requirements-dev.txt
```

With the local server running on port 8000 and Chromium available at `/usr/bin/chromium`, run:

```sh
python3 -m unittest discover -s tests -v
```

Tests use isolated browser contexts; they do not read your phone or modify your normal browser profile.
