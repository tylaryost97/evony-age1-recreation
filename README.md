# Age 1 Fidelity Server
Authoritative backend foundation for a mechanically faithful historical recreation. No Evony copyrighted assets are included.

## Run
```bash
python -m pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload
```

## Test
```bash
pytest -q
```

`GAME_DATABASE_URL` selects persistence. SQLite is the zero-setup development store; production should use a transactional server RDBMS before multiplayer deployment.

Historical constants belong only in `game_definitions/`. Unknown historical values must remain `HISTORICAL_VALUE_UNKNOWN` until sourced.

## Architecture foundation verification
As of 2026-09-29, `python -m pytest -q` passes 4 tests covering persistence, duplicate-request concurrency/idempotency, convergence of concurrent callers, and required model-table presence. Development seed data has also been verified after a database reopen and is safe to run repeatedly without duplicating the seeded world.

## Interior city building phase
The City view now persists 34 interior locations: dedicated Town Hall and Walls plus 32 player-selectable general plots. Empty general plots query authoritative construction eligibility. Verified base tables currently include selected early levels; unresolved historical values remain disabled/marked HISTORICAL_VALUE_UNKNOWN. Run `pytest -q` for the fidelity regression suite.

## Dedicated Town Hall
Town Hall now has a dedicated authoritative endpoint and UI. The project target field progression is enforced exactly: 10, 13, 16, 19, 22, 25, 28, 31, 34, 37 exterior plots for TH1–TH10. Tax, rename, and production controls persist server-side. Comfort/Levy and disputed TH3+ prerequisites remain explicitly unfinished rather than guessed. See `GAME_FIDELITY.md` for the historical-source conflict and audit.

## Cottage implementation
Cottage levels 1–10 are configured in `game_definitions/core.json`. Population limit is authoritative derived state: the server sums the capacity of every completed Cottage in the city. Cottage completion/upgrades reconcile `PopulationState` immediately. Current residents do not appear instantly merely because housing was added; the historical population tick system remains a separate population-system phase.

Run `pytest -q` to execute the full suite, including mixed Cottage count/level, prerequisite, Level 10 item, completion propagation, and population-bound tests.

### Warehouse implementation
Warehouse levels 1–10, multiple-Warehouse capacity stacking, persistent Food/Lumber/Stone/Iron allocation, Stockpile capacity effects, Privateering protection reduction, Level 10 Michelangelo's Script consumption, and transactional player-city plunder protection are implemented. Gold is never warehouse-protected. If a victorious army's carrying capacity is below the total exposed resources, resolution currently stops with `HISTORICAL_VALUE_UNKNOWN` rather than inventing the unverified Age I partial-load resource distribution rule.

## Inn implementation
The Inn is a building-specific recruitment interface. Verified Age I rules implemented: levels 1-10, candidate count = Inn level, Cottage Lv2 prerequisite, Level 10 Michelangelo's Script, persistent candidates, hourly refresh metadata, employment fee = hero level × 1,000 gold, and Feasting Hall capacity enforcement. Exact historical candidate RNG is unresolved and intentionally marked `HISTORICAL_VALUE_UNKNOWN`; production refresh will not fabricate heroes until that formula is sourced.


## Feasting Hall
The Feasting Hall endpoint is `/api/players/{player_id}/cities/{city_id}/feasting-hall`.
It exposes persistent hero roster/details, level-derived capacity, loyalty, experience, salary rate, mayor state, march state, and captured state.
Mayor appointment/removal and hero dismissal/release are server mutations with idempotency keys.

Verified mayor formulas are centralized in the service layer:
- Politics: production multiplier `1 + Politics/100`; construction time `base * 0.995^Politics`.
- Attack: troop training time `base * 0.995^Attack`.
- Intelligence: research time `base * 0.995^Intelligence`.
Construction now snapshots the Politics effect when a construction/upgrade starts. Barracks/Academy queue creation will use the corresponding helpers when those phases are implemented.

`HISTORICAL_VALUE_UNKNOWN` remains for the exact captured-hero title persuasion gate and for the exact consequence when a city cannot meet hero salary. Those behaviors are not guessed.

## Embassy
The Embassy is the authoritative alliance/reinforcement building interface. Level 1 enables alliance applications and allied garrison permission; level 2 enables alliance creation. Embassy level controls simultaneous foreign garrison waves. Foreign allied troops persist in `foreign_garrisons` and retain owner/source/army/hero/troop identity; they are never merged into the host city's native `troop_quantities`.

The host can send a garrison home and its owner can recall it; both transition the associated march to RETURNING. Full return travel-time settlement belongs to the later march-timing phase.

