# Performance Dashboard

> Charts pull from `Ladder Games/` and `Practice Runs/`. All dataviewjs.
> Reference benchmarks: [[Zerg Macro Benchmarks]]

---

## Drone Economy Timing (80 Drones)

```dataviewjs
if (!window.Chart) {
  await import("https://cdn.jsdelivr.net/npm/chart.js");
}
// mmss: parses "M:SS" timing strings → decimal minutes. Also handles plain numbers.
const mmss = s => { if (s == null) return null; const p = String(s).split(':'); return p.length === 2 ? +p[0] + +p[1]/60 : +s; };

// .array() converts Dataview DataArray → plain JS Array so Chart.js can call .push()
const pages = dv.pages('"Ladder Games"')
  .where(p => p.drones80 != null && String(p.drones80).trim() !== '')
  .sort(p => p.date)
  .slice(-25)
  .array();

const labels = pages.map(p => dv.date(p.date).toFormat("MM-dd"));
const raw    = pages.map(p => mmss(p.drones80));
const trend  = raw.map((_, i, arr) => {
  const subset = arr.slice(Math.max(0, i - 2), i + 1);
  return subset.reduce((a, b) => a + b, 0) / subset.length;
});
const goal = new Array(raw.length).fill(9.0);
const goalGreat = new Array(raw.length).fill(8.0);

const canvas = dv.el("canvas");
new Chart(canvas, {
  type: "line",
  data: {
    labels,
    datasets: [
      { label: "80 Drone Time",       data: raw,       tension: 0.3 },
      { label: "Trend (3-game avg)",  data: trend,     tension: 0.4, borderDash: [3, 3] },
      { label: "Good (9:00)",         data: goal,      borderDash: [6, 6], borderColor: "green",  pointRadius: 0 },
      { label: "Great (8:00)",        data: goalGreat, borderDash: [4, 4], borderColor: "#00aa44", pointRadius: 0 }
    ]
  },
  options: { plugins: { title: { display: true, text: "80-Drone Timing — lower is better" } } }
});
```

**Goal:** Trend toward **8:00 (great) or 9:00 (good)** — flagged beyond 10:00.

---

## Max Supply Timing

```dataviewjs
if (!window.Chart) {
  await import("https://cdn.jsdelivr.net/npm/chart.js");
}
const mmss = s => { if (s == null) return null; const p = String(s).split(':'); return p.length === 2 ? +p[0] + +p[1]/60 : +s; };

const pages = dv.pages('"Ladder Games"')
  .where(p => p.maxsupply != null && String(p.maxsupply).trim() !== '')
  .sort(p => p.date)
  .slice(-25)
  .array();

const labels = pages.map(p => dv.date(p.date).toFormat("MM-dd"));
const raw    = pages.map(p => mmss(p.maxsupply));
const trend  = raw.map((_, i, arr) => {
  const subset = arr.slice(Math.max(0, i - 2), i + 1);
  return subset.reduce((a, b) => a + b, 0) / subset.length;
});
const goalGood  = new Array(raw.length).fill(10.0);
const goalGreat = new Array(raw.length).fill(9.0);

const canvas = dv.el("canvas");
new Chart(canvas, {
  type: "line",
  data: {
    labels,
    datasets: [
      { label: "Max Supply Time",   data: raw,       tension: 0.3 },
      { label: "Trend",             data: trend,     tension: 0.4, borderDash: [3, 3] },
      { label: "Good (10:00)",       data: goalGood,  borderDash: [6, 6], borderColor: "green",  pointRadius: 0 },
      { label: "Great (9:00)",      data: goalGreat, borderDash: [4, 4], borderColor: "#00aa44", pointRadius: 0 }
    ]
  },
  options: { plugins: { title: { display: true, text: "Max Supply Timing — lower is better" } } }
});
```

**Goal: ~9:30–10:00**

---

## Win Rate by Matchup

