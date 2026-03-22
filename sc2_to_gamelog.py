#!/usr/bin/env python3
"""
sc2_to_gamelog.py  v4
---------------------
Parses a StarCraft II .SC2Replay and generates a Game Log markdown file
compatible with the ZergBenchmarks Obsidian vault.

Usage:
    python3 sc2_to_gamelog.py path/to/replay.SC2Replay [ladder_dir] [practice_dir]
    Defaults: ladder_dir = "Ladder Games",  practice_dir = "Practice Runs"

    vs AI    → Practice Runs/Drill YYYY-MM-DD vs AI.md   (drill YAML format)
    vs Human → Ladder Games/Game YYYY-MM-DD <matchup>.md (game log YAML format)

Requirements: Python 3.6+ stdlib only — no external packages needed.

Auto-extracted:
    ✅ Map, game version, real + game duration
    ✅ Both player names, races, results, MMR, APM
    ✅ Matchup code (ZvT, ZvZ, ZvP …)
    ✅ vs AI detection → routes file to Practice Runs in drill format
    ✅ Opponent build heuristic (structure + unit counts)
    ✅ Opponent army composition
    ✅ Zerg drone milestones: 40 / 55 / 66 / 80 drones
    ✅ Zerg unit / structure summary
    ⚠️  inject rating, creep score, supply blocks — fill manually after replay review

v4 changes:
    NEW  vs AI  → Practice Runs/ in drill YAML format (type: drill)
    NEW  vs Human → Ladder Games/ unchanged (type: ladder-game)
"""

import sys, os, bz2, re, json
from collections import Counter
from datetime import date


# ── BZ2 / MPQ extraction ────────────────────────────────────────────────────

def extract_streams(data):
    """
    Find and decompress every BZip2 stream in the replay binary.
    Returns {byte_offset: decompressed_bytes} for all valid streams.
    SC2 replays are MPQ archives; each internal file is BZip2-compressed.
    """
    streams, pos = {}, 0
    while True:
        idx = data.find(b'BZh9', pos)
        if idx == -1:
            break
        for length in [1000, 5000, 20000, 100000, 200000]:
            try:
                raw = bz2.decompress(data[idx:idx + length])
                if len(raw) > 50:
                    streams[idx] = raw
                break
            except Exception:
                pass
        pos = idx + 1
    return streams


# ── Metadata ────────────────────────────────────────────────────────────────

def parse_metadata(streams):
    """Find and parse the JSON game metadata block (replay.gamemetadata.json)."""
    for raw in streams.values():
        if b'"Title"' in raw:
            try:
                return json.loads(raw.decode('utf-8'))
            except Exception:
                pass
    return None



# ── Unit lists (verified against real tracker event stream data) ─────────────
#
# All names confirmed by scanning .SC2Replay tracker binary with length-prefixed
# s2protocol string patterns. Wrong names produce 0 matches and silently miss units.

RACE_MAP     = {'Terr': 'Terran', 'Zerg': 'Zerg', 'Prot': 'Protoss', 'random': 'Random'}
MATCHUP_CODE = {'Terran': 'T', 'Zerg': 'Z', 'Protoss': 'P', 'Random': 'R'}

ZERG_UNITS = [
    'Drone', 'Queen', 'Overlord', 'Overseer', 'OverlordCocoon',
    'Zergling', 'Baneling', 'Roach', 'Ravager',
    'Hydralisk', 'LurkerMP', 'LurkerMPEgg',          # FIX 4: LurkerMP not Lurker
    'Mutalisk', 'Corruptor', 'BroodLord',
    'Infestor', 'Viper', 'Ultralisk', 'SwarmHostMP',
]
ZERG_STRUCTS = [
    'Hatchery', 'Lair', 'Hive',
    'SpawningPool', 'RoachWarren', 'BanelingNest',
    'Spire', 'GreaterSpire', 'HydraliskDen',
    'InfestationPit', 'UltraliskCavern', 'NydusNetwork', 'NydusCanal',
    'Extractor', 'EvolutionChamber', 'SpineCrawler', 'SporeCrawler',
    'CreepTumor', 'CreepTumorBurrowed',               # FIX 6: added
]

TERRAN_UNITS = [
    'SCV', 'Marine', 'Marauder', 'Reaper', 'Ghost',
    'Hellion', 'HellionTank',                         # FIX 2: HellionTank not Hellbat
    'SiegeTank', 'SiegeTankSieged',                   # FIX 6: added SiegeTankSieged
    'Thor', 'ThorAP',
    'VikingFighter', 'VikingAssault',                 # FIX 3: two forms, not 'Viking'
    'Medivac', 'Liberator', 'LiberatorAG', 'Raven',
    'Banshee', 'Battlecruiser',                       # FIX 1: lowercase 'c'
    'Cyclone', 'WidowMine', 'WidowMineBurrowed',      # FIX 5: burrowed form
]
TERRAN_STRUCTS = [
    'CommandCenter', 'OrbitalCommand', 'PlanetaryFortress',  # FIX 6: added OrbitalCommand
    'Barracks', 'Factory', 'Starport', 'SupplyDepot',
    'Refinery', 'EngineeringBay', 'Armory',
    'GhostAcademy', 'FusionCore', 'Bunker', 'MissileTurret', 'SensorTower',
]

PROTOSS_UNITS = [
    'Probe', 'Zealot', 'Stalker', 'Adept', 'Sentry',
    'Immortal', 'Colossus', 'Disruptor',
    'Oracle', 'Phoenix', 'VoidRay', 'Carrier', 'Tempest',
    'DarkTemplar', 'HighTemplar', 'Archon',
    'Mothership', 'MothershipCore',
]
PROTOSS_STRUCTS = [
    'Nexus', 'Gateway', 'WarpGate', 'CyberneticsCore',
    'RoboticsFacility', 'RoboticsBay',
    'Stargate', 'FleetBeacon',
    'TwilightCouncil', 'TemplarArchive', 'DarkShrine',
    'Forge', 'ShieldBattery', 'PhotonCannon',
    'Assimilator',
]

ALL_TRACKED = list(set(
    ZERG_UNITS + ZERG_STRUCTS +
    TERRAN_UNITS + TERRAN_STRUCTS +
    PROTOSS_UNITS + PROTOSS_STRUCTS
))


# ── s2protocol string pattern helpers ───────────────────────────────────────


def _load_protocol(meta):
    """
    Load the s2protocol version matching this replay's BaseBuild.
    Falls back to the closest available protocol <= the build number.
    Returns the protocol module, or None if s2protocol is not installed.
    """
    try:
        from s2protocol import versions
        import os
        base_build = int(''.join(c for c in meta.get('BaseBuild', '0') if c.isdigit()))
        proto_dir  = os.path.dirname(versions.__file__)
        avail      = sorted([
            int(f[8:-3]) for f in os.listdir(proto_dir)
            if f.startswith('protocol') and f.endswith('.py')
        ])
        for build in reversed([v for v in avail if v <= base_build] or avail):
            try:
                proto = versions.build(build)
                if hasattr(proto, 'decode_replay_tracker_events'):
                    return proto
            except Exception:
                continue
        return None
    except ImportError:
        return None


def parse_unit_events(tracker, real_duration_sec, meta=None):
    """
    Decode unit events from the tracker stream with exact timestamps.

    With s2protocol installed: reads real game-loop values for exact timings.
      - SUnitBornEvent   → combat units, workers, initial structures
      - SUnitInitEvent   → completed structures (hatch, lair start of construction ends here)
      - SUnitTypeChangeEvent → morphed structures (Lair, Hive, upgrades)
      Conversion: real_sec = game_loop / 22.4  (16 loops/game-sec × Faster 1.4×)

    Requires s2protocol. Returns empty list if protocol unavailable or stream corrupted.

    Returns list of dicts sorted chronologically:
        {'unit': str, 'pos': int, 'real_sec': float, 'player_id': int|None}
    """
    total  = len(tracker)
    events = []

    # ── Exact parsing with s2protocol ────────────────────────────────────────
    if meta is not None:
        protocol = _load_protocol(meta)
        if protocol is not None:
            try:
                s2_evts    = list(protocol.decode_replay_tracker_events(tracker))

                # Build unit-tag → player_id lookup from all events that carry pid
                tag_to_pid = {}
                for ev in s2_evts:
                    pid = ev.get('m_upkeepPlayerId')
                    tag = ev.get('m_unitTagIndex')
                    if pid is not None and tag is not None:
                        tag_to_pid[tag] = pid

                BORN    = 'NNet.Replay.Tracker.SUnitBornEvent'
                INIT    = 'NNet.Replay.Tracker.SUnitInitEvent'
                CHANGE  = 'NNet.Replay.Tracker.SUnitTypeChangeEvent'

                for ev in s2_evts:
                    etype = ev.get('_event', '')
                    if etype not in (BORN, INIT, CHANGE):
                        continue
                    unit_bytes = ev.get('m_unitTypeName', b'')
                    unit       = unit_bytes.decode('utf-8', errors='ignore')
                    if not unit or unit not in ALL_TRACKED:
                        continue

                    game_loop = ev.get('_gameloop', 0)
                    real_sec  = game_loop / 22.4

                    # Determine player_id
                    pid = ev.get('m_upkeepPlayerId')
                    if pid is None:
                        # TypeChangeEvent: look up via unit tag
                        pid = tag_to_pid.get(ev.get('m_unitTagIndex'))

                    events.append({
                        'unit':      unit,
                        'pos':       game_loop,   # game loop used as ordering key
                        'real_sec':  real_sec,
                        'player_id': pid,
                    })

                events.sort(key=lambda e: e['pos'])
                return events
            except Exception:
                # Corrupted or truncated tracker stream — return empty list
                return []

    # s2protocol not installed or meta not provided
    if meta is not None:
        print("   ⚠️  s2protocol required for unit event parsing. "
              "Run: pip install s2protocol --no-deps  (see SETUP.md)")
    return []


# ── Zerg milestones ──────────────────────────────────────────────────────────

def detect_zerg_milestones(human_events, tracker=None, meta=None, human_player_id=None):
    """
    Return the real-time (seconds) when the human player's alive drone count first
    reached each milestone: {40, 55, 66, 80}.

    With s2protocol: uses SUnitBornEvent and SUnitDiedEvent matched by unit tag to
    track the number of drones alive simultaneously. A drone that dies (killed or
    morphed into a building) reduces the alive count. This is the correct economic
    measure — it shows how many drones you actually had working at any given time.

    Requires s2protocol. Returns all-None milestones if protocol unavailable or stream corrupted.

    Physical minimum sanity bounds are NOT applied to alive-count (they only made
    sense as workarounds for the old born-count method which couldn't account for
    deaths pushing milestones earlier than physically possible).
    """
    # ── Alive-count via s2protocol ────────────────────────────────────────────
    if tracker is not None and meta is not None and human_player_id is not None:
        protocol = _load_protocol(meta)
        if protocol is not None:
            try:
                evts = list(protocol.decode_replay_tracker_events(tracker))

                # Collect drone born tags owned by human player
                drone_tags = set()
                born_entries = []    # (gameloop,) for each drone born
                for e in evts:
                    if e['_event'] == 'NNet.Replay.Tracker.SUnitBornEvent':
                        if (e.get('m_unitTypeName', b'').decode() == 'Drone'
                                and e.get('m_upkeepPlayerId') == human_player_id):
                            tag = (e['m_unitTagIndex'], e['m_unitTagRecycle'])
                            drone_tags.add(tag)
                            born_entries.append(('born', e['_gameloop']))

                # Match drone deaths by tag
                for e in evts:
                    if e['_event'] == 'NNet.Replay.Tracker.SUnitDiedEvent':
                        tag = (e.get('m_unitTagIndex'), e.get('m_unitTagRecycle'))
                        if tag in drone_tags:
                            born_entries.append(('died', e['_gameloop']))

                # Walk timeline
                born_entries.sort(key=lambda x: x[1])
                alive = 0
                milestones = {40: None, 55: None, 66: None, 80: None}
                for etype, loop in born_entries:
                    if etype == 'born':
                        alive += 1
                    else:
                        alive -= 1
                    for n in [40, 55, 66, 80]:
                        if milestones[n] is None and alive >= n:
                            milestones[n] = loop / 22.4
                return milestones

            except Exception:
                # Corrupted stream — return empty milestones
                return {40: None, 55: None, 66: None, 80: None}

    # s2protocol not installed or required args not provided
    if tracker is not None and meta is not None:
        print("   ⚠️  s2protocol required for drone milestone tracking. "
              "Run: pip install s2protocol --no-deps  (see SETUP.md)")
    return {40: None, 55: None, 66: None, 80: None}


def fmt_time(seconds):
    """Convert seconds to 'M:SS' string, or 'N/A' if None. Clamps negatives to 0:00."""
    if seconds is None:
        return 'N/A'
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


# ── Upgrade names tracked in tracker stream ───────────────────────────────────


def detect_structure_milestones(human_events, all_events=None, opp_race=''):
    """
    Return timing of key structural benchmarks from human-filtered events.

    With s2protocol: Hatchery times come from SUnitInitEvent (construction complete),
    which arrive in human_events with correct player_id. Lair/Hive come from
    SUnitTypeChangeEvent with tag-based ownership already resolved.

    Requires s2protocol for correct player attribution of Lair/Hive morphs.

    Returns dict (float|None real seconds): hatch3, hatch4, lair, hive, max_supply
    """
    # Collect all Hatchery times — both BornEvent (placement) and InitEvent (completion).
    # With s2protocol: InitEvent arrives later than BornEvent for the same hatch.
    # We want COMPLETION times, so keep the latest occurrence per hatch.
    # Deduplication: if two times are within 5s, keep the later one.
    all_hatch = sorted(e['real_sec'] for e in human_events if e['unit'] == 'Hatchery')
    hatch_times = []
    for t in all_hatch:
        if hatch_times and t - hatch_times[-1] <= 5:
            hatch_times[-1] = t   # replace with the later (completion) time
        else:
            hatch_times.append(t)

    # Lair/Hive: with s2protocol these are already player-attributed via unit tags.
    # Always use human_events only — no race-exclusivity fallback needed.
    lair_sorted = sorted((e for e in human_events if e['unit'] == 'Lair'),
                         key=lambda x: x['real_sec'])
    hive_sorted = sorted((e for e in human_events if e['unit'] == 'Hive'),
                         key=lambda x: x['real_sec'])

    # Max supply: 24th Overlord born = supply cap first hits 200
    overlord_times = sorted(e['real_sec'] for e in human_events if e['unit'] == 'Overlord')
    max_supply_time = overlord_times[23] if len(overlord_times) >= 24 else None

    return {
        'hatch3':     hatch_times[2] if len(hatch_times) >= 3 else None,
        'hatch4':     hatch_times[3] if len(hatch_times) >= 4 else None,
        'lair':       lair_sorted[0]['real_sec'] if lair_sorted else None,
        'hive':       hive_sorted[0]['real_sec'] if hive_sorted else None,
        'max_supply': max_supply_time,
    }


def _find_game_stream(streams, meta):
    """
    Find the game events stream (replay.game.events) among all decompressed streams.
    Returns the raw bytes of the stream, or None if not found / s2protocol unavailable.
    """
    protocol = _load_protocol(meta)
    if protocol is None:
        return None
    for _offset, raw in sorted(streams.items(), key=lambda x: len(x[1])):
        if len(raw) < 5000:
            continue
        try:
            evts = list(protocol.decode_replay_game_events(raw))
            if any(e['_event'] == 'NNet.Game.SCmdEvent' for e in evts):
                return raw
        except Exception:
            pass
    return None


def detect_inject_rate(streams, meta, hatch_times, dur_real_sec, human_player_uid):
    """
    Count queen inject casts from the game events stream and compute inject metrics.

    Inject = SCmdEvent with m_abil.m_abilLink == 113, m_abil.m_abilCmdIndex == 0,
    targeting a unit (TargetUnit), issued by the human player (0-indexed user id).

    Returns dict:
        inject_count:   total injects cast by the human player
        inject_per_min: injects per real-game-minute (primary metric)
        inject_rating:  % of theoretical max injects for the first 3 hatcheries
                        (main + natural + 3rd base), which are the hatches typically
                        on the inject cycle. Theoretical cycle = 44.4 real-seconds.
    """
    INJECT_CYCLE_SECS = 44.4   # seconds between injects per hatchery

    protocol = _load_protocol(meta)
    if protocol is None:
        return {'inject_count': None, 'inject_per_min': None, 'inject_rating': None}

    game_raw = _find_game_stream(streams, meta)
    if game_raw is None:
        return {'inject_count': None, 'inject_per_min': None, 'inject_rating': None}

    try:
        game_evts = list(protocol.decode_replay_game_events(game_raw))
    except Exception:
        return {'inject_count': None, 'inject_per_min': None, 'inject_rating': None}

    # Target-based detection: any SCmdEvent issued by the human player that targets
    # their own Hatchery / Lair / Hive. This catches all inject variants:
    #   • Standard inject      (m_abilLink=113, m_abilCmdIndex=0)
    #   • Alt-hotkey variant   (m_abilLink=388, observed in some replays)
    #   • Queued/unconfirmed   (m_abilLink=None — certain camera-inject shortcuts)
    # Unit type links: Hatchery=109, Lair=123, Hive=124
    HATCH_UNIT_LINKS = {109, 123, 124}

    injects = [
        e for e in game_evts
        if e['_event'] == 'NNet.Game.SCmdEvent'
        and 'TargetUnit' in e.get('m_data', {})
        and e['_userid']['m_userId'] == human_player_uid
        and e['m_data']['TargetUnit'].get('m_snapshotUnitLink') in HATCH_UNIT_LINKS
        and e['m_data']['TargetUnit'].get('m_snapshotUpkeepPlayerId') == human_player_uid + 1
    ]

    count   = len(injects)
    per_min = round(count / (dur_real_sec / 60), 2) if dur_real_sec > 0 else 0.0

    # Inject rating: actual vs theoretical for first 3 hatches only
    # (these are the ones players typically keep on inject cycle)
    active_hatches = sorted(hatch_times)[:3]
    theoretical = sum(
        max(0.0, (dur_real_sec - t) / INJECT_CYCLE_SECS)
        for t in active_hatches
    )
    rating = round(count / theoretical * 100) if theoretical > 0 else 0

    return {
        'inject_count':   count,
        'inject_per_min': per_min,
        'inject_rating':  rating,
    }


