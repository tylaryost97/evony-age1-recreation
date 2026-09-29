# GAME FIDELITY

| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Authoritative state | Server owns gameplay state | Project fidelity requirement | SQL-backed authoritative domain state | Gameplay endpoints not yet implemented | None | Persistence tested |
| Static definitions | Costs/prereqs/formulas/level tables centralized | Project fidelity requirement | `game_definitions/core.json` | Historical tables intentionally empty pending evidence | Historical numeric formulas/tables | Definition boundary established |
| Cities & plots | Age 1 city + exterior field structure | Historical evidence not yet attached to this repository | Persistent city and explicit plot records | Exact plot counts/layout not seeded | `HISTORICAL_VALUE_UNKNOWN` | Schema only |
| Resources/economy | Age 1 resource production/capacity/tax/population | Historical evidence required | Persistent resource/economy fields | Formula evaluation unfinished | All exact formulas | Transaction tests pass |
| Heroes | Age 1 hero stats/XP/assignments | Historical evidence required | Persistent hero model | Exact formulas unfinished | XP/stat formulas | Schema only |
| Troops/training | Age 1 troop types and queues | Historical evidence required | Definition-keyed troop state + timed queue | Historical troop table absent | Costs/stats/times | Idempotent mutation tested |
| Technologies | Age 1 research | Historical evidence required | Definition-keyed levels + timed queue | Historical tech table absent | Costs/prereqs/times | Schema only |
| World map | NPC cities, valleys, flats | Historical evidence required | Persistent coordinates/map tile subtypes | Map generation rules unfinished | Generation/level rules | Seed smoke coverage |
| Marches/armies | Age 1 missions and travel | Historical evidence required | Persistent army/march + server timestamps | Resolution unfinished | Speeds/missions/rules | Schema only |
| Combat | Age 1 battle rounds | Historical evidence required | Battle + round persistence | Simulator unfinished | Combat formulas | Schema only |
| Alliances/mail/reports/quests/items | Age 1 social/meta systems | Historical evidence required | Persistent models | Behavior unfinished | Numerous historical rules | Schema only |
| Prestige/honor/title | Age 1 progression | Historical evidence required | Persistent player fields + definition key | Formula/rank tables absent | Historical tables | Schema only |
| Duplicate request safety | One logical mutation per request | Project fidelity requirement | Unique player/idempotency key + transaction marker | SQLite dev locking differs from production RDBMS | None | Concurrent duplicate test passes |

## Phase 1 fidelity audit

**Status: PASS for authoritative architecture foundation (2026-09-29); NOT a claim that historical gameplay mechanics are complete.**

The requested persistent state categories are represented by first-class tables, including normalized coordinates, building levels, resource production/capacity, population/economy state, hero stats/experience/assignment, march missions, alliance ranks, and player prestige/honor/title progression. Compatibility fields remain on some aggregate records but are not a substitute for these normalized records. Static definition tables are deliberately not populated with guessed Age 1 constants. Gameplay behavior dependent on historical constants remains unfinished and marked above.


### Completion verification — 2026-09-29

- `python -m pytest -q`: **4 passed**.
- Persistence verified across independent SQLAlchemy sessions.
- Eight concurrent requests sharing one idempotency key converge on one response and one mutation.
- Requested authoritative model-table presence is asserted by automated test.
- Development seed verified after database reopen: 3 players, 4 cities (including one player with multiple cities), 2 NPC cities, 2 valleys, 2 flats, and persisted city/resource state.
- Running the seed again is non-duplicating.
- Historical gameplay constants remain intentionally unpopulated where evidence has not yet been established.

## Phase 3 — Age I interior city building layout

| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Interior locations | 34 total; Town Hall and Walls dedicated; 32 general plots | Evony Wiki Build Location; Age I guide | 34 persisted plots, indices 0/33 dedicated, 1–32 unrestricted general plots | Visual geometry is original rather than copied | Exact pixel geometry | PASS |
| Free city composition | General plots are player-selected; multiple Barracks/Cottages/Warehouses legal | Age I guides, historical Q&A/layout guides | No building-specific normal slots; repeatable definitions can occupy any general plot | Repeatability of some support buildings remains unverified and is conservatively restricted after first instance | Some single-instance rules | PASS |
| Empty plot interaction | Clicking empty plot opens build choices | Contemporary Age I guide | Server evaluates definitions, prerequisites, cost/time, unmet requirements; UI opens construction list | Definitions without verified level-1 tables are disabled, not guessed | Remaining building tables | PASS |
| Construction authority | Resource cost + timed server action; one building construction at a time | Historical Age I guide; building tables | Transactional/idempotent server operation, persisted queue, timestamp completion | Mayor/Construction-tech time modifiers not yet applied | Exact modifier formula | PASS (base time) |
| Occupied building interaction | Building opens its own functions | Building documentation | Building-key-specific server payload/UI; only implemented functions are actionable | Many downstream systems remain explicitly UNFINISHED | Downstream mechanics | PARTIAL |
| Upgrade | Per-level cost/time/prerequisites | Historical building tables | Upgrade is functional only for verified levels in centralized definitions | Only a subset of level tables populated in this phase | Remaining tables/modifiers | PARTIAL |
| Demolition/downgrade | Labor removes one level over time and returns resources; Dynamite removes immediately without refund | Evony Wiki Demolish / historical guides | Interface accurately exposes feature as UNFINISHED; no fake control | Not executable yet | Exact building labor-refund formula | NOT PASS |

**Phase 3 fidelity audit:** NOT COMPLETE. Core 34-location layout, free composition, construction persistence/idempotency and verified-base-time upgrades are implemented and tested. The phase cannot be marked complete until building-specific downstream functions and historically correct demolition/downgrade are implemented. No unknown values were invented to force a pass.

## Phase 4 — Dedicated Town Hall

| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Dedicated Town Hall | Permanent dedicated city administration structure, not a normal movable plot | Evony Wiki, Town hall; project topology requirement | Plot 0 is permanently seeded as `town_hall`; generic building construction cannot replace it | None in current topology | None | PASS |
| Town Hall administration | Production, Tax Rate, Comfort and Levy are Town Hall functions; rename is an administration action | Evony Wiki Town hall; official Evony Beginner Tutorial; historical startup guides | Dedicated Town Hall API/UI exposes population/public state, production controls, tax, rename, upgrade, and clearly marks Comfort/Levy unfinished | Comfort/Levy are not executable until exact rules are verified | Comfort/Levy costs, effects and cooldowns; exact production/tax/population/public-state tick formulas | PARTIAL |
| Upgrade costs/timers | TH2–TH10 historical resource costs and 30m→128h base timer sequence; level 10 requires Michelangelo's Script | Evony Wiki Town hall; Routine Quest; 2009 atwiki Town Hall table | Centralized `town_hall_levels` config; TH2 executable transactionally; TH10 item requirement configured | TH3+ execution is intentionally blocked because prerequisite sources conflict | Exact TH3–TH10 prerequisite chain | PARTIAL |
| Exterior field unlocks | Project target: TH1=10, then +3 per level through TH10=37 | User-specified target; Build Location corroborates TH1=10 and +3/level. Town Hall tables conflict by displaying TH2=16 etc. | Exact target sequence `[10,13,16,19,22,25,28,31,34,37]`; authoritative field view only returns unlocked plots | Historical surviving tables conflict with the project target after TH1; conflict preserved here rather than hidden | Whether the surviving 16/19/.../40 table reflects a version difference or documentation error | PASS (project target) |
| Tax management | Tax rate set in Town Hall | Evony Wiki Tax Rate/Loyalty/Public Grievance; official tutorial | 0–100 control, idempotent persisted mutation | Revenue and population/loyalty tick simulation not yet active | Exact tick timing/formula details | PASS control / PARTIAL simulation |
| Rename city | Rename city through administration/Town Hall flow | Official tutorial; historical startup guides | Idempotent persisted rename | Historical name length/character restrictions not imposed | Exact name validation rules | PASS control |
| Production controls | Four resource production percentages managed from Town Hall/Overview | Historical startup guides and Town Hall documentation | Persisted 0–100 values for food/lumber/stone/iron | Does not alter production output until formula is verified | Exact output/worker formula | PASS control / PARTIAL simulation |

### Source notes
- Evony Wiki — Town hall: https://evony.fandom.com/wiki/Town_hall
- Evony Wiki — Build Location: https://evony.fandom.com/wiki/Build_Location
- Evony Wiki — Routine Quest: https://evony.fandom.com/wiki/Routine_Quest
- Evony Wiki — Tax Rate, Loyalty, and Public Grievance: https://evony.fandom.com/wiki/Tax_Rate%2C_Loyalty%2C_and_Public_Grievance
- Official Evony Beginner Tutorial: https://evony.com/index.do?PageModule=Static&type=BeginnerTutorial
- 2009 Japanese Age I Town Hall table: https://w.atwiki.jp/evony/pages/45.html

**Fidelity audit:** Town Hall structure, target field progression, persisted administration controls, and verified TH2 upgrade transaction are implemented. The Town Hall phase is **not marked fully complete** because exact TH3–TH10 prerequisite requirements and exact Comfort/Levy and civic simulation formulas remain unresolved. Those values are explicitly `HISTORICAL_VALUE_UNKNOWN`; no fake controls are provided.