The documented host-food upkeep rule is represented, but automatic starvation/forced-return is intentionally unfinished because exact Age I tick sequencing is not yet verified.

## Academy and Age I technology
Research is available only through the Academy interface. `Technology` is player-global persistent research state; `ResearchQueue` is city-scoped persistent timed work. Each Academy can conduct one research at a time, and duplicate attempts are idempotent.

Completed research is shared between cities only when the receiving city's Academy meets the technology's Academy requirement. The documented Age I exception is Construction, whose construction-time reduction applies empire-wide.

Technology calculation hooks now cover resource production, troop/mechanic training, troop attack/defense/life, load, infantry and mounted/mechanic movement, ranged range, Warehouse Stockpile, construction, wall/fortification endurance, machinery repair, Privateering, and Informatics scouting level. Existing construction and Warehouse calculations consume these hooks directly. Combat/march/scout/fortification subsystems that are not yet fully implemented consume the same authoritative helpers when those phases are completed.

Horseback Riding's commonly mirrored research-time table explicitly identifies itself as wrong for Age I. Privateering's complete ten-level timer table also was not corroborated. Those timers remain `HISTORICAL_VALUE_UNKNOWN`; the server refuses to start those research levels rather than inventing timings.

## Rally Spot
Rally Spot is the authoritative army-deployment interface. Level N permits N simultaneous outgoing waves and 10,000×N troops per wave (War Ensign: +25%). Dispatch atomically removes selected troops, carried resources, and required march food from the source city and creates persistent `Army` and `March` rows with server timestamps. Recall transitions a force to `RETURNING`; troops/resources are restored only when the return timestamp is reached.

March validation covers source ownership, available troops, hero availability, Attack hero requirement, Rally Spot wave/troop capacity, destination existence and mission legality, cargo load, Logistics, food, camp time, and allied/own restrictions for Reinforce/Transport. Travel uses the slowest selected troop, Compass for infantry, Horseback Riding for mounted/mechanical troops, and sending-city Relief Station multipliers for own/allied-city Reinforce/Transport travel.

Exercise remains intentionally non-authoritative until the exact Age I battle-round resolver is implemented; historical Exercise used the player's own research for both hypothetical armies. Medic Camp wounded state is persistent, but healing is blocked while exact Age I gold costs/wounded formula remain unverified.

## Barracks
Barracks is the only troop-recruitment interface. Multiple Barracks are legal and every Barracks owns its own sequential training queue; its level is also its maximum queued-batch count. Troop definitions contain Barracks/technology gates, four-resource cost, population, base time, life, attack, defense, load, Age I food upkeep, speed, and range for all 12 troop types.

Starting training atomically consumes real resources and idle/total population. Duration is snapshotted from the Age I formula `BaseTime × quantity × 0.9^MilitaryScience × 0.995^MayorAttack`. Queues persist by server timestamps, advance sequentially while offline, and completed batches enter the city's authoritative `TroopQuantity`. Idempotency keys prevent duplicate requests from double-spending or duplicating units.

## Building phases: Beacon Tower through Demolition
Implemented and fidelity-gated sequentially:
- Beacon Tower: Lv1-10 incoming-march intelligence disclosure.
- Forge: Lv1-10 and matching Military Science / Workshop dependencies.
- Stable: Lv1-10 and matching Horseback Riding / Relief Station dependencies; no fabricated cavalry training bonus.
- Workshop: Lv1-10 and matching Metal Casting / Walls dependencies.
- Relief Station: Lv1-10, matching HBR prerequisite, sending-city 2x/3x/4x/5x/6x support travel multipliers.
- Walls: Lv1-10 durability/space, fortification queues, five Age I fortification types, Construction/Politics, Engineering, Machinery and Archer Tower range integration.
- Demolition: timed one-level labor downgrade and immediate Dynamite removal for normal buildings.

Known fidelity boundary: complete Dynamite removal of the dedicated Walls is not sufficiently verified and is blocked as `HISTORICAL_VALUE_UNKNOWN`. Full battle-round casualty resolution is still a later phase; Wall defensive stats/hooks are authoritative but not presented as a completed battle simulator.

## Complete City Exterior / Resource Fields
The City Exterior now renders the full normal project field footprint, with Town Hall-gated plots visibly locked. Every unlocked field is independently player-selectable as Farm, Sawmill, Quarry, or Iron Mine; no balancing rule exists. All four have Lv1-10 historical cost/time/labor/output/capacity tables and Lv10 Michelangelo's Script requirements.