```dataviewjs
if (!window.Chart) {
  await import("https://cdn.jsdelivr.net/npm/chart.js");
}
const pages = dv.pages('"Ladder Games"')
  .where(p => p.matchup && p.result)
  .array();

const matchups = {};
pages.forEach(p => {
  if (!matchups[p.matchup]) matchups[p.matchup] = { wins: 0, total: 0 };
  matchups[p.matchup].total++;
  if (String(p.result).toLowerCase() === "win") matchups[p.matchup].wins++;
});

const labels = Object.keys(matchups);
const data   = labels.map(m => Math.round((matchups[m].wins / matchups[m].total) * 100));

const canvas = dv.el("canvas");
new Chart(canvas, {
  type: "bar",
  data: {
    labels,
    datasets: [{ label: "Win Rate %", data, backgroundColor: ["#4e79a7", "#f28e2b", "#e15759"] }]
  },
  options: {
    plugins: { title: { display: true, text: "Win Rate by Matchup" } },
    scales: { y: { beginAtZero: true, max: 100 } }
  }
});

dv.paragraph(
  labels.map((l, i) =>
    `**${l}**: ${matchups[l].wins}W / ${matchups[l].total - matchups[l].wins}L (${data[i]}%)`
  ).join(" · ")
);
```

---

## Supply Block Discipline

```dataviewjs
if (!window.Chart) {
  await import("https://cdn.jsdelivr.net/npm/chart.js");
}
const pages = dv.pages('"Ladder Games"')
  .where(p => p.supplyblocks != null)
  .sort(p => p.date)
  .slice(-25)
  .array();

const labels = pages.map(p => dv.date(p.date).toFormat("MM-dd"));
const raw    = pages.map(p => Number(p.supplyblocks));
const trend  = raw.map((_, i, arr) => {
  const subset = arr.slice(Math.max(0, i - 2), i + 1);
  return subset.reduce((a, b) => a + b, 0) / subset.length;
});
const goal = new Array(raw.length).fill(2);

const canvas = dv.el("canvas");
new Chart(canvas, {
  type: "line",
  data: {
    labels,
    datasets: [
      { label: "Supply Blocks",  data: raw,   tension: 0.3 },
      { label: "Trend",          data: trend, tension: 0.4, borderDash: [3, 3] },
      { label: "Goal (<=2)",     data: goal,  borderDash: [6, 6], borderColor: "green", pointRadius: 0 }
    ]
  },
  options: { plugins: { title: { display: true, text: "Supply Block Discipline — lower is better" } } }
});
```

**Goal: Trend toward 0–2 per game. 0 is great, 1–2 is good, 3+ is flagged.**

---

## Inject Consistency

```dataviewjs
if (!window.Chart) {
  await import("https://cdn.jsdelivr.net/npm/chart.js");
}
const pages = dv.pages('"Ladder Games"')
  .where(p => p.injectrating != null)
  .sort(p => p.date)
  .slice(-25)
  .array();

const labels = pages.map(p => dv.date(p.date).toFormat("MM-dd"));
const raw    = pages.map(p => Number(p.injectrating));
const trend  = raw.map((_, i, arr) => {
  const subset = arr.slice(Math.max(0, i - 2), i + 1);
  return subset.reduce((a, b) => a + b, 0) / subset.length;
});
const goal = new Array(raw.length).fill(4);

const canvas = dv.el("canvas");
new Chart(canvas, {
  type: "line",
  data: {
    labels,
    datasets: [
      { label: "Inject Rating (1-5)",  data: raw,   tension: 0.3 },
      { label: "Trend",                data: trend, tension: 0.4, borderDash: [3, 3] },
      { label: "Goal (4+)",            data: goal,  borderDash: [6, 6], borderColor: "green", pointRadius: 0 }
    ]
  },
  options: {
    plugins: { title: { display: true, text: "Inject Consistency — higher is better" } },
    scales: { y: { min: 1, max: 5 } }
  }
});
```

**Target: Average 4–5 rating.** See [[Inject Practice]] for drill methods.

---

## Creep Spread Consistency

