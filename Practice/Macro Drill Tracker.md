# Macro Drill Tracker

Practice vs AI to improve macro consistency. The table below auto-fills from your 10 most recent drill notes in `Practice Runs/`. Fill **score** and **notes** manually after each session.

```dataviewjs
const mmss = s => {
  if (s == null || String(s).trim() === '') return null;
  const p = String(s).split(':');
  return p.length === 2 ? +p[0] + +p[1]/60 : +s;
};

// [great_min, good_min, ok_min]
const B = {
  drones40:    [3.50, 4.50, 5.50],  // great=3:30 / good=4:30 / ok=5:30
  drones55:    [5.50, 7.00, 8.50],  // great=5:30 / good=7:00 / ok=8:30
  drones66:    [7.00, 8.50, 10.00], // great=7:00 / good=8:30 / ok=10:00
  drones80:    [8.50, 10.00, 11.50],// great=8:30 / good=10:00 / ok=11:30
  hatch3:      [2.50, 3.50, 4.50],  // great=2:30 / good=3:30 / ok=4:30
  lair:        [3.50, 4.50, 5.50],  // great=3:30 / good=4:30 / ok=5:30
  hatch4:      [4.50, 6.00, 7.50],  // great=4:30 / good=6:00 / ok=7:30
  atk1:        [5.50, 7.00, 8.50],  // great=5:30 / good=7:00 / ok=8:30
  maxsupply:   [9.00, 10.00, 11.00],// great=9:00 / good=10:00 / ok=11:00
  supplyblocks:[0,    0,     2   ],  // lower is better
  creeptumors: [30,   20,   10  ],  // higher is better: >30 great, >20 good, >10 ok
  injectpm:    [2.0,  1.5,  1.0 ],  // higher is better: >2.0 great, >1.5 good, >1.0 ok
};

function timingCell(raw, key) {
  const v = mmss(raw);
  const display = (v == null) ? '—' : String(raw);
  let color = '#888';
  if (v != null && B[key]) {
    const [great, good, ok] = B[key];
    if (v <= great) color = '#00bb55';
    else if (v <= good) color = '#44aa44';
    else if (v <= ok)  color = '#ddaa00';
    else               color = '#cc4444';
  }
  const td = dv.el('td', display, {attr:{style:`color:${color};font-weight:bold;padding:3px 6px;white-space:nowrap`}});
  return td;
}

function countCell(raw, key) {
  const v = raw != null && String(raw).trim() !== '' ? +raw : null;
  const display = v != null ? String(v) : '—';
  let color = '#888';
  if (v != null && B[key]) {
    const [great, good, ok] = B[key];
    // For count fields: higher is better
    if (key === 'creeptumors') {
      if (v >= great) color = '#00bb55';
      else if (v >= good) color = '#44aa44';
      else if (v >= ok)  color = '#ddaa00';
      else               color = '#cc4444';
    } else if (key === 'supplyblocks') {
      // lower is better
      if (v <= 0)    color = '#00bb55';
      else if (v <= good) color = '#44aa44';
      else if (v <= ok)  color = '#ddaa00';
      else               color = '#cc4444';
    } else if (key === 'injectpm') {
      // higher is better (float)
      if (v >= great) color = '#00bb55';
      else if (v >= good) color = '#44aa44';
      else if (v >= ok)  color = '#ddaa00';
      else               color = '#cc4444';
    }
  }
  return dv.el('td', display, {attr:{style:`color:${color};font-weight:bold;padding:3px 6px`}});
}

const pages = dv.pages('"Practice Runs"')
  .where(p => p.type === 'drill')
  .sort(p => p.file.mtime, 'desc')
  .slice(0, 10)
  .array()
  .reverse();

if (pages.length === 0) {
  dv.paragraph('_No drill notes found yet. Run a game vs AI and the watcher fills this automatically._');
} else {
  const headers = ['#','Date','vs','40d','55d','66d','80d','3rdH','Lair','4thH','+1/+1','MaxSup','Blk','Tumors','Inj/m','Score','Notes'];
  const table = dv.el('table','',{attr:{style:'width:100%;border-collapse:collapse;font-size:0.85em'}});
  const thead = dv.el('thead','');
  const hrow  = dv.el('tr','');
  headers.forEach(h => {
    hrow.appendChild(dv.el('th', h, {attr:{style:'text-align:left;padding:3px 6px;border-bottom:1px solid #555;white-space:nowrap'}}));
  });
  thead.appendChild(hrow);
  table.appendChild(thead);

  const tbody = dv.el('tbody','');
  pages.forEach((p, i) => {
    const tr = dv.el('tr','',{attr:{style: i%2===1?'background:rgba(255,255,255,0.03)':''}});
    const pad = s => dv.el('td', String(s ?? '—'), {attr:{style:'padding:3px 6px;white-space:nowrap'}});

    tr.appendChild(pad(i + 1));
    tr.appendChild(pad(String(p.date||'').slice(0,10)));
    tr.appendChild(pad(String(p.vs||'').replace('A.I. ','')));

    tr.appendChild(timingCell(p.drones40,  'drones40'));
    tr.appendChild(timingCell(p.drones55,  'drones55'));
    tr.appendChild(timingCell(p.drones66,  'drones66'));
    tr.appendChild(timingCell(p.drones80,  'drones80'));
    tr.appendChild(timingCell(p.hatch3,    'hatch3'));
    tr.appendChild(timingCell(p.lair,      'lair'));
    tr.appendChild(timingCell(p.hatch4,    'hatch4'));
    tr.appendChild(timingCell(p.atk1,      'atk1'));
    tr.appendChild(timingCell(p.maxsupply, 'maxsupply'));

    tr.appendChild(countCell(p.supplyblocks, 'supplyblocks'));
    tr.appendChild(countCell(p.creeptumors,  'creeptumors'));
    tr.appendChild(countCell(p.injectpm,     'injectpm'));

    tr.appendChild(pad(p.score != null && String(p.score).trim() !== '' ? p.score : ''));
    tr.appendChild(pad(p.notes != null && String(p.notes).trim() !== '' ? p.notes : ''));

    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  dv.container.appendChild(table);

  dv.paragraph('🟢 Great &nbsp; 🟡 Good &nbsp; 🟠 OK &nbsp; 🔴 Late — Timing cols: lower=better. Tumors: higher=better. Fill **Score** (1–5) and **Notes** after each session.');
}
```

