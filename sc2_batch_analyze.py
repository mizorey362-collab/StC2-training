#!/usr/bin/env python3
"""
sc2_batch_analyze.py
--------------------
Processes every .SC2Replay in your replay folder and writes a Game Log
or Drill note for each one into your Obsidian vault.

Already-processed replays are skipped — safe to run repeatedly.
A summary report is printed at the end.

Usage (double-click ANALYZE_ALL.bat, or run directly):
    python3 sc2_batch_analyze.py [replay_dir] [vault_dir]

CONFIG section below is shared with sc2_watcher.py — edit once.

Requirements: Python 3.10+, s2protocol (pip install s2protocol --no-deps).
sc2_to_gamelog.py must be in the same folder as this script.
See SETUP.md for full installation instructions.
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — same values as sc2_watcher.py
# ─────────────────────────────────────────────────────────────────────────────

PLAYER_NAME = "PlayerName"

VAULT_PATH = r"C:\_workspace\starcraft\ZergBenchmarks"

VAULT_NAME = "ZergBenchmarks"

SC2_REPLAY_DIR = r"ReplayFolder"

LADDER_GAMES_SUBDIR  = "Ladder Games"
PRACTICE_RUNS_SUBDIR = "Practice Runs"

ANTHROPIC_API_KEY = ""

# ── Batch options ─────────────────────────────────────────────────────────────

# How many days back to look. 0 = process ALL replays ever recorded.
DAYS_BACK = 0

# Skip replays already covered by an existing note in the vault.
# Match is by date+time prefix in the filename (YYYY-MM-DD HH-MM).
SKIP_ALREADY_PROCESSED = True

# Delay between replays to avoid hammering the API if coaching is enabled
DELAY_BETWEEN_REPLAYS = 0.5   # seconds

# ─────────────────────────────────────────────────────────────────────────────
# END CONFIG
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR     = Path(__file__).parent.resolve()
GAMELOG_SCRIPT = SCRIPT_DIR / "sc2_to_gamelog.py"
LOG_FILE       = SCRIPT_DIR / "sc2_batch.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Import parser ─────────────────────────────────────────────────────────────

sys.path.insert(0, str(SCRIPT_DIR))
try:
    import sc2_to_gamelog
except ImportError:
    log.error("sc2_to_gamelog.py not found next to this script.")
    input("Press Enter to exit.")
    sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_sc2_replay_dir():
    """Auto-detect SC2 replay directory (same logic as watcher)."""
    for docs_root in [Path.home() / "Documents",
                      Path.home() / "OneDrive" / "Documents"]:
        base = docs_root / "StarCraft II" / "Accounts"
        if not base.exists():
            continue
        candidates = list(base.glob("*/*/Replays/Multiplayer"))
        if candidates:
            def latest(d):
                files = list(d.glob("*.SC2Replay"))
                return max((f.stat().st_mtime for f in files), default=0)
            candidates.sort(key=latest, reverse=True)
            return str(candidates[0])
    return None


def collect_existing_timestamps(vault_path):
    """
    Return a set of 'YYYY-MM-DD HH-MM' strings from notes already in the vault.
    Used to skip replays that have already been processed.
    """
    timestamps = set()
    for subdir in (LADDER_GAMES_SUBDIR, PRACTICE_RUNS_SUBDIR):
        folder = Path(vault_path) / subdir
        if not folder.exists():
            continue
        for f in folder.glob("*.md"):
            # filenames: "Game 2026-03-14 18-45 ZvT.md"
            #            "Drill 2026-03-14 19-00 vs AI Hard.md"
            parts = f.stem.split()
            if len(parts) >= 3:
                # parts[0]='Game'/'Drill', parts[1]='2026-03-14', parts[2]='18-45'
                ts = f"{parts[1]} {parts[2]}"
                if len(ts) == 16:   # 'YYYY-MM-DD HH-MM'
                    timestamps.add(ts)
    return timestamps


def replay_timestamp(replay_path):
    """Return 'YYYY-MM-DD HH-MM' from a replay file's mtime."""
    mtime = os.path.getmtime(replay_path)
    return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H-%M')