## Cottage — fidelity audit
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Cottage levels 1–10 | Repeatable city building; levels increase population limit | Evony Wiki Cottage; joevony Cottage table | Complete 1–10 centralized tables | None known in Cottage table | None | PASS |
| Costs/times | L1 100/500/100/50, 75s; doubles through L10 51,200/256,000/51,200/25,600, 10h40m | Evony Wiki Cottage; joevony | Centralized `building_levels.cottage` | None known | None | PASS |
| Prerequisites | L3 requires TH2, then prior TH level through L10 requiring TH9 | Evony Wiki Cottage; joevony | Authoritatively enforced on upgrade | None known | None | PASS |
| Level 10 item | Michelangelo's Script x1 | Evony Wiki Cottage; Age I construction documentation | Authoritatively required and consumed transactionally | None known | None | PASS |
| Population limit | Sum of every completed Cottage's level capacity: 100,300,600,1000,1500,2100,2800,3600,4500,5500 | Evony Wiki Cottage; joevony | Derived from all completed Cottages and persisted to PopulationState | None known | None | PASS |
| Current population integration | Population is bounded by Cottage-defined max and changes toward loyalty over Age I ticks | Evony Wiki Tax/Loyalty/Public Grievance | Cottage completion immediately updates cap; current population is clamped if cap falls; no fake instant residents are added | Full six-minute population tick engine is not yet implemented | Exact employment/labor-demand integration awaits resource-field implementation | PASS for Cottage dependency; population tick deferred |
| Idle population integration | Idle population cannot exceed current population and Cottage capacity ultimately bounds it | Evony Wiki Cottage/population documentation | Idle population is clamped through authoritative PopulationState whenever Cottage capacity changes | Exact field labor assignment is not yet implemented | Labor demand by resource field/production percentage | PASS for Cottage dependency; workforce calculation deferred |

## Warehouse — Phase audit

| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Levels 1–10 | Historical resource costs, construction timers and storage capacities | Evony Wiki Warehouse historical table | Centralized `building_levels.warehouse` table; transactional upgrades | None identified in verified table | Exact undocumented intermediate building prerequisites, if any, remain absent rather than invented | PASS |
| Multiple Warehouses | Multiple Warehouses permitted; capacities combine | Evony Wiki Stockpile discussion documents two Lv10 Warehouses combining to 1,100,000 before Stockpile | Unlimited normal-plot Warehouses subject to ordinary plot/build queue rules; completed capacities sum | None identified | None | PASS |
| Allocation | Combined capacity allocated by percentages among Food/Lumber/Stone/Iron; gold excluded | Historical `warehousepolicy` syntax and Evony Wiki Warehouse/Stockpile discussion | Persistent 4-resource percentages; server requires exactly 100%; gold always 0 protected | None identified | None | PASS |
| Stockpile | +10% Warehouse capacity per level; Lv10 +100% according to level table | Evony Wiki Stockpile | Effective capacity = combined base × (1 + 0.10 × level) | Wiki page contains a conflicting later multiplicative-edit claim; level table and historical discussion support additive percentage-point interpretation | Conflict retained here | PASS against documented level table |
| Privateering | Each attacker level reduces rival Warehouse ability by 3%; Lv10 table = 30% | Evony Wiki Privateering and Warehouse; Michelangelo's Script guidance | Protected allocation reduced by 3 percentage points per attacker Privateering level | Warehouse page contains a conflicting later exponential-edit claim (~26% at Lv10); primary level table says 30% | Conflict retained here | PASS against documented level table |
| Plunder integration | Warehouse protection changes resources actually removable after successful player-city attack | Warehouse/Privateering documentation | Transactional plunder resolver subtracts only exposed resources and persists result; duplicate resolution is idempotent | Full combat simulator is not implemented yet | Exact distribution when army load is smaller than total exposed resources is `HISTORICAL_VALUE_UNKNOWN`; resolver refuses to invent an ordering in that case | PASS for sufficient-load plunder |
| Lv10 special item | Michelangelo's Script required | Evony Wiki Warehouse level table | One Script required and consumed transactionally on Lv9→10 | None identified | None | PASS |
| Upgrade/allocation UI | Warehouse-specific interface | Age I building interaction model + Warehouse allocation evidence | Functional Warehouse interface shows combined/effective capacity, allocation, protected amounts and real upgrade action | Original artwork/visual geometry not copied | None affecting mechanics | PASS |

## Inn / Hero Recruitment
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Inn levels | Lv1-10; candidate count equals Inn level | Evony Wiki Inn; 2009 evonyLord | Centralized exact costs/times/counts; Cottage Lv2 prerequisite; Lv10 Script | None known for table | none | PASS |
| Recruitment location | Recruitment accessed through Inn, heroes reside in Feasting Hall | Official Evony beginner tutorial; Evony Wiki Hero | Dedicated `/inn` building interface; no global recruitment tab | none | none | PASS |
| Feasting Hall capacity | Hero capacity equals Feasting Hall level; full hall blocks hire | Evony Wiki Feasting Hall; official tutorial | Server-enforced before gold spend/hero transfer | Full Feasting Hall management is a later phase | none for capacity | PASS |
| Hiring fee | 1,000 gold per hero level | Evony Wiki Hero examples/formula | Transactional/idempotent gold spend | Hero salary tick not part of this phase | none | PASS |
| Candidate persistence | Roster must not reroll on render; rotates hourly | 2009 evonyLord; Hero Hunting docs | Persistent `InnCandidate` records with timestamps | Production RNG cannot yet create replacements | Exact original candidate generation distribution/formula | PARTIAL |
| Refresh | Automatic hourly; Hero Hunting immediate; hire immediately replaces slot | 2009 evonyLord; Evony Wiki Hero Hunting | Refresh semantics/config represented; endpoint refuses fabricated generation | Automatic/item refresh cannot complete until generator is verified | `HISTORICAL_VALUE_UNKNOWN` candidate RNG | BLOCKED |
| Candidate attributes/level | Higher Inn permits more/higher-level heroes; P/A/I vary | Evony Wiki Inn/Hero | Persistent model stores level/P/A/I/loyalty; verified fixtures used in tests | No invented production distribution | Exact level/stat/name generation algorithm | BLOCKED |


## Feasting Hall / Hero management
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Capacity | One resident/captured hero per Feasting Hall level, Lv1-10 | Evony Wiki Feasting Hall; official beginner tutorial | Derived from completed Feasting Hall level | None known | None | Automated |
| Roster/status | Feasting Hall manages heroes; Mayor, Idle, march-away, captured states | Evony Wiki Hero/Feasting Hall | Persistent roster resolves Mayor/Idle/March/Captured from authoritative records | Recall/valley stationing not yet implemented | Exact full legacy status vocabulary | Automated core |
| Salary | 20 gold per hero level per hour | Evony Wiki Stats/Hero | Salary rate exposed and modeled | Periodic gold settlement still requires economy tick integration | Exact insufficient-gold consequence | Rate tested |
| Mayor Politics | Resource production bonus; construction time factor 0.995^Politics | Guides for Evony / Start-Up Guide | Production multiplier and construction start-time factor implemented | Resource production tick must consume multiplier in later economy phase | None for documented factor | Automated |
| Mayor Attack | Troop training factor 0.995^Attack at queue start | Evony Wiki Troops / Guides for Evony | Authoritative helper implemented for training queue integration | Full Barracks training phase not built yet | None for documented factor | Automated helper |
| Mayor Intelligence | Research factor 0.995^Intelligence at research start | Evony Wiki Stats / Guides for Evony | Authoritative helper implemented for research queue integration | Full Academy research phase not built yet | None for documented factor | Automated helper |
| Captured heroes | Vacancy required, loyalty 0, release/persuade | Evony Wiki Hero/Feasting Hall | Capture vacancy, state and release implemented | Persuasion blocked until title gate is verified | Exact title requirement due documented glitch/ambiguity | Automated vacancy/release |

## Embassy
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Levels 1-10 | Costs/timers; TH2 for Lv1; Script at Lv10; garrison waves = level | Evony Wiki Embassy | Centralized definitions | Lv10 source has a typographic timer suffix; interpreted as 102h24m | Repeatability restriction not verified | Automated level effects |
| Alliance access | Lv1 join/apply/invitations; Lv2 create | Evony Wiki Embassy | Apply, authorized acceptance, create | Invitation workflow not yet separately modeled | Exact invitation expiration | Core automated |
| Host alliance limit | 10 members per host Embassy level | Evony Wiki Embassy | Enforced on application acceptance using host city Embassy | Host-city selection if host owns multiple cities needs historical verification | Which host city determines limit in multi-city ownership | Documented/guarded |
| Allied garrison | Opt-in checkbox; one garrison wave per Embassy level; same alliance | Evony Wiki Reinforce; evonyLord 2009 | Persistent ForeignGarrison + March integration | Battle resolver does not yet consume foreign garrisons because full combat phase is unfinished | Exact multi-wave ordering in defense | Automated persistence/capacity |
| Ownership | Reinforcements defend only and are not host-controlled/native | Evony Wiki Reinforce | Foreign troops never added to host TroopQuantity | Full battle casualty routing pending combat phase | None for ownership rule | Automated |
| Return | Sender recalls; host sends home | evonyLord 2009 | Both actors can transition garrison/march to RETURNING | Travel-time completion pending full march timing phase | Exact UI/report wording | Automated |
| Upkeep | Host city provides food; zero-food reports/return documented | Evony Wiki Embassy; Age I guides | Rule surfaced; garrison retains carried food | Economy starvation/upkeep tick not implemented | Exact food-consumption/forced-return tick sequencing | Unfinished |

