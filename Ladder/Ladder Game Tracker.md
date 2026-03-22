# Ladder Game Tracker

> Log every game. For deep per-game notes use [[Templates/New Game Log]]. Review losses with [[Replay Review Checklist]].
> Dashboard pulls from the `Ladder Games/` folder — create each game file there.

---

## How to Log a Game

1. In the `Ladder Games/` folder, create a new note using the **New Game Log** template (Templater will prompt you)
2. Fill in all YAML fields — these feed the Dashboard charts
3. Flag the game for replay review if it was a loss or felt wrong

---

## YAML Field Reference

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `date` | YYYY-MM-DD | 2026-03-10 | Required for sorting |
| `matchup` | ZvT / ZvP / ZvZ | ZvT | Required for win-rate chart |
| `result` | Win / Loss | Win | Must be exactly Win or Loss |
| `map` | text | Goldenaura LE | Map name |
| `drones66` | decimal | 6.0 | Minute:second as decimal (6:00 = 6.0) |
| `drones80` | decimal | 7.5 | 7:30 = 7.5 |
| `maxsupply` | decimal | 9.5 | 9:30 = 9.5 |
| `supplyblocks` | integer | 2 | Count of supply blocks |
| `injectrating` | 1–5 | 4 | 5=perfect, 1=very poor |
| `creeprating` | 1–5 | 3 | 5=excellent coverage, 1=none |
| `scouting_score` | 1–5 | 3 | Did you identify and react to build? |

> ⚠️ Use **decimal point** not comma for timing fields: `7.5` not `7,5`

---

## Manual Summary Table

> Backup log if Dataview isn't rendering. Copy key numbers here.

| # | Date | vs | Map | Result | 66d | 80d | Max | SB | INJ | Notes |
|---|------|----|-----|--------|-----|-----|-----|----|-----|-------|
| 1 | | | | | | | | | | |
| 2 | | | | | | | | | | |
| 3 | | | | | | | | | | |
| 4 | | | | | | | | | | |
| 5 | | | | | | | | | | |

---

## Benchmark Reference

| Metric | Target | Good |
|--------|--------|------|
| 66 drones | By 6:00 | By 5:30 |
| 80 drones | By 7:30–8:00 | By 7:00 |
| Max supply | By 9:30–10:00 | By 9:00 |
| Supply blocks | ≤ 2 | 0 |
| Inject rating | 4+ | 5 |

Full details: [[Zerg Macro Benchmarks]]