def detect_upgrade_milestones(tracker, real_duration_sec, human_player_id, meta=None):
    """
    Return Zerg upgrade completion timings for the human player.

    With s2protocol: reads SUpgradeEvent entries with exact game-loop timestamps.
    Requires s2protocol. Returns all-None if protocol unavailable or stream corrupted.

    Returns dict:
      atk1, atk2, atk3:     attack upgrade completions (Melee or Missile, whichever first)
      armor1, armor2, armor3: ground armour completions
      double_upgrade1:      max(atk1, armor1) — when both +1 upgrades are done
    """
    # ── Exact timing via s2protocol ──────────────────────────────────────────
    if meta is not None:
        protocol = _load_protocol(meta)
        if protocol is not None:
            try:
                t_evts = list(protocol.decode_replay_tracker_events(tracker))
                atk_times   = {}
                armor_times = {}
                flyer_atk   = {}
                flyer_armor = {}

                for e in t_evts:
                    if e['_event'] != 'NNet.Replay.Tracker.SUpgradeEvent':
                        continue
                    if e.get('m_playerId') != human_player_id:
                        continue
                    name  = e.get('m_upgradeTypeName', b'').decode('utf-8', errors='ignore')
                    t_sec = e['_gameloop'] / 22.4

                    if 'MeleeWeapons' in name or 'MissileWeapons' in name:
                        lvl = int(name[-1])
                        if lvl not in atk_times:
                            atk_times[lvl] = t_sec
                    elif 'GroundArmors' in name:
                        lvl = int(name[-1])
                        if lvl not in armor_times:
                            armor_times[lvl] = t_sec
                    elif 'FlyerWeapons' in name:
                        lvl = int(name[-1])
                        if lvl not in flyer_atk:
                            flyer_atk[lvl] = t_sec
                    elif 'FlyerArmors' in name:
                        lvl = int(name[-1])
                        if lvl not in flyer_armor:
                            flyer_armor[lvl] = t_sec

                a1 = atk_times.get(1);   a2 = atk_times.get(2);   a3 = atk_times.get(3)
                r1 = armor_times.get(1); r2 = armor_times.get(2);  r3 = armor_times.get(3)
                double1 = max(a1, r1) if (a1 is not None and r1 is not None) else (a1 or r1)
                return {
                    'atk1': a1, 'atk2': a2, 'atk3': a3,
                    'armor1': r1, 'armor2': r2, 'armor3': r3,
                    'double_upgrade1': double1,
                    'flyer_atk1': flyer_atk.get(1), 'flyer_armor1': flyer_armor.get(1),
                }
            except Exception:
                # Corrupted stream — return empty upgrades
                return {'atk1': None, 'atk2': None, 'atk3': None,
                        'armor1': None, 'armor2': None, 'armor3': None,
                        'double_upgrade1': None, 'flyer_atk1': None, 'flyer_armor1': None}

    # s2protocol not installed or required args not provided
    if meta is not None:
        print("   ⚠️  s2protocol required for upgrade timing. "
              "Run: pip install s2protocol --no-deps  (see SETUP.md)")
    return {'atk1': None, 'atk2': None, 'atk3': None,
            'armor1': None, 'armor2': None, 'armor3': None,
            'double_upgrade1': None, 'flyer_atk1': None, 'flyer_armor1': None}


def detect_supply_blocks(events, human_race, player_id):
    """
    Estimate the number of supply blocks by simulating supply state from
    unit birth events, with build times subtracted to approximate queue time.

    Supply blocks are detected when a unit was queued while supply_used ≥ supply_cap.

    Returns (block_count, [real_sec, ...]) — times of distinct block events.

    Caveats:
      • Supply block timing is approximate (simulated from unit events) — very close blocks may merge.
      • Does not account for units that died before game end (supply freed).
      • Zerglings cost 0.5 supply each (fractional).
    """
    # Supply cost per unit (supply consumed)
    COST = {
        'Drone': 1, 'Queen': 2,
        'Zergling': 0.5, 'Baneling': 0,            # Baneling morphs from Zergling
        'Overlord': 0, 'OverlordCocoon': 0, 'Overseer': 0,
        'Roach': 2, 'Ravager': 3, 'Hydralisk': 2, 'LurkerMP': 3,
        'Mutalisk': 2, 'Corruptor': 2, 'BroodLord': 4,
        'Infestor': 2, 'Viper': 3, 'Ultralisk': 6, 'SwarmHostMP': 3,
        'SCV': 1, 'Marine': 1, 'Marauder': 2, 'Reaper': 1, 'Ghost': 2,
        'Hellion': 2, 'HellionTank': 2, 'SiegeTank': 3, 'SiegeTankSieged': 0,
        'Thor': 6, 'ThorAP': 0,
        'VikingFighter': 2, 'VikingAssault': 0,
        'Medivac': 2, 'Liberator': 3, 'LiberatorAG': 0, 'Raven': 2,
        'Banshee': 3, 'Battlecruiser': 6, 'Cyclone': 3,
        'WidowMine': 2, 'WidowMineBurrowed': 0,
        'Probe': 1, 'Zealot': 2, 'Stalker': 2, 'Adept': 2, 'Sentry': 2,
        'Immortal': 4, 'Colossus': 6, 'Disruptor': 3,
        'Oracle': 3, 'Phoenix': 2, 'VoidRay': 4, 'Carrier': 6,
        'Tempest': 4, 'HighTemplar': 2, 'DarkTemplar': 2,
        'Archon': 4, 'Mothership': 8, 'MothershipCore': 2,
    }
    # Supply provided per building/unit type
    PROVIDED = {
        'Hatchery': 6, 'Lair': 0, 'Hive': 0,
        'Overlord': 8,
        'SupplyDepot': 8,
        'CommandCenter': 11, 'OrbitalCommand': 0, 'PlanetaryFortress': 0,
        'Nexus': 15, 'Pylon': 8,
    }
    # Real-time build durations (seconds) to shift birth → queue time
    BUILD_TIME = {
        'Overlord': 18, 'Hatchery': 71,
        'SupplyDepot': 21, 'Pylon': 18,
    }
    # Starting state by race
    INITIAL = {
        'Zerg':    (14.0, 22.0),   # 12 drones + 2 overlords + 1 hatch
        'Terran':  (12.0, 22.0),   # 12 SCVs + CC
        'Protoss': (12.0, 27.0),   # 12 probes + nexus + starting pylon
    }

    supply_used, supply_cap = INITIAL.get(human_race, (12.0, 22.0))

    # Filter events to this player and attach queue time.
    # Skip events at real_sec < 5.0: these are the initial units placed at game_loop=0
    # (starting drones, first overlord, starting hatchery). The INITIAL supply state
    # already accounts for them; processing them again causes a spurious 0:00 block.
    queued = []
    for ev in events:
        if ev.get('player_id') != player_id:
            continue
        if ev['real_sec'] < 5.0:          # skip pre-game initialization events
            continue
        name = ev['unit']
        build_time = BUILD_TIME.get(name, 0)
        queue_t = max(0.0, ev['real_sec'] - build_time)
        queued.append((queue_t, ev['real_sec'], name))
    queued.sort()

    blocks = []
    in_block = False

    for queue_t, born_t, name in queued:
        cost     = COST.get(name, 0)
        provided = PROVIDED.get(name, 0)

        if cost > 0:
            at_cap = supply_used >= supply_cap - 0.5
            if at_cap and not in_block:
                in_block = True
                blocks.append(queue_t)
            elif not at_cap:
                in_block = False

        supply_used += cost
        supply_cap  += provided

    # Merge blocks within 10 seconds of each other
    distinct = []
    for t in blocks:
        if not distinct or t - distinct[-1] > 10:
            distinct.append(t)

    return len(distinct), distinct


# ── AI coaching analysis ─────────────────────────────────────────────────────

