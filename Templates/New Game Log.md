<%*
const matchup = await tp.system.suggester(
["ZvT","ZvP","ZvZ"],
["ZvT","ZvP","ZvZ"]
)

const result = await tp.system.suggester(
["Win","Loss"],
["Win","Loss"]
)

const map = await tp.system.prompt("Map name")
const enemyBuild = await tp.system.prompt("Enemy build (optional)")
%>

---
date: <% tp.date.now("YYYY-MM-DD") %>
matchup: <% matchup %>
result: <% result %>
map: <% map %>

enemy_build: <% enemyBuild %>
build_detected:
reaction_correct:

drones40:
drones55:
drones66:
drones80:

hatch3:
hatch4:
lair:
hive:
atk1:
armor1:

maxsupply:
supplyblocks:
injectcount:
injectpm:
injectrating:
scouting_score:
creepscore:

tags: [ladder-game]
---

# Game Summary

Opponent strategy:

---

# Key Moments

2:00 scout  
4:00 tech read  
6:00 first fight  

---

# Mistakes

-

---

# Lessons Learned

-

---

# Next Practice Focus

-
