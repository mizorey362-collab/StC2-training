# ZergBenchmarks — SC2 Replay → Obsidian Vault

An automatic StarCraft II improvement tracker for Zerg players. After every game, a structured Game Log note is written into your [Obsidian](https://obsidian.md) vault with exact timings, coaching feedback, build analysis, and a recommended counter-strategy — all parsed directly from the `.SC2Replay` binary using Blizzard's [s2protocol](https://github.com/Blizzard/s2protocol) library.

* * *

## What it does

After each ladder game or practice drill:

1. **Detects your race, opponent, build, and result** from the replay binary
2. **Extracts exact timings** via s2protocol game-loop timestamps (not estimates):
  * Drone milestones: 40 / 55 / 66 / 80 alive simultaneously (deaths subtracted)
  * Hatchery completions (3rd, 4th), Lair, Hive
  * +1/+2 attack and armour upgrade completions
  * Max supply (when 24th Overlord completes, first hitting 200 cap)
  * Inject count, rate (per minute), and % of 3-hatch theoretical capacity
  * Supply block count with timestamps
3. **Detects your build order and opener** (Hatch First / Pool First, then composition)
4. **Evaluates your reaction** to the enemy build (✅ Correct / ❌ Suboptimal / ⚠️ Situational)
5. **Generates a coaching section** with specific mistakes, lessons, and a next-session focus
6. **Recommends the correct counter-strategy** for the enemy build, including:
  * Ideal composition and build order
  * Key timings to hit
  * Best attack window with army requirements
  * Common mistakes to avoid

* * *

## Files

| File | Purpose |
| --- | --- |
| `sc2_to_gamelog.py` | Core parser — 3,000 lines, pure stdlib + s2protocol |
| `sc2_watcher.py` | Windows background watcher — polls for new replays and auto-parses |
| `sc2_batch_analyze.py` | Bulk processor — parses your entire existing replay folder |
| `START_WATCHER.bat` | Double-click to start the live watcher |
| `INSTALL_STARTUP.bat` | Registers the watcher to auto-start on Windows login |
| `ANALYZE_ALL.bat` | Double-click to process all existing replays |
| `SETUP.md` | Full installation and configuration guide |

* * *

## Requirements

* **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
* **s2protocol** — Blizzard's official replay decoder

    pip install s2protocol --no-deps

> **Python 3.12+ note:** The `imp` module was removed in Python 3.12. If you see `ModuleNotFoundError: No module named 'imp'` after installing s2protocol, follow the patch in `SETUP.md` Step 2 — it's a one-time 15-line edit to the installed s2protocol file.

Verify your setup:

    python -c "from s2protocol import versions; v = versions.build(95299); print('OK -', v.__name__)"

* * *

## Quick start

1. Install Python and s2protocol (see above)
2. Edit `sc2_watcher.py` — set `PLAYER_NAME`, `VAULT_PATH`, `VAULT_NAME`
3. Copy all files into your vault root folder
4. Double-click `ANALYZE_ALL.bat` to process existing replays
5. Double-click `START_WATCHER.bat` — new notes appear within ~15 seconds of finishing a game

* * *

## Example output

### YAML front-matter (Obsidian DataviewJS compatible)

    type: ladder-game
    date: 2026-03-10
    matchup: ZvT
    result: Win
    map: "Ruby Rock LE"
    
    enemy_build: "Bio/Tank (Marine + Siege Tank)"
    my_build: "Hatch First → Hydra/Lurker"
    build_detected: true
    reaction_correct: true
    
    drones40: 5:03
    drones55: 7:36
    drones66: 11:55
    drones80:
    
    hatch3: 2:41
    hatch4: 10:05
    lair: 4:32
    hive: 10:59
    
    atk1: 6:07
    armor1: 7:42
    
    maxsupply: 14:44
    supplyblocks: 4
    injectcount: 24
    injectpm: 1.23
    injectrating: 32
    
    apm: 90
    mmr: 2274
    duration: "19:30"

### Auto-coaching (rule-based, offline)

    # Mistakes
    
    - 4th hatchery at 10:05 — 155s behind the 7:30 target.
    - 4 supply blocks detected (4:53, 6:31, 9:26, 14:52) — set a habit
      of checking supply every inject cycle.
    - 24 injects (1.23/min) — below average; try to inject every 45
      seconds per hatchery (32% of 3-hatch cycle capacity).

### Counter-strategy guide

    # Recommended Counter vs Bio/Tank (Marine + Siege Tank)
    
    **Ideal composition:** Hydra/Lurker (with Banelings vs bio clumps)
    **Build order:** Hatch First → Pool ~1:15 → Roach Warren → Hydra Den → Lurker Den
    
    ### Best Attack Timing vs Bio/Tank (Marine + Siege Tank)
    
    **Window:** 10:00–13:00 real time
    **Army needed:** 8–12 Lurkers + 15+ Hydralisks + Banelings
    
    - Hold first, then counter: Bio/Tank attacks at 11–13 min — let it
      break on your Lurkers, then push out
    - Attack timing: 13:00–15:00 — move out while Terran is rebuilding
    - Vipers (Blinding Cloud) + Hydra is the late-game answer

* * *

## How the parser works

### Player identification

Replays record which player saved the file via a `0x06` local-player marker in the initdata stream. When `PLAYER_NAME` is set, name matching takes priority over this marker — this handles replays recorded by the opponent (where the marker points to their slot instead of yours).

### Drone milestone detection

Uses `SUnitBornEvent` + `SUnitDiedEvent` from the tracker stream, matched by unit tag. Each drone birth increments an alive counter; each death decrements it. A milestone fires when the alive count first reaches the target. This gives true "simultaneously alive" counts rather than cumulative births, which is the meaningful metric for macro evaluation.

### Inject detection

Scans `SCmdEvent` entries in the game events stream for commands targeting a unit with `m_snapshotUnitLink` ∈ {109=Hatchery, 123=Lair, 124=Hive} issued by the human player. This catches all inject variants — standard hotkey, alternate hotkey, queued injects — regardless of which ability link was used.

### Build detection

**Opener** is determined by comparing structure completion timestamps:

* If natural hatch completes before pool → Hatch First
* If pool placed within 10 real seconds → Early Pool (9-pool)
* Otherwise → Pool First

**Composition** uses unit production counts (not structure presence), with thresholds requiring meaningful quantities: `Lurker > 3`, `Hydralisk > 5`, `Corruptor > 3`, etc. This avoids false positives from buildings built as prerequisites (e.g. Infestors Pit built for Hive tech, not an Infestor build).

### All timings are exact

Every timestamp comes from s2protocol game-loop data converted with:

    real_seconds = game_loop / 22.4
    # = 16 game loops/game-second × 1.4 Faster game speed

There are no byte-position approximations or interpolated estimates anywhere in the codebase.

* * *

## Enemy builds detected

| Terran | Protoss | Zerg |
| --- | --- | --- |
| Bio/Tank (Marine + Siege Tank) | FFE (Forge Fast Expand) | Muta Transition |
| Standard Bio (MMM) | Stargate / Oracle / Air | Roach Rush |
| Early Bio Aggression | Robo (Immortal/Colossus) | Roach/Hydra |
| BattleCruiser Rush | Gateway Aggression / 4-Gate | Ling/Bane |
| Mech | Standard Gate Expand | Lurker (Ling/Lurker or Roach/Lurker) |
| Air Heavy (Banshee/Liberator/BC) |     | Standard Hatch First |
| Standard 1-1-1 Opener |     |     |

Each has a full counter guide with ideal composition, build order, attack timing window, key units, and common mistakes.

* * *

## Obsidian vault structure

    ZergBenchmarks/
    ├── Dashboard.md              ← overview with DataviewJS charts
    ├── Ladder Games/
    │   ├── Game 2026-03-10 19-30 ZvT.md
    │   └── ...
    ├── Practice Runs/
    │   ├── Drill 2026-03-09 vs AI Hard.md
    │   └── ...
    ├── Analysis/                 ← manual notes and session reviews
    ├── Benchmarks/               ← reference timing targets
    └── Strategy/                 ← matchup notes

Ladder game notes are named `Game YYYY-MM-DD HH-MM ZvX.md` (dashes in time for Windows compatibility). Drill notes use `Drill YYYY-MM-DD HH-MM vs AI Hard.md`. All timestamps come from the replay file's modification time.

* * *

## Benchmarks (Diamond ~2200 MMR, calibrated on real replays)

### Drone milestones — alive count

| Milestone | ZvT great | ZvT ok | ZvP great | ZvP ok | Drill great | Drill ok |
| --- | --- | --- | --- | --- | --- | --- |
| 40 drones | 4:00 | 6:30 | 3:30 | 6:00 | 4:00 | 6:00 |
| 66 drones | 8:00 | 12:00 | 7:00 | 10:00 | 7:00 | 10:00 |
| 80 drones | 10:00 | 14:00 | 8:30 | 12:30 | 8:30 | 11:30 |

### Inject rate

| Rating | Injects/min |
| --- | --- |
| Great | ≥ 2.0 |
| Good | ≥ 1.5 |
| Ok  | ≥ 1.0 |

* * *

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `ModuleNotFoundError: No module named 'imp'` | Apply the patch in `SETUP.md` Step 2 |
| `Injects: ⚠️ not detected` | s2protocol not working — run the verify command in `SETUP.md` |
| Wrong player detected | Set `PLAYER_NAME` in `sc2_watcher.py` to your exact SC2 battle.net name |
| Opponent shown as AI | Opponent had no MMR (unranked). Fixed in current version — name-based detection used first |
| Drill filed as ladder game | If the parser can't find "A.I." in any player name it defaults to ladder classification |

* * *

## Limitations

* **1v1 only** — team games are not supported
* **Zerg player only** — opponent's race is tracked but coaching and drone metrics only apply to Zerg
* **Replay must be on disk** — the watcher polls the filesystem; cloud-only replays won't be detected until synced
* **Corrupted replays** — disconnects and very short games (< 1 min) may produce partial data; the note is still written with available fields

* * *

## License

MIT