def _rule_coaching(d):
    """
    Rule-based coaching engine — runs locally with no API key or internet access.
    Produces the same dict shape as the API path:
      vs AI:    {'problems': [...], 'focus': [...]}
      vs human: {'mistakes': [...], 'lessons': [...], 'next_focus': [...]}

    Rules are keyed on:
      • Drone milestone timings vs published Zerg benchmarks
      • Enemy build identity
      • Matchup
      • Result (Win / Loss)
      • APM
      • Duration (game length)
      • Army composition (opp_units)
    """
    ms          = d['ms']                   # {40: sec|None, 55: sec|None, …}
    human_race  = d['human_race']
    matchup     = d['matchup']
    result      = d['result']               # 'Win' | 'Loss'
    apm         = d['apm']
    enemy_build = d['enemy_build']
    dur_real    = d['dur_real_sec']         # real seconds
    vs_ai       = d['vs_ai']
    diff        = d['ai_difficulty'] if vs_ai else None
    opp_units   = d['opp_units']
    my_units    = d.get('my_units', {})
    is_zerg     = human_race == 'Zerg'

    # ── Benchmark tables ─────────────────────────────────────────────────────
    #
    # Three tiers per metric: (great_sec, good_sec, ok_sec)
    #   great → significantly ahead of standard
    #   good  → meeting the standard
    #   ok    → acceptable but room to improve
    #   late  → beyond ok_sec → flagged in coaching output
    #
    # DRILL (vs AI): universal — no matchup pressure, focused on macro habits.
    # LADDER: matchup-specific — each matchup has different eco/pressure dynamics.
    # -------------------------------------------------------------------------

    # ── Drill drone benchmarks (universal) ──────────────────────────────────
    # ── Drone timing benchmarks — calibrated for ALIVE drone count ──────────────
    #
    # These use the number of drones simultaneously alive (not total built).
    # A drone that dies or morphs into a building reduces the alive count.
    # Alive-count milestones are later than born-count (especially in ZvT where
    # bio attacks kill drones), but they accurately reflect economic strength.
    #
    # Benchmarks from exact s2protocol data across 20 replays at ~2200 MMR.
    # -------------------------------------------------------------------------

    # Drill (vs AI) — drone deaths are rare, so timings are close to born-count
    DRONE_DRILL = {
        40: (240, 300, 360),   # great=4:00 / good=5:00 / ok=6:00
        55: (360, 450, 540),   # great=6:00 / good=7:30 / ok=9:00
        66: (420, 510, 600),   # great=7:00 / good=8:30 / ok=10:00
        80: (510, 600, 690),   # great=8:30 / good=10:00 / ok=11:30
    }

    # ZvT: bio attacks kill many drones; alive count lags significantly behind born
    DRONE_ZvT = {
        40: (240, 300, 390),   # great=4:00 / good=5:00 / ok=6:30
        55: (360, 450, 540),   # great=6:00 / good=7:30 / ok=9:00
        66: (480, 600, 720),   # great=8:00 / good=10:00 / ok=12:00
        80: (600, 720, 840),   # great=10:00 / good=12:00 / ok=14:00
    }
    # ZvP: Oracle/Stalker harassment kills some drones; moderate lag
    DRONE_ZvP = {
        40: (210, 270, 360),   # great=3:30 / good=4:30 / ok=6:00
        55: (330, 420, 510),   # great=5:30 / good=7:00 / ok=8:30
        66: (420, 510, 600),   # great=7:00 / good=8:30 / ok=10:00
        80: (510, 630, 750),   # great=8:30 / good=10:30 / ok=12:30
    }
    # ZvZ: fast games, less sustained drone harassment
    DRONE_ZvZ = {
        40: (210, 270, 360),   # great=3:30 / good=4:30 / ok=6:00
        55: (330, 420, 510),   # great=5:30 / good=7:00 / ok=8:30
        66: (420, 510, 600),   # great=7:00 / good=8:30 / ok=10:00
        80: (510, 630, 750),   # great=8:30 / good=10:30 / ok=12:30
    }

    # Drill structure benchmarks (universal)
    STRUCT_DRILL = {
        'hatch3':          (150, 210, 270),   # great=2:30 / good=3:30 / ok=4:30
        'hatch4':          (270, 360, 450),   # great=4:30 / good=6:00 / ok=7:30
        'lair':            (210, 270, 330),   # great=3:30 / good=4:30 / ok=5:30
        'hive':            (420, 510, 600),   # great=7:00 / good=8:30 / ok=10:00
        'double_upgrade1': (390, 450, 540),   # great=6:30 / good=7:30 / ok=9:00
        'max_supply':      (540, 630, 720),   # great=9:00 / good=10:30 / ok=12:00
    }

    # Ladder structure benchmarks (per matchup)
    STRUCT_ZvT = {
        'hatch3':          (150, 210, 270),   # great=2:30 / good=3:30 / ok=4:30
        'hatch4':          (270, 360, 450),   # great=4:30 / good=6:00 / ok=7:30
        'lair':            (210, 270, 330),   # great=3:30 / good=4:30 / ok=5:30
        'hive':            (420, 510, 600),   # great=7:00 / good=8:30 / ok=10:00
        'double_upgrade1': (390, 450, 540),   # great=6:30 / good=7:30 / ok=9:00
        'max_supply':      (540, 600, 660),   # great=9:00 / good=10:00 / ok=11:00
    }
    STRUCT_ZvP = {
        'hatch3':          (120, 180, 240),   # great=2:00 / good=3:00 / ok=4:00
        'hatch4':          (240, 330, 450),   # great=4:00 / good=5:30 / ok=7:30
        'lair':            (180, 240, 300),   # great=3:00 / good=4:00 / ok=5:00
        'hive':            (390, 480, 570),   # great=6:30 / good=8:00 / ok=9:30
        'double_upgrade1': (360, 420, 510),   # great=6:00 / good=7:00 / ok=8:30
        'max_supply':      (510, 570, 630),   # great=8:30 / good=9:30 / ok=10:30
    }
    STRUCT_ZvZ = {
        'hatch3':          (120, 180, 240),   # great=2:00 / good=3:00 / ok=4:00
        'hatch4':          (240, 330, 420),   # great=4:00 / good=5:30 / ok=7:00
        'lair':            (180, 240, 300),   # great=3:00 / good=4:00 / ok=5:00
        'hive':            (390, 480, 570),   # great=6:30 / good=8:00 / ok=9:30
        'double_upgrade1': (360, 420, 480),   # great=6:00 / good=7:00 / ok=8:00
        'max_supply':      (480, 540, 600),   # great=8:00 / good=9:00 / ok=10:00
    }

    # ── Select correct benchmark tables based on context ─────────────────────
    if vs_ai:
        BENCH        = DRONE_DRILL
        STRUCT_BENCH = STRUCT_DRILL
    else:
        _mu = matchup  # e.g. 'ZvT', 'ZvP', 'ZvZ', 'ZvR'
        BENCH        = {'ZvT': DRONE_ZvT,   'ZvP': DRONE_ZvP,   'ZvZ': DRONE_ZvZ  }.get(_mu, DRONE_ZvT)
        STRUCT_BENCH = {'ZvT': STRUCT_ZvT,  'ZvP': STRUCT_ZvP,  'ZvZ': STRUCT_ZvZ }.get(_mu, STRUCT_ZvT)

    # ── Helper functions ─────────────────────────────────────────────────────

    def grade(target):
        """Return 'great', 'good', 'ok', 'late', or 'missed' for a drone milestone."""
        t = ms.get(target)
        if t is None:
            return 'missed'
        great_s, good_s, ok_s = BENCH[target]
        if t <= great_s: return 'great'
        if t <= good_s:  return 'good'
        if t <= ok_s:    return 'ok'
        return 'late'

    def fmt(target):
        t = ms.get(target)
        return fmt_time(t) if t is not None else 'not reached'

    def late_by(target):
        """Seconds behind ok_sec, or 999 if missed."""
        t = ms.get(target)
        if t is None:
            return 999
        return max(0, t - BENCH[target][2])   # index 2 = ok_sec

    # ── Build-specific reaction advice (ZvT / ZvP / ZvZ) ────────────────────
    BUILD_REACTION = {
        # ZvT
        'BattleCruiser Rush': (
            "Scout the Starport + TechLab at 3:30 with an Overlord — BC rush telegraphs early.",
            "Practice transitioning into Corruptors the moment you see a Starport building a Reactor-less BC."
        ),
        'Bio/Tank (Marine + Siege Tank)': (
            "Hold the third base tighter — bio/tank pressures the natural around 7–9 min.",
            "Build Banelings before Roaches when you see a Barracks count ≥ 2 and a Factory."
        ),
        'Mech': (
            "Identify Mech by Factory count (≥3) before 6:00 and switch to Roach/Hydra or Swarm Hosts.",
            "Avoid trading Zerglings into Siege Tanks — kite with Roaches and reinforce with Ravagers."
        ),
        'Air Heavy (Banshee/Liberator/BC)': (
            "Build a Spore Crawler at each mineral line by 4:30 when you see 2+ Starports.",
            "Add a second Queen per base and keep them near minerals to spot Banshee cloaks early."
        ),
        'Standard Bio (MMM)': (
            "Engage bio with Banelings first, then clean up with Zerglings — never move onto Marines without Banes.",
            "Drone to 66 before committing to Bane nest; early aggression is a feint to stall your eco."
        ),
        'Early Bio Aggression': (
            "Pull Queen forward to help hold early bio pushes at the ramp — one Queen buys a lot.",
            "Avoid over-droning past 28 supply before you see what pressure is coming."
        ),
        'Standard 1-1-1 Opener': (
            "Send an Overlord to opponent's natural at 2:30 to confirm expansion or all-in intent.",
            "Drone safely to 55 then take your third; 1-1-1 punishes greedy thirds, not standard 55-drone timings."
        ),
        # ZvP
        'FFE (Forge Fast Expand)': (
            "FFE means a slow Protoss army — drone aggressively past 66 before any pressure arrives.",
            "Take your third around 5:00 and build a Roach Warren to discourage Blink pushes."
        ),
        'Stargate / Oracle / Air': (
            "Detect Stargate by placing an Overlord over the Protoss natural by 2:45 — Stargate goes up fast.",
            "Build 2 Spore Crawlers per base at the first Oracle sight, not after the second visit."
        ),
        'Robo (Immortal/Colossus)': (
            "Prioritise Corruptors over Mutas if you see a Robotics Bay — Colossus needs air answer.",
            "Engage Colossus with Corruptors first then clean up ground units with Zerglings."
        ),
        'Gateway Aggression / 4-Gate': (
            "Hold 4-gate by walling your natural ramp with a Spine Crawler + Queen before 4:30.",
            "Do not over-drone past 22 until you've confirmed no 4-gate pressure at your ramp."
        ),
        'Standard Gate Expand': (
            "Gate expand is safe — drone to 66 and take your third before 5:30.",
            "Look for a Twilight Council (Blink) or Robo at 5:00 to plan your defensive investment."
        ),
        # ZvZ
        'Lurker (Ling/Lurker or Roach/Lurker)': (
            "Detect Lurker tech by scouting for a HydraliskDen before 6:30 — pre-build Roach/Ravager.",
            "Engage Lurkers with Ravager bile from range; never run Zerglings directly into Lurker lines."
        ),
        'Muta Transition': (
            "Build a second Spore Crawler per base the moment you see a Spire — Mutas punish slow reactions.",
            "Match Muta with Muta or go mass Roach/Ravager and defend with Spores; do not attack into Mutas."
        ),
        'Roach/Hydra': (
            "Meet Roach/Hydra with Roach/Ravager and Banelings to break the concave.",
            "Bile key Hydras before engaging — Ravager bile on clustered Hydralisks is high value."
        ),
        'Roach/Bane': (
            "Spread Zerglings wide to absorb Banelings before engaging Roaches.",
            "Roach/Bane crumbles to Hydras — build a HydraliskDen if you see a BanelingNest."
        ),
        'Ling/Bane': (
            "Hold Ling/Bane by building a Spine Crawler at your natural by 3:00 and spreading Queens.",
            "Counter with your own Banelings — Zergling-only defence will be overwhelmed by Bane hits."
        ),
        'Roach Rush': (
            "Detect Roach rush by the 4:00 mark — if opponent's gas is taken early, expect Roaches.",
            "Build 2 Spine Crawlers at natural ramp before 3:30 when you scout no fast Hatchery."
        ),
        'Standard Hatch First': (
            "Mirror Hatch First safely — drone to 40 then immediately add an Overlord and Queen.",
            "After 40 drones, take your natural gas and begin tech; Hatch First mirrors are eco races."
        ),
    }

    # ── Drone observation sentences ──────────────────────────────────────────
    def drone_obs():
        if not is_zerg:
            return []
        # Very short game (<3 min): skip all drone coaching — no time to reach milestones
        if dur_real < 180:
            return []
        notes = []
        for target, label in [(40, '40'), (55, '55'), (66, '66'), (80, '80')]:
            g     = grade(target)
            t     = fmt(target)
            ok_s  = BENCH[target][2]
            ok_fmt = fmt_time(ok_s)
            if g == 'missed':
                # Only flag "never reached" if the game ran long enough that it was achievable
                if dur_real >= ok_s:
                    # For wins, 80d alive is often just a result of drone attrition under pressure
                    # rather than a true macro failure — only flag 40d/55d misses on wins
                    if result == 'Win' and target in (66, 80):
                        pass   # suppress — player won, missing 66/80 alive is expected under attack
                    else:
                        notes.append(f"{label}-drone mark was never reached — game ended at {fmt_time(dur_real)}; review whether macro or aggression was the cause.")
                # If game ended before the milestone was even due, skip silently
            elif g == 'late':
                over = int(late_by(target))
                if over >= 30:   # suppress trivial flags under 30 seconds
                    notes.append(f"{label}-drone mark hit at {t} — {over}s behind the {ok_fmt} target; look for supply blocks or missed inject cycles in this window.")
            # great / good / ok → no complaint
        return notes

    def drone_focus():
        """Return the single most lagging drone milestone as the top drill focus."""
        if not is_zerg:
            return []
        worst_target, worst_lag = None, 0
        for target in [40, 55, 66, 80]:
            lag = late_by(target)
            if lag > worst_lag:
                worst_lag, worst_target = lag, target
        if worst_target is None or worst_lag < 10:
            return []
        good_fmt = fmt_time(BENCH[worst_target][1])   # index 1 = good_sec
        if worst_lag == 999:
            return [f"The {worst_target}-drone mark was never reached this game — make hitting it by {good_fmt} the single goal of your next session."]
        return [f"Drill the {worst_target}-drone timing to {good_fmt}: that milestone was {int(worst_lag)}s off target and is the biggest macro gap this game."]

    # ── APM observation ──────────────────────────────────────────────────────
    def apm_obs():
        if apm < 60:
            return [f"APM of {apm} is low — slow mechanics leave queens uninjected and supply blocks unaddressed. Aim for 80+ to keep up with basic macro cycles."]
        if apm < 80:
            return [f"APM of {apm} is below average — try setting a metronome alarm every 20 seconds to remind yourself to inject, spread creep, and check supply."]
        return []

    # ── Supply block observation ─────────────────────────────────────────────
    def supply_obs():
        sb    = d.get('supply_block_count', 0)
        times = d.get('supply_block_times', [])
        if sb == 0:
            return []
        time_strs = ', '.join(fmt_time(t) for t in times)
        race = d.get('human_race', 'Zerg')
        if race == 'Zerg':
            supply_unit = "Overlord"
            habit_tip   = "set a habit of checking supply every inject cycle"
            early_tip   = "build Overlords when at 4–6 below cap, not when capped"
            cause_tip   = "try building one whenever you morph 4+ larvae at once"
        elif race == 'Terran':
            supply_unit = "Supply Depot"
            habit_tip   = "queue a Supply Depot whenever you spend below ~100 minerals"
            early_tip   = "queue Supply Depots before you need them — build at 4–6 below cap"
            cause_tip   = "queue one proactively whenever minerals pass 150"
        else:  # Protoss
            supply_unit = "Pylon"
            habit_tip   = "build a Pylon whenever supply reaches 3–4 below cap"
            early_tip   = "build Pylons before you need them — at 3–4 below cap"
            cause_tip   = "build one proactively whenever minerals pass 100"

        if sb == 1:
            return [f"1 supply block detected around {time_strs} — {early_tip}."]
        if sb <= 3:
            return [f"{sb} supply blocks detected ({time_strs}) — queuing {supply_unit}s reactively is the main cause; {cause_tip}."]
        return [f"{sb} supply blocks detected ({time_strs}) — chronic supply blocks are a major drag on macro; {habit_tip}."]

    STRUCT_LABELS = {
        'hatch3':          '3rd hatchery',
        'hatch4':          '4th hatchery',
        'lair':            'Lair',
        'hive':            'Hive',
        'double_upgrade1': '+1/+1 double upgrade',
        'max_supply':      'Max supply (200 cap)',
    }

    # ── Structural / upgrade observation sentences ───────────────────────────
    def struct_obs():
        if not is_zerg:
            return []
        sm = d.get('struct_ms', {})
        um = d.get('upgrade_ms', {})
        # max_supply comes from struct_ms; double_upgrade1 from upgrade_ms
        combined = {**sm, 'double_upgrade1': um.get('double_upgrade1')}
        notes = []
        for key, label in STRUCT_LABELS.items():
            val   = combined.get(key)
            bench = STRUCT_BENCH.get(key)
            if bench is None:
                continue
            great_s, good_s, ok_s = bench
            if val is None:
                # Only flag missing tech/milestone if game was long enough to reach it
                if key in ('lair', 'hive', 'double_upgrade1', 'max_supply') and dur_real > ok_s + 120:
                    notes.append(f"{label} was never reached — aim for {fmt_time(ok_s)} in future games.")
            elif val > ok_s:
                over = int(val - ok_s)
                if over >= 30:   # only flag if meaningfully behind (>=30s, not 4s)
                    notes.append(f"{label} at {fmt_time(val)} — {over}s behind the {fmt_time(ok_s)} target.")
        return notes
    def duration_obs():
        mins = dur_real / 60
        notes = []
        if result == 'Loss' and mins < 6:
            notes.append(f"Game lasted only {fmt_time(dur_real)} — likely died to an all-in; identify the exact timing it hit and practise that specific defence.")
        if result == 'Win' and mins < 8 and vs_ai:
            notes.append(f"Fast win vs AI ({fmt_time(dur_real)}) — consider raising the difficulty or focusing macro past the win condition rather than ending early.")
        return notes

    # ── Inject observation ───────────────────────────────────────────────────
    def inject_obs():
        if not is_zerg:
            return []
        ipm  = d.get('inject_per_min')
        irat = d.get('inject_rating')
        cnt  = d.get('inject_count')
        mins = dur_real / 60
        if ipm is None or mins < 3:
            return []
        if ipm < 1.0:
            return [f"Only {cnt} injects in {fmt_time(dur_real)} ({ipm}/min) — aim for 1.5+/min; set a habit of cycling inject after every creep spread or army move."]
        if ipm < 1.5:
            return [f"{cnt} injects ({ipm}/min) — below average; try to inject every 45 seconds per hatchery ({irat}% of 3-hatch cycle capacity)."]
        return []
    def creep_obs():
        if not is_zerg:
            return []
        tumors = d.get('creep_tumors', 0)
        tpm    = d.get('creep_tumors_pm', 0.0)
        mins   = dur_real / 60
        if mins < 5:
            return []   # too short to judge creep
        if tpm < 0.5:
            return [f"Only {tumors} creep tumor(s) placed ({tpm}/min) — prioritise spreading creep after each inject cycle; aim for 2+/min."]
        if tpm < 1.0:
            return [f"{tumors} creep tumors placed ({tpm}/min) — creep spread below average; plant a tumor whenever a queen has 50+ energy and isn't injecting."]
        return []

    # ── Compose for vs AI (drill) ────────────────────────────────────────────
    if vs_ai:
        problems = drone_obs() + struct_obs() + supply_obs() + inject_obs() + creep_obs() + apm_obs() + duration_obs()
        reaction, drill = BUILD_REACTION.get(enemy_build, (None, None))
        focus = drone_focus()
        if drill:
            focus.append(drill)
        if not problems:
            problems = [f"No obvious errors — good baseline run vs {diff} AI. Raise the difficulty or tighten drone benchmarks."]
        if not focus:
            focus = [f"Continue drilling macro consistency: aim for 40 drones by {fmt_time(BENCH[40][1])}, 66 by {fmt_time(BENCH[66][1])}."]
        return {'problems': problems[:6], 'focus': focus[:3]}

    # ── Compose for ladder game ──────────────────────────────────────────────
    mistakes = drone_obs() + struct_obs() + supply_obs() + inject_obs() + creep_obs() + apm_obs() + duration_obs()
    reaction, drill = BUILD_REACTION.get(enemy_build, (None, None))

    if result == 'Loss':
        if reaction:
            mistakes.append(f"Against {enemy_build}: {reaction}")
        elif not mistakes:
            mistakes.append(f"Loss to {enemy_build} in {matchup} — review the replay for the exact moment the game turned.")
    else:
        if not mistakes:
            mistakes = ["No major errors detected from stats alone — check the replay for scouting or positioning issues."]

    lessons = []
    if reaction:
        lessons.append(reaction)
    if is_zerg:
        worst_g = min((grade(t) for t in [40,55,66,80]), key=lambda g: {'great':4,'good':3,'ok':2,'late':1,'missed':0}[g])
        if worst_g in ('late', 'missed'):
            lessons.append("Macro consistency is the highest-leverage improvement at this MMR — one missed inject costs ~4 drones over a full game.")
    if not lessons:
        lessons = ["Review the replay focusing on the first moment you felt behind — that's usually where the game was decided."]

    next_focus = drone_focus()
    if drill:
        next_focus.append(drill)
    if not next_focus:
        next_focus = [f"Run a macro-only practice game vs Easy AI: drone to 80 by {fmt_time(BENCH[80][1])} with zero supply blocks."]

    return {
        'mistakes':   mistakes[:6],
        'lessons':    lessons[:2],
        'next_focus': next_focus[:3],
    }


def get_coaching_notes(d, api_key=''):
    """
    Return structured coaching notes.

    Always runs the local rule engine first (free, offline, instant).
    If api_key is set, the API result is used instead for richer language.
    Falls back to local rules if the API call fails.
    """
    # Always generate local notes — used as fallback and when no key is set
    local = _rule_coaching(d)
    if not api_key:
        print("   Coaching notes: rule-based (free, offline)")
        return local

    # Optional API enrichment
    import urllib.request, urllib.error

    matchup     = d['matchup']
    result      = d['result']
    apm         = d['apm']
    enemy_build = d['enemy_build']
    dur_str     = d['dur_str']
    vs_ai       = d['vs_ai']
    diff        = d['ai_difficulty'] if vs_ai else None
    human_race  = d['human_race']
    ms          = d['ms']

    opponent_desc = f"A.I. {diff}" if vs_ai else f"human ({matchup})"
    _mu = d.get('matchup', 'ZvT')
    BENCH = ({40:(240,300,360), 55:(360,450,540), 66:(420,510,600), 80:(510,600,690)}
             if vs_ai else
             {'ZvT':{40:(240,300,390),55:(360,450,540),66:(480,600,720),80:(600,720,840)},
              'ZvP':{40:(210,270,360),55:(330,420,510),66:(420,510,600),80:(510,630,750)},
              'ZvZ':{40:(210,270,360),55:(330,420,510),66:(420,510,600),80:(510,630,750)},
             }.get(_mu, {40:(240,300,390),55:(360,450,540),66:(480,600,720),80:(600,720,840)}))
    drone_lines = ''
    if human_race == 'Zerg' and ms:
        for t, (great_s, good_s, ok_s) in BENCH.items():
            val = ms.get(t)
            timing = fmt_time(val) if val else 'not reached'
            status = 'on time' if (val and val <= ok_s) else 'LATE'
            drone_lines += f"  {t} drones: {timing} [{status}]\n"

    opp_units   = d['opp_units']
    top_units   = ', '.join(f"{u}×{n}" for u,n in sorted(opp_units.items(), key=lambda x:-x[1])[:5]) or 'none'

    stats = (f"Matchup: {matchup} | Result: {result} | vs: {opponent_desc}\n"
             f"Enemy build: {enemy_build} | Duration: {dur_str} | APM: {apm}\n"
             + (f"Drone timings:\n{drone_lines}" if drone_lines else '')
             + f"Opponent top units: {top_units}")

    key_type   = 'problems/focus' if vs_ai else 'mistakes/lessons/next_focus'
    schema     = ('{"problems":["..."],"focus":["..."]}' if vs_ai
                  else '{"mistakes":["..."],"lessons":["..."],"next_focus":["..."]}')
    sys_prompt = ("You are a StarCraft II coaching assistant. Give concise, specific, "
                  "actionable feedback referencing the actual numbers. Respond with valid JSON only.")
    usr_prompt = f"SC2 game stats:\n{stats}\n\nRespond with {key_type}:\n{schema}"

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 400,
        "system": sys_prompt,
        "messages": [{"role": "user", "content": usr_prompt}],
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = json.loads(resp.read())['content'][0]['text'].strip()
            text = text.replace('```json','').replace('```','').strip()
            print("   Coaching notes: Claude API")
            return json.loads(text)
    except urllib.error.HTTPError as e:
        print(f"   ⚠️  API error {e.code} — using local coaching rules")
        return local
    except Exception as e:
        print(f"   ⚠️  API unavailable ({e}) — using local coaching rules")
        return local


# ── Build detection ──────────────────────────────────────────────────────────

def detect_enemy_build(counter, race):
    """
    Heuristic build classification from cumulative unit/structure counts.
    Checks are ordered from most specific to most general.
    """
    if race == 'Terran':
        bc    = counter.get('Battlecruiser', 0)        # FIX 1: correct capitalisation
        stp   = counter.get('Starport', 0)
        fac   = counter.get('Factory', 0)
        bar   = counter.get('Barracks', 0)
        siege = counter.get('SiegeTank', 0) + counter.get('SiegeTankSieged', 0)
        med   = counter.get('Medivac', 0)
        tank  = counter.get('HellionTank', 0)          # FIX 2: correct name
        if bc >= 2:              return "BattleCruiser Rush"
        if stp >= 3 and fac <= 1: return "Air Heavy (Banshee/Liberator/BC)"
        if siege >= 2:           return "Bio/Tank (Marine + Siege Tank)"
        if fac >= 4 or tank >= 4: return "Mech"
        if bar >= 4 and med >= 2: return "Standard Bio (MMM)"
        if bar >= 2:             return "Early Bio Aggression"
        return "Standard 1-1-1 Opener"

    elif race == 'Zerg':
        spire = counter.get('Spire', 0) + counter.get('GreaterSpire', 0)
        roach = counter.get('RoachWarren', 0)
        bane  = counter.get('BanelingNest', 0)
        hydra = counter.get('HydraliskDen', 0)
        lurk  = counter.get('LurkerMP', 0)             # FIX 4: correct name
        if lurk:                 return "Lurker (Ling/Lurker or Roach/Lurker)"
        if spire:                return "Muta Transition"
        if hydra and roach:      return "Roach/Hydra"
        if roach and bane:       return "Roach/Bane"
        if bane:                 return "Ling/Bane"
        if roach:                return "Roach Rush"
        return "Standard Hatch First"

    elif race == 'Protoss':
        forge = counter.get('Forge', 0)
        robo  = counter.get('RoboticsFacility', 0)
        sgate = counter.get('Stargate', 0)
        gate  = counter.get('Gateway', 0) + counter.get('WarpGate', 0)
        if forge and gate <= 1:  return "FFE (Forge Fast Expand)"
        if sgate >= 2:           return "Stargate / Oracle / Air"
        if robo:                 return "Robo (Immortal/Colossus)"
        if gate >= 3:            return "Gateway Aggression / 4-Gate"
        return "Standard Gate Expand"

    return "Unknown"