## Marketplace
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Levels | Lv1-10; equal four-resource costs doubling from 1,000; 12m30s doubling; concurrent transactions = level; Script Lv10 | Evony Wiki Marketplace | Central definitions | None known | Exact prerequisite column is blank in surviving table | Automated |
| Order book | Player bids/offers for food/lumber/stone/iron; gold currency; max transaction 10m | Evony Wiki Marketplace/Q&A | Persistent MarketOrder | No NPC liquidity | None | Automated |
| Matching | Compatible bids/offers match; crossing example pays seller buyer bid | 2009 period guide | Price/time ordered server matching | Broader original server tie-breaking not independently documented | Exact same-price tie-break beyond observed chronology | Core automated |
| Fee | 0.5% system fee documented by period trading material | 2009 Bahamut guide; 2012 bot config corroboration | 0.5% each transaction side | Integer rounding may need packet evidence | Exact original rounding convention | Automated arithmetic path |
| Delivery | Matched purchase arrives after 30m; seller gold immediate; Merchant Fleet speeds a delivery chunk | Age I guides; Wiki Merchant Fleet discussion | Persistent MarketTrade with 30m server timestamp; settlement mutates real buyer resource | Merchant Fleet item action not yet implemented | Exact Merchant Fleet mechanics | Automated |
| Cancellation | Open/partial order can be cancelled | Historical UI references | Server-side cancellation | No cancellation fee found | Whether any edge-case fee existed | Automated |
| Plunder | Pending listed/bid assets not protected from plunder | Evony Wiki Q&A | Orders do not escrow/remove pending resources/gold | Matching revalidates funds/assets | Exact attack-time order cancellation behavior varied historically | Structural |

## Academy / Age I Technology System
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences / unknowns | Test |
|---|---|---|---|---|---|
| Academy | Lv1-10, TH2 prerequisite, Script Lv10; one research per Academy; research shared subject to local Academy | Evony Wiki Academy; Routine Quest | Building table, Academy-only UI/API, persistent queues, local Ct gating | None known for table; Lv10 source timer typo interpreted as 68h16m | Automated |
| Production techs | Agriculture/Lumbering/Masonry/Mining +10% base production/lv; matching field level gates | Individual research tables | Calculation multipliers + research validation | Economy tick integration remains separate from currently incomplete field-production engine | Automated calculation |
| Metal Casting | +10% mechanic construction/training speed/lv; Workshop target-level gate; Mining 2 | Metal Casting | Mechanic training factor | Full mechanic troop queue not yet implemented | Automated calculation |
| Informatics | Increased scout success/detail; Academy 3 | Informatics; Scout mission | Effective scouting level exposed for scout resolver | Exact city scout disclosure matrix depends also on Beacon Tower and remains combat/scout-report phase | Automated gate |
| Military Science | Training `base * 0.9^level * 0.995^Attack`; Forge target level | Military Science; Troops | Training calculation wired | Barracks queue phase incomplete | Automated calculation |
| Military Tradition | +5% troop attack/lv; MS1 | Military Tradition | Combat attack multiplier | Full battle round engine incomplete | Automated |
| Iron Working | +5% troop defense/lv; MS2 | Iron Working | Combat defense multiplier | Full battle round engine incomplete | Automated |
| Logistics | +10% carrying load/lv; MS2 | Logistics | Army load multiplier | March dispatch load validator not yet complete | Automated |
| Compass | +10% infantry speed/lv; MS3 | Compass | Movement multiplier | Full march travel calculator incomplete | Automated |
| Horseback Riding | +5% cavalry/mechanics speed/lv; Stable target level; MS5 | Horseback Riding | Effect/gates defined | **Age I Lv1-10 research times unresolved; research blocked rather than using Age II/mislabeled table** | Definition/gate |
| Archery | +5% ranged range/lv; MS4 | Archery | Range multiplier | Full combat engine incomplete | Automated |
| Stockpile | +10% Warehouse capacity/lv; Warehouse target level; Lumbering3 | Stockpile | Warehouse capacity uses local effective tech | Production storage-cap side effect needs field economy completion | Automated |
| Medicine | +5% troop life/lv; Logistics3 | Medicine | Life multiplier | Full battle engine incomplete | Automated |
| Construction | time `base * 0.9^level * 0.995^Politics`; Lumbering5 + Metal Casting2; empire-wide exception | Construction; Academy Q&A | Existing building construction now uses research factor; applies even in cities without supporting Academy | None known for formula | Automated |
| Engineering | +10% wall/fortification endurance/lv; Construction3 | Engineering | Endurance multiplier | Fortification battle engine incomplete | Automated |
| Machinery | repairable fortification rate increases by one base-rate multiple/lv; Metal Casting4 | Machinery | Repair multiplier | Per-type repair settlement waits for battle/fortification phase | Automated |
| Privateering | reduces Warehouse protection by 3%/lv; Informatics5 + MS8; Academy10 | Routine Quest; Warehouse | Modifier defined and existing plunder system uses tech level | Source disagreement additive vs multiplicative already recorded in Warehouse audit | Automated modifier |

## Rally Spot
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences / unknowns | Test |
|---|---|---|---|---|---|
| Levels 1-10 | Lv N = N outgoing waves and 10,000×N troops/wave; Script Lv10 | Evony Wiki Rally Spot; NPC conquer guide | Exact centralized level table and limits | Wiki Lv6 lumber displays 18,200 while doubling pattern suggests 19,200; retained displayed historical table value | Automated |
| March | Attack/Scout/Reinforce/Transport; hero mandatory for Attack; camp time | Attacking; Transport | Persistent Army + March; mission/destination/hero/troop/slot validation | Diplomacy beyond own/allied reinforcement/transport awaits full diplomacy phase | Automated |
| Troop stats | Age I load/upkeep/speed for 12 troop types | Evony Wiki Troops; 2009 Japanese guide corroboration | Centralized troop definitions used by deployment | None known for listed stats | Automated calculations |
| Load | Sum troop load, Logistics +10%/level | Logistics; Transporter | Real cargo validation | None known | Automated |
| Travel | Slowest troop controls wave; Compass infantry +10%/lv; HBR mounted/mechanics +5%/lv; sending Relief Station accelerates own/allied-city travel | Troops; Compass; HBR; Relief Station | Server timestamp arrival, no teleport | Exact integer rounding at sub-second boundary not packet-verified | Automated |
| Deployment food | Dispatch requires minimum food; troop Age-I food/upkeep values are published | Attacking; Troops | Food deducted atomically from real city resource | Exact legacy client/server rounding convention inferred with ceiling and isolated | Automated |
| Recall | March/camped force may be recalled and physically returns | 2009 evonyLord recall guide | Timed RETURNING state; source troops restored only on return completion | Attack post-contact return-speed changes from plunder weight belong combat resolver | Automated |
| War Ensign | +25% wave capacity, consumes item | Rally Spot; Attacking | Item-gated 1.25× cap | Item alias retained for historical naming variants | Structural |
| Exercise | Hypothetical battle; uses player's research for both sides | Rally Spot Q&A | Correct location/API, but refuses fake result | Full Age I battle-round resolver not yet complete | Explicitly unfinished |
| Medic Camp | Wounded casualties healed for gold; Medicine affects wounded percentage | Rally Spot | Persistent wounded model and display | Exact per-unit healing gold cost / wounded casualty formula unresolved | Explicitly unfinished |
| Open Gates | Rally Spot controls whether city army joins defense | Rally Spot; Defending | Persistent city toggle | Battle resolver consumption awaits combat phase | State implemented |

## Barracks
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences / unknowns | Test |
|---|---|---|---|---|---|
| Building Lv1-10 | Multiple Barracks; Rally Spot 1 prerequisite; Lv N has N queued batches; Script Lv10 | Evony Wiki Barracks / REFACTOR Barracks / Routine Quest | Exact level costs/timers, repeatable placement, per-building queue capacity | One surviving Barracks page lists Lv8 as 8h15 while refactor/doubling table gives 10h40; implementation uses 10h40 corroborated progression | Automated |
| Worker/Warrior | Barracks 1 | Individual unit pages; Routine Quest | Exact costs/stats/times | None known | Exact-definition test |
| Scout/Pikeman | Barracks 2 + Informatics1 / Military Tradition1 | Individual unit pages | Exact requirements/costs/stats/times | Scout page rounds 98s table vs 100s individual page; implementation uses individual unit 1m40 | Exact-definition test |
| Swordsman/Archer | Barracks3 + Iron Working1 / Barracks4 + Archery1 | Individual unit pages | Exact requirements/costs/stats/times | Swordsman aggregate table shows 3:44 while individual page shows 3:45; implementation uses individual page | Exact-definition test |
| Cavalry/Cataphract | HBR1; Iron Working5+HBR5 | Individual unit pages | Exact requirements/costs/stats/times | None known | Exact-definition test |
| Transporter | Barracks6 + Logistics1 + Metal Casting3 | Transporter page | Exact requirements/costs/stats/times | None known | Exact-definition test |
| Ballista | Barracks9 + Metal Casting5 + Archery6 | Ballista page | Exact requirements/costs/stats/times | None known | Exact-definition test |
| Battering Ram | Barracks9 + Metal Casting8; 4000F/6000L/0S/1500I; 75m | Age-I-derived unit datasets plus troop stat table | Definition and gating implemented | Primary Evony Wiki individual page was not retrievable in current crawl; retain source caveat | Exact-definition test |
| Catapult | Barracks10 + Metal Casting10 + Archery10 | Catapult page | Exact requirements/costs/stats/times | None known | Exact-definition test |
| Training formula | BaseTime × quantity × 0.9^MilitaryScience × 0.995^MayorAttack | Evony Wiki Troops | Snapshot at queue creation; authoritative server timer | Integer rounding uses nearest second | Automated |
| Population/resources | Recruit from idle population and consume unit resources | Troops + unit pages | Real resources and both population/idle population consumed at queue time | Population regrowth tick remains Town Hall/economy phase | Automated |
| Offline queues | Queued training continues persistently | Persistent Age I gameplay; Barracks queue behavior | Server timestamps; completion cascades through elapsed sequential batches | None known | Automated |
| Availability UI | Units appear with requirements but cannot train until all are met | Barracks/unit pages | Missing prerequisites displayed; train disabled | No global training tab | Automated/service + UI |

