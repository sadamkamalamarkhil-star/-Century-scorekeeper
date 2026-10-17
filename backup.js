/* CueScore local-only transfer. No dependencies and no network requests. */
(() => {
  "use strict";

  const PREFIX = "centurySnooker.";
  const FORMAT = "cuescore-phone-backup";
  const VERSION = 1;
  const MAX_BYTES = 20 * 1024 * 1024;
  // Deliberately exact: a shared origin may contain unrelated applications.
  // Keep this list in sync with K, LEGACY, scoreLock and visualSeats in index.html.
  const TYPES = Object.freeze({
    [PREFIX + "mode.v4"]: "mode",
    [PREFIX + "results.v4"]: "results",
    [PREFIX + "century.settings.v4"]: "centurySettings",
    [PREFIX + "century.state.v4"]: "centuryState",
    [PREFIX + "century.timeline.v4"]: "centuryTimeline",
    [PREFIX + "snooker.settings.v4"]: "snookerSettings",
    [PREFIX + "snooker.state.v4"]: "snookerState",
    [PREFIX + "snooker.timeline.v4"]: "snookerTimeline",
    [PREFIX + "table.mode.v1"]: "boolean",
    [PREFIX + "profiles.v1"]: "profiles",
    [PREFIX + "clubTimer.v1"]: "timer",
    [PREFIX + "scoreLock.v1"]: "boolean",
    [PREFIX + "visualSeats.v1"]: "seats",
    "century.settings.v1": "centurySettings",
    "century.state.v1": "centuryState",
    "snooker.settings.v1": "snookerSettings",
    "snooker.state.v1": "snookerState",
    "app.mode.v1": "mode",
    "scorekeeper.results.v1": "results"
  });
  const KEYS = Object.keys(TYPES);
  const $ = id => document.getElementById(id);
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const string = value => typeof value === "string";
  const number = value => typeof value === "number" && Number.isFinite(value);
  const integer = value => number(value) && Number.isInteger(value);
  const nonnegative = value => number(value) && value >= 0;
  const nullableString = value => value === null || string(value);
  const boolean = value => typeof value === "boolean";
  const range = (min, max) => value => integer(value) && value >= min && value <= max;
  const member = values => value => values.includes(value);
  const arrayOf = predicate => value => Array.isArray(value) && value.every(predicate);
  const seatColor = member(["gold", "blue", "emerald", "purple", "rose", "cyan"]);
  const mode = member(["century", "snooker"]);
  const billing = member(["exact", "half", "hour"]);
  let pending = null;
  let fileSequence = 0;

  function requireValid(condition, message) {
    if (!condition) throw new Error(message);
  }

  function fields(value, schema) {
    return object(value) && Object.entries(schema).every(([key, predicate]) => !own(value, key) || predicate(value[key]));
  }

  const reference = value => fields(value, {
    name: string, kind: member(["regular", "guest", "legacy"]),
    id: nullableString, seatColor
  });
  const slot = value => fields(value, {
    kind: member(["regular", "guest"]), profileId: nullableString,
    guestName: string, name: string, seatColor
  });
  const log = arrayOf(value => string(value) || (object(value) && string(value.text) && fields(value, {
    t: number, actor: value => value === null || range(0, 3)(value), actorId: nullableString
  })));
  const pricing = value => fields(value, {
    club: string, clubId: member(["qball", "vip-club", "custom"]),
    sectionId: member(["normal", "vip"]), currency: string,
    hourlyRate: nonnegative, billing
  });

  function settings(value, century) {
    const max = century ? 4 : 2;
    return fields(value, {
      names: value => arrayOf(string)(value) && value.length <= max,
      slots: value => arrayOf(slot)(value) && value.length <= max,
      ...(century ? {
        playerCount: range(2, 4), target: value => number(value) && value >= 20 && value <= 1000,
        protectMode: member(["shooter", "leader", "manual"]),
        manualProtect: boolean, exactTarget: boolean
      } : {startingReds: range(1, 15)})
    });
  }

  function state(value, century, snapshot = false) {
    if (!object(value)) return false;
    const scores = value => arrayOf(number)(value) && value.length === 2;
    const players = value => Array.isArray(value) && value.length >= 2 && value.length <= 4 && value.every(player => fields(player, {
      score: number, freeReds: value => integer(value) && value >= 0,
      freeRed: boolean, best: nonnegative
    }) && own(player, "score"));
    const count = century ? (Array.isArray(value.players) ? value.players.length : 4) : 2;
    if (snapshot) {
      // Undo/redo installs snapshots directly, without the startup migrations
      // that fill missing fields in an older current-state record.
      const required = ["gameId", "startedAt", "endedAt", "active", "log", "winner",
        ...(century ? ["players", "visit"] : ["scores", "best", "startingReds", "break", "reds", "ballOn", "clearance", "respotted", "reason"])];
      if (!required.every(key => own(value, key))) return false;
      if (!Array.isArray(value.log) || !value.log.every(entry => object(entry) && string(entry.text) && number(entry.t))) return false;
      if (century && (!players(value.players) || !value.players.every(player =>
        own(player, "freeReds") && own(player, "best")))) return false;
    }
    return fields(value, {
      gameId: string, startedAt: number, endedAt: value => value === null || number(value),
      matchRefs: value => arrayOf(reference)(value) && value.length <= 4,
      active: range(0, count - 1), log, history: log,
      winner: value => value === null || range(0, count - 1)(value),
      ...(century ? {players, visit: nonnegative} : {
        scores, best: value => scores(value) && value.every(nonnegative),
        startingReds: range(1, 15), reds: range(0, 15), break: nonnegative,
        ballOn: member(["red", "colour", "yellow", "green", "brown", "blue", "pink", "black"]),
        clearance: boolean, respotted: boolean, reason: nullableString
      })
    });
  }

  function results(value) {
    return arrayOf(result => object(result) && string(result.id) && result.id.length > 0 &&
      arrayOf(string)(result.players) && result.players.length >= 2 && result.players.length <= 4 &&
      // Older saves can retain extra scores after a player-count change.
      // The app reads scores by player index and tolerates missing values;
      // keep the complete numeric array without inventing or dropping seats.
      arrayOf(number)(result.scores) && fields(result, {
        mode, winner: value => value === null || range(0, result.players.length - 1)(value),
        best: arrayOf(nonnegative), playerRefs: arrayOf(reference),
        startedAt: number, endedAt: number, losers: arrayOf(string), reason: string,
        target: number, playerCount: range(2, 4), startingReds: range(1, 15), actions: nonnegative
      }))(value);
  }

  function timer(value) {
    return fields(value, {
      settings: pricing,
      presets: value => object(value) && Object.values(value).every(nonnegative),
      active: value => value === null || (object(value) &&
        member(["running", "paused"])(value.status) && number(value.startedAt) && fields(value, {
          id: string, segmentStart: value => value === null || number(value),
          elapsedMs: nonnegative, pricing
        })),
      history: arrayOf(value => object(value) && string(value.id) &&
        number(value.startedAt) && number(value.endedAt) &&
        nonnegative(value.totalMs) && nonnegative(value.billableMs) &&
        nonnegative(value.charge) && pricing(value))
    });
  }

  function seats(value) {
    if (!object(value) || Object.keys(value).some(key => !["century", "snooker"].includes(key))) return false;
    return Object.entries(value).every(([key, layout]) => {
      if (!object(layout) || !string(layout.gameId) || !Array.isArray(layout.order)) return false;
      const count = layout.order.length;
      return count >= 2 && count <= (key === "century" ? 4 : 2) &&
        new Set(layout.order).size === count && layout.order.every(range(0, count - 1));
    });
  }

  function validAppValue(value, type) {
    switch (type) {
      case "mode": return mode(value);
      case "boolean": return boolean(value);
      case "profiles": return arrayOf(profile => object(profile) && string(profile.id) && profile.id.length > 0 && string(profile.name) && fields(profile, {nickname: nullableString, createdAt: number}))(value);
      case "results": return results(value);
      case "centurySettings": return settings(value, true);
      case "snookerSettings": return settings(value, false);
      case "centuryState": return state(value, true);
      case "snookerState": return state(value, false);
      case "centuryTimeline":
      case "snookerTimeline": return object(value) && arrayOf(snapshot => state(snapshot, type === "centuryTimeline", true))(value.past) && arrayOf(snapshot => state(snapshot, type === "centuryTimeline", true))(value.future);
      case "timer": return timer(value);
      case "seats": return seats(value);
      default: return false;
    }
  }

  function safeStructure(value) {
    const stack = [[value, 0]];
    while (stack.length) {
      const [node, depth] = stack.pop();
      requireValid(depth <= 64, "Backup data is nested too deeply (maximum 64 levels).");
      if (typeof node === "number") requireValid(Number.isFinite(node), "Backup contains a non-finite number.");
      if (node && typeof node === "object") {
        for (const child of Object.values(node)) stack.push([child, depth + 1]);
      }
    }
  }

  function validateArchive(text) {
    requireValid(new Blob([text]).size <= MAX_BYTES, "Backup exceeds the 20 MiB limit. No records were imported.");
    let archive;
    try { archive = JSON.parse(text); } catch { throw new Error("This file is not valid JSON. Choose a CueScore backup JSON file."); }
    requireValid(object(archive) && archive.format === FORMAT, "Unknown backup format. Choose a CueScore phone backup.");
    requireValid(archive.version === VERSION, "Unsupported backup version. This page supports version 1 only.");
    requireValid(Object.keys(archive).length === 5 && ["format", "version", "exportedAt", "sourceOrigin", "storage"].every(key => own(archive, key)), "The backup header is malformed or contains unexpected fields.");
    requireValid(string(archive.exportedAt) && Number.isFinite(Date.parse(archive.exportedAt)) && string(archive.sourceOrigin), "The backup date or source is invalid.");
    requireValid(object(archive.storage), "The backup storage must be an object of raw saved strings.");
    for (const [key, raw] of Object.entries(archive.storage)) {
      requireValid(own(TYPES, key), "Unexpected storage key: " + key + ". Nothing was imported.");
      requireValid(string(raw), "Invalid raw storage value for " + key + ". Expected a string.");
      let parsed;
      try { parsed = JSON.parse(raw); } catch { throw new Error("Invalid JSON saved under " + key + ". Nothing was imported."); }
      safeStructure(parsed);
      requireValid(validAppValue(parsed, TYPES[key]), "Invalid CueScore value for " + key + ". Nothing was imported.");
    }
    return archive;
  }

  function readOwnedStorage() {
    const values = Object.create(null);
    for (const key of KEYS) {
      const raw = localStorage.getItem(key);
      if (raw !== null) values[key] = raw;
    }
    return values;
  }

  function createArchive(storage) {
    return {format: FORMAT, version: VERSION, exportedAt: new Date().toISOString(), sourceOrigin: location.origin, storage};
  }

  function downloadArchive(storage, safety = false) {
    // Export raw bytes even if an old value is corrupt, so it is never lost.
    const blob = new Blob([JSON.stringify(createArchive(storage), null, 2)], {type: "application/json"});
    requireValid(blob.size <= MAX_BYTES, "This backup exceeds 20 MiB. Nothing was changed or truncated.");
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "cuescore-" + (safety ? "before-restore-" : "backup-") + new Date().toISOString().replace(/[:.]/g, "-") + ".json";
    document.body.append(anchor);
    try { anchor.click(); } finally {
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
  }

  function parseSaved(storage, current, legacy, fallback) {
    for (const key of [PREFIX + current, legacy].filter(Boolean)) {
      if (own(storage, key)) {
        try { return JSON.parse(storage[key]); } catch { /* summary only */ }
      }
    }
    return fallback;
  }

  function summary(storage) {
    const savedResults = parseSaved(storage, "results.v4", "scorekeeper.results.v1", []);
    const profiles = parseSaved(storage, "profiles.v1", null, []);
    const timer = parseSaved(storage, "clubTimer.v1", null, {});
    const currentMode = parseSaved(storage, "mode.v4", "app.mode.v1", "not saved");
    const century = parseSaved(storage, "century.state.v4", "century.state.v1", {});
    const snooker = parseSaved(storage, "snooker.state.v4", "snooker.state.v1", {});
    const count = value => Array.isArray(value) ? value.length : 0;
    const cScores = Array.isArray(century?.players) ? century.players.map(player => player?.score).join(" / ") : "not saved";
    const sScores = Array.isArray(snooker?.scores) ? snooker.scores.join(" / ") : "not saved";
    const lines = [
      count(savedResults) + " saved result(s) · " + count(profiles) + " profile(s)",
      count(timer?.history) + " timer receipt(s) · active timer: " + (timer?.active?.status || "none"),
      "Current mode: " + String(currentMode),
      "Century scores: " + cScores,
      "Snooker scores: " + sScores,
      Object.keys(storage).length + " saved storage key(s), including settings, seating and undo/redo when present."
    ];
    for (const game of ["century", "snooker"]) {
      const timeline = parseSaved(storage, game + ".timeline.v4", null, {});
      lines.push((game === "century" ? "Century" : "Snooker") + " undo / redo: " + count(timeline?.past) + " / " + count(timeline?.future));
    }
    return lines.join("\n");
  }

  function showStatus(message, kind = "success") {
    $("status").textContent = message;
    $("status").dataset.kind = kind;
  }

  function resetPreview() {
    pending = null;
    $("restorePreview").hidden = true;
    $("confirmReplace").checked = false;
    $("restoreBackup").disabled = true;
  }

  function sameStorage(left, right) {
    return KEYS.every(key => own(left, key) === own(right, key) && left[key] === right[key]);
  }

  function applyStorage(storage) {
    // Free all owned keys first so replacement fits when large values move
    // between keys. Unrelated storage is never removed.
    // This is synchronous; the caller owns rollback and verification.
    for (const key of KEYS) localStorage.removeItem(key);
    for (const [key, raw] of Object.entries(storage)) localStorage.setItem(key, raw);
    requireValid(sameStorage(storage, readOwnedStorage()), "Browser storage verification failed.");
  }

  function rollback(storage) {
    // applyStorage removes partial data before reinstating the original copy.
    applyStorage(storage);
  }

  $("exportBackup").addEventListener("click", () => {
    try {
      const storage = readOwnedStorage();
      downloadArchive(storage);
      $("currentSummary").textContent = summary(storage);
      showStatus("Backup download started. Keep the JSON file somewhere safe.");
    } catch (error) { showStatus("Backup failed: " + error.message, "error"); }
  });

  $("backupFile").addEventListener("change", async event => {
    const sequence = ++fileSequence;
    resetPreview();
    $("status").textContent = "";
    const file = event.target.files[0];
    if (!file) return;
    try {
      requireValid(file.size <= MAX_BYTES, "Backup exceeds the 20 MiB limit. No records were imported.");
      const archive = validateArchive(await file.text());
      if (sequence !== fileSequence) return;
      const before = readOwnedStorage();
      pending = {archive, before};
      $("previewSummary").textContent = "Exported: " + archive.exportedAt + "\nFrom: " + archive.sourceOrigin + "\n\n" + summary(archive.storage);
      $("restorePreview").hidden = false;
      showStatus("Backup checked. Review the preview and confirm replacement to restore.");
    } catch (error) {
      if (sequence === fileSequence) {
        $("backupFile").value = "";
        showStatus(error.message, "error");
      }
    }
  });

  $("confirmReplace").addEventListener("change", event => {
    $("restoreBackup").disabled = !pending || !event.target.checked;
  });

  $("restoreBackup").addEventListener("click", () => {
    if (!pending || !$("confirmReplace").checked) return;
    const {archive, before} = pending;
    $("restoreBackup").disabled = true;
    let started = false;
    try {
      requireValid(sameStorage(before, readOwnedStorage()), "CueScore data changed since this preview. Close other CueScore tabs and choose the backup again.");
      downloadArchive(before, true);
      started = true;
      applyStorage(archive.storage);
      resetPreview();
      $("backupFile").value = "";
      $("currentSummary").textContent = summary(archive.storage);
      showStatus("Restore complete. All archived CueScore values were restored. Keep the safety backup, then use Back to CueScore to open your games.");
    } catch (error) {
      let message = "Restore stopped: " + error.message;
      if (started) {
        try {
          rollback(before);
          message = "Restore failed and was rolled back. Your original CueScore data is unchanged. " + error.name + ": " + error.message;
        } catch (recoveryError) {
          message = "Restore failed and automatic recovery could not finish. Keep the downloaded before-restore safety backup and do not continue scoring. " + error.name + ": " + error.message + " Recovery: " + recoveryError.message;
        }
      }
      resetPreview();
      $("backupFile").value = "";
      showStatus(message, "error");
    }
  });

  try { $("currentSummary").textContent = summary(readOwnedStorage()); }
  catch (error) { showStatus("Browser storage is unavailable: " + error.message, "error"); }
})();