def detect_my_build(human_counter, struct_times, matchup):
    """
    Classify the human player's Zerg build from their unit/structure counters
    and the timing of key structures (SUnitInitEvent completion times).

    Returns a human-readable build name in the format:
      "<Opener> → <Composition>"  e.g. "Hatch First → Hydra/Lurker"
    or just the composition when the opener is unclear.
    """
    POOL_BUILD_TIME  = 65 / 1.4   # real seconds pool takes to finish building
    HATCH_BUILD_TIME = 71 / 1.4   # real seconds hatch takes to finish building

    def has(*structs): return any(human_counter.get(s, 0) > 0 for s in structs)
    def when(struct):  return struct_times.get(struct)
    def cnt(unit):     return human_counter.get(unit, 0)

    # ── Composition flags — based on units actually PRODUCED, not structures ────
    lurker  = cnt('LurkerMP')    > 3
    hydra   = cnt('Hydralisk')   > 5
    muta    = cnt('Mutalisk')    > 3
    corr    = cnt('Corruptor')   > 3
    bane    = cnt('Baneling')    > 3
    roach   = cnt('Roach')       > 3
    ultra   = cnt('Ultralisk')   > 1
    infest  = cnt('Infestor')    > 2   # requires actual Infestors, not just the pit
    viper   = cnt('Viper')       > 4   # 1-4 utility vipers ≠ Viper build
    brood   = cnt('BroodLord')   > 1
    swarm   = cnt('SwarmHostMP') > 1
    ravager = cnt('Ravager')     > 3
    spire   = has('Spire', 'GreaterSpire')   # keep for BC detection

    # ── Opening detection ────────────────────────────────────────────────────
    # Infer PLACEMENT times from completion times (subtract build duration).
    pool_complete  = when('SpawningPool')
    hatch_complete = when('Hatchery')   # first completed non-starting hatch

    if pool_complete is not None and hatch_complete is not None:
        pool_placed  = pool_complete  - POOL_BUILD_TIME
        hatch_placed = hatch_complete - HATCH_BUILD_TIME
        if hatch_placed < pool_placed:
            opener = "Hatch First"       # natural expansion placed before pool
        elif pool_placed < 10:
            opener = "Early Pool"        # 9-pool: placed within first 10 real seconds
        else:
            opener = "Pool First"        # pool placed before natural hatch
    elif pool_complete is not None and pool_complete < 40:
        opener = "Early Pool"            # pool completed before 0:40 = very aggressive
    else:
        opener = "Hatch First"           # default assumption for standard Zerg

    # ── Aggressive Roach opener: RoachWarren before natural hatch ────────────
    roach_t  = when('RoachWarren') or 999
    hatch_t  = when('Hatchery') or 999
    early_roach = roach_t < 3.5 * 60 and hatch_t > roach_t

    # ── Composition name (most specific first) ───────────────────────────────
    if brood:
        comp = "Roach/Corruptor/Broodlord"
    elif ultra and (hydra or lurker):
        comp = "Hydra/Lurker/Ultralisk"
    elif ultra:
        comp = "Ultralisk Transition"
    elif infest and viper:
        comp = "Infestor/Viper"
    elif infest and lurker:
        comp = "Infestor/Lurker"
    elif swarm and lurker:
        comp = "SwarmHost/Lurker"
    elif lurker and hydra and bane:
        comp = "Ling/Bane/Hydra/Lurker"
    elif lurker and hydra and corr:
        comp = "Hydra/Lurker/Corruptor"
    elif lurker and hydra:
        comp = "Hydra/Lurker"
    elif muta and bane:
        comp = "Ling/Bane/Muta"
    elif muta and corr:
        comp = "Muta/Corruptor"
    elif muta:
        comp = "Muta Transition"
    elif hydra and corr:
        comp = "Hydra/Corruptor"
    elif hydra and roach and bane:
        comp = "Roach/Hydra/Bane"
    elif hydra and roach:
        comp = "Roach/Hydra"
    elif hydra and bane:
        comp = "Ling/Bane/Hydra"
    elif hydra:
        comp = "Hydra Macro"
    elif bane and roach:
        comp = "Roach/Bane"
    elif bane:
        comp = "Ling/Bane"
    elif roach and ravager:
        comp = "Roach/Ravager"
    elif early_roach:
        comp = "Roach Rush"
    elif roach:
        comp = "Roach Macro"
    else:
        comp = "Macro Eco"

    return f"{opener} → {comp}"


# Reaction correctness: (enemy_build, my_build_contains) → True/False/None
# my_build is now "Opener → Composition", so we match on the composition part
_GOOD_REACTIONS = {
    # ZvT — Bio/Tank
    ('Bio/Tank (Marine + Siege Tank)', 'Hydra/Lurker'):                 True,
    ('Bio/Tank (Marine + Siege Tank)', 'Ling/Bane/Hydra/Lurker'):       True,
    ('Bio/Tank (Marine + Siege Tank)', 'Hydra/Lurker/Corruptor'):       True,
    ('Bio/Tank (Marine + Siege Tank)', 'Ling/Bane/Muta'):               True,
    ('Bio/Tank (Marine + Siege Tank)', 'Roach/Hydra'):                  None,  # workable but slow vs tanks
    ('Bio/Tank (Marine + Siege Tank)', 'Infestor/Viper'):               True,  # great vs mech/tank
    ('Bio/Tank (Marine + Siege Tank)', 'Ling/Bane'):                    None,  # no lurkers = bad vs tanks
    ('Bio/Tank (Marine + Siege Tank)', 'Macro Eco'):                    None,
    # ZvT — Pure Bio
    ('Standard Bio (MMM)',             'Ling/Bane/Hydra/Lurker'):       True,
    ('Standard Bio (MMM)',             'Ling/Bane/Muta'):               True,
    ('Standard Bio (MMM)',             'Hydra/Lurker'):                 True,
    ('Standard Bio (MMM)',             'Ling/Bane'):                    True,
    ('Standard Bio (MMM)',             'Roach/Hydra'):                  None,
    # ZvT — Early aggression
    ('Early Bio Aggression',           'Ling/Bane/Hydra/Lurker'):       True,
    ('Early Bio Aggression',           'Ling/Bane/Muta'):               True,
    ('Early Bio Aggression',           'Hydra/Lurker'):                 True,
    ('Early Bio Aggression',           'Ling/Bane'):                    True,
    ('Early Bio Aggression',           'Roach/Hydra'):                  True,
    ('Early Bio Aggression',           'Macro Eco'):                    False,  # too greedy vs aggression
    # ZvT — BattleCruiser Rush
    ('BattleCruiser Rush',             'Hydra/Lurker/Corruptor'):       True,
    ('BattleCruiser Rush',             'Hydra/Corruptor'):              True,
    ('BattleCruiser Rush',             'Muta/Corruptor'):               True,
    ('BattleCruiser Rush',             'Roach/Corruptor/Broodlord'):    True,
    ('BattleCruiser Rush',             'Ling/Bane/Hydra/Lurker'):       None,  # Lurkers help but no AA
    ('BattleCruiser Rush',             'Hydra/Lurker'):                 None,  # Lurkers stall, no AA
    ('BattleCruiser Rush',             'Roach/Hydra'):                  None,
    ('BattleCruiser Rush',             'Ling/Bane'):                    False,  # no anti-air
    # ZvT — Mech / Air
    ('Mech',                           'Roach/Hydra'):                  True,
    ('Mech',                           'Hydra/Lurker'):                 True,
    ('Mech',                           'Infestor/Viper'):               True,
    ('Mech',                           'Ling/Bane'):                    False,
    ('Air Heavy (Banshee/Liberator/BC)','Muta/Corruptor'):              True,
    ('Air Heavy (Banshee/Liberator/BC)','Hydra/Lurker'):                True,
    ('Air Heavy (Banshee/Liberator/BC)','Hydra/Lurker/Corruptor'):      True,
    ('Air Heavy (Banshee/Liberator/BC)','Hydra/Corruptor'):             True,
    # ZvT — Standard
    ('Standard 1-1-1 Opener',          'Macro Eco'):                    True,
    ('Standard 1-1-1 Opener',          'Hydra/Lurker'):                 True,
    ('Standard 1-1-1 Opener',          'Roach/Hydra'):                  True,
    ('Standard 1-1-1 Opener',          'Ling/Bane/Hydra/Lurker'):       True,

    # ZvP — Forge Fast Expand
    ('FFE (Forge Fast Expand)',         'Macro Eco'):                    True,
    ('FFE (Forge Fast Expand)',         'Hydra/Lurker'):                 True,
    ('FFE (Forge Fast Expand)',         'Hydra/Lurker/Corruptor'):       True,
    ('FFE (Forge Fast Expand)',         'Ling/Bane/Hydra/Lurker'):       True,
    ('FFE (Forge Fast Expand)',         'Ling/Bane/Muta'):               True,
    ('FFE (Forge Fast Expand)',         'Roach/Hydra'):                  None,
    ('FFE (Forge Fast Expand)',         'Roach Rush'):                   False,
    # ZvP — Stargate / Oracle
    ('Stargate / Oracle / Air',         'Hydra/Lurker'):                 True,
    ('Stargate / Oracle / Air',         'Hydra/Lurker/Corruptor'):       True,
    ('Stargate / Oracle / Air',         'Hydra/Corruptor'):              True,
    ('Stargate / Oracle / Air',         'Ling/Bane/Hydra/Lurker'):       True,  # banes for gateway, hydras for air
    ('Stargate / Oracle / Air',         'Muta/Corruptor'):               True,
    ('Stargate / Oracle / Air',         'Roach/Corruptor/Broodlord'):    True,
    ('Stargate / Oracle / Air',         'Hydra Macro'):                  True,
    ('Stargate / Oracle / Air',         'Ling/Bane/Muta'):               None,  # mutas can help but risky
    ('Stargate / Oracle / Air',         'Ling/Bane'):                    False,  # no anti-air
    ('Stargate / Oracle / Air',         'Roach/Hydra'):                  None,  # Hydras ok but slow to build
    # ZvP — Robo
    ('Robo (Immortal/Colossus)',        'Hydra/Lurker'):                 True,
    ('Robo (Immortal/Colossus)',        'Muta/Corruptor'):               True,
    ('Robo (Immortal/Colossus)',        'Roach/Corruptor/Broodlord'):    True,
    ('Robo (Immortal/Colossus)',        'Hydra/Lurker/Corruptor'):       True,
    ('Robo (Immortal/Colossus)',        'Ling/Bane/Hydra/Lurker'):       True,
    ('Robo (Immortal/Colossus)',        'Roach/Hydra'):                  None,
    # ZvP — Gateway aggression
    ('Gateway Aggression / 4-Gate',    'Roach/Hydra'):                  True,
    ('Gateway Aggression / 4-Gate',    'Roach/Bane'):                   True,
    ('Gateway Aggression / 4-Gate',    'Ling/Bane/Hydra/Lurker'):       True,
    ('Gateway Aggression / 4-Gate',    'Ling/Bane'):                    True,
    ('Gateway Aggression / 4-Gate',    'Macro Eco'):                    False,
    # ZvP — Gate expand
    ('Standard Gate Expand',           'Macro Eco'):                    True,
    ('Standard Gate Expand',           'Hydra/Lurker'):                 True,
    ('Standard Gate Expand',           'Roach/Hydra'):                  True,
    ('Standard Gate Expand',           'Ling/Bane/Hydra/Lurker'):       True,

    # ZvZ — Muta
    ('Muta Transition',                'Muta Transition'):              True,
    ('Muta Transition',                'Hydra/Lurker'):                 True,
    ('Muta Transition',                'Roach/Hydra'):                  True,
    ('Muta Transition',                'Hydra Macro'):                  True,
    ('Muta Transition',                'Ling/Bane/Hydra/Lurker'):       True,
    # ZvZ — Roach/Hydra mirror
    ('Roach Rush',                     'Roach Rush'):                   True,
    ('Roach Rush',                     'Roach/Hydra'):                  True,
    ('Roach Rush',                     'Roach/Bane'):                   True,
    ('Roach Rush',                     'Macro Eco'):                    False,
    ('Roach/Hydra',                    'Roach/Hydra'):                  True,
    ('Roach/Hydra',                    'Hydra/Lurker'):                 True,
    ('Roach/Hydra',                    'Ling/Bane/Hydra/Lurker'):       True,
    ('Roach/Hydra',                    'Hydra Macro'):                  True,
    # ZvZ — Ling/Bane
    ('Ling/Bane',                      'Roach/Hydra'):                  True,
    ('Ling/Bane',                      'Ling/Bane'):                    True,
    ('Ling/Bane',                      'Roach/Bane'):                   True,
    # ZvZ — Lurker
    ('Lurker (Ling/Lurker or Roach/Lurker)', 'Hydra/Lurker'):           True,
    ('Lurker (Ling/Lurker or Roach/Lurker)', 'Ling/Bane/Hydra/Lurker'): True,
    # ZvZ — Standard / Hatch First mirror
    ('Standard Hatch First',           'Macro Eco'):                    True,
    ('Standard Hatch First',           'Hydra/Lurker'):                 True,
    ('Standard Hatch First',           'Roach/Hydra'):                  True,
    ('Standard Hatch First',           'Ling/Bane/Hydra/Lurker'):       True,
}


def evaluate_reaction(enemy_build, my_build, matchup, result):
    """
    Return (correct: bool|None, explanation: str).

    my_build is now "Opener → Composition" (e.g. "Hatch First → Hydra/Lurker").
    We match on the composition part so the opener doesn't prevent a match.
    """
    # Extract the composition part (everything after " → " if present)
    comp = my_build.split(' → ')[-1] if ' → ' in my_build else my_build

    key = (enemy_build, comp)
    correct = _GOOD_REACTIONS.get(key)

    if correct is True:
        return True,  f"{comp} is a strong response to {enemy_build}."
    elif correct is False:
        return False, f"{comp} is a poor response to {enemy_build} — check the build-response guide."
    elif correct is None:
        return None,  f"{comp} vs {enemy_build} — reaction is situational; review the replay."
    else:
        if result == 'Win':
            return None, f"Built {comp} vs {enemy_build} — won, but verify it was the right choice."
        else:
            return None, f"Built {comp} vs {enemy_build} — consider whether the build choice contributed to the loss."


def summarise_army(counter, race):
    """Split a unit counter into (combat_units, structures) dicts for the given race."""
    units_list   = {'Terran': TERRAN_UNITS,   'Zerg': ZERG_UNITS,   'Protoss': PROTOSS_UNITS  }.get(race, [])
    structs_list = {'Terran': TERRAN_STRUCTS, 'Zerg': ZERG_STRUCTS, 'Protoss': PROTOSS_STRUCTS}.get(race, [])
    units   = {u: counter[u] for u in units_list   if counter.get(u, 0) > 0}
    structs = {u: counter[u] for u in structs_list if counter.get(u, 0) > 0}
    return units, structs
