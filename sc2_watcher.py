#!/usr/bin/env python3
"""
sc2_watcher.py
--------------
Watches your SC2 Replays folder for new games and automatically:
  1. Parses the replay (via sc2_to_gamelog.py)
  2. Writes a Game Log .md file into your Obsidian vault
  3. Shows a Windows desktop notification
  4. Opens the new note in Obsidian

Requirements: Python 3.6+ stdlib only. No pip packages needed.

Setup: edit the CONFIG section below, then run START_WATCHER.bat
"""

import os
import sys
import time
import subprocess
import logging
from pathlib import Path
from urllib.parse import quote

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — edit these paths before first use
# ─────────────────────────────────────────────────────────────────────────────

# Your in-game name exactly as it appears in replays (e.g. 'Mizo').
# This is REQUIRED — without it, the parser always picks PlayerID 1 as you,
# which is wrong whenever you happen to be PlayerID 2.
PLAYER_NAME = "PlayerName"

# Your Obsidian vault root folder (where Dashboard.md lives)
VAULT_PATH = r"C:\_workspace\starcraft\ZergBenchmarks"

# The vault name exactly as it appears in Obsidian (File → Vault name)
VAULT_NAME = "ZergBenchmarks"

# SC2 replay folder
SC2_REPLAY_DIR = r"ReplayFolder"

# Subfolder inside your vault where ladder game logs go
LADDER_GAMES_SUBDIR = "Ladder Games"

# Subfolder inside your vault where AI / practice run logs go
PRACTICE_RUNS_SUBDIR = "Practice Runs"

# How often to check for new replays (seconds)
POLL_INTERVAL = 8

# How long to wait after a replay appears before parsing it
# (SC2 writes the file while the game is ending — wait for it to finish)
PARSE_DELAY = 5

# ── Claude coaching (optional) ────────────────────────────────────────────────
# Set your Anthropic API key here to auto-fill Mistakes, Lessons, and Next Focus
# after each game. Leave as "" to skip coaching notes.
# Get your key at: https://console.anthropic.com/
# Alternatively set the ANTHROPIC_API_KEY environment variable.
ANTHROPIC_API_KEY = ""

# ─────────────────────────────────────────────────────────────────────────────
# END CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# Script lives next to sc2_to_gamelog.py
SCRIPT_DIR = Path(__file__).parent.resolve()
GAMELOG_SCRIPT = SCRIPT_DIR / "sc2_to_gamelog.py"

# Log file written next to this script for debugging
LOG_FILE = SCRIPT_DIR / "sc2_watcher.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── SC2 replay directory detection ───────────────────────────────────────────

def find_sc2_replay_dir():
    """
    Auto-detect the StarCraft II Multiplayer replay directory.
    SC2 stores replays at:
      Documents/StarCraft II/Accounts/{id}/{region}/Replays/Multiplayer/
    Returns the path with the most recent replay, or None if not found.
    """
    docs = Path.home() / "Documents"
    base = docs / "StarCraft II" / "Accounts"

    if not base.exists():
        # Try OneDrive Documents location
        onedrive_docs = Path.home() / "OneDrive" / "Documents"
        base = onedrive_docs / "StarCraft II" / "Accounts"

    if not base.exists():
        return None

    # Glob all Multiplayer dirs and pick the one with the most recent file
    candidates = list(base.glob("*/*/Replays/Multiplayer"))
    if not candidates:
        return None

    # Sort by most recently modified replay file
    def latest_mtime(d):
        files = list(d.glob("*.SC2Replay"))
        return max((f.stat().st_mtime for f in files), default=0)

    candidates.sort(key=latest_mtime, reverse=True)
    return str(candidates[0])


# ── Windows desktop notification ─────────────────────────────────────────────

def notify(title, message):
    """
    Show a Windows 10/11 toast-style balloon notification via PowerShell.
    Uses System.Windows.Forms — no external packages needed.
    Runs in a detached hidden window so it doesn't block the watcher.
    """
    # Escape any quotes in the strings
    title   = title.replace('"', '`"')
    message = message.replace('"', '`"')

    ps = f"""
Add-Type -AssemblyName System.Windows.Forms
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon    = [System.Drawing.SystemIcons]::Information
$n.Visible = $true
$n.ShowBalloonTip(6000, "{title}", "{message}", [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Seconds 7
$n.Dispose()
"""
    try:
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        log.warning(f"Notification failed: {e}")


# ── Open file in Obsidian ─────────────────────────────────────────────────────