---

**Drill targets (vs AI) — exact s2protocol timings:**

| Benchmark | 🟢 Great | ✅ Good | ⚠️ OK |
|-----------|---------|--------|-------|
| 40 drones | ≤ 3:30 | ≤ 4:30 | ≤ 5:30 |
| 55 drones | ≤ 5:30 | ≤ 7:00 | ≤ 8:30 |
| 66 drones | ≤ 7:00 | ≤ 8:30 | ≤ 10:00 |
| 80 drones | ≤ 8:30 | ≤ 10:00 | ≤ 11:30 |
| 3rd hatch | ≤ 2:30 | ≤ 3:30 | ≤ 4:30 |
| Lair      | ≤ 3:30 | ≤ 4:30 | ≤ 5:30 |
| 4th hatch | ≤ 4:30 | ≤ 6:00 | ≤ 7:30 |
| +1/+1 upg | ≤ 7:00 | ≤ 8:30 | ≤ 10:00 |
| Hive      | ≤ 7:00 | ≤ 8:30 | ≤ 10:00 |
| Max supply | ≤ 9:00 | ≤ 10:00 | ≤ 11:00 |
| Creep tumors | ≥ 30 | ≥ 20 | ≥ 10 |
| Injects/min | ≥ 2.0 | ≥ 1.5 | ≥ 1.0 |
| Supply blocks | 0 | ≤ 2 | ≤ 4 |

See full benchmarks: [[Zerg Macro Benchmarks]]