# Maps each detected enemy build to a structured counter recommendation.
# Each entry has:
#   'target_comp'  : ideal Zerg composition to build towards
#   'opener'       : recommended opening
#   'key_timings'  : list of "build X by T:TT" cues
#   'key_units'    : which units matter most and why
#   'mistakes'     : common mistakes to avoid
#   'tips'         : 2–3 matchup-specific tips
_COUNTER_GUIDE = {

    # ── ZvT ──────────────────────────────────────────────────────────────────

    "Bio/Tank (Marine + Siege Tank)": {
        'target_comp': "Hydra/Lurker (with Banelings vs bio clumps)",
        'opener': "Hatch First → Pool ~1:15–1:20 → 2-base eco → Roach Warren → Hydra Den → Lurker Den",
        'attack_timing': {
            'window': '10:00–13:00 real time',
            'setup': 'Have 8–12 Lurkers + 15+ Hydralisks + Banelings before moving out',
            'lines': ['**Hold first, then counter:** Bio/Tank attacks at 11–13 min — set Lurkers at the ramp and let it break on your defenses, then push out', '**Attack timing: 13:00–15:00** — after holding the bio push, move out with 8+ Lurkers + Hydra + Banelings while Terran is rebuilding', 'Wait for Blinding Cloud (Vipers at ~13 min) before engaging their main Tank line', 'A well-timed 3rd base + push at 14–16 min wins most ZvT Bio/Tank games'],
        },
        'key_timings': [
            "Pool by 1:20 real time",
            "Lair by 4:30–5:00 (don't get supply-blocked out of Lurker morph)",
            "Lurker Den before 9:00 — Lurkers shut down tank lines",
            "+1/+1 upgrades by 7:00–8:00",
            "4th hatch by 6:00–7:00 to sustain unit production",
        ],
        'key_units': [
            "Lurkers — burrow under tank lines to nullify Siege Tanks",
            "Banelings — required for bio clumps (without Banelings, MMM walks over Hydras)",
            "Hydralisks — main DPS once Lurkers pin the tanks",
            "Overseers — detect cloaked Ghosts and drop/reveal",
        ],
        'mistakes': [
            "Building Roach/Hydra with no Lurkers — tanks shred anything that walks forward",
            "No Banelings — bio without Banelings requires Lurkers at every engagement",
            "Skipping Lair tech — delays Lurkers and lets the Terran push while you're still on Hydra only",
            "Droning past 70 without Lurkers — you'll have eco but no way to fight the push",
        ],
        'tips': [
            "Build a Baneling Nest early (by 3:00–4:00) if you see aggressive bio — Banelings stop bio floods before Lurkers are ready",
            "Place Lurkers in the natural ramp mineral line to force siege — never walk Hydra into unsieged Tanks",
            "Vipers (Blinding Cloud) + Hydra is the late-game answer when Tanks are spread wide",
        ],
    },

    "Standard Bio (MMM)": {
        'target_comp': "Ling/Bane/Hydra or Ling/Bane/Lurker",
        'opener': "Hatch First → Pool ~1:15 → early Baneling Nest by 3:30 → Ling speed → Hydra Den",
        'attack_timing': {
            'window': '8:00–11:00 real time',
            'setup': '12+ Banelings + Zergling speed + 10+ Hydralisks before moving out',
            'lines': ['**Hold at 6:00–8:00** with Ling/Bane, then immediately counter-attack before the Terran re-masses', '**Attack timing: 9:00–11:00** — Hydra Den finished + first 10 Hydralisks + Zergling surround', 'Every minute you wait, more Bio stacks up — strike while they rebuild after the initial push', 'Take the 3rd base on the way out — fight at the Terran natural while your 3rd drones'],
        },
        'key_timings': [
            "Baneling Nest by 3:30 real time",
            "Zergling speed before 4:00",
            "Hydralisk Den by 6:00–7:00",
            "Lair for Lurkers if the push doesn't come early",
        ],
        'key_units': [
            "Banelings — the core answer to MMM clumps; essential",
            "Zerglings — surrounds and free kills on spread bio",
            "Hydralisks — anti-air for Medivacs and damage dealer",
        ],
        'mistakes': [
            "No Banelings against MMM — pure Hydra/Roach dies to bio",
            "Droning too long vs bio pressure — bio can arrive at 5–6 min",
        ],
        'tips': [
            "Use Zerglings to surround while Banelings target Marauder/Medivac clumps",
            "Creep spread allows Zerglings to run down retreating bio — critical",
        ],
    },

    "Early Bio Aggression": {
        'target_comp': "Ling/Bane hold → Hydra/Lurker for mid-game",
        'opener': "Hatch First → Pool by 1:10–1:15 → Baneling Nest by 3:00 → hold with Ling/Bane → tech to Hydra",
        'attack_timing': {
            'window': 'After holding (5:00–7:00)',
            'setup': 'Hold with Ling/Bane/Spine → counter immediately after',
            'lines': ['**Counter-attack at 6:00–7:30** the moment the bio push breaks — Terran macro is behind', 'Run Zerglings into the Terran main while your Banelings clean up stragglers at your ramp', 'The Terran spent all their gas on early bio — they have no Factory/Starport follow-up for several minutes', 'Take your 3rd base and re-drone while harassing — economic advantage snowballs fast'],
        },
        'key_timings': [
            "Pool before 1:15 — scout the 2-rax and react fast",
            "Baneling Nest by 3:00 real time",
            "Spine Crawler at natural ramp if bio arrives before Banelings",
            "Don't get supply-blocked — keep Overlords queued",
        ],
        'key_units': [
            "Banelings — 4+ Banelings hold a 2-rax attack easily",
            "Queens — pull Queens forward to block the ramp",
            "Spine Crawlers — 1–2 at natural ramp buys time for Banelings",
        ],
        'mistakes': [
            "Continuing to drone past 22 supply vs 2-rax without Banelings ready",
            "No Spine Crawlers — 1 spine at the ramp with a Queen is often enough to hold",
            "Building Roach Warren instead of Baneling Nest — Roaches are too slow vs bio",
        ],
        'tips': [
            "Pull one Queen forward to the top of the ramp — she blocks choke and deals damage",
            "2 Banelings + 6 Zerglings can hold almost any 2-rax bio attack on a single ramp",
            "If you have Ling speed, flood the main after defending — punish the Terran's lack of units",
        ],
    },

    "BattleCruiser Rush": {
        'target_comp': "Hydra/Lurker/Corruptor — Corruptors are mandatory for BC",
        'opener': "Hatch First → Pool ~1:15 → Roach Warren → Hydra Den → Spire by 6:00 → Corruptors",
        'attack_timing': {
            'window': '9:00–12:00 (before BC critical mass)',
            'setup': '6–8 Corruptors before BCs warp in (~11 min); Hydra/Lurker for ground',
            'lines': ['**Corruptors must be ready by 10:00** — BCs begin arriving at 10–11 min and kill everything without Corruptors', '**Attack timing: 12:00–14:00** — once the first BC wave is eliminated, push with Corruptors + Hydra/Lurker', 'Morph surviving Corruptors to Broodlords for the finishing push — Broodlords are devastating vs Terran ground', 'Do not wait longer than 14 min — each minute more gives Terran time to rebuild BC production'],
        },
        'key_timings': [
            "Scout the Starport + TechLab at 3:30 with Overlord over opponent's main",
            "Spire started before 5:30 real time — Corruptors need to be ready",
            "First Corruptors warping in before 8:00",
            "Keep Hydralisks for ground defense while Corruptors handle BCs",
        ],
        'key_units': [
            "Corruptors — the only reliable answer to BCs; build 6–10 before BCs arrive",
            "Hydralisks — deal with ground support units and add anti-air",
            "Queens — 3+ Queens can buy time if BCs arrive before Corruptors",
        ],
        'mistakes': [
            "No Spire — BCs with no Corruptors will destroy everything",
            "Building Lurker Den instead of Spire — Lurkers can't shoot up",
            "Letting the BC player tech up uncontested — pressure the ground to delay BC production",
            "Forgetting Queens — Stack Queens for early BC harassment",
        ],
        'tips': [
            "When you scout Starport + TechLab (or Fusion Core), immediately start Spire",
            "6 Corruptors kill a BC in seconds — get them out before the BCs arrive (~11 min)",
            "After killing BCs with Corruptors, morph them to Broodlords for a decisive push",
        ],
    },

    "Mech": {
        'target_comp': "Hydra/Lurker → Infestor/Viper late game",
        'opener': "Hatch First → Pool → mass eco → Hydra Den by 6:00 → Lurker Den → Infestors/Vipers",
        'attack_timing': {
            'window': '14:00–18:00 real time',
            'setup': 'Max out Hydra/Viper (200 supply) with +2/+2 upgrades before engaging',
            'lines': ['**Never attack Mech before 14:00** — you need Vipers with Blinding Cloud + full upgrades first', '**Ideal attack: 15:00–18:00** on 4–5 bases with 3/3 upgrades + 6+ Vipers', 'Blinding Cloud the front row of Tanks, then send Hydra to clean up — practice this sequence', 'If Terran turtles past 20 min, transition to Broodlords — they outrange Tanks'],
        },
        'key_timings': [
            "Heavy drone to 70+ — Mech is slow, exploit the eco advantage",
            "Hydralisk Den by 6:00",
            "Infestor or Viper tech by 10:00 — Blinding Cloud and Fungal break mech",
            "Spores at every base for Banshee/Liberator",
        ],
        'key_units': [
            "Vipers — Blinding Cloud on mech clumps is devastating; they can't shoot",
            "Infestors — Fungal Growth roots mech, Infested Terran absorbs tank fire",
            "Hydralisks — main damage dealer with Viper support",
            "Lurkers — hold defensive positions, force siege",
        ],
        'mistakes': [
            "Attacking Mech without Vipers — mech with vision destroys anything moving",
            "Not spreading spores — Banshees and Liberators freely kill drones without anti-air",
            "Racing into a sieged-up Mech ball — use Blinding Cloud first, THEN attack",
        ],
        'tips': [
            "Blinding Cloud the front row of Tanks, then send Hydralisks to clean up",
            "Abuse terrain — Lurkers on high ground cover low-ground Mech movements",
            "Stay on 3–4 bases and max at 200 with Hydra/Viper before engaging",
        ],
    },

    "Air Heavy (Banshee/Liberator/BC)": {
        'target_comp': "Hydra/Corruptor or Muta/Corruptor",
        'opener': "Hatch First → Pool → Hydra Den by 5:30 → Spire if you see heavy air",
        'attack_timing': {
            'window': '11:00–14:00 real time',
            'setup': '12+ Hydralisks + 6+ Corruptors before engaging air-heavy compositions',
            'lines': ['**Attack timing: 11:00–13:00** — once you have Hydra + Corruptors, their ground is weak', 'Corruptors trade +25% damage to armored, making Liberators and BCs melt fast', 'Move out while they are building their air force — their ground army is minimal', 'After clearing air, push their main hard — they have little ground defense'],
        },
        'key_timings': [
            "Hydralisk Den by 5:30 — Hydras are the main anti-air unit",
            "Spore Crawlers at every mineral line — mandatory vs Banshees",
            "Corruptors from Spire once you confirm heavy air production",
        ],
        'key_units': [
            "Hydralisks — anti-air backbone; get 12+ before engaging",
            "Corruptors — efficient vs capital ships (BCs, Liberators)",
            "Spore Crawlers — 2 per base defends Banshee harassment",
            "Queens — extra anti-air at each hatchery",
        ],
        'mistakes': [
            "No Spore Crawlers — Cloaked Banshees free-kill drones indefinitely",
            "Only Roaches vs heavy air — Roaches cannot shoot up",
        ],
        'tips': [
            "3 Queens + 2 Spores hold Banshee harass cheaply",
            "Once you have Corruptors, engage aggressively — air armies can't kite as well as bio",
        ],
    },

    "Standard 1-1-1 Opener": {
        'target_comp': "Hatch First macro → Hydra/Lurker or Roach/Hydra",
        'opener': "Hatch First → drone hard to 66 → flex based on scouting",
        'attack_timing': {
            'window': '9:00–12:00 real time',
            'setup': 'React to what you see — scout at 4–5 min to determine the follow-up',
            'lines': ['**Scout at 4:30** with an Overlord to determine if they go Bio, Mech, or Air follow-up', 'If Bio follow-up: attack at **9:00–11:00** with Ling/Bane/Hydra', 'If Mech follow-up: delay to **14:00+** and build Vipers', 'If Air follow-up: get Corruptors by **9:00** and attack at **11:00–13:00**'],
        },
        'key_timings': [
            "Scout at 2:00 to confirm 1-1-1 (1 Barracks, 1 Factory, 1 Starport)",
            "If Factory: get RoachWarren + Hydra Den (Tank follow-up likely)",
            "If Starport + Reactor: get Spores for Medivac/Liberator",
            "Secure 3rd base before 6:00",
        ],
        'key_units': [
            "Hydralisks — flexible vs air and ground",
            "Lurkers — if Tank follow-up is coming",
        ],
        'mistakes': [
            "Assuming 1-1-1 stays standard — it often transitions into BC rush or Mech",
            "Skipping scouting at 4:00 — confirms whether the threat is real",
        ],
        'tips': [
            "1-1-1 is a scouting opener for the Terran — respond to what you see at 4–5 min",
            "Keep an Overlord in the Terran main to spot the tech building",
        ],
    },

    # ── ZvP ──────────────────────────────────────────────────────────────────

    "FFE (Forge Fast Expand)": {
        'target_comp': "Macro Hatch First → Hydra/Lurker or Ling/Bane/Hydra",
        'opener': "Hatch First → extreme drone priority → 4th base by 6:00 → Hydra Den → Lurker Den",
        'attack_timing': {
            'window': '12:00–16:00 real time',
            'setup': '80 drones alive + 3rd base + Hydra/Lurker + +1/+1 upgrades before moving out',
            'lines': ['**Attack timing: 12:00–15:00** with Hydra/Lurker before Protoss gets Colossus or Storm', 'Wait for +1/+1 upgrades to complete — Hydra with +1 attack kills Stalkers in 3 fewer shots', 'Set Lurkers outside the Protoss 3rd base; when they pull back, flood Hydra through', 'Do NOT attack before 12:00 — FFE defenses (2–3 gates + Stalkers) hold early pushes easily', 'If Protoss takes a 4th base, match with your own — then push at 16:00 with full upgrades'],
        },
        'key_timings': [
            "FFE gives Protoss a strong economy — match it by droning to 80+ before attacking",
            "4th Hatchery by 6:00–7:00 to match Protoss eco",
            "Hydralisk Den by 6:30 — timing attack timing hits at 8–10 min",
            "+1/+1 upgrades before the first major engagement",
            "Lurker Den by 8:00–9:00 for mid-game fights",
        ],
        'key_units': [
            "Hydralisks — core anti-air and gateway unit counter",
            "Lurkers — force Protoss to micro Stalkers or concede ground",
            "Corruptors — needed if Protoss transitions to Skytoss",
            "Zerglings — free flanks and surround vs Zealot/Stalker",
        ],
        'mistakes': [
            "Attacking before your eco and unit count match the Protoss — FFE is greedy, punish with your own greed first",
            "No Corruptors vs FFE → Void Ray follow-up destroys without anti-air",
            "Attacking straight into a fortified 3rd with no Lurkers",
        ],
        'tips': [
            "Spread creep aggressively — Protoss gateway armies lose efficiency off creep",
            "Watch for Colossus/Disruptor transition; adjust Corruptors accordingly",
            "Nydus into the Protoss main forces units home while you macro",
        ],
    },

    "Stargate / Oracle / Air": {
        'target_comp': "Hydra/Lurker → Corruptor for air denial",
        'opener': "Hatch First → Pool ~1:15 → extra Queens (3–4 early) → Hydra Den by 5:00 → Spore Crawlers",
        'attack_timing': {
            'window': '10:00–13:00 real time',
            'setup': 'Hold Oracle harass first → 10+ Hydralisks + 6+ Corruptors → move out',
            'lines': ['**Attack timing: 10:00–13:00** — once Oracles are shut down, the Protoss ground army is minimal', 'Move out with Hydra/Corruptor as soon as their air harass is neutralised', 'Their gate count is lower than Gateway expand players — they cannot hold Hydra + Lurker ground pressure', 'Do NOT wait past 15:00 — Carrier or Void Ray critical mass becomes very hard to fight'],
        },
        'key_timings': [
            "3 Queens at each base by 4:00 — Oracle harass needs anti-air before Hydras",
            "Spore Crawler at each mineral line before 4:30",
            "Hydralisk Den by 5:00–5:30 — Hydras are the answer to Oracles and Void Rays",
            "Corruptors from Spire if Protoss masses Carriers or Void Rays",
        ],
        'key_units': [
            "Hydralisks — primary Oracle/Void Ray counter; build 12+ before moving out",
            "Queens — emergency air defense and creep spread; stack them",
            "Spore Crawlers — 2 per base, especially mineral lines",
            "Corruptors — needed once Protoss goes heavy Skytoss (Carrier/Void Ray)",
        ],
        'mistakes': [
            "No Spores — Oracles blink in and kill 8+ drones per second without response",
            "Sending Hydralisks into a Skytoss ball without Corruptors — Void Rays shred ground",
            "Forgetting to morph Corruptors into Brood Lords for a ground push late game",
        ],
        'tips': [
            "Every extra Queen costs 150 minerals and counters Oracle harassment for free",
            "Oracle does 60 DPS to bio and is cloaked; stack Queens by mineral lines early",
            "Once you have Hydras + Corruptors, Protoss Skytoss melts — push before Carriers",
        ],
    },

    "Robo (Immortal/Colossus)": {
        'target_comp': "Hydra/Lurker with Corruptors for Colossus",
        'opener': "Hatch First → Hydra Den by 6:00 → Lurker Den → Spire or Infestation Pit vs heavy Colossus",
        'attack_timing': {
            'window': '11:00–14:00 real time',
            'setup': 'Corruptors ready before Colossus arrives (~10 min); Hydra/Lurker for ground',
            'lines': ['**Kill first Colossus ASAP** (usually 9:30–11:00) with 4–6 Corruptors', '**Attack timing: 11:00–14:00** — the moment their Colossus dies, push with Hydra/Lurker', 'Viper Abduct pulls Immortals or Colossus into your army for instant kills', 'Observer scouting is key — know when Colossus is warping in and pre-position Corruptors'],
        },
        'key_timings': [
            "Scout the Robotics Facility — Colossus or Immortal tells you the timing",
            "Hydra Den by 5:30–6:00",
            "Spire or Corruptors before Colossus arrives (~10 min)",
            "Lurkers vs Immortal-heavy — Immortals cannot shoot Lurkers efficiently",
        ],
        'key_units': [
            "Corruptors — kill Colossus before it clears Hydralisks",
            "Hydralisks — core composition vs gateway units",
            "Lurkers — great vs Immortal push; burrowed Lurkers force Observers",
            "Vipers — Abduct Colossi and Immortals into your army",
        ],
        'mistakes': [
            "No anti-air vs Colossus — Corruptors must arrive before the Colossus does",
            "Engaging Colossus on open ground — use Corruptors or Abduct first",
        ],
        'tips': [
            "Viper Abduct pulls a Colossus back into your army — one Abduct wins the engagement",
            "Lurkers force Observers; killing the Observer makes your Lurkers invincible",
        ],
    },

    "Gateway Aggression / 4-Gate": {
        'target_comp': "Roach/Hydra or Ling/Bane for early defense",
        'opener': "Hatch First → Pool ~1:15 → Roach Warren by 3:00 → hold with Roaches + Zerglings",
        'attack_timing': {
            'window': 'After holding (7:00–9:00)',
            'setup': 'Hold with Roach + Spine + Zergling → immediately counter-push',
            'lines': ['**Counter-attack at 7:00–8:00** the moment the 4-gate breaks — Protoss has almost no army left', 'Push to the Protoss natural and plant Spine Crawlers to deny expansion while you drone up', 'The Protoss delayed their own Nexus by going 4-gate — their eco is crippled', 'Follow up with Hydra Den tech while you hold their 3rd base timing'],
        },
        'key_timings': [
            "Roach Warren by 3:00 — 4-gate arrives at 5–6 min",
            "6–8 Roaches + Zerglings to hold the natural ramp",
            "Spine Crawlers at the natural if the push is heavy",
            "After holding, drone to 66 and take 3rd base",
        ],
        'key_units': [
            "Roaches — tank the gateway units at the ramp",
            "Zerglings — surround and kill injured Stalkers/Zealots",
            "Spine Crawlers — 1–2 reinforce the ramp defense cheaply",
        ],
        'mistakes': [
            "Trying to drone vs 4-gate without Roaches — you'll die",
            "Building only Zerglings vs Stalker-heavy 4-gate — Stalkers kite Zerglings",
        ],
        'tips': [
            "Hold at the ramp with Roaches — don't chase into the open",
            "After holding, expand greedily; Protoss invested all their gas in early attacks",
        ],
    },

    "Standard Gate Expand": {
        'target_comp': "Macro Hatch First → Hydra/Lurker",
        'opener': "Hatch First → drone heavy → 4th base by 6:30 → Hydra Den → Lurker Den",
        'attack_timing': {
            'window': '12:00–15:00 real time',
            'setup': '4 bases + 70+ drones + Hydra/Lurker + +1/+1 before pushing',
            'lines': ['**Take 4 bases freely** — Gate expand cannot stop fast expansions with economic Zerg play', '**Attack timing: 12:00–15:00** before Colossus/Disruptor arrives (~13–14 min)', 'Lurkers + Hydra forces a difficult response from 3-gate players with no Colossus yet', 'If Protoss completes Colossus tech (scouted via Observer or Spire), wait for Vipers or Corruptors'],
        },
        'key_timings': [
            "Standard Gate Expand is economic — match with your own greed",
            "4th Hatchery by 6:30",
            "+1/+1 upgrades before first engagement",
            "Watch for timing at 8–10 min (Gateway timing attack)",
        ],
        'key_units': [
            "Hydralisks — flex vs any gateway follow-up",
            "Lurkers — essential vs Stalker/Colossus mid-game",
        ],
        'mistakes': [
            "Not scouting at 5–6 min — Standard Gate can transition to Colossus or Void Rays",
        ],
        'tips': [
            "Keep an Overlord outside the Protoss natural to spot the tech choice",
            "Spread creep to the third — Protoss with no creep loses zealot-heavy fights",
        ],
    },

    # ── ZvZ ──────────────────────────────────────────────────────────────────

    "Muta Transition": {
        'target_comp': "Hydra/Lurker — best counter to Mutas",
        'opener': "Hatch First → Pool → Roach Warren → Hydra Den by 5:00 → Spore Crawlers at each base",
        'attack_timing': {
            'window': '8:00–10:00 real time',
            'setup': '10+ Hydralisks clumped + Spore Crawlers at home → push once Mutas stop harassing',
            'lines': ['**Attack timing: 8:00–10:00** — Muta players have almost zero ground army', 'Move out with 10+ clumped Hydralisks while leaving Spores at home to handle remaining Mutas', 'Their hatcheries have no larvae injection because Queens are dead or denied — they cannot rebuild fast', "Add Lurkers once you're inside their base to deny re-production"],
        },
        'key_timings': [
            "Hydralisk Den by 5:00 — Hydralisks need to be ready before Mutas hit",
            "Spore Crawlers at each mineral line before 6:00",
            "Do NOT build a Spire to mirror — Hydra/Spore beats Muta decisively",
            "Lurker Den after Hydra Den — late game Lurkers complement Hydralisks",
        ],
        'key_units': [
            "Hydralisks — destroy Mutas at 3 shots each with upgrades",
            "Spore Crawlers — cheap home defense that frees your Hydralisks to attack",
            "Queens — each Queen kills Mutas efficiently and costs only 150 minerals",
        ],
        'mistakes': [
            "Building a Spire to counter Mutas with Mutas — Hydralisks are far more cost-efficient",
            "No Spores — Mutas will harass freely between your Hydra movements",
            "Chasing Mutas across the map — let Hydras stay at base until you have 12+",
        ],
        'tips': [
            "Stack 10+ Hydralisks and move as a group — Mutas can't trade against clumped Hydras",
            "Keep your Hydralisks near Spores so Mutas can't separate them",
            "After shutting down Muta harass, push with Hydra/Lurker — the Muta player has no ground army",
        ],
    },

    "Roach Rush": {
        'target_comp': "Roach/Hydra or Roach/Bane to match the rush",
        'opener': "Hatch First → Pool ~1:10 → Roach Warren by 3:00 → 8 Roaches + Spine at natural",
        'attack_timing': {
            'window': 'After holding (5:00–7:00)',
            'setup': 'Hold with Roach + Spine → counter immediately',
            'lines': ['**Counter-attack at 6:00–7:00** the moment the rush fails — their economy is behind', 'Your Roaches + Zerglings can march straight to their natural and deny it', 'Roach Rush players often have no 3rd hatch — every second you wait lets them recover', 'Add Hydra Den tech while counter-attacking to transition into mid-game dominance'],
        },
        'key_timings': [
            "Roach Warren by 3:00 — Roach Rush hits at 3:30–4:30",
            "1 Spine Crawler at natural ramp while Roaches build",
            "Match Roach count — if they have 8, you need 6–8 plus Spine",
            "Drone after holding, then out-macro with 3rd base",
        ],
        'key_units': [
            "Roaches — mirror the rush; Roach vs Roach favors the defender with Spine",
            "Spine Crawlers — 1 Spine at the natural ramp is worth 4 Roaches defensively",
            "Zerglings — surround finishing-low Roaches after the main fight",
        ],
        'mistakes': [
            "Droning to 22 vs Roach Rush without Roaches — you will die",
            "Not placing a Spine at the natural — Spine holds the choke while Roaches arrive",
        ],
        'tips': [
            "After holding, you likely have more eco — push with Roach/Hydra while opponent rebuilt",
            "Scouting matters most in ZvZ — Overlord at 1:30 confirms Roach Warren timing",
        ],
    },

    "Roach/Hydra": {
        'target_comp': "Roach/Hydra or Hydra/Lurker",
        'opener': "Hatch First → Roach Warren → Hydra Den → Lurker Den — match the mirror",
        'attack_timing': {
            'window': '10:00–13:00 real time',
            'setup': 'First 4–6 Lurkers complete before moving out; Overseer for detection',
            'lines': ['**Lurker Den started by 9:00** gives first Lurkers ready at ~11:30', '**Attack timing: 11:00–13:00** with 4–6 Lurkers + Hydra behind them', "Burrow Lurkers at the opponent's 3rd base ramp — they cannot defend without Overseer or Ravagers", 'Match Overseer count — they will try to counter your Lurkers with their own Overseers'],
        },
        'key_timings': [
            "Match their Hydra Den timing — if they have Hydras by 6:00, you need them too",
            "Lurker Den gives the decisive advantage in the Roach/Hydra mirror",
            "+1/+1 upgrades to win supply-equal fights",
        ],
        'key_units': [
            "Lurkers — burrowed Lurkers beat Roach/Hydra armies decisively",
            "Hydralisks — main damage dealer in the mirror",
            "Vipers — Blinding Cloud removes Hydra vision and cripples the opponent",
        ],
        'mistakes': [
            "Staying on Roach/Hydra with no Lurkers late game — whoever gets Lurkers wins",
            "Forgetting upgrades — +1 attack closes on +0 armour every fight",
        ],
        'tips': [
            "First player to Lurkers in ZvZ Roach/Hydra mirror wins the mid-game",
            "Use Overlord spread to scout when they take their 3rd base — attack if they're greedy",
        ],
    },

    "Ling/Bane": {
        'target_comp': "Roach/Hydra — Roaches tank Banelings efficiently",
        'opener': "Hatch First → Roach Warren by 3:00 → Roaches to tank Banes → Hydra Den",
        'attack_timing': {
            'window': '7:00–10:00 real time',
            'setup': 'Roach tank + Spine hold → transition to Hydra Den and push',
            'lines': ['**Hold at 5:00–7:00** with 6+ Roaches + Spine at natural — Banes cannot crack this', '**Attack timing: 9:00–11:00** — Hydra Den online + 10 Hydralisks + Roaches to absorb Banes', 'Your Roaches walk first to eat Banelings, then Hydralisks mop up remaining Zerglings', "Take the 3rd base on the way out while they're reinvesting in Banes"],
        },
        'key_timings': [
            "Roach Warren by 3:00 — Roaches are the answer to Ling/Bane",
            "Spine Crawlers at both bases while Roaches build",
            "Do not leave Hydralisks/Zerglings in front — Banelings kill light units",
            "After holding, out-tech with Hydra Den → Lurker Den",
        ],
        'key_units': [
            "Roaches — tank Banelings (each Baneling does 35 vs armored = 2 hits to kill Roach)",
            "Spine Crawlers — hold the ramp while Roaches build",
        ],
        'mistakes': [
            "No Roaches — Zerglings die instantly to enemy Banelings",
            "Clumping Hydralisks in front — Banes splash kills them all",
            "Not spreading Zerglings — Banes do splash, spread before engaging",
        ],
        'tips': [
            "Roach + Spine at natural ramp holds almost every Ling/Bane attack",
            "After holding, transition to Hydra/Lurker — Bane player has no answer to Lurkers",
        ],
    },

    "Lurker (Ling/Lurker or Roach/Lurker)": {
        'target_comp': "Hydra/Lurker — mirror with better upgrades and detection",
        'opener': "Hatch First → Roach Warren → Hydra Den → Lurker Den — match their Lurker timing",
        'attack_timing': {
            'window': '12:00–15:00 real time',
            'setup': 'Mirror Lurker tech + Overseer → Hydra/Lurker for the engagement',
            'lines': ['**Always have 2 Overseers with your army** — fighting enemy Lurkers without detection = guaranteed loss', '**Attack timing: 12:00–15:00** with your own Lurkers, Overseers, and +1/+1 upgrades', 'Use Vipers (Abduct) to pull Lurkers out of burrow for instant kills', 'Flank from two angles — Lurkers have a fixed facing and cannot cover all directions simultaneously'],
        },
        'key_timings': [
            "Get your own Lurker Den — Lurker mirror favors better upgrades and more Overseers",
            "Overseer at all times — revealing enemy Lurkers is essential",
            "+1/+1 upgrades before engaging",
        ],
        'key_units': [
            "Overseers — detect burrowed Lurkers; without this you walk into ambushes",
            "Hydralisks — deal with Lurkers once revealed",
            "Your own Lurkers — burrowed counter-burrowed fight in corridors",
        ],
        'mistakes': [
            "No Overseer — walking Hydras into undetected Lurkers loses the game",
            "Engaging in narrow corridors vs Lurkers — use flanks and Overseers",
        ],
        'tips': [
            "Keep 2 Overseers with your army at all times in ZvZ Lurker games",
            "Vipers can Abduct Lurkers out of burrow position for instant kills",
        ],
    },

    "Standard Hatch First": {
        'target_comp': "Hatch First → Roach/Hydra or Hydra/Lurker (mirror eco game)",
        'opener': "Hatch First → drone aggressively → match their tech path",
        'attack_timing': {
            'window': '10:00–13:00 real time',
            'setup': 'Match their tech, get Lurkers first, then push with Hydra/Lurker + Overseer',
            'lines': ['**First to Lurkers wins** — race to Lurker Den and push the moment they complete', '**Attack timing: 10:00–13:00** with 4–6 Lurkers + Hydralisks + Overseer', 'Scout at 1:30 and 3:30 to determine if they go Muta or Roach/Hydra — adjust accordingly', 'Spread creep to their 3rd base — force them to respond while your Lurkers set up'],
        },
        'key_timings': [
            "Scout at 1:30 to confirm Hatch First and tech direction",
            "Match their Lair timing — whoever gets Lurkers first has advantage",
            "+1/+1 upgrades before first engagement",
        ],
        'key_units': [
            "Hydralisks — flexible core unit in ZvZ macro",
            "Lurkers — decisive advantage once both players are on Roach/Hydra",
        ],
        'mistakes': [
            "Not scouting tech direction — you need to know if they go Muta or Roach/Hydra",
        ],
        'tips': [
            "In ZvZ mirrors, the player with better drone timing and first Lurkers usually wins",
            "Spread creep — Zerglings on creep crush Zerglings off creep in the mid-game",
        ],
    },

    "Unknown": {
        'target_comp': "Flex — scout before committing to a composition",
        'opener': "Hatch First → drone to 40 → check opponent's tech before deciding",
        'attack_timing': {
            'window': 'Depends on scouting',
            'setup': 'Scout at 1:30, 3:30, and 5:30 before committing',
            'lines': ['**Scout before attacking** — send Overlords at 1:30, 3:30, and 5:30 to identify the enemy build', 'Default safe timing: **12:00–14:00** with Hydra/Lurker + +1/+1 upgrades works vs most builds', 'If you see heavy air: delay to 13:00 and build Corruptors first', 'If you see Roach aggression: react defensively first, then push at 9:00 after holding'],
        },
        'key_timings': [
            "Send an Overlord at 1:30 to check the main base",
            "Identify: Bio / Mech / Air for Terran; Gateway / Robo / Stargate for Protoss",
            "React at 3:00 with the appropriate tech building",
        ],
        'key_units': ["Depends on scouting — build Hydra Den as a safe default"],
        'mistakes': ["Committing to a single composition without scouting"],
        'tips': ["Hydralisk Den at 5:30–6:00 is a safe default vs any build you can't identify"],
    },
}