```dataviewjs
if (!window.Chart) {
  await import("https://cdn.jsdelivr.net/npm/chart.js");
}
const pages = dv.pages('"Ladder Games"')
  .where(p => p.creeprating != null)
  .sort(p => p.date)
  .slice(-25)
  .array();

const labels = pages.map(p => dv.date(p.date).toFormat("MM-dd"));
const raw    = pages.map(p => Number(p.creeprating));
const goal   = new Array(raw.length).fill(4);

const canvas = dv.el("canvas");
new Chart(canvas, {
  type: "line",
  data: {
    labels,
    datasets: [
      { label: "Creep Rating (1-5)",  data: raw,  tension: 0.3 },
      { label: "Goal (4+)",           data: goal, borderDash: [6, 6], borderColor: "green", pointRadius: 0 }
    ]
  },
  options: {
    plugins: { title: { display: true, text: "Creep Spread Rating — higher is better" } },
    scales: { y: { min: 1, max: 5 } }
  }
});
```

**Target: 4+ rating.** See [[Creep Spread Practice]] for drill methods.

---

## Inject Rate

```dataviewjs
const pages = dv.pages('"Ladder Games" or "Practice Runs"')
  .where(p => p.injectpm != null && !isNaN(p.injectpm))
  .sort(p => p.date, 'asc')
  .slice(-20);

const labels = pages.map(p => p.date?.toString()?.slice(5) ?? '?').array();
const raw    = pages.map(p => parseFloat(p.injectpm) || 0).array();
const goalGreat = new Array(raw.length).fill(2.0);
const goalGood  = new Array(raw.length).fill(1.5);

const canvas = this.container.createEl('canvas', {attr:{width:'700',height:'200'}});
new Chart(canvas, {
  type: 'line',
  data: {
    labels,
    datasets: [
      { label: 'Injects/min', data: raw, borderColor: '#bb44ff', backgroundColor: 'rgba(187,68,255,0.1)', tension: 0.3, fill: true },
      { label: 'Great (2.0/min)', data: goalGreat, borderColor: '#00bb55', borderDash: [6,3], pointRadius: 0 },
      { label: 'Good (1.5/min)', data: goalGood, borderColor: '#ddaa00', borderDash: [4,3], pointRadius: 0 },
    ]
  },
  options: { responsive: false, plugins: { legend: { labels: { color: '#ccc' } } }, scales: { x: { ticks: { color: '#aaa' } }, y: { min: 0, max: 3, ticks: { color: '#aaa' }, title: { display: true, text: 'injects/min', color: '#aaa' } } } }
});
```

**Goal:** Trend toward **2.0/min (great)** or **1.5/min (good)**.
---

## Creep Spread (Tumors Placed)

```dataviewjs
if (!window.Chart) {
  await import("https://cdn.jsdelivr.net/npm/chart.js");
}
const pages = dv.pages('"Ladder Games"')
  .where(p => p.creeptumors != null && String(p.creeptumors).trim() !== '')
  .sort(p => p.date)
  .slice(-25)
  .array();

const labels = pages.map(p => dv.date(p.date).toFormat("MM-dd"));
const raw    = pages.map(p => +p.creeptumors);
const trend  = raw.map((_, i, arr) => {
  const subset = arr.slice(Math.max(0, i - 2), i + 1);
  return subset.reduce((a, b) => a + b, 0) / subset.length;
});
const goalGood  = new Array(raw.length).fill(20);
const goalGreat = new Array(raw.length).fill(30);

const canvas = dv.el("canvas");
new Chart(canvas, {
  type: "line",
  data: {
    labels,
    datasets: [
      { label: "Creep Tumors",    data: raw,       tension: 0.3 },
      { label: "Trend",           data: trend,     tension: 0.4, borderDash: [3, 3] },
      { label: "Good (20+)",      data: goalGood,  borderDash: [6, 6], borderColor: "green",  pointRadius: 0 },
      { label: "Great (30+)",     data: goalGreat, borderDash: [4, 4], borderColor: "#00aa44", pointRadius: 0 }
    ]
  },
  options: { plugins: { title: { display: true, text: "Creep Spread — Tumors Placed per Game (higher is better)" } } }
});
```

**Target: 20+ per game (good), 30+ (great).** Active creep spread = map control and vision.
