# SC2 → Obsidian Integration — Setup Guide

Automatically turns every StarCraft II replay into a Game Log note in your
ZergBenchmarks vault, with exact timings from Blizzard's s2protocol library.

---

## Files in this folder

| File | Purpose |
|------|---------|
| `sc2_to_gamelog.py` | Replay parser — reads the .SC2Replay binary |
| `sc2_watcher.py` | Background watcher — detects new replays |
| `sc2_batch_analyze.py` | Bulk processor — parses all your existing replays |
| `START_WATCHER.bat` | Double-click to start watching for new replays |
| `INSTALL_STARTUP.bat` | Makes the watcher launch on Windows login |
| `ANALYZE_ALL.bat` | Double-click to process all existing replays |
| `sc2_watcher.log` | Created automatically — check here if something breaks |

---

## Step 1 — Install Python

Download Python 3.10+ from https://www.python.org/downloads/
During install, **check "Add Python to PATH"**.

---

## Step 2 — Install s2protocol (required for exact timings)

Open Command Prompt and run:

```
pip install s2protocol --no-deps
```

This installs Blizzard's official replay decoder. The `--no-deps` flag skips
the optional `mpyq` archive library (not needed — we handle that ourselves).

**Without s2protocol:** the parser falls back to approximate byte-position timing
(accuracy ±1–2 min). Everything still works, but drone/structure/upgrade timings
will be less precise and **inject counts will not be recorded**.

To verify it installed correctly:
```
python -c "from s2protocol import versions; v = versions.build(95299); print('OK -', v.__name__)"
```

It should print `OK - protocol95299`. If you see an error about `imp`, follow the fix below.

---

### Fix: `ModuleNotFoundError: No module named 'imp'` (Python 3.12+)

The `imp` module was removed in Python 3.12. If you see this error, manually patch
the installed file.

**1.** Open this file in Notepad (adjust your username if needed):
```
C:\Users\ema_m\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\s2protocol\versions\__init__.py
```

**2.** Find the line at the very top that says:
```python
import imp
```

**3.** Delete that line and replace it with the following block:
```python
import importlib.util, importlib.machinery
import types, os

class imp:
    @staticmethod
    def find_module(name, path=None):
        search = path or []
        for directory in search:
            full = os.path.join(directory, name + '.py')
            if os.path.isfile(full):
                return (open(full, 'r'), full, ('.py', 'r', 1))
        raise ImportError(f"No module named {name!r}")

    @staticmethod
    def load_module(name, file, pathname, description):
        loader = importlib.machinery.SourceFileLoader(name, pathname)
        spec   = importlib.util.spec_from_loader(name, loader)
        mod    = types.ModuleType(spec.name)
        mod.__file__ = pathname
        mod.__spec__ = spec
        loader.exec_module(mod)
        return mod

    @staticmethod
    def load_source(name, path):
        loader = importlib.machinery.SourceFileLoader(name, path)
        spec   = importlib.util.spec_from_loader(name, loader)
        mod    = types.ModuleType(spec.name)
        loader.exec_module(mod)
        return mod
```

**4.** Save the file, then run the verify command again:
```
python -c "from s2protocol import versions; v = versions.build(95299); print('OK -', v.__name__)"
```

It should now print `OK - protocol95299` and inject tracking will work.

> **Note:** The path above contains `pythoncore-3.14-64` — if you have a different
> Python version installed the folder name will differ slightly. Browse to
> `C:\Users\ema_m\AppData\Local\Python\` to find your version's folder.

---

## Step 3 — Place the files

Put **all files** inside your vault folder, at the root
(same level as `Dashboard.md`):

```
ZergBenchmarks/
├── Dashboard.md
├── Ladder Games/
├── sc2_to_gamelog.py     ← here
├── sc2_watcher.py        ← here
├── sc2_batch_analyze.py  ← here
├── START_WATCHER.bat     ← here
├── INSTALL_STARTUP.bat   ← here
└── ANALYZE_ALL.bat       ← here
```

---

## Step 4 — Edit sc2_watcher.py (two lines)

Open `sc2_watcher.py` in Notepad and find the CONFIG block near the top.
Change these two lines:

```python
VAULT_PATH = r"C:\Users\YourName\Documents\ZergBenchmarks"
VAULT_NAME = "ZergBenchmarks"
```

- **VAULT_PATH** — full path to your vault folder on disk
- **VAULT_NAME** — the name exactly as shown in Obsidian's vault switcher

The SC2 replay folder is already set to your path:

```
C:\Users\ema_m\OneDrive\Documents\StarCraft II\Accounts\406314395\2-S2-1-10900170\Replays\Multiplayer
```

If you ever need to change it, edit `SC2_REPLAY_DIR` in `sc2_watcher.py`.

---

## Step 5 — Process existing replays (optional)

Double-click **ANALYZE_ALL.bat** to parse all replays in your SC2 folder.
Already-processed replays are skipped automatically — safe to run again anytime.

---

## Step 6 — Start the live watcher

1. Double-click **START_WATCHER.bat**
2. A console window opens — it's now watching
3. Play a game (or copy any `.SC2Replay` into your Multiplayer folder)
4. Within ~15 seconds you should see:
   - A Windows desktop notification
   - Obsidian opens the new Game Log note

---

## Step 7 — Auto-start on login (optional but recommended)

Double-click **INSTALL_STARTUP.bat** once.
After that the watcher starts automatically every time you log into Windows.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: s2protocol` | Run `pip install s2protocol --no-deps` |
| `ModuleNotFoundError: No module named 'imp'` | See the **Fix** section in Step 2 above |
| `AttributeError: type object 'imp' has no attribute 'find_module'` | Your patch is incomplete — replace the full `import imp` block using the code in Step 2 |
| Injects show ⚠️ not detected | s2protocol not working — run the verify command in Step 2 and apply the imp fix if needed |
| Timings look off | Verify s2protocol: `python -c "from s2protocol import versions; v = versions.build(95299); print('OK -', v.__name__)"` |
| No notification | Check `sc2_watcher.log` in your vault folder for errors |
| Wrong player detected | Set `PLAYER_NAME` in `sc2_watcher.py` to match your SC2 battle.net name exactly |

---

## What gets recorded

Each game note contains:
- **Drone milestones** (40 / 55 / 66 / 80 drones) — exact game-loop timing
- **Hatchery completions** (3rd, 4th hatch) — when construction finishes, not placed
- **Tech structures** (Lair, Hive) — morph completion time
- **Upgrades** (+1 attack, +1 armour) — exact completion time
- **Max supply** — when the 24th Overlord completes
- **Inject rate** — count, per-minute rate, % of 3-hatch cycle capacity
- **Creep tumors** — total count + per-minute rate
- **Supply blocks** — count + timestamps
- **Opponent build** — detected from unit composition
- **Auto-coaching** — rule-based feedback on what to improve
