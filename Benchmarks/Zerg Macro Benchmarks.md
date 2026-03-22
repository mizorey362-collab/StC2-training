# Zerg Macro Benchmarks

Goal: **80 drones by 9:00 and max supply by 10:00–11:00**

Three tiers per benchmark. The parser flags anything beyond **OK**.

> ℹ️ *Drone milestones track **drones simultaneously alive** (not total built). Deaths from attacks and morphs are subtracted. Benchmarks calibrated with exact s2protocol timestamps at Faster speed.*

---

## Drone Milestones — Drill (vs AI, universal)

| Benchmark | 🟢 Great | ✅ Good | ⚠️ OK | ❌ Late |
|-----------|---------|--------|-------|--------|
| 40 drones | ≤ 3:30 | ≤ 4:30 | ≤ 5:30 | > 5:30 |
| 55 drones | ≤ 5:30 | ≤ 7:00 | ≤ 8:30 | > 8:30 |
| 66 drones | ≤ 7:00 | ≤ 8:30 | ≤ 10:00 | > 10:00 |
| 80 drones | ≤ 8:30 | ≤ 10:00 | ≤ 11:30 | > 11:30 |

---

## Drone Milestones — Ladder (matchup-specific)

### ZvT
| Benchmark | 🟢 Great | ✅ Good | ⚠️ OK | ❌ Late |
|-----------|---------|--------|-------|--------|
| 40 drones | ≤ 4:00 | ≤ 5:00 | ≤ 6:30 | > 6:30 |
| 55 drones | ≤ 6:00 | ≤ 7:30 | ≤ 9:00 | > 9:00 |
| 66 drones | ≤ 8:00 | ≤ 10:00 | ≤ 12:00 | > 12:00 |
| 80 drones | ≤ 10:00 | ≤ 12:00 | ≤ 14:00 | > 14:00 |
### ZvP
| Benchmark | 🟢 Great | ✅ Good | ⚠️ OK | ❌ Late |
| 40 drones | ≤ 3:30 | ≤ 4:30 | ≤ 6:00 | > 6:00 |
| 55 drones | ≤ 5:30 | ≤ 7:00 | ≤ 8:30 | > 8:30 |
| 66 drones | ≤ 7:00 | ≤ 8:30 | ≤ 10:00 | > 10:00 |
| 80 drones | ≤ 8:30 | ≤ 10:30 | ≤ 12:30 | > 12:30 |
| 80 drones | ≤ 7:30 | ≤ 8:30 | ≤ 9:30 | > 9:30 |
| 3rd hatch | ≤ 2:00 | ≤ 3:00 | ≤ 4:00 | > 4:00 |
| 4th hatch | ≤ 4:00 | ≤ 5:30 | ≤ 7:30 | > 7:30 |
| Lair      | ≤ 3:00 | ≤ 4:00 | ≤ 5:00 | > 5:00 |
| Hive      | ≤ 6:30 | ≤ 8:00 | ≤ 9:30 | > 9:30 |
| +1/+1 upgrades | ≤ 6:30 | ≤ 8:00 | ≤ 9:30 | > 9:30 |
| Max supply | ≤ 8:30 | ≤ 9:30 | ≤ 10:30 | > 10:30 |

### ZvZ
| Benchmark | 🟢 Great | ✅ Good | ⚠️ OK | ❌ Late |
| 40 drones | ≤ 3:30 | ≤ 4:30 | ≤ 6:00 | > 6:00 |
| 55 drones | ≤ 5:30 | ≤ 7:00 | ≤ 8:30 | > 8:30 |
| 66 drones | ≤ 7:00 | ≤ 8:30 | ≤ 10:00 | > 10:00 |
| 80 drones | ≤ 8:30 | ≤ 10:30 | ≤ 12:30 | > 12:30 |
| 80 drones | ≤ 7:30 | ≤ 8:30 | ≤ 9:30 | > 9:30 |
| 3rd hatch | ≤ 2:00 | ≤ 3:00 | ≤ 4:00 | > 4:00 |
| 4th hatch | ≤ 4:00 | ≤ 5:30 | ≤ 7:30 | > 7:30 |
| Lair      | ≤ 3:00 | ≤ 4:00 | ≤ 5:00 | > 5:00 |
| Hive      | ≤ 6:30 | ≤ 8:00 | ≤ 9:30 | > 9:30 |
| +1/+1 upgrades | ≤ 6:30 | ≤ 8:00 | ≤ 9:30 | > 9:30 |
| Max supply | ≤ 8:00 | ≤ 9:00 | ≤ 10:00 | > 10:00 |

---

## Max Supply

| Tier | ZvT | ZvP/ZvZ |
|------|-----|---------|
| 🟢 Great | ≤ 9:00 | ≤ 8:00–8:30 |
| ✅ Good | ≤ 10:00 | ≤ 9:00–9:30 |
| ⚠️ OK | ≤ 11:00 | ≤ 10:00–10:30 |

---


---

## Inject Rate

| Tier | Injects/min | Notes |
|------|------------|-------|
| 🟢 Great | ≥ 2.0/min | Consistent inject cycling every ~45s per hatch |
| ✅ Good | ≥ 1.5/min | Missing some cycles but staying attentive |
| ⚠️ OK | ≥ 1.0/min | Noticeable gaps; room to automate the habit |
| ❌ Low | < 1.0/min | Queens sitting idle — significant larva loss |

**3-hatch cycle capacity:** ~1.35 injects/min theoretical maximum.  
**Practical target:** 1.5–2.0/min accounts for inject cycles across main, natural, and 3rd base.

The parser tracks **inject_rating** = actual ÷ theoretical max for 3 hatches × 100%.  
A rating of 50%+ is solid; 70%+ is excellent for the Diamond level.

Related:
- [[Macro Drill Tracker]]
- [[Build Order Benchmark]]
- [[Macro Timeline (0-10 Minutes)]]
- [[Zerg Decision Tree (First 8 Minutes)]]