def get_counter_guide(enemy_build):
    """Return the counter guide dict for the given enemy build, or None if not found."""
    return _COUNTER_GUIDE.get(enemy_build)




# ── Output path helper ───────────────────────────────────────────────────────

def unique_path(directory, filename):
    """
    Return a path that does not already exist.
    If 'Game 2026-03-10 ZvT.md' exists, tries 'Game 2026-03-10 ZvT (2).md', etc.
    FIX 11: prevents silent overwrite when multiple games of the same matchup are
    played on the same day.
    """
    base, ext = os.path.splitext(filename)
    path = os.path.join(directory, filename)
    counter = 2
    while os.path.exists(path):
        path = os.path.join(directory, f"{base} ({counter}){ext}")
        counter += 1
    return path


# ── AI detection ─────────────────────────────────────────────────────────────

def _parse_initdata_slots(streams):
    """
    Internal: scan the initdata stream for player slots using the binary marker.

    SC2 stores each player slot as:
        [name bytes] [0x01 0x00] [0x06 = local | 0x02 = remote] [...]

    We scan every candidate stream for all 0x01 0x00 0x02/0x06 markers and
    read the ASCII player name that ends immediately before each marker.
    This handles all-caps names (e.g. OKNEMU), mixed-case, and any extra
    padding bytes that some replay versions insert before the marker.

    Returns list of (name: str, is_local: bool) in stream order (= PlayerID order).
    """
    EXCLUDED = {'terran', 'zerg', 'protoss', 'random', 'starcraft',
                'dflt', 'dfltq', 'comp', 'open', 'rewa', 'part',
                'unknown', 'human', 'computer'}

    def name_before(raw, pos):
        """
        Read the player name ending just before pos.
        Names are stored as raw UTF-8 bytes. We read backward collecting
        bytes that are plausible name characters (printable, non-control,
        not the structural 0x00/0x01/0x10 bytes used as field separators).
        """
        end = pos
        start = end - 1
        # Walk back over bytes that could be part of a UTF-8 name.
        # Stop at null, 0x01 (field tag), 0x10 (length prefix), or
        # any byte that is clearly a structural separator (< 0x20 except
        # valid UTF-8 continuation bytes 0x80-0xBF which we allow).
        while start >= 0:
            b = raw[start]
            # Allow: printable ASCII (0x21-0x7e), UTF-8 lead (0xC0-0xFF),
            # UTF-8 continuation (0x80-0xBF)
            if 0x21 <= b <= 0x7e or 0x80 <= b <= 0xFF:
                start -= 1
            else:
                break
        start += 1
        if end - start < 2:
            return ''
        raw_name = raw[start:end]
        # Try UTF-8 first, fall back to latin-1
        try:
            s = raw_name.decode('utf-8')
        except UnicodeDecodeError:
            try:
                s = raw_name.decode('latin-1')
            except Exception:
                return ''
        # Must start with a letter (any Unicode letter is fine for display;
        # just reject strings that start with a digit or punctuation)
        if not s or not (s[0].isalpha() or s[0].isdigit()):
            return ''
        return s

    best = []
    for raw in streams.values():
        if b'"Title"' in raw or len(raw) > 20000:
            continue
        slots = []

        # ── Pass 1: collect all marker-prefixed slots (01 00 02/06) ──────────
        for i in range(len(raw) - 2):
            if raw[i] != 0x01 or raw[i + 1] != 0x00 or raw[i + 2] not in (0x02, 0x06):
                continue
            name = name_before(raw, i)
            if not name:
                continue
            if name[0].isdigit():
                continue
            if name.lower() in EXCLUDED or any(name.lower().startswith(e) for e in EXCLUDED):
                continue
            slots.append((name, raw[i + 2] == 0x06))

        # ── Pass 2: if only the local slot was found (no 0x02 for the opponent),
        #    try to recover the first player name from the 0x10 [len] [name]
        #    prefix that every initdata stream starts with. ───────────────────
        if len(slots) == 1 and raw[0] == 0x10:
            first_len = raw[1]
            if 2 <= first_len <= 30 and first_len + 2 <= len(raw):
                name_bytes = raw[2:2 + first_len]
                try:
                    first_name = name_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        first_name = name_bytes.decode('latin-1')
                    except Exception:
                        first_name = ''
                if (first_name
                        and first_name[0].isalpha()
                        and not any(first_name.lower().startswith(e) for e in EXCLUDED)
                        and first_name.lower() != slots[0][0].lower()):
                    # Determine whether the first name is local or remote
                    # by checking if the existing slot (local=True) is different
                    # The first-in-stream name has no marker, so it's the opponent
                    slots.insert(0, (first_name, False))   # prepend as remote (index 0)

        # Keep streams that have at least a local marker and at least 1 slot
        # (opponent may have failed to parse if their name is non-ASCII)
        has_local = any(loc for _, loc in slots)
        if has_local and len(slots) >= 1:
            if len(slots) > len(best):
                best = slots

    # Deduplicate consecutive identical entries (some replays repeat the same slot)
    deduped = []
    seen = set()
    for name, is_local in best:
        key = (name.lower(), is_local)
        if key not in seen:
            seen.add(key)
            deduped.append((name, is_local))

    return deduped[:2]