## Beacon Tower — fidelity gate PASS
| Feature | Target Age 1 behavior | Evidence | Implementation | Test |
|---|---|---|---|---|
| Lv1-10 | Barracks1 prerequisite; 150/1000/3000/300 and 7m30s at Lv1, doubling through Lv10; Script Lv10 | Evony Wiki Beacon Tower; Routine Quest | Exact table centralized | Exact-definition test |
| Incoming intelligence | Lv1 warning; Lv2 purpose; Lv3 arrival; Lv4 lord status; Lv5 source; Lv6 troop branches; Lv7 approximate numbers; Lv8 exact numbers; Lv9 hero level; Lv10 military tech | Evony Wiki Beacon Tower | Derived from persistent incoming March/Army/Hero/Technology state | Progressive disclosure test |
| Scouting relationship | Beacon Tower participates in scouting detail together with Informatics/scouts | Evony Wiki Scouting | Beacon level is authoritative and available to scout-report resolver | Full scout-report battle phase remains separate |

## Forge — fidelity gate PASS
Exact Lv1-10 table from Evony Wiki Forge; Ironmine Lv3 prerequisite; Script Lv10. Forge level N is enforced as the building requirement for Military Science N. Forge Lv2 exposes the documented Workshop dependency. Forge has no invented troop-training speed modifier.

## Stable — fidelity gate PASS
Exact Lv1-10 Stable table from Evony Wiki: Farm5 prerequisite, Script Lv10, matching Stable level gates Horseback Riding. Stable unlocks Relief Station. No cavalry/cataphract training-time bonus is applied because the Age I source explicitly reports the displayed claim as nonfunctional.

## Workshop — fidelity gate PASS
Exact Lv1-10 table; Forge2 prerequisite; Script Lv10. Workshop LvN gates Metal Casting LvN and Workshop1 is the Walls prerequisite. Mechanical/siege availability continues through verified Metal Casting/Archery/Logistics dependencies rather than a fabricated generic Workshop stat.

## Relief Station — fidelity gate PASS
Exact Lv1-10 table. Every level requires Stable1 and matching Horseback Riding level; Script Lv10. Sending-city multiplier is exactly 2× at Lv1-3, 3× Lv4, 4× Lv5-7, 5× Lv8-9, 6× Lv10. Existing Rally Spot travel now consumes this table only for own/allied-city Transport/Reinforce.

## Walls — fidelity gate PASS
Exact Lv1-10 cost/time/durability/space table; Quarry2 + Workshop1 at Lv1; Script Lv10. Wall level supplies equal fortification queue slots and reserves queued space immediately. Trap/Abatis/Archer Tower/Rolling Log/Defensive Trebuchet have documented costs, base times, space and prerequisite gates. Construction+Mayor Politics modify build time; Engineering modifies effective wall/fortification life; Machinery repair rates are exposed; Archer Tower range uses `1300*(1+.05*(Wall+Archery))`. Fortifications persist and completed queues enter real city defense inventory. The full battle-round resolver remains a separate phase; no fabricated casualty simulation was added.

## Building demolition/downgrade — fidelity gate PASS
Age I building menu now exposes the historical two paths: labor downgrade by exactly one level over time with resource return, or immediate complete removal with one Dynamite and zero refund. Labor demolition uses the removed level's build time subject to current Construction/Mayor Politics and a 30% resource return; the 30% recovery is corroborated by period Age I demolition practice. Town Hall is permanent. Normal buildings become an empty plot at Lv0. Dedicated Walls can be labor-downgraded but complete Dynamite removal remains `HISTORICAL_VALUE_UNKNOWN` and is intentionally blocked. Operations are idempotent and share the city's construction/demolition exclusion; active Barracks queues cannot be orphaned.

## City Exterior / Resource Fields — fidelity gate PASS
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences / unknowns | Test status |
|---|---|---|---|---|---|
| Field topology | Project target: TH1 = exactly 10 unlocked; +3 per TH level, through 37 at TH10; player chooses every field type | User-required target; Age I Build Location/Town Hall docs corroborate +3 per TH upgrade but surviving tables conflict on initial absolute count | 37 normal plots rendered; unlocked prefix follows 10/13/16/19/22/25/28/31/34/37; remainder visibly locked | Surviving community Town Hall table reports a conflicting absolute count; project target intentionally controls | Existing TH progression + specialization tests |
| Farm Lv1-10 | Exact costs, time, labor, 100/300/600/1000/1500/2100/2800/3600/4500/5500 output, 10k..550k capacity; Script at Lv10 | Evony Wiki Farm | Centralized exact table; FIELD construction/upgrade | None known for normal Age I Lv1-10 | exact table test |
| Sawmill Lv1-10 | Exact costs, time, labor, same output/capacity progression; Script at Lv10 | Evony Wiki Sawmill | Centralized exact table | Source lists Lv10 Food/Lumber as 51,000; retained literally rather than silently normalizing to 51,200 | exact table test |
| Quarry Lv1-10 | Exact costs, time, labor, same output/capacity progression; Script at Lv10 | Evony Wiki Quarry | Centralized exact table | None known | exact table test |
| Ironmine Lv1-10 | Exact costs, time, labor, same output/capacity progression; Script at Lv10 | Evony Wiki Ironmine | Centralized exact table | None known | exact table test |
| Specialization | No balanced-distribution restriction | Age I strategy/resource docs explicitly describe all/mostly-one-resource cities | Any unlocked plot may independently hold any of the four field buildings | None | 10-Sawmill specialization test |
| Production percentages / labor | Town Hall production percentages assign labor to each resource; resource fields have documented labor requirements | Routine Quest Administration; field tables; period guides discuss idle/negative available population | Labor scales with per-resource 0-100% production setting and is deducted from idle population; negative idle is preserved rather than inventing an undocumented shortage multiplier | Exact legacy UI rounding of fractional assigned labor is not documented | modifier/labor test |
| Technology | Agriculture/Lumbering/Masonry/Mining add 10% of base per level | Evony Wiki technology pages | Local effective Academy technology contributes +10% base/level | None | modifier test |
| Mayor Politics | +1% production per Politics point | Evony Wiki Stats | Current Mayor Politics contributes +1% base/point; state is settled before mayor changes | None | modifier test |
| Valleys | Grassland/Swamp/Lake food, Hill iron, Desert stone, Forest lumber with documented level tables | Evony Wiki Valley | Valley has authoritative city ownership and bonuses sum into that city's matching resource | Older persisted SQLite DB needs schema migration/reset for new `valleys.city_id` column | modifier test |
| Production items | +25% resource-specific 24h/7d Produce items | Evony Wiki Items/Farm/Sawmill/Quarry/Blower | Plowshares/Iron Rake, Arch Saw/Double Saw, Quarrying Tools/Adv Quarrying Tools, Blower/Blast Furnace consume inventory, create persistent timed Buffs, and affect only matching resource/city | Item naming follows documented Age I names | piecewise expiry test |
| Offline accumulation | Production must continue from server timestamps without client timers and stop at capacity | Age I capacity behavior; server-authoritative project rule | `ResourceProduction.last_calculated_at` + fractional remainder; elapsed intervals settled on reads/mutations; item start/expiry split piecewise; field/research/mayor/percentage changes settle at exact boundaries | No permanent per-field browser timers | 2-hour offline + capacity test |
| Demolition interaction | Resource fields use existing building downgrade/Dynamite system | Prior demolition fidelity phase | Production is settled before FIELD downgrade/removal and at timed demolition completion | None | full regression |