def open_in_obsidian(vault_name, relative_file_path):
    """
    Open a note in Obsidian using the obsidian:// URI scheme.
    relative_file_path should be relative to the vault root, e.g.:
        "Ladder Games/Game 2026-03-10 ZvT.md"
    Obsidian must already be running, or it will launch automatically.
    """
    # Obsidian URI encodes the file path (forward slashes, URL-encoded)
    file_encoded = quote(relative_file_path.replace("\\", "/"), safe="/")
    vault_encoded = quote(vault_name)
    uri = f"obsidian://open?vault={vault_encoded}&file={file_encoded}"

    try:
        # 'start' is the Windows command to open a URI with its default handler
        subprocess.Popen(
            f'start "" "{uri}"',
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        log.info(f"Opening in Obsidian: {uri}")
    except Exception as e:
        log.warning(f"Could not open Obsidian: {e}")


# ── Replay parser wrapper ─────────────────────────────────────────────────────

def parse_replay(replay_path, ladder_dir, practice_dir, api_key='', player_name=''):
    """
    Call sc2_to_gamelog.generate_game_log() directly.
    player_name: your in-game name — used to identify which player is you.
    """
    if str(SCRIPT_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import sc2_to_gamelog
        import importlib
        importlib.reload(sc2_to_gamelog)
        return sc2_to_gamelog.generate_game_log(str(replay_path), ladder_dir, practice_dir, api_key, player_name)
    except Exception as e:
        log.error(f"Parser error for {replay_path}: {e}", exc_info=True)
        return None


# ── File watcher ──────────────────────────────────────────────────────────────

def watch(replay_dir, vault_path, vault_name):
    """
    Poll replay_dir every POLL_INTERVAL seconds.
    New replay → parse → route to Ladder Games or Practice Runs based on AI detection.
    """
    replay_dir   = Path(replay_dir)
    ladder_dir   = str(Path(vault_path) / LADDER_GAMES_SUBDIR)
    practice_dir = str(Path(vault_path) / PRACTICE_RUNS_SUBDIR)

    log.info("=" * 60)
    log.info("SC2 → Obsidian Watcher  started")
    log.info(f"  Watching:      {replay_dir}")
    log.info(f"  Ladder Games:  {ladder_dir}")
    log.info(f"  Practice Runs: {practice_dir}")
    log.info("=" * 60)

    known = set(replay_dir.glob("*.SC2Replay"))
    log.info(f"Found {len(known)} existing replays — watching for new ones...")

    # Resolve API key and player name
    api_key     = ANTHROPIC_API_KEY.strip() or os.environ.get('ANTHROPIC_API_KEY', '')
    player_name = PLAYER_NAME.strip()       or os.environ.get('SC2_PLAYER_NAME', '')
    if api_key:
        log.info("Coaching notes: enabled (Claude API key set)")
    else:
        log.info("Coaching notes: disabled (set ANTHROPIC_API_KEY in config to enable)")

    notify("SC2 Watcher Active", "Watching for new replays.")

    pending = {}

    while True:
        try:
            time.sleep(POLL_INTERVAL)

            current = set(replay_dir.glob("*.SC2Replay"))
            new_replays = current - known
            known = current

            for rp in new_replays:
                log.info(f"New replay detected: {rp.name}")
                pending[rp] = time.monotonic() + PARSE_DELAY

            ready = [rp for rp, t in pending.items() if time.monotonic() >= t]
            for rp in ready:
                del pending[rp]
                log.info(f"Parsing: {rp.name}")

                out_path = parse_replay(rp, ladder_dir, practice_dir, api_key, player_name)

                if out_path:
                    out_path = Path(out_path)

                    # Determine which folder it landed in for the notification
                    if PRACTICE_RUNS_SUBDIR in str(out_path):
                        dest_label = "Practice Runs (vs AI)"
                    else:
                        dest_label = "Ladder Games"

                    log.info(f"Written to {dest_label}: {out_path.name}")

                    try:
                        rel = out_path.relative_to(vault_path)
                    except ValueError:
                        parent = PRACTICE_RUNS_SUBDIR if PRACTICE_RUNS_SUBDIR in str(out_path) else LADDER_GAMES_SUBDIR
                        rel = Path(parent) / out_path.name

                    notify(
                        f"New Log → {dest_label}",
                        f"{out_path.stem}\nOpening in Obsidian…"
                    )

                    time.sleep(2)
                    open_in_obsidian(vault_name, str(rel))

                else:
                    log.error(f"Failed to parse: {rp.name}")
                    notify("SC2 Watcher — Parse Error", f"Could not parse {rp.name}.\nCheck sc2_watcher.log")

        except KeyboardInterrupt:
            log.info("Watcher stopped by user.")
            break
        except Exception as e:
            log.error(f"Watcher loop error: {e}", exc_info=True)
            time.sleep(POLL_INTERVAL)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # Validate sc2_to_gamelog.py exists
    if not GAMELOG_SCRIPT.exists():
        print(f"ERROR: sc2_to_gamelog.py not found at {GAMELOG_SCRIPT}")
        print("Make sure sc2_watcher.py and sc2_to_gamelog.py are in the same folder.")
        input("Press Enter to exit...")
        sys.exit(1)

    # Resolve replay directory
    replay_dir = SC2_REPLAY_DIR.strip() if SC2_REPLAY_DIR.strip() else None
    if not replay_dir:
        log.info("SC2_REPLAY_DIR not set — auto-detecting...")
        replay_dir = find_sc2_replay_dir()
        if replay_dir:
            log.info(f"Auto-detected replay dir: {replay_dir}")
        else:
            print("\nERROR: Could not auto-detect your SC2 replay folder.")
            print("Please open sc2_watcher.py and set SC2_REPLAY_DIR manually.")
            input("Press Enter to exit...")
            sys.exit(1)

    if not Path(replay_dir).exists():
        print(f"\nERROR: Replay directory not found:\n  {replay_dir}")
        print("Check that SC2 is installed and has created replays.")
        input("Press Enter to exit...")
        sys.exit(1)

    # Validate vault path
    vault_path = VAULT_PATH.strip()
    if not Path(vault_path).exists():
        print(f"\nERROR: Vault path not found:\n  {vault_path}")
        print("Please edit VAULT_PATH in sc2_watcher.py to point to your vault folder.")
        input("Press Enter to exit...")
        sys.exit(1)

    watch(replay_dir, vault_path, VAULT_NAME)


if __name__ == "__main__":
    main()