Production is server-authoritative and timestamp based. `ResourceProduction.last_calculated_at` and a fractional remainder accumulate elapsed production across offline time. Rates incorporate Town Hall production percentages/labor, effective Agriculture/Lumbering/Masonry/Mining, current Mayor Politics, city-owned valley bonuses, and persistent 24-hour/7-day Produce-item buffs. Capacity is derived from completed fields of the matching resource and halts passive accumulation at the cap. Production state is settled before rate-changing mutations so new bonuses are not applied retroactively.

## Authoritative economy
`settle_economy()` is the single elapsed-time economy settlement path. It advances resource production/upkeep, six-minute tax/loyalty/population ticks, hero salaries, population roles, capacities and authoritative city mirrors. City payloads settle before rendering; spending/training/marching/market and hero-salary boundaries settle before mutation. Concurrent stale requests cannot claim the same elapsed interval twice.

Set `DEVELOPMENT_MODE=1` to expose the Economy Debug button/API. Production totals, tax, population and food shown by the normal UI come from server state; the browser does not synthesize resource totals.

## Hero system
Heroes originate in the Inn and occupy Feasting Hall capacity. Feasting Hall now exposes View, Mayor, Dismiss/Release/Persuade, level upgrades, loyalty rewards, supported Age I items, rename and safe redistribution. Hero attributes feed production/construction, training, research, scouting inputs and verified combat attack calculations. Army/March state prevents a hero from leading incompatible simultaneous marches.

## Persistent world map
The map is a server-backed 800×800 coordinate world. Viewports return a complete coordinate matrix, with persisted Player Cities, NPC Cities, Flats and typed Valleys overlaid at their coordinates. Home, X/Y Go, arrow/drag pan, current-coordinate display and persistent per-player bookmarks are implemented. Each rendered tile has its own world-coordinate hitbox, so hit testing does not depend on viewport pixel position.

Custom server rule: NPC world-generation density target is twice the baseline/historical distribution (`CUSTOM_SERVER_RULE: DOUBLE NPC DENSITY`). This is intentionally non-historical and is recorded in `GAME_FIDELITY.md`.

## Age I valleys and flats
Wilderness is persistent world state, not a collectible-node system. Grassland, Swamp, Lake, Hill, Desert and Forest levels 1–10 provide their historical percentage bonus to the owning city's base production. Flats provide no production bonus. Valleys and Flats share the city's Town Hall-level ownership quota, have persistent defenders, can be scouted, conquered after battle victory, camp the winning army, and can be abandoned.

A conquered Flat can found a city when the player's title permits another city and the source city supplies 250 Workers plus 10,000 each Food/Lumber/Stone/Iron. The founding Flat level is stored. Abandoning that later non-last city converts its coordinate into an NPC of the same level. The custom doubled baseline NPC-density rule remains documented separately.

## Authoritative march engine
Marches are persistent server objects backed by an Army and MarchMission. The server owns departure, arrival, return, recall and one-shot arrival resolution. Rally Spot level controls simultaneous waves and per-wave troop limits. Map/Rally Spot read the same authoritative march state. Scout/Transport/Reinforce and undefended wilderness occupation resolve fully at arrival. Hostile arrivals with defenders create exactly one persistent Battle handoff; casualties/outcome are intentionally deferred to the dedicated Age-I combat resolver rather than fabricated.

## Dedicated combat engine
`app/combat.py` is a pure deterministic Age-I battle domain module. Call `simulateBattle(input, ruleset)` (or Python alias `simulate_battle`) with troop definitions and attacker/defender state. `BattleResult` includes winner/reason, opening distance, complete round-by-round movement/attack/casualty events, initial armies, survivors, losses, fortification survivors, plunder slot, honor/prestige slots and explicit uncertainty flags. Disputed historical behavior is represented by `Age1CombatRules`, never hidden in UI code.

## Defensive fortifications
All Age I fortified units are constructed from the Walls interface: Trap, Abatis, Archer Tower, Rolling Log and Defensive Trebuchet. Wall level supplies fortified-space capacity; queued construction reserves that capacity immediately. Costs, prerequisites, build times, range/effects and combat metadata are centralized in `game_definitions/core.json`. The pure combat engine consumes fortification stacks directly; no UI code calculates combat.

## NPC / barbarian city gameplay
NPC cities are persistent mutable world actors, not loot buttons. Levels 1–10 use centralized Age I resource/troop/fortification maxima. Resources regenerate over eight hours; defenders regenerate 10% of maximum per six-minute tick. Scout and Attack are real marches. Attack arrival executes the dedicated combat engine exactly once, persists rounds/reports, mutates NPC survivors/resources, loads plunder into the returning army, and starts a return march. The custom doubled NPC density does not scale NPC strength.