## Complete economic simulation — fidelity gate PASS
| Feature | Target Age 1 behavior | Implementation | Fidelity note |
|---|---|---|---|
| Civic tick | 6-minute server tick | `settle_economy` processes elapsed whole ticks from persisted timestamps | Verified 10 ticks/hour |
| Tax/Gold | Current population × tax rate hourly; collected across ticks | 1/10 hourly tax income each 6-minute tick; real `CityEconomyState.gold` | A surviving Q&A line says “1/6th” despite also saying 10 ticks/hour; hourly tax examples and 10-tick cadence require 1/10 |
| Loyalty | trends toward `100 - Tax - Grievance` | ±1 per tick | Verified |
| Population | occupancy trends toward Loyalty; tax controls +/- tick speed | Documented linear 0–100% tax table, capped upward at loyalty occupancy | Verified |
| Population roles | civilian / limit / working / idle / troop | Central `population_breakdown`; field labor consumes working population; Barracks consumes actual idle/current population | Troop population is tracked separately after recruitment |
| Resources | elapsed server-time production | Persistent production timestamps/fractional remainder; no client generation | Verified offline |
| Labor | resource fields require population | Insufficient civilians proportionally constrain actual output | Corrects prior display-only labor constraint |
| Food upkeep | Age I troop table; outside troops 2× | Garrison + persistent outgoing Army/March upkeep integrated into food settlement | Verified |
| Starvation | Age I troops Refuge when food unavailable, +1 grievance per refugee event | Food floors at zero; exact troop-loss event quantity intentionally not fabricated | `HISTORICAL_VALUE_UNKNOWN` |
| Hero salary | `20 × hero level` gold/hour | Real elapsed gold deduction with fractional carry | Exact insufficient-gold consequence remains unknown |
| Storage | field capacity stops passive generation | Integrated capacity clamp | Verified |
| Protection | Warehouse allocation + Stockpile + Privateering | Existing real protection calculation exposed in economy snapshot/debug | Partial-load plunder distribution remains prior documented unknown |
| Concurrency | elapsed interval must settle once | Atomic conditional `last_settled_at` claim | Simultaneous-request test passes |
| Debug | development only | `/api/dev/.../economy-debug` + hidden-by-default UI panel enabled only with `DEVELOPMENT_MODE=1` | Lists every production modifier and net drains |

## Complete hero system — fidelity gate PASS
| Feature | Age I target | Implementation / status |
|---|---|---|
| Origin/residence | Recruit from Inn; vacancy in Feasting Hall | Persistent InnCandidate -> Hero; FH capacity enforced |
| Recruitment | employment fee = level × 1,000; initial loyalty 70 | Authoritative gold spend and persistent Hero |
| Level/XP | next level XP = `100 × current_level²`; each level grants one P/A/I point | Exact formula and server-side level/attribute mutation |
| Politics | +1% production/point; construction/fortification time `0.995^Politics` | Integrated production, construction, Walls |
| Attack | Mayor training `0.995^Attack`; army hero adds `floor(baseATK × Attack/100)`; highest available Attack hero defends | Integrated Barracks + battle stat hook |
| Intelligence | Mayor research `0.995^Intelligence`; attacking/defending scout intelligence | Integrated Academy; scout intelligence exposed to report resolver |
| Loyalty | Inn 70; gold reward level×100 gives +5; 15m cooldown | Persistent and enforced |
| Salary | level×20 gold/hour | Integrated authoritative economy |
| Assignment | Mayor cannot march; marching hero cannot be mayor/dismissed/reused | Persistent HeroAssignment + Army/March exclusivity |
| Status/return | Idle/Mayor/Captured/March/Returning | Derived from persistent assignment + March |
| Captured | vacancy required; loyalty0; persuade/release | Persuasion uses title ladder, level×1000 gold, documented medal ladder; successful persuasion loyalty10 |
| Redistribution | Holy Water, one per 10 levels; reset allocated level points | Lossless only when original base/allocation provenance exists. Legacy/old Inn records without provenance are blocked as `HISTORICAL_VALUE_UNKNOWN`, never guessed |
| Hero items | Anabasis +1k XP; Epitome +10k; On War +100k; Wealth/Excalibur/Art of War 25% P/A/I for 7 days | Persistent item consumption and timed HeroBuff. Age I combat Excalibur hook uses documented +25 battle Attack points rather than display +25% |
| Equipment | Age II-style gear/energy not part of intended Age I rules | Not implemented |
| Training XP | Mayor receives documented per-unit XP when training completes | Integrated Barracks completion |
| Battle XP | Based on enemy troops/fortifications destroyed | Hook/data documented; full battle-round casualty resolver remains the combat phase and is not fabricated here |

## Persistent world map — fidelity gate PASS
| Feature | Target Age 1 behavior | Current implementation | Status |
|---|---|---|---|
| World coordinates | Age I world is 800×800; historical map references describe sixteen 200×200 states | Persistent coordinates 0–799 on both axes; viewport is coordinate bounded | PASS |
| Player cities | City occupies persistent world coordinate | City record overlays tile at exact x/y | PASS |
| Barbarian/NPC city | Persistent NPC city on map, level 1–10 | `MapTile` + `NPCCity` | PASS |
| Flats | Persistent buildable/attackable wilderness coordinate | `MapTile` + `Flat` | PASS |
| Valleys | Forest, Desert, Hill, Lake, Grassland wilderness; persistent level/ownership | `MapTile` + `Valley`; exact type retained | PASS |
| Tile actions | Clicking object exposes map target/action interface | Coordinate-derived tile API + full-cell hitbox; Player City/NPC/Flat/Valley actions supplied | PASS; march execution remains Rally Spot responsibility |
| Navigation | Pan/scroll, Home, coordinate jump, current coordinate | Arrow + drag pan, immediate Home to selected city, X/Y Go, live center coordinate | PASS |
| Bookmarks | Player coordinate bookmarks | Persistent per-player add/list/delete/jump | PASS |
| Hit testing | Every visible tile clickable independent of viewport location | Every tile owns an absolute world-coordinate button; no viewport-midpoint coordinate calculation | PASS; automated all-169-cell viewport interaction contract |
| NPC density | Historical baseline distribution | **CUSTOM_SERVER_RULE: DOUBLE NPC DENSITY.** World-generation target is 2× the configured historical/baseline NPC count. Development seed demonstrates doubled deterministic NPC fixture slots. | INTENTIONAL DEVIATION |
| Historic Cities | Age II mechanic, not Age I target | Not added | PASS |
| Wilderness daily level cycling | Period accounts describe unowned valley/flat level changes at maintenance | `HISTORICAL_VALUE_UNKNOWN` exact reset schedule/transition behavior; not fabricated in this phase | OPEN |

## Age I valleys and flats — fidelity gate PASS
| Feature | Target Age I behavior | Current implementation | Status |
|---|---|---|---|
| Terrain | Flat, Grassland, Swamp, Lake, Hill, Desert, Forest | All persisted at map coordinates; prior missing Swamp corrected | PASS |
| Levels | Wilderness levels 1–10 | Persistent level on Valley/Flat/MapTile | PASS |
| Bonuses | Grassland Food 3–12%; Swamp Food 5–23%; Lake Food 8–35%; Hill/Desert/Forest Iron/Stone/Lumber 5–23% | Exact level tables feed authoritative city base-production modifier | PASS |
| Ownership limit | Per-city owned wilderness count equals Town Hall level | Valleys + conquered Flats share TH quota | PASS |
| Defenders | Unowned wilderness contains varying hostile troops; higher levels generally stronger | Defender composition persisted per tile; no fabricated universal level table | PASS / generator distribution remains HISTORICAL_VALUE_UNKNOWN |
| Scouting | Informatics controls exactness; vague troop-size bands at insufficient intel | Persistent defender scout reports with Few→Giga bands | PASS |
| Attack/conquest | Must defeat defenders; winning army camps if slot available | Conquest service refuses while defenders remain, checks TH quota, persists ownership, camps resolved winning march | PASS; casualty resolution remains combat phase |
| Abandon | Releases wilderness; native defenders regenerate | Persistent release; regeneration hook/time recorded | PASS; exact randomized regeneration composition HISTORICAL_VALUE_UNKNOWN |
| Flat | No resource bonus; conquerable and counts toward wilderness limit | Implemented | PASS |
| Build City | Conquered Flat + title/city slot + 250 Workers + 10,000 each Food/Lumber/Stone/Iron | Transactional consumption and city creation at exact coordinate | PASS |
| NPC creation | Abandon city founded on flat → NPC at founding flat level | Founding-flat provenance persisted; non-last city converts transactionally to same-level NPC | PASS |
| NPC density | Baseline historical distribution | **CUSTOM_SERVER_RULE: DOUBLE NPC DENSITY.** World generation remains 2× baseline; player-created NPCs are additional normal Age I conversions | INTENTIONAL DEVIATION |
| Daily level cycle | Unowned wilderness rises one level per maintenance/day; Lv10 cycles to Lv1 | Documented target, but exact server-maintenance clock remains HISTORICAL_VALUE_UNKNOWN | OPEN — not fabricated |

