# Zerg Improvement Dashboard

> **Goal: 80 drones by 7:30–8:00. Max supply by 9:30–10:00.**
> Reference: [[Zerg Macro Benchmarks]]

---

## Daily Training Loop

1. Run 3 macro drills → [[Macro Drill Tracker]]
2. Play 3–6 ladder games → [[Ladder Game Tracker]]
3. Review 1 loss → [[Replay Review Checklist]]
4. Record insight → [[Improvement Journal]]

---

## Core Sections

| Area | File |
|------|------|
| 🏋️ Practice | [[Macro Drill Tracker]] · [[Inject Practice]] · [[Creep Spread Practice]] |
| 📊 Benchmarks | [[Zerg Macro Benchmarks]] · [[Build Order Benchmark]] · [[Macro Timeline (0-10 Minutes)]] |
| 🎮 Strategy | [[Zerg Decision Tree (First 8 Minutes)]] · [[Scouting Guide]] · [[Build Recognition System]] |
| 🪜 Ladder | [[Ladder Game Tracker]] · [[Replay Review Checklist]] |
| 📈 Progress | [[Weekly Training Focus]] · [[Improvement Journal]] |

---

## Recent Ladder Games

```dataview
table date, matchup, result, drones80, maxsupply, supplyblocks, injectrating
from "Ladder Games"
sort date desc
limit 10
```

---

## Macro Averages (Ladder)

```dataview
table
avg(drones66) as "Avg 66 Drone Time",
avg(drones80) as "Avg 80 Drone Time",
avg(maxsupply) as "Avg Max Supply Time"
from "Ladder Games"
```

Reference: [[Zerg Macro Benchmarks]]

---

## Practice Drill Results

```dataview
table date, drones80, maxsupply, score
from "Practice Runs"
sort date desc
limit 10
```

---

## Win Rate by Matchup

```dataview
table matchup, length(rows) as "Games Played"
from "Ladder Games"
group by matchup
```

---

## Supply Block Tracker

```dataview
table date, matchup, supplyblocks
from "Ladder Games"
sort supplyblocks desc
limit 10
```

---

## Inject Consistency

```dataview
table date, matchup, injectrating
from "Ladder Games"
sort date desc
limit 15
```

---

## Strategy Quick Links

- [[Zerg Decision Tree (First 8 Minutes)]]
- [[Build Recognition System]]
- [[Scouting Guide]]
- [[Macro Timeline (0-10 Minutes)]]