## Persistent reports
Battle, Scout, Transport, Reinforcement and System reports are persistent server records. Event resolvers create immutable report snapshots; the browser only renders those payloads. Reading marks a report read, while deletion is a server-side soft delete. Scout disclosure is calculated on the server from Informatics, Beacon Tower, target level and scout-party size; uncertain hero-Intelligence weighting is not fabricated.

## Persistent mail
Player mail provides Inbox, Sent, Compose, Reply, Delete, recipient lookup and read/unread status. Sends are server-authoritative and idempotent. A sliding server-side limit permits at most 10 player mails/minute and 5/minute to one recipient. System mail can only be created through the internal service adapter and does not replace specialized Battle/Scout/Transport/Reinforcement reports.

## Alliance system
Persistent alliances support creation through the Embassy, applications, invitations, rank-authorized personnel management, Host transfer, member lists, information, alliance chat, alliance mail and diplomacy. Rank names are backed by server-enforced permission records. Alliance relationship feeds map and march legality; Embassy reinforcement remains limited by its own garrison rules.

## Multiplayer chat
Persistent World, Alliance and Whisper channels are server-authoritative. Alliance membership is checked at send and read time. Chat updates incrementally every 1.5 seconds using persisted message IDs. Blocking, muting, server-side rate limits and auditable moderation actions are project safety/server rules; they are not represented as recovered historical Age I constants.

## Data-driven quests
Routine quests are defined in `game_definitions/quests.json`. Completion is evaluated from authoritative player/city state; military-action objectives use server-recorded event evidence. Completion and award claiming are separate, and claims are transactional/idempotent. Verified historical rewards are granted exactly as configured; unresolved rewards are explicitly marked `HISTORICAL_VALUE_UNKNOWN` and grant nothing.

## Age I player progression
Player progression uses Prestige, Honor, military Rank and noble Title—there is no replacement player XP level. Promotion requirements are centralized in `game_definitions/progression.json`. Gold and medals are consumed; Town Hall, Rank and Prestige are qualification gates. Title controls the authoritative city cap (Civilian 1 through Prinzessin 10). Promotion previews expose every satisfied/missing requirement and promotion is validated transactionally on the server.

## Multiple cities
Owned cities are independent simulation roots, not skins. Switching the selected city changes the authoritative city/field state used by the interface. Technology knowledge is player-wide but its effective level is city-local through the Academy gate. Founding a city requires an owned conquered Flat, a free Title city slot, 250 Workers, and 10,000 each Food, Lumber, Stone, Iron **and Gold**. Conquest and abandonment enforce city-slot/last-city rules server-side.

## Age I items and timed buffs
`game_definitions/items.json` is the authoritative item catalog. Implemented items have real server effects: queue timestamp reduction, persistent production/hero buffs, city teleportation, population/loyalty effects, hero XP/attributes, demolition, march limits, building requirements and promotion medals. Timed effects store absolute expiration timestamps and therefore survive logout/restart. Same-resource production boosts are mutually exclusive and Napoleon/Archimedes queue applications are persistently one-per-target. Items whose exact effect requires an unresolved random generator (notably Aries Amulet/Wheel and Hero Hunting/Inn generation) are explicitly marked `implemented:false` and cannot be consumed; no fake reward tables are substituted. No monetization requirement is enforced.

## Items, buffs and teleportation
Supported Age I items are centralized in `game_definitions/items.json`; inventory quantities and timed effects are authoritative and persistent. City Teleporter requires a selected Age I state and relocates the city to an available Flat in that state. Advanced City Teleporter requires a specified unoccupied Flat and applies the persistent 24-hour no-march/no-reteleport restriction. Teleporting requires dispatched and garrisoned troops to be home, releases valleys, preserves the city's internal state/queues, and uses an atomic world-tile claim so two cities cannot occupy one coordinate. Existing incoming marches remain targeted to their original coordinates.

## Beginner Protection
Beginner Protection is player-level authoritative state beginning at account creation. It lasts seven days unless any owned city's Town Hall reaches level 5 first. Protected players cannot attack or scout player/NPC cities, and other players cannot attack or scout their cities; wilderness remains militarily accessible. Expiration/loss is persisted with a reason and timestamp and generates one system mail. The HUD displays the server-derived remaining protection time.

## Classic Age I UI fidelity pass
The client preserves the three primary world views while restoring the classic information hierarchy: persistent resources/player status, city chooser, Town/City/Map controls, city overview, operations, quick-access communications and chat. Building plots remain the gateway to building-specific systems; empty plots remain construction entry points. Map tiles use full-tile hitboxes and military map actions now enter the actual Rally Spot with target coordinates/mission prefilled. Responsive layouts retain all major information and reflow it for tablet/mobile rather than deleting controls.