## Authoritative march engine — fidelity gate PASS (combat handoff explicit)
| Feature | Target Age 1 behavior | Implementation | Status |
|---|---|---|---|
| Persistent march | ID, origin, destination, mission, hero, army/cargo, departure/arrival, return destination/arrival, status | `March` + `Army` + `MarchMission`; explicit return city/x/y and one-shot resolution marker | PASS |
| Missions | Attack, Scout, Transport, Reinforce; conquest/occupation where applicable; recall/return | All implemented; `OCCUPY` is internal wilderness conquest mission, not Age II Colonize | PASS |
| Rally limits | level N = N simultaneous waves; 10,000×N troops/wave; War Ensign +25% | Enforced server-side | PASS |
| Travel | Euclidean coordinate distance; slowest troop; Compass/HBR where applicable; friendly Relief Station for Transport/Reinforce | Central `army_travel_seconds` | PASS |
| Camp time | Adds to outbound arrival, not return | Persisted `camp_seconds`; return uses travel-only time | PASS |
| Offline | Server timestamps, no client authority | `process_due_marches` advances arrivals/returns whenever authoritative state is touched | PASS |
| Arrival exactly once | no duplicate mission/report/cargo | Atomic conditional claim on `arrival_processed_at`; duplicate call becomes no-op | PASS |
| Scout | Scouts required; wilderness scouting uses Informatics/detail rules | Scout report persisted, then automatic return | PASS |
| Transport | Friendly/self/alliance city; cargo/load validation | Cargo delivered once; TransportReport persisted | PASS |
| Reinforce | Friendly/self/alliance city | Army remains distinct `GARRISONED` march until recalled | PASS |
| Wilderness occupy | Attack/Occupy with hero; ownership only after defenders are actually gone | Conquest persists and army camps | PASS |
| Attack with defenders/city | Arrival must hand off to battle resolution | Creates exactly one persistent Battle and BattleReport with `PENDING_COMBAT`; **does not fabricate casualties/outcome**. Return begins only after dedicated Age-I battle resolver supplies outcome. | DEPENDENCY: combat phase |
| Recall | outbound/camped/garrisoned return | Return duration based on distance already traveled outbound or full travel from destination | PASS |
| UI | Rally Spot and map show authoritative march state | Both consume server march payload/status/countdown | PASS |

## Dedicated Age I combat simulation engine — fidelity gate PASS (documented core; disputed rules isolated)
| Mechanic | Target Age I behavior | Implementation / uncertainty | Status |
|---|---|---|---|
| Architecture | Combat independent of UI | Pure `app/combat.py`: `simulateBattle(input, ruleset) -> BattleResult`; no DB/UI imports | PASS |
| Stacks/layering | Each troop type is a separate combat stack; one target per stack/round | Persistent per-type stack positions/counts; never pools army HP | PASS |
| Base stats | Age I Life/Attack/Defense/Range/Speed | Consumes centralized `game_definitions/core.json` troop definitions | PASS |
| Opening range | 200 + longest modified participating range | Implemented | PASS |
| Rounds | movement/range/fire repeat; defender holds after 100 rounds | Deterministic round log; 100 default | PASS |
| Damage | Published Age I combat-pair equation; ranged Archer/Ballista/Catapult ×0.5; ceil partial casualty | Implemented with documented interaction table | PASS |
| Military Tradition | +5% attack/level | Implemented | PASS |
| Iron Working | +5% defense/level | Implemented | PASS |
| Medicine | +5% life/level | Implemented | PASS |
| Archery | +5% range/level for ranged troops | Implemented | PASS |
| Compass | +10% infantry movement/level | Implemented | PASS |
| HBR | +5% mounted/mechanics movement/level | Implemented | PASS |
| Hero Attack | documented to modify army combat | `HISTORICAL_VALUE_UNKNOWN`: coefficient not invented; configurable `hero_attack_mode` / `hero_attack_per_point` | OPEN CONFIG |
| Target selection | one combat pair/stack/round; layering materially affects targeting | nearest-in-range + centralized documented-priority tie-break | DISPUTED CONFIG |
| Movement ordering | stacks move by combat speed until target enters range | centralized rule | DISPUTED CONFIG |
| Archer Tower | Life 2000, Attack 300, Defense 360; range `1300*(1+.05*(Wall+Archery))` | Implemented | PASS |
| Trap | infantry-only | eligibility modeled; exact casualty algorithm unresolved, damage intentionally not fabricated | OPEN CONFIG |
| Abatis | mounted-only | eligibility modeled; exact casualty algorithm unresolved, damage intentionally not fabricated | OPEN CONFIG |
| Rolling Log | Attack 500, Range 1300, one-shot | Implemented | PASS |
| Defensive Trebuchet | Attack 800, Range 5000, siege-oriented, one-shot | Implemented; exact target subtleties remain configurable | PASS/DISPUTED |
| Machinery | post-battle fortification repair | exact base Archer Tower repair rate unresolved; not applied inside pure battle rounds | OPEN |
| Walls | tower range and fortification participation | wall level feeds Archer Tower range | PASS |
| Cavalry/ranged/siege interactions | documented combat-pair multipliers | implemented interaction matrix | PASS |
| Plunder | post-victory capacity/protection transfer | `BattleResult.plunder` reserved; campaign adapter dependency, no invented ordering | OPEN ADAPTER |
| Honor/prestige | battle consequences | exact formulas insufficiently verified; result explicitly emits `HISTORICAL_VALUE_UNKNOWN` | OPEN |

## Defensive fortifications — fidelity gate PASS
| Feature | Target Age 1 behavior | Implementation | Fidelity note |
|---|---|---|---|
| Production surface | Fortified units built through Walls | Walls-only API/UI and persistent FortificationQueue | PASS; no global defense screen |
| Wall capacity | L1–10 durability/spaces: 10k/1k, 30k/3k, 60k/6k, 100k/10k, 150k/15k, 210k/21k, 280k/28k, 360k/36k, 450k/45k, 550k/55k | Central Walls level table; built + queued units reserve space | PASS |
| Trap | Walls1; 1 space; 50/500/100/50; 60s; range5000; one-use infantry obstacle | Persistent construction + combat obstacle targeting foot layers | Exact casualty curve is disputed; configurable `obstacle_casualty_rule`, default follows surviving one-device/one-eligible-casualty observations |
| Abatis | Walls2 + Metal Casting1; 2 spaces; 100/1200/0/150; 120s; range5000; mounted only | Persistent construction + mounted-only combat obstacle | Exact casualty curve shares configurable uncertainty |
| Archer Tower | Walls3 + Archery3; 3 spaces; 200/2000/1000/500; 180s; Life2000 Attack300 Defense360 Range1300 | Persistent stack; fires across rounds; range = 1300*(1+.05*(Walls+Archery)) | General Walls table says 1500 stone while dedicated page + quest totals support 1000; retained 1000 and documented conflict |
| Rolling Log | Walls5 + Metal Casting5; 4 spaces; 300/6000/0/0; 360s; Attack500 Range1300 | One-shot combat stack | PASS for documented stats/one-shot behavior |
| Defensive Trebuchet | Walls7 + Metal Casting6; 5 spaces; 600/0/8000/0; 600s; Attack800 Range5000 | One-shot anti-siege stack; Politics exponent divisor 4 per dedicated Age I reference | Exact casualty interactions beyond published stats remain combat-ruleset uncertainty |
| Build-time modifiers | Construction research + Mayor Politics | Server-authoritative timing; DT uses documented Politics/4 exponent | PASS |
| Machinery | post-battle repair rates: Trap5%, Abatis5%, Log7%, Treb8%; each Machinery level adds one base-rate multiple | Existing repair-rate calculation exposed by Walls | Archer Tower base repair is historically unresolved; no fabricated rate |
| Engineering | fortified life/durability effect | Existing wall/fortification life multiplier exposed | PASS where applicable |

## NPC / barbarian cities — fidelity gate PASS
| Feature | Age I target | Implementation | Status |
|---|---|---|---|
| Levels | NPC 1–10 fixed level maxima | Central `NPC_LEVELS` resources, troops and fortifications | PASS |
| Resources | Level-specific Food/Lumber/Stone/Iron/Gold; no Warehouse | Persistent mutable JSON state; no Privateering protection | PASS |
| Defenders | Fixed level troop + wall-defense maxima | Persistent mutable troops/fortifications feed pure combat engine | PASS |
| Regeneration | resources full in 8h; troops/fortifications +10% max each 6m/full in 1h | Timestamp-based offline regeneration | PASS |
| Defensive behavior | NPCs defend but do not proactively attack cities | Real combat on incoming Attack; no autonomous city attacks | PASS |
| Scout | Rally Spot Scout mission/report | Arrival reads regenerated persistent NPC state; Informatics controls exact/detail exposure | PASS; exact intermediate Informatics thresholds remain HISTORICAL_VALUE_UNKNOWN |
| Attack | real march + battle | `simulateBattle` + persisted Battle/BattleRound/BattleReport; survivor state written back exactly once | PASS |
| Loot | surviving army load; NPC has no Warehouse | Persistent resources removed and placed in returning Army cargo | PASS; resource selection ordering centralized because exact ordering is weakly documented |
| Loyalty/conquest | repeated wins reduce loyalty; NPC regenerates 3 loyalty/6m; city capture requires city slot | persistent loyalty; 3 loss above 50 and 2 at/below 50 per surviving conquest descriptions; zero loyalty transfers coordinate when title slot exists | PASS with documented community-source basis |
| Prestige | NPC wins can award prestige but surviving formulas conflict/outdated | `HISTORICAL_VALUE_UNKNOWN`; never fabricated | OPEN exact value |
| Density | custom ~2× NPC world density | **CUSTOM_SERVER_RULE: DOUBLE NPC DENSITY.** Only population density changes; NPC internal strength tables remain historical | INTENTIONAL DEVIATION |