def collect_replays(replay_dir, days_back):
    """Return all .SC2Replay paths sorted by mtime (oldest first)."""
    folder = Path(replay_dir)
    replays = list(folder.rglob("*.SC2Replay"))
    if days_back > 0:
        cutoff = time.time() - days_back * 86400
        replays = [r for r in replays if r.stat().st_mtime >= cutoff]
    replays.sort(key=lambda r: r.stat().st_mtime)
    return replays


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Allow overriding paths via command-line arguments
    replay_dir = sys.argv[1] if len(sys.argv) > 1 else SC2_REPLAY_DIR
    vault_path = sys.argv[2] if len(sys.argv) > 2 else VAULT_PATH
    player     = sys.argv[3] if len(sys.argv) > 3 else PLAYER_NAME
    api_key    = sys.argv[4] if len(sys.argv) > 4 else (
                     ANTHROPIC_API_KEY or os.environ.get('ANTHROPIC_API_KEY', ''))

    # Auto-detect replay dir if not set
    if not replay_dir or not Path(replay_dir).exists():
        log.info("SC2_REPLAY_DIR not set or not found — auto-detecting...")
        replay_dir = find_sc2_replay_dir()
        if not replay_dir:
            log.error("Could not find SC2 replay folder. Set SC2_REPLAY_DIR in config.")
            input("Press Enter to exit.")
            sys.exit(1)
        log.info(f"Using replay folder: {replay_dir}")

    if not Path(vault_path).exists():
        log.error(f"Vault not found: {vault_path}")
        log.error("Set VAULT_PATH in the CONFIG section of this script.")
        input("Press Enter to exit.")
        sys.exit(1)

    ladder_dir   = str(Path(vault_path) / LADDER_GAMES_SUBDIR)
    practice_dir = str(Path(vault_path) / PRACTICE_RUNS_SUBDIR)

    # Collect replays
    replays = collect_replays(replay_dir, DAYS_BACK)
    log.info(f"Found {len(replays)} replay(s) in: {replay_dir}")
    if not replays:
        log.info("Nothing to process.")
        input("Press Enter to exit.")
        return

    # Collect already-processed timestamps
    existing_ts = collect_existing_timestamps(vault_path) if SKIP_ALREADY_PROCESSED else set()
    if existing_ts:
        log.info(f"  Vault already has {len(existing_ts)} note(s) — skipping those replays.")

    # Filter
    to_process = []
    skipped    = 0
    for rp in replays:
        ts = replay_timestamp(rp)
        if ts in existing_ts:
            skipped += 1
        else:
            to_process.append(rp)

    log.info(f"  Skipping {skipped} already-processed | Processing {len(to_process)} new replay(s)\n")

    if not to_process:
        log.info("All replays already processed — vault is up to date.")
        input("Press Enter to exit.")
        return

    # Process
    stats = {'ok': 0, 'err': 0, 'skip_err': 0}
    start_time = time.time()

    for i, rp in enumerate(to_process, 1):
        ts  = replay_timestamp(rp)
        age = datetime.fromtimestamp(rp.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        log.info(f"[{i}/{len(to_process)}] {rp.name}  ({age})")

        try:
            out = sc2_to_gamelog.generate_game_log(
                str(rp), ladder_dir, practice_dir, api_key, player
            )
            if out:
                stats['ok'] += 1
            else:
                stats['err'] += 1
                log.warning(f"  → Parser returned None (skipped)")
        except Exception as e:
            stats['err'] += 1
            log.error(f"  → ERROR: {e}")

        if DELAY_BETWEEN_REPLAYS > 0 and i < len(to_process):
            time.sleep(DELAY_BETWEEN_REPLAYS)

    # Summary
    elapsed = int(time.time() - start_time)
    print()
    print("═" * 55)
    print(f"  Batch complete in {elapsed}s")
    print(f"  ✅ Written:  {stats['ok']}")
    print(f"  ⏭  Skipped:  {skipped} (already in vault)")
    if stats['err']:
        print(f"  ❌ Errors:   {stats['err']}  (check sc2_batch.log)")
    print(f"  Vault:  {vault_path}")
    print("═" * 55)
    print()
    input("Press Enter to close.")


if __name__ == '__main__':
    main()