def parse_initdata_names(streams):
    """
    Extract player names from the initdata stream in PlayerID order.
    Returns a list like ['OKNEMU', 'Mizo'] — index 0 = PlayerID 1, etc.
    """
    return [name for name, _ in _parse_initdata_slots(streams)]


def find_local_player_index(streams):
    """
    Return the 0-based index of the local player (replay owner) in players[].
    Uses the 0x06 local-player marker in the initdata binary.

    Player slots in the initdata are separated by a 0x81 0x00 byte sequence.
    Counting how many 0x81 0x00 pairs appear before the 0x01 0x00 0x06 marker
    gives the player's index (0 = PlayerID 1, 1 = PlayerID 2).

    This works regardless of whether the opponent slot has a 0x02 marker,
    and regardless of name encoding (ASCII, all-caps, UTF-8, etc.).

    Returns None if not determinable (vs AI, observer replays).
    """
    for raw in streams.values():
        if b'"Title"' in raw or len(raw) > 20000:
            continue

        # Find the first 0x01 0x00 0x06 (local-player marker)
        local_pos = None
        for i in range(len(raw) - 2):
            if raw[i] == 0x01 and raw[i + 1] == 0x00 and raw[i + 2] == 0x06:
                local_pos = i
                break

        if local_pos is None:
            continue

        # Also verify a valid name precedes the marker (sanity check)
        end, start = local_pos, local_pos - 1
        while start >= 0 and (0x21 <= raw[start] <= 0x7e or 0x80 <= raw[start] <= 0xFF):
            start -= 1
        start += 1
        if end - start < 2:
            continue   # no name before this marker — spurious match

        # Count 0x81 0x00 separator pairs before the marker.
        # Each separator begins a new player slot, so:
        #   0 separators before marker → local player is PlayerID 1 (index 0)
        #   1 separator  before marker → local player is PlayerID 2 (index 1)
        sep_count = sum(
            1 for i in range(local_pos - 1)
            if raw[i] == 0x81 and raw[i + 1] == 0x00
        )
        return sep_count

    return None


def find_human_index(players, streams, configured_name=''):
    """
    Return the 0-based index into players[] for the local (human) player.

    Detection order:
    1. configured_name match — highest priority when set. Handles replays recorded
       by the opponent (where the 0x06 marker points to their slot, not yours).
    2. Initdata 0x06 marker  — correct for replays you saved yourself.
    3. MMR presence          — in vs-AI replays the human has MMR, the AI does not.
    4. Default to 0          — last resort.
    """
    # 1. Name match — always try first when a name is configured
    if configured_name:
        name_lower = configured_name.strip().lower()
        initdata_names = parse_initdata_names(streams)
        for i, name in enumerate(initdata_names):
            if i >= len(players):
                break
            if name.lower().startswith(name_lower) or name_lower.startswith(name.lower()):
                return i
        # Name not matched — warn and fall through
        print(f"   ⚠️  PLAYER_NAME '{configured_name}' not found in {initdata_names} — trying other methods")

    # 2. Local-player marker (correct when you saved the replay yourself)
    idx = find_local_player_index(streams)
    if idx is not None and idx < len(players):
        return idx

    # 3. MMR presence (vs AI: exactly one player has MMR)
    mmr_indices = [i for i, pl in enumerate(players) if 'MMR' in pl]
    if len(mmr_indices) == 1:
        return mmr_indices[0]

    return 0


def is_vs_ai(players, streams=None):
    """
    Return True if the opponent is an AI (computer player).

    Priority:
    1. If initdata names are available (via streams), check for 'A.I.' in any name.
       This is definitive — AI player names always contain 'A.I.'.
    2. Fall back to MMR absence only when names are unavailable.
       NOTE: Some unranked human players also lack MMR, so this can false-positive;
       the name check above prevents that when streams are provided.
    """
    if len(players) < 2:
        return False

    # 1. Name-based check (most reliable)
    if streams is not None:
        try:
            names = parse_initdata_names(streams)
            if any('A.I.' in name or 'A.I ' in name for name in names):
                return True
            # Both players have real non-AI names → definitely not vs AI
            if len(names) >= 2 and all(name.strip() for name in names):
                return False
        except Exception:
            pass

    # 2. MMR-absence fallback (less reliable for unranked human opponents)
    for p in players:
        if 'MMR' not in p:
            return True
    return False


def get_ai_difficulty(players):
    """
    Estimate AI difficulty from the opponent (AI) player's APM.
    Finds the AI player as the one without an MMR field.
    Easy ≈ 50 | Medium ≈ 80 | Hard ≈ 100–141 | Very Hard ≈ 180 | Elite ≈ 200+
    """
    # Find the AI player (no MMR field)
    p_ai = next((p for p in players if 'MMR' not in p), None)
    if p_ai is None:
        return 'Hard'   # fallback if no AI found

    # Try name field first (some replay versions include difficulty in name)
    name = str(p_ai.get('name', ''))
    for level in ('Very Hard', 'VeryHard', 'Hard', 'Medium', 'Easy', 'Insane', 'Elite'):
        if level.lower().replace(' ', '') in name.lower().replace(' ', ''):
            return level.replace('VeryHard', 'Very Hard')

    # Fall back to APM estimate
    apm = int(p_ai.get('APM', 141))
    if apm <= 60:  return 'Easy'
    if apm <= 100: return 'Medium'
    if apm <= 160: return 'Hard'
    if apm <= 200: return 'Very Hard'
    return 'Elite'


# ── Shared data extraction ────────────────────────────────────────────────────

def _get_remote_player_name(streams):
    """
    Fallback: scan initdata streams for the first slot with a 0x02 (remote) marker,
    returning its name decoded as UTF-8. Used when the opponent has a non-ASCII name
    that the main slot parser couldn't pair with Mizo's slot.
    """
    EXCLUDED = {'terran', 'zerg', 'protoss', 'random', 'starcraft',
                'dflt', 'dfltq', 'comp', 'open', 'rewa', 'part',
                'unknown', 'human', 'computer'}
    for raw in streams.values():
        if b'"Title"' in raw or len(raw) > 20000:
            continue
        for i in range(len(raw) - 2):
            if raw[i] == 0x01 and raw[i+1] == 0x00 and raw[i+2] == 0x02:
                # Walk back collecting UTF-8 / printable bytes
                end, start = i, i - 1
                while start >= 0 and (0x21 <= raw[start] <= 0x7e or 0x80 <= raw[start] <= 0xFF):
                    start -= 1
                start += 1
                if end - start < 2:
                    continue
                try:
                    name = raw[start:end].decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        name = raw[start:end].decode('latin-1')
                    except Exception:
                        continue
                if not name or not name[0].isalpha():
                    continue
                if any(name.lower().startswith(e) for e in EXCLUDED):
                    continue
                return name
    return None