## Persistent reports — fidelity gate PASS
| Feature | Target Age 1 behavior | Current implementation | Status |
|---|---|---|---|
| Persistence | Reports remain available until player deletion | Dedicated persistent report tables; read state + soft deletion | PASS |
| Battle reports | Authoritative battle outcome with participants, location/time, hero, troops, losses/survivors, defenses, loot, outcome | Immutable deep snapshot generated from Battle/BattleResult at resolution | PASS |
| Prestige/Honor | Battle report shows applicable changes | Fields persisted when known; unresolved formulas remain `HISTORICAL_VALUE_UNKNOWN` | NO INVENTION |
| Scout reports | Detail depends on scouting systems | Informatics + source Beacon Tower + target level + scout count; hero Intelligence contribution explicitly disputed/unknown | PASS / uncertainty isolated |
| Scout quantity bands | Few/Pack/Lots/Horde/Throng/Swarm/Zounds/Legion/Bulk/Giga | Historical ranges implemented when exact counts unavailable | PASS |
| Transport | Report generated from completed authoritative transport | Immutable origin/destination, delivered troops/resources, time | PASS |
| Reinforcement | Allied/self reinforcement arrival information | Dedicated ReinforcementReport generated on authoritative arrival | PASS |
| System | Miscellaneous authoritative system events | Dedicated SystemReport helper/store for refuge/rebellion/etc. event producers | PASS infrastructure |
| Client authority | Client must never invent report facts | UI only lists/renders server payloads and invokes read/delete APIs | PASS |

## Persistent player mail — fidelity gate PASS
| Feature | Target Age 1 behavior | Implementation | Status |
|---|---|---|---|
| Inbox / Sent | persistent player mailboxes | One immutable Mail row, independent sender/recipient soft-delete flags | PASS |
| Compose | mail addressed to another lord/player | Exact case-insensitive recipient resolution; subject/body server validated | PASS |
| Reply | reply to received player mail | Server verifies original recipient and locks reply to original sender | PASS |
| Delete | each side can remove its own visible copy | Per-mailbox soft delete; physical cleanup only after no visible copy remains | PASS |
| Read/unread | recipient mail status | Server-owned `read`; opening recipient copy marks read | PASS |
| Timestamp | persistent send time | UTC server timestamp | PASS |
| Recipient lookup | player/lord name lookup | Prefix lookup, 2-char minimum, max 20 results | PASS |
| System communication | system may communicate without replacing Reports | Internal-only `create_system_mail`; nullable sender displayed as System; no public API can spoof system sender | PASS |
| Abuse resistance | reject malformed/spammy sends | 120-char subject, 5000-char body, control-char rejection, exact recipient validation, idempotency, 10 sends/min global and 5/min to same recipient | PROJECT SERVER RULE |

## Alliance system — fidelity gate PASS
| Feature | Target Age 1 behavior | Implementation | Status |
|---|---|---|---|
| Creation | Alliance created through Embassy capability | Embassy L2 required; creator becomes Host | PASS |
| Ranks | Host, Vice Host, Presbyter, Officer, Member | Persistent AllianceMember rank + AllianceRank permission records | PASS |
| Permissions | ranks have actual authority | Every invite/application/rank/expel/diplomacy/info/mail/leadership mutation checks server permission | PASS |
| Application | Embassy member application | Persistent pending application; authorized accept/reject | PASS |
| Invitation | authorized invitation to player | Persistent invitation; recipient accept/reject | PASS |
| Personnel | promote/demote/expel/leave | Hierarchy checks prevent action on equal/higher ranks; Host transfer required before leaving | PASS |
| Leadership | one Host | Explicit Host transfer; old Host becomes Vice Host | PASS |
| Information | alliance name/info/member list | Persistent name/information and rank-ordered roster | PASS |
| Chat | alliance-only channel | Persistent alliance chat; membership checked server-side; project anti-spam limit | PASS |
| Alliance mail | authorized alliance-wide communication | Presbyter+ permission; delivered as persistent internal Alliance Mail to member inboxes | PASS |
| Diplomacy | Friendly/Neutral/Hostile | Persistent symmetric AllianceRelation; Vice Host/Host permission | PASS |
| Map/marches | relationship affects interactions | Same-alliance/Friendly cities are not attack/scout targets; map exposes friendly view instead of attack; Hostile/Neutral remain attackable | PASS |
| Reinforcement | Embassy interaction and same-alliance garrison | Existing Embassy garrison capacity/permission + same-alliance check retained | PASS |
| Transport | friendly same-alliance/self movement | Existing Age-I same-alliance transport rule retained | PASS |

## Multiplayer chat — fidelity gate PASS
| Feature | Target Age 1 experience | Implementation | Status |
|---|---|---|---|
| World | server-wide player channel | Persistent WORLD ChatMessage stream | PASS |
| Alliance | alliance-member channel | Persistent ALLIANCE stream keyed to alliance; membership rechecked on send/read | PASS |
| Whisper | private player-to-player channel | Persistent WHISPER rows with recipient; query restricted to participants | PASS |
| Metadata | sender/time/channel/recipient | Server-authored immutable metadata | PASS |
| Near real time | continuously updating chat | Incremental `since_id` API polled every 1.5 seconds; persisted source of truth | PASS |
| Blocking | prevent unwanted direct contact | Recipient block rejects new whispers and filters blocked sender from reads | PROJECT SERVER RULE |
| Muting | locally hide sender | Persistent per-player mute applied server-side to delivery query | PROJECT SERVER RULE |
| Rate limiting | abuse resistance | 5 messages / 10 seconds per sender across channels | PROJECT SERVER RULE |
| Moderation | removal/restriction auditability | Persistent moderation actions, soft-hidden messages, timed/permanent send restrictions | PROJECT SERVER RULE / INFRASTRUCTURE |

## Quest system — fidelity gate PASS
| Feature | Target Age 1 behavior | Implementation | Status |
|---|---|---|---|
| Definitions | Routine Quest progression is data-driven | `game_definitions/quests.json`, 27 verified/partially verified definitions | PASS |
| Completion | checked from accomplished objectives | Building/tech/troop/resource/population/hero/alliance/prestige predicates query authoritative state | PASS |
| Military objectives | actual scout/conquest actions | Persistent QuestProgress event evidence recorded by server gameplay adapters | PASS |
| Award flow | completed quest then explicit Get Award | Separate completed/claimed state | PASS |
| One claim | award cannot be duplicated | QuestProgress claimed flag + OperationRequest idempotency | PASS |
| Rewards | resources/gold/items/population/prestige | Transactional server grants | PASS |
| Unknown rewards | do not invent | `HISTORICAL_VALUE_UNKNOWN` + empty grant table | PASS |
| Wording | preserve mechanics without copying protected prose | Original short names/descriptions only; no historical quest prose copied | PASS |

## Player progression — fidelity gate PASS
| Feature | Target Age 1 behavior | Implementation | Status |
|---|---|---|---|
| Structure | Prestige/Honor + separate Rank and Title; no player XP level | Persistent PlayerProgression; separate Rank/Title keys | PASS |
| Rank | Civilian → Lieutenant → Captain → Major → Colonel → General | Data-driven exact Gold/Town Hall/medal requirements and documented awards | PASS |
| Title | Civilian → Knight → Baronet → Baron → Viscount → Earl → Marquis → Duke → Furstin → Prinzessin | Data-driven Rank/Gold/Prestige/medal requirements and awards | PASS |
| City ownership | Title determines 1–10 city cap | Existing city founding and NPC conquest call `player_city_cap`, now derived from Title definition | PASS |
| Consumption | Gold + medals spent; TH/Rank/Prestige are gates | Transactional promotion service | PASS |
| Promotion UI | current/next/satisfied/missing | Server-generated per-requirement preview; client only renders it | PASS |
| Validation | server decides promotion | Next-step-only validation + idempotent transaction | PASS |
| Prestige | persistent score and promotion gate/reward | Promotion/quest awards authoritative; historical activity prestige divisor documented, but unverified raw experience constants are not invented | PARTIAL / HISTORICAL_VALUE_UNKNOWN for missing activity XP constants |
| Honor | PvP-derived score | Persistent and displayed; surviving sources establish resource-value-relative PvP behavior but not a sufficiently exact numeric formula | HISTORICAL_VALUE_UNKNOWN numeric battle formula |
| Population/resource promotion gates | only where historically documented | No invented population/resource requirements added to Rank/Title tables | PASS |

## Multiple-city ownership — fidelity gate PASS
| Feature | Target Age 1 behavior | Implementation | Status |
|---|---|---|---|
| Independent cities | each city owns its own economy/military/buildings | City-keyed buildings, fields, resources, population, troops, heroes, queues, fortifications, mayor and source marches; independence snapshot tests | PASS |
| Coordinates | every city occupies its own world coordinate | City + CityCoordinate + MapTile ownership | PASS |
| Switching | City/Fields interfaces operate on selected city | Existing city selector reloads `/overview`; current city ID now synchronized for newer subsystem panels | PASS |
| Research | learned empire-wide, applied locally only with sufficient Academy | Player Technology + `effective_technology_level(city,key)` Academy gate | PASS |
| Founding | conquered Flat + title slot + 250 Workers + 10,000 Food/Lumber/Stone/Iron/Gold | Transactional `build_city_on_flat`; corrected prior missing Gold cost | PASS |
| Founding result | new city is complete independent city | own TH/Walls, 34 interior plots, 10 TH1 exterior plots, resources/economy/population rows and coordinate | PASS |
| Title cap | title limits cities | `player_city_cap` from Age I Title progression; checked on founding/conquest | PASS |
| NPC conquest | loyalty 0 + title slot | existing NPC conversion creates independent city | PASS |
| Player-city conquest | loyalty 0, title slot, cannot take opponent's only city | authoritative ownership transfer helper | PASS |
| Abandonment | cannot abandon last city; founded-city abandonment creates NPC of source Flat level | persistent source-flat provenance + NPC conversion; active armies must be resolved/returned first | PASS |

## Item / buff framework — fidelity gate PASS
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Inventory | persistent item quantities | Age I item lists / Routine Quest rewards | PlayerItem + data-driven `items.json`; authoritative quantity consumption | none for implemented inventory mechanics | acquisition/drop probabilities outside this phase | PASS |
| Guidelines | construction/research timer reduction | Age I Speed Up item list | 15m/1h/2.5h/8h fixed and 30% Ultimate effects on real queue timestamps | Master Guidelines excluded because random 10–30h distribution is not verified | Master random distribution | PASS |
| Training speedup | Napoleon's Diary: -30%, once/group | Age I Speed Up item list | persistent ItemApplication prevents second use on same training queue | none | none | PASS |
| Fortification speedup | Archimedes' Note: -30%, once/queue | Age I Speed Up item list | same one-target application framework | none | none | PASS |
| Production | +25% resource production, 24h/7d | Age I Produce item list | city-targeted persistent Buff with server expiration; same-resource production buffs do not stack | exact historical replacement/overlap UI wording not reproduced | none affecting output | PASS |
| Michelangelo's Script | required for level-10 buildings | Age I building/item documentation | existing level-10 item_cost consumes inventory transactionally | none | none | PASS |
| Hero XP books | +1k/+10k/+100k XP | Age I item list | delegates to authoritative HeroExperience | none | none | PASS |
| Hero attribute books | +25% I/P/A for 7 days | Age I item list | persistent HeroBuff, expiration timestamp, effective stats/combat hooks | hero reward cooldown retained from hero subsystem | none | PASS |
| Holy Water | hero redistribution with level-scaled quantity | Age I item docs | existing authoritative redistribution consumes inventory | only heroes with preserved base-stat provenance are safely supported | conflicting historical quantity descriptions remain isolated by existing hero rule | PASS |
| Teleport | random/specific city relocation | Age I item docs | city coordinates + map tile move; valleys/flats released; active marches block teleport | random City Teleporter uses deterministic free-coordinate search because State partitioning is not modeled | exact random destination algorithm | PASS |
| Advanced teleport restriction | no outgoing marches for 24h | Age I Adv City Teleporter docs | persistent 24h city-targeted Buff checked by march creation | none | none | PASS |
| Civil Code | add 20% population limit or minimum 100 | Age I item list | authoritative population mutation capped at limit | none | none | PASS |
| Speech Text | loyalty 100 / grievance 0 | Age I item list | authoritative city/economy mutation | none | none | PASS |
| Dynamite | instant building removal, no refund | Age I item list | existing authoritative demolition path | dedicated Walls behavior remains unknown | Walls exact handling | PASS |
| War Ensign | +25% march personnel limit | Age I item list | existing Rally Spot/march consumption path | not manually usable; consumed in march operation | none | PASS |
| Medals | Rank/Title material | Age I progression docs | persistent inventory consumed by promotion server rules | hero medal rewards/persuasion not added here | exact secondary medal uses | PASS |
| Aries Amulet | opens random Wheel of Fortune prize | Age I Wheel docs | recognized inventory definition but explicitly `implemented:false`; cannot be consumed | no fake wheel/prize table | exact 24-item selection/prize distribution | NOT IMPLEMENTED / NO FABRICATION |
| Hero Hunting | refresh Inn | Age I item docs | recognized but `implemented:false` | blocked rather than fabricate Inn candidates | exact Inn candidate RNG | NOT IMPLEMENTED / NO FABRICATION |
| Monetization | item mechanics independent of purchases | user requirement | no Cents/shop purchase requirement in item validation | acquisition economy not implemented | none | PASS |

## Item/buff + city teleportation — fidelity gate PASS
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Inventory/items | persistent quantities; concrete effects | historical item references | data-driven item definitions, authoritative consumption, idempotent use | reward acquisition tables remain separate | unresolved reward/drop probabilities | PASS |
| Timed buffs | persist by timestamp | historical item durations | database start/expiration timestamps; offline-safe | none for implemented effects | none | PASS |
| City Teleporter | consume item; choose state; random legal Flat; all dispatched/garrison troops home | Age I City Teleporter references | state-scoped legal-Flat selection, atomic tile claim | original server RNG not reconstructed | exact RNG | PASS |
| Advanced City Teleporter | chosen available Flat; troops home; 24h no marches after use | Age I Advanced City Teleporter references | exact Flat validation, atomic claim, persistent 24h city lock | none known | none | PASS |
| Teleport holdings | city/resource fields/troops remain; valleys lost | historical Q&A | releases Valley/Flat holdings, preserves city-local state/queues | none known | old-site Flat level provenance not established | PASS |
| Incoming marches | coordinate-targeted world behavior | Age I coordinate march model | existing marches retain old target coordinates after teleport | battle result depends on arrival resolver | exact original report wording | PASS |
| World occupancy | one city per coordinate | persistent map invariant | City (x,y) uniqueness + MapTile uniqueness + compare-and-swap Flat claim | none | none | PASS |
| Bookmarks | map coordinate bookmarks | coordinate bookmark model | remain attached to bookmarked coordinate, not silently moved with city | none | none | PASS |
| Beginner protection | do not invent teleport prohibition | official Age I tutorial documents combat BP restrictions | no extra teleport ban added | none | no verified Age I BP-specific teleport prohibition found | PASS/no fabricated rule |

## Beginner Protection — fidelity gate PASS
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Entry | new player/account begins protected | official Beginner Tutorial | player-level BeginnerProtection starts from account creation timestamp | legacy DBs need migration/backfill | none | PASS |
| Duration | 7 days | official Beginner Tutorial | persistent `expires_at = started_at + 7 days` | none | none | PASS |
| Early termination | any Town Hall reaches level 5 | official tutorial + Town Hall documentation | scans all owned cities; TH5 completion refreshes BP immediately | none | none | PASS |
| PvP city attacks | neither protected player nor opponents may attack protected player cities | official/community historical docs | server march creation rejects both directions | none | none | PASS |
| Scouting | protected player cannot scout cities; protected cities cannot be scouted | historical BP documentation | server rejects SCOUT against player/NPC city as applicable | none | none | PASS |
| NPC cities | protected player cannot attack/scout NPC cities | historical BP documentation | server blocks ATTACK/OCCUPY/SCOUT to NPC city | none | none | PASS |
| Wilderness | valleys/resource tiles remain scoutable/attackable | historical BP documentation | wilderness missions remain legal, including other players' valleys | none | none | PASS |
| Multi-city | second city does not restart protection | protection is player/account period | single player-level state | none | none | PASS |
| Expiration | authoritative state change + notification | Age I patch notes mention system mail | persisted end timestamp/reason + one system mail | exact historical mail prose not copied | exact prose | PASS |
| UI | visible BP state | historical protection status | HUD countdown refreshed from server | visual treatment original | exact original artwork | PASS |

## Complete UI fidelity pass — fidelity gate PASS
| Feature | Target Age 1 behavior | Evidence/source | Current implementation | Known differences | Unknown values | Test status |
|---|---|---|---|---|---|---|
| Global hierarchy | dense Town/City/Map client with city chooser, player/city status and chat visible | Age I UI references | persistent top resources/status, left city rail, Town/City/Map switch, right city overview/quick access, bottom operations/chat | original visual artwork/CSS only | exact pixel geometry | PASS |
| Town building clicks | each building is its functional gateway | Age I UI/building references | building-specific dispatch; Town Hall, Cottage, Warehouse, Inn, Embassy, Marketplace, Academy, Barracks, Feasting Hall, Rally Spot, Walls and previously implemented specialist buildings open their own interfaces | no copied Evony art | exact historical window skin | PASS |
| Empty plots | opens construction list | Age I guides | empty interior/resource plots retain construction behavior | none | none | PASS |
| City fields | resource management outside Town | Age I UI references | dedicated City view with production summary, field plots and production items | original presentation | exact historical background art | PASS |
| Map | every visible tile clickable; coordinate navigation | Age I UI references | full-tile hitbox, coordinates, pan/home/go, bookmarks; tile military actions route into real Rally Spot target flow | map art is original symbolic terrain UI | exact original tile art | PASS |
| Rally/marches | dispatch and movements located at Rally Spot | Rally Spot documentation | map actions prefill real Rally Spot; active operations remain visible globally | none mechanically | exact historical labels | PASS |
| Reports/Mail/Alliance/Chat | accessible from classic surrounding chrome, not primary world views | Age I UI references | right quick-access reports/mail/alliance; bottom Chat; Embassy links Alliance | original styling | exact original placement per client revision | PASS |
| Responsive | information reflows rather than disappears | project requirement | desktop side rails; tablet stacked right rail; mobile horizontal city chooser + stacked panels; scrollable map/modal | mobile adaptation is project-specific because Age I predated mobile | historical mobile layout N/A | PASS |
| Viewport audit | no clipped major controls | project requirement | tested 1366x768, 1440x900, 1920x1080, 2560x1440, 768x1024, 390x844; document/control horizontal overflow = 0 | map itself intentionally scrolls within its viewport on narrow screens | none | PASS |