def _extract_core(replay_path, player_name=''):
    """
    Parse a replay and return a dict of all extracted data.
    player_name: your in-game name (e.g. 'Mizo') — used to identify which
                 player in the metadata is you, regardless of PlayerID order.
    Returns None on failure.
    """
    with open(replay_path, 'rb') as f:
        data = f.read()

    streams = extract_streams(data)
    if not streams:
        print("ERROR: Could not decompress any streams.")
        return None

    meta = parse_metadata(streams)
    if not meta:
        print("ERROR: Metadata not found.")
        return None

    players = meta.get('Players', [])
    if not players:
        print("ERROR: No player data.")
        return None

    from datetime import datetime as _dt
    _mtime      = os.path.getmtime(replay_path)
    _game_dt    = _dt.fromtimestamp(_mtime)
    game_date   = _game_dt.strftime('%Y-%m-%d')
    game_time   = _game_dt.strftime('%H-%M')   # HH-MM — safe for filenames on all OSes

    dur_game_sec = meta.get('Duration', 0)
    dur_real_sec = dur_game_sec / 1.4
    dur_str      = fmt_time(dur_real_sec)
    dur_game_min = int(dur_game_sec // 60)

    p_human_idx = find_human_index(players, streams, player_name)
    p_opp_idx   = 1 - p_human_idx  # works for 1v1; falls back gracefully

    p_human = players[p_human_idx]
    p_opp   = players[p_opp_idx] if len(players) > p_opp_idx else {}

    human_race = RACE_MAP.get(p_human.get('AssignedRace', ''), '?')
    opp_race   = RACE_MAP.get(p_opp.get('AssignedRace',   ''), '?')
    result     = p_human.get('Result', '?')
    mmr        = p_human.get('MMR', 'N/A')
    apm        = int(p_human.get('APM', 0))
    opp_mmr    = p_opp.get('MMR', 'N/A')
    opp_apm    = int(p_opp.get('APM', 0))
    matchup    = f"{MATCHUP_CODE.get(human_race,'?')}v{MATCHUP_CODE.get(opp_race,'?')}"

    # Use initdata-ordered names (same order as Players[]) for display
    initdata_names = parse_initdata_names(streams)
    display_name_human = initdata_names[p_human_idx] if p_human_idx < len(initdata_names) else (player_name or 'Unknown')

    if p_opp_idx < len(initdata_names):
        display_name_opp = initdata_names[p_opp_idx]
    elif 'MMR' not in p_opp:
        display_name_opp = 'A.I.'
    else:
        # Opponent name may contain non-ASCII characters (e.g. accented letters).
        # Scan the initdata stream directly for any slot whose marker is 0x02 (remote).
        display_name_opp = _get_remote_player_name(streams) or 'Unknown'

    tracker  = streams[max(streams, key=lambda k: len(streams[k]))]
    events   = parse_unit_events(tracker, dur_real_sec, meta)

    # Build per-player event sets.
    # For the opponent counter we also include None-player_id events whose unit type
    # belongs exclusively to the opponent's race — this recovers morphed units
    # (HellionTank, OrbitalCommand, Lair, etc.) whose player byte we can't always decode.
    # Safe for TvZ/TvP/ZvP; in ZvZ shared Zerg units with None are excluded so no bleed.
    opp_player_id   = p_opp_idx + 1
    human_player_id = p_human_idx + 1

    opp_race_units   = set(
        {'Terran': TERRAN_UNITS + TERRAN_STRUCTS,
         'Zerg':   ZERG_UNITS   + ZERG_STRUCTS,
         'Protoss':PROTOSS_UNITS + PROTOSS_STRUCTS}.get(opp_race, [])
    )
    human_race_units = set(
        {'Terran': TERRAN_UNITS + TERRAN_STRUCTS,
         'Zerg':   ZERG_UNITS   + ZERG_STRUCTS,
         'Protoss':PROTOSS_UNITS + PROTOSS_STRUCTS}.get(human_race, [])
    )
    # Units that can only belong to the opponent (not shared with human's race)
    exclusive_opp = opp_race_units - human_race_units

    opp_events   = [e for e in events
                    if e.get('player_id') == opp_player_id
                    or (e.get('player_id') is None and e['unit'] in exclusive_opp)]
    human_events = [e for e in events if e.get('player_id') == human_player_id]

    opp_counter   = Counter(e['unit'] for e in opp_events)
    human_counter = Counter(e['unit'] for e in human_events)

    enemy_build          = detect_enemy_build(opp_counter, opp_race)
    opp_units, opp_strs = summarise_army(opp_counter, opp_race)

    # Human (Mizo) build detection — Zerg only
    if human_race == 'Zerg':
        # Get structure completion timings for build-order signals
        my_struct_times = {}
        try:
            _protocol = _load_protocol(meta)
            if _protocol:
                _t_evts = list(_protocol.decode_replay_tracker_events(tracker))
                for _e in sorted(_t_evts, key=lambda x: x['_gameloop']):
                    if _e['_event'] == 'NNet.Replay.Tracker.SUnitInitEvent':
                        if _e.get('m_upkeepPlayerId') != human_player_id:
                            continue
                        _name = _e.get('m_unitTypeName', b'').decode()
                        if _name not in my_struct_times:
                            my_struct_times[_name] = _e['_gameloop'] / 22.4
        except Exception:
            pass

        my_build = detect_my_build(human_counter, my_struct_times, matchup)
        reaction_correct, reaction_note = evaluate_reaction(
            enemy_build, my_build, matchup,
            p_human.get('Result', '?')
        )
    else:
        my_build          = ''
        reaction_correct  = None
        reaction_note     = ''

    # Zerg milestones — filtered to human player's drones only (fixes ZvZ double-count)
    ms          = detect_zerg_milestones(human_events, tracker, meta, human_player_id) if human_race == 'Zerg' else {}
    my_units, _ = summarise_army(human_counter, human_race) if human_race == 'Zerg' else ({}, {})

    # Creep tumor count — CreepTumor born events are reliably player-attributed
    creep_tumors      = sum(1 for e in human_events if e['unit'] == 'CreepTumor')
    creep_tumors_pm   = round(creep_tumors / (dur_real_sec / 60), 1) if dur_real_sec > 0 else 0
    struct_ms  = detect_structure_milestones(human_events, events, opp_race) if human_race == 'Zerg' else {}
    upgrade_ms = detect_upgrade_milestones(tracker, dur_real_sec, human_player_id, meta) if human_race == 'Zerg' else {}

    # Inject rate — queen inject casts from game events (Zerg only)
    if human_race == 'Zerg':
        hatch_times_for_inject = sorted(
            [e['real_sec'] for e in human_events if e['unit'] == 'Hatchery']
        )
        inject_data = detect_inject_rate(
            streams, meta, hatch_times_for_inject, dur_real_sec,
            human_player_uid=p_human_idx   # 0-indexed user id
        )
    else:
        inject_data = {'inject_count': None, 'inject_per_min': None, 'inject_rating': None}

    # Supply block detection — works for any race, uses player-tagged events
    supply_block_count, supply_block_times = detect_supply_blocks(
        events, human_race, human_player_id
    )

    return {
        'ms': ms, 'my_units': my_units,
        'struct_ms': struct_ms, 'upgrade_ms': upgrade_ms,
        'dur_real_sec': dur_real_sec, 'dur_str': dur_str, 'dur_game_min': dur_game_min,
        'human_race': human_race, 'opp_race': opp_race,
        'result': result, 'mmr': mmr, 'apm': apm,
        'opp_mmr': opp_mmr, 'opp_apm': opp_apm,
        'matchup': matchup,
        'player_name': display_name_human, 'opp_name': display_name_opp,
        'enemy_build': enemy_build,
        'my_build':    my_build,
        'reaction_correct': reaction_correct,
        'reaction_note':    reaction_note,
        'opp_units': opp_units, 'opp_strs': opp_strs,
        'supply_block_count': supply_block_count,
        'supply_block_times': supply_block_times,
        'creep_tumors':       creep_tumors,
        'creep_tumors_pm':    creep_tumors_pm,
        'inject_count':       inject_data['inject_count'],
        'inject_per_min':     inject_data['inject_per_min'],
        'inject_rating':      inject_data['inject_rating'],
        'events': events,
        'human_events': human_events,
        'counter': human_counter,
        'map_name': meta.get('Title', 'Unknown'),
        'game_version': meta.get('GameVersion', '?'),
        'today':        game_date,
        'game_time':    game_time,
        'vs_ai': is_vs_ai(players, streams),
        'ai_difficulty': get_ai_difficulty(players),
    }


# ── Practice Run (vs AI) file generator ──────────────────────────────────────

def write_practice_run(d, practice_dir, coaching=None):
    """
    Write a drill-format .md file to Practice Runs/.
    Uses the same YAML schema as Macro Drill template:
      type, date, drones40, drones55, drones66, drones80, maxsupply, score, notes
    """
    ms           = d['ms']
    human_race   = d['human_race']
    map_name     = d['map_name']
    dur_str      = d['dur_str']
    dur_game_min = d['dur_game_min']
    today        = d['today']
    game_time    = d['game_time']
    apm          = d['apm']
    result       = d['result']
    diff         = d['ai_difficulty']
    matchup      = d['matchup']
    player_name  = d['player_name']

    def ms_str(t):
        """Return M:SS timing or blank string for YAML (not 'N/A')."""
        return fmt_time(t) if t is not None else ''

    drones40_str = ms_str(ms.get(40)) if human_race == 'Zerg' else ''
    drones55_str = ms_str(ms.get(55)) if human_race == 'Zerg' else ''
    drones66_str = ms_str(ms.get(66)) if human_race == 'Zerg' else ''
    drones80_str = ms_str(ms.get(80)) if human_race == 'Zerg' else ''
    maxsupply_str = ms_str(d['struct_ms'].get('max_supply')) if human_race == 'Zerg' else ''

    sb_count = d['supply_block_count']
    sb_times = d['supply_block_times']
    sb_str   = str(sb_count)
    sb_note  = (f"Supply blocks ×{sb_count}: "
                + ', '.join(fmt_time(t) for t in sb_times)
                if sb_count else "No supply blocks detected")

    # Build a short notes line of drone milestones for the notes field
    if human_race == 'Zerg':
        notes_auto = (
            f"66d={fmt_time(ms.get(66))} "
            f"80d={fmt_time(ms.get(80))} "
            f"apm={apm}"
        )
    else:
        notes_auto = f"apm={apm} result={result}"

    # Zerg stats body section
    if human_race == 'Zerg':
        zerg_body = f"""
### Drone Milestones
- 40 drones: {fmt_time(ms.get(40))}
- 55 drones: {fmt_time(ms.get(55))}
- 66 drones: {fmt_time(ms.get(66))}
- 80 drones: {fmt_time(ms.get(80))}
- {sb_note}
- Creep tumors: {d['creep_tumors']} ({d['creep_tumors_pm']}/min)
{'- Injects: ' + str(d['inject_count']) + ' (' + str(d['inject_per_min']) + '/min) — ' + str(d['inject_rating']) + '% of 3-hatch cycle' if d['inject_count'] is not None else '- Injects: ⚠️ not detected — install s2protocol (pip install s2protocol --no-deps)'}
- 3rd hatchery: {fmt_time(d['struct_ms'].get('hatch3'))}
- 4th hatchery: {fmt_time(d['struct_ms'].get('hatch4'))}
- Lair: {fmt_time(d['struct_ms'].get('lair'))}
- Hive: {fmt_time(d['struct_ms'].get('hive'))}
- Max supply (200 cap): {fmt_time(d['struct_ms'].get('max_supply'))}
- +1 attack: {fmt_time(d['upgrade_ms'].get('atk1'))}
- +1 armour: {fmt_time(d['upgrade_ms'].get('armor1'))}
- +2 attack: {fmt_time(d['upgrade_ms'].get('atk2'))}
- +2 armour: {fmt_time(d['upgrade_ms'].get('armor2'))}
> ℹ️ *Drone counts = drones simultaneously alive (deaths subtracted). Timings exact via s2protocol.*
"""
    else:
        zerg_body = f"\n> ⚠️ *Played as {human_race} — Zerg drone fields left blank.*\n"

    # Opponent AI army
    opp_units, opp_strs = d['opp_units'], d['opp_strs']
    unit_lines   = '\n'.join(f"- {u} × {n}" for u, n in sorted(opp_units.items(), key=lambda x: -x[1])) or "- (none)"
    struct_lines = '\n'.join(f"- {u} × {n}" for u, n in sorted(opp_strs.items(),  key=lambda x: -x[1])) or "- (none)"

    # AI coaching sections
    if coaching:
        problems_md = '\n'.join(f"- {p}" for p in coaching.get('problems', ['-'])) or '-'
        focus_md    = '\n'.join(f"- {f}" for f in coaching.get('focus',    ['-'])) or '-'
        coached_note = "\n> 🤖 *Auto-generated by Claude — verify against your replay.*\n"
    else:
        problems_md = '-'
        focus_md    = '-'
        coached_note = ''

    md = f"""---
type: drill
date: {today}
map: "{map_name}"
matchup: {matchup}
vs: "A.I. {diff}"
result: {result}

drones40: {drones40_str}
drones55: {drones55_str}
drones66: {drones66_str}
drones80: {drones80_str}

hatch3: {ms_str(d['struct_ms'].get('hatch3'))}
hatch4: {ms_str(d['struct_ms'].get('hatch4'))}
lair: {ms_str(d['struct_ms'].get('lair'))}
hive: {ms_str(d['struct_ms'].get('hive'))}
atk1: {ms_str(d['upgrade_ms'].get('atk1'))}
armor1: {ms_str(d['upgrade_ms'].get('armor1'))}

maxsupply: {maxsupply_str}
supplyblocks: {sb_str}
creeptumors: {d['creep_tumors'] if human_race == 'Zerg' else ''}
injectcount: {d['inject_count'] if human_race == 'Zerg' and d['inject_count'] is not None else ''}
injectpm: {d['inject_per_min'] if human_race == 'Zerg' and d['inject_per_min'] is not None else ''}
injectrating: {d['inject_rating'] if human_race == 'Zerg' and d['inject_rating'] is not None else ''}
my_build: "{d.get('my_build', '')}"
enemy_build: "{d.get('enemy_build', '')}"
score:
notes: "{notes_auto}"

apm: {apm}
duration: "{dur_str}"
tags: [drill, vs-ai, auto-generated]
---

# Practice Run vs A.I. {diff}

**Player:** {player_name} ({human_race}) — **{result}** | APM: {apm}
**Opponent:** A.I. {diff} ({d['opp_race']}) | APM: {d['opp_apm']}
**Map:** {map_name}
**Duration:** {dur_str}

---
{zerg_body}
---

# AI Build Used

**AI Build:** {d['enemy_build']}
**Your Build:** {d.get('my_build','') or '—'}

### Units
{unit_lines}

### Structures
{struct_lines}

---
{coached_note}
# Problems Encountered

{problems_md}

# Focus Next Run

{focus_md}
"""

    filename = f"Drill {today} {game_time} vs AI {diff}.md"
    os.makedirs(practice_dir, exist_ok=True)
    out_path = unique_path(practice_dir, filename)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(md)
    return out_path


# ── Ladder Game file generator ────────────────────────────────────────────────

def write_ladder_game(d, ladder_dir, coaching=None):
    """
    Write a ladder-game-format .md file to Ladder Games/.
    """
    ms           = d['ms']
    human_race   = d['human_race']
    matchup      = d['matchup']
    today        = d['today']
    game_time    = d['game_time']
    map_name     = d['map_name']
    game_version = d['game_version']
    dur_str      = d['dur_str']
    dur_game_min = d['dur_game_min']
    player_name  = d['player_name']
    opp_name     = d['opp_name']
    result       = d['result']
    mmr, apm     = d['mmr'], d['apm']
    opp_mmr_raw  = d['opp_mmr']
    opp_mmr      = opp_mmr_raw if (isinstance(opp_mmr_raw, (int, float)) and opp_mmr_raw > 0) else ''
    opp_apm      = d['opp_apm']
    enemy_build  = d['enemy_build']
    my_build     = d.get('my_build', '')
    reaction_correct = d.get('reaction_correct')   # True / False / None
    reaction_note    = d.get('reaction_note', '')

    # Build the counter-guide section
    guide = get_counter_guide(enemy_build)
    if guide and human_race == 'Zerg':
        timings_md   = '\n'.join(f"- {t}" for t in guide['key_timings'])
        units_md     = '\n'.join(f"- {u}" for u in guide['key_units'])
        mistakes_md2 = '\n'.join(f"- {m}" for m in guide['mistakes'])
        tips_md      = '\n'.join(f"- {t}" for t in guide['tips'])

        atk = guide.get('attack_timing', {})
        if atk:
            atk_lines_md = '\n'.join(f"- {l}" for l in atk.get('lines', []))
            attack_section = f"""
### Best Attack Timing vs {enemy_build}

**Window:** {atk.get('window', 'N/A')}

**Army needed:** {atk.get('setup', 'N/A')}

{atk_lines_md}
"""
        else:
            attack_section = ''

        counter_section = f"""
# Recommended Counter vs {enemy_build}

**Ideal composition:** {guide['target_comp']}

**Build order:** {guide['opener']}

### Key Timings
{timings_md}

### Key Units and Why
{units_md}
{attack_section}
### Common Mistakes to Avoid
{mistakes_md2}

### Tips
{tips_md}

---
"""
    else:
        counter_section = ''

    # YAML booleans / strings for front-matter
    rc_yaml = ('true' if reaction_correct is True
               else 'false' if reaction_correct is False
               else '')

    def ms_str(t):
        return fmt_time(t) if t is not None else ''

    drones40_str  = ms_str(ms.get(40)) if human_race == 'Zerg' else ''
    drones55_str  = ms_str(ms.get(55)) if human_race == 'Zerg' else ''
    drones66_str  = ms_str(ms.get(66)) if human_race == 'Zerg' else ''
    drones80_str  = ms_str(ms.get(80)) if human_race == 'Zerg' else ''
    maxsupply_str = ms_str(d['struct_ms'].get('max_supply')) if human_race == 'Zerg' else ''

    sb_count = d['supply_block_count']
    sb_times = d['supply_block_times']
    sb_str   = str(sb_count)
    sb_note  = (f"Supply blocks ×{sb_count}: "
                + ', '.join(fmt_time(t) for t in sb_times)
                if sb_count else "No supply blocks detected")

    zerg_section = ''
    if human_race == 'Zerg':
        queens  = sum(1 for e in d['human_events'] if e['unit'] == 'Queen')
        hatches = sum(1 for e in d['human_events'] if e['unit'] == 'Hatchery')
        lairs   = 1 if d['struct_ms'].get('lair')  is not None else 0
        hives   = 1 if d['struct_ms'].get('hive')  is not None else 0
        army_str = ', '.join(
            f"{u} ×{n}"
            for u, n in sorted(d['my_units'].items(), key=lambda x: -x[1])
            if u not in ('Drone', 'Overlord', 'Queen', 'OverlordCocoon', 'Overseer')
        ) or "—"
        zerg_section = f"""
### Your Zerg Stats
- 40 drones: {fmt_time(ms.get(40))}
- 55 drones: {fmt_time(ms.get(55))}
- 66 drones: {fmt_time(ms.get(66))}
- 80 drones: {fmt_time(ms.get(80))}
- {sb_note}
- Creep tumors: {d['creep_tumors']} ({d['creep_tumors_pm']}/min)
{'- Injects: ' + str(d['inject_count']) + ' (' + str(d['inject_per_min']) + '/min) — ' + str(d['inject_rating']) + '% of 3-hatch cycle' if d['inject_count'] is not None else '- Injects: ⚠️ not detected — install s2protocol (pip install s2protocol --no-deps)'}
- Queens built: {queens}
- Hatcheries: {hatches} | Lairs: {lairs} | Hives: {hives}
- 3rd hatchery: {fmt_time(d['struct_ms'].get('hatch3'))}
- 4th hatchery: {fmt_time(d['struct_ms'].get('hatch4'))}
- Lair: {fmt_time(d['struct_ms'].get('lair'))} | Hive: {fmt_time(d['struct_ms'].get('hive'))}
- Max supply (200 cap): {fmt_time(d['struct_ms'].get('max_supply'))}
- +1/+1 upgrades: atk={fmt_time(d['upgrade_ms'].get('atk1'))} armour={fmt_time(d['upgrade_ms'].get('armor1'))}
- Combat units: {army_str}
> ℹ️ *Drone counts = drones simultaneously alive (deaths subtracted). Timings exact via s2protocol.*

---
"""

    opp_units, opp_strs = d['opp_units'], d['opp_strs']
    unit_lines   = '\n'.join(f"- {u} × {n}" for u, n in sorted(opp_units.items(), key=lambda x: -x[1])) or "- (none detected)"
    struct_lines = '\n'.join(f"- {u} × {n}" for u, n in sorted(opp_strs.items(),  key=lambda x: -x[1])) or "- (none detected)"
    non_zerg_note = (
        f"\n> ⚠️ *{matchup} — vault tracks Zerg. Zerg fields left blank.*\n"
        if human_race != 'Zerg' else ''
    )

    # AI coaching sections
    if coaching:
        mistakes_md    = '\n'.join(f"- {m}" for m in coaching.get('mistakes',    ['-'])) or '-'
        lessons_md     = '\n'.join(f"- {l}" for l in coaching.get('lessons',     ['-'])) or '-'
        next_focus_md  = '\n'.join(f"- {f}" for f in coaching.get('next_focus',  ['-'])) or '-'
        coached_note   = "\n> 🤖 *Auto-generated by Claude — verify against your replay.*\n"
    else:
        mistakes_md   = '-'
        lessons_md    = '-'
        next_focus_md = '-'
        coached_note  = ''

    md = f"""---
date: {today}
matchup: {matchup}
result: {result}
map: "{map_name}"

enemy_build: "{enemy_build}"
my_build: "{my_build}"
build_detected: {rc_yaml}
reaction_correct: {rc_yaml}

drones40: {drones40_str}
drones55: {drones55_str}
drones66: {drones66_str}
drones80: {drones80_str}
maxsupply: {maxsupply_str}

supplyblocks: {sb_str}
injectrating: {d['inject_rating'] if human_race == 'Zerg' and d['inject_rating'] is not None else ''}
injectcount: {d['inject_count'] if human_race == 'Zerg' and d['inject_count'] is not None else ''}
injectpm: {d['inject_per_min'] if human_race == 'Zerg' and d['inject_per_min'] is not None else ''}
creeptumors: {d['creep_tumors'] if human_race == 'Zerg' else ''}
scouting_score:
creepscore:

apm: {apm}
mmr: {mmr}
opp_mmr: {opp_mmr}
duration: "{dur_str}"
game_version: "{game_version}"
tags: [ladder-game, auto-generated]
---

# Game Summary

**Player:** {player_name} ({human_race}) — **{result}** | MMR: {mmr} | APM: {apm}
**Opponent:** {opp_name} ({d['opp_race']}) | MMR: {opp_mmr} | APM: {opp_apm}
**Map:** {map_name}
**Duration:** {dur_str}
{non_zerg_note}
---
{zerg_section}
# Opponent Build Detected

**Build:** {enemy_build}

### Units
{unit_lines}

### Structures
{struct_lines}

---

# Your Build

**Build:** {my_build if my_build else '(non-Zerg or undetected)'}

**Reaction:** {'✅ Correct' if reaction_correct is True else '❌ Suboptimal' if reaction_correct is False else '⚠️ Situational / Review'}

{reaction_note}

---

{counter_section}

{f'''# Key Moments

2:00 scout
4:00 tech read
6:00 first fight

---
''' if d['dur_real_sec'] > 180 else ''}{coached_note}
# Mistakes

{mistakes_md}

---

# Lessons Learned

{lessons_md}

---

# Next Practice Focus

{next_focus_md}
"""

    filename = f"Game {today} {game_time} {matchup}.md"
    os.makedirs(ladder_dir, exist_ok=True)
    out_path = unique_path(ladder_dir, filename)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(md)
    return out_path


# ── Main ─────────────────────────────────────────────────────────────────────

def generate_game_log(replay_path, ladder_dir='Ladder Games', practice_dir='Practice Runs', api_key='', player_name=''):
    """
    Parse a replay and write the appropriate file:
      - vs AI    → practice_dir  (drill format, type: drill)
      - vs Human → ladder_dir    (game log format, type: ladder-game)
    player_name: your in-game name (e.g. 'Mizo') — needed when you are PlayerID 2.
    api_key: if set, coaching notes are auto-generated by Claude.
    Returns the path of the written file, or None on failure.
    """
    print(f"Parsing: {replay_path}")

    # ── s2protocol hard requirement ───────────────────────────────────────────
    # All timing data (drones, structures, upgrades, injects) requires s2protocol.
    # Without it the parser cannot produce accurate data — abort immediately.
    try:
        from s2protocol import versions as _s2v
        _s2_ok = True
    except ImportError:
        print()
        print("  ❌  s2protocol is not installed.")
        print("      All drone, inject, upgrade and structure timings require it.")
        print()
        print("  Fix:")
        print("    1. Open Command Prompt")
        print("    2. Run:  pip install s2protocol --no-deps")
        print("    3. If you see 'No module named imp', follow the patch in SETUP.md Step 2")
        print("    4. Verify:  python -c \"from s2protocol import versions; v = versions.build(95299); print('OK -', v.__name__)\"")
        print()
        return None

    d = _extract_core(replay_path, player_name)
    if d is None:
        return None

    # Fetch coaching notes (always — local rules run for free, API used if key is set)
    coaching = get_coaching_notes(d, api_key)

    if d['vs_ai']:
        out_path = write_practice_run(d, practice_dir, coaching)
        label = f"→ Practice Runs  [vs A.I. {d['ai_difficulty']}]"
    else:
        out_path = write_ladder_game(d, ladder_dir, coaching)
        label = f"→ Ladder Games   [vs {d['opp_name']}]"

    print(f"\n✅ Written: {out_path}  {label}")
    print(f"   {d['player_name']} ({d['human_race']}) | {d['result']} | {d['dur_str']} | MMR {d['mmr']}")
    print(f"   Enemy build: {d['enemy_build']}")
    if d['human_race'] == 'Zerg':
        for target in [40, 55, 66, 80]:
            print(f"   {target} drones → {fmt_time(d['ms'].get(target))}")
        inj = d.get('inject_count')
        ipm = d.get('inject_per_min')
        if inj is not None:
            print(f"   Injects → {inj} ({ipm}/min)")
        else:
            print(f"   Injects → ⚠️  not detected (s2protocol required)")
    return out_path


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 sc2_to_gamelog.py <replay.SC2Replay> [ladder_dir] [practice_dir] [api_key] [player_name]")
        sys.exit(1)
    replay_file   = sys.argv[1]
    ladder_dir    = sys.argv[2] if len(sys.argv) > 2 else 'Ladder Games'
    practice_dir  = sys.argv[3] if len(sys.argv) > 3 else 'Practice Runs'
    api_key       = sys.argv[4] if len(sys.argv) > 4 else os.environ.get('ANTHROPIC_API_KEY', '')
    player_name   = sys.argv[5] if len(sys.argv) > 5 else os.environ.get('SC2_PLAYER_NAME', '')
    if not os.path.exists(replay_file):
        print(f"ERROR: File not found: {replay_file}")
        sys.exit(1)
    generate_game_log(replay_file, ladder_dir, practice_dir, api_key, player_name)
