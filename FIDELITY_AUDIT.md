# FIDELITY_AUDIT.md

## Scope and standard

This is a source-level implementation audit, not a UI checklist. I searched the Python server, JavaScript client, HTML/CSS, game-definition JSON, tests, README and prior fidelity ledger for `TODO`, `FIXME`, `placeholder`, `mock`, `fake`, `stub`, `temporary`, `hardcoded`, `coming soon`, `not implemented`, `UNFINISHED`, `HISTORICAL_VALUE_UNKNOWN`, random generation, client-only state, dead buttons and empty handlers.

Classification meanings:

- **VERIFIED MATCH** — implemented server-authoritatively and the relevant historical behavior/value has supporting evidence.
- **IMPLEMENTED BUT DIFFERENT** — implemented behavior conflicts with historical evidence.
- **PARTIAL** — some of the historical mechanic exists, but a required part is absent.
- **PLACEHOLDER** — UI/data/code stands in for a mechanic without implementing it.
- **BROKEN** — intended implementation cannot perform its claimed behavior.
- **UNKNOWN HISTORICAL BEHAVIOR** — historical evidence is insufficient/conflicting; uncertainty is retained rather than guessed.
- **NOT IMPLEMENTED** — no authoritative implementation exists for the named historical mechanic.

This audit deliberately does **not** convert unknown behavior into guessed constants.

## Corrections made during this audit

1. Town Hall level 3–10 prerequisites were previously marked unknown even though historical tables document Walls Lv.1 through Lv.8. They are now data-driven and server-enforced. Town Hall Lv.3 iron was corrected from 400 to 500.
2. Town Hall Comforting and Levy were previously explicitly unfinished. Disaster Relief, Praying, Blessing, Population Raising and Gold/Food/Lumber/Stone/Iron levies are now authoritative, transactional and subject to the documented 15-minute cooldown.
3. Rally Spot Exercise previously returned `HISTORICAL_VALUE_UNKNOWN` without simulating. It now uses the same deterministic combat rules engine in a no-hero/no-tech exercise context.
4. Transport previously delivered the transport troops into the destination city and ended immediately. Historical transport unloads resources and the troops make the return trip. This is corrected.
5. `OCCUPY` could target cities. It is now restricted to Flats/Valleys.
6. `BATTLE_PENDING` was omitted from active march states. It now consumes an active march slot and keeps its army/hero occupied.
7. Allied reinforcement arrival previously had two representations and the march resolver did not create the Embassy garrison record. Allied arrivals now create the authoritative foreign garrison; own-city Reinforce transfers troops into the player's destination city.
8. Reinforcement upkeep previously charged the source city at 2x while the troops were garrisoned. The host city now feeds allied garrisons at normal in-city upkeep, while traveling/camped armies remain outside upkeep.
9. Marketplace delivery had a hardcoded 30-minute timestamp while the settlement function still claimed the time was historically unknown. Historical evidence supports 30 minutes; the value is centralized as `MARKETPLACE_DELIVERY_SECONDS`.
10. Captured NPC cities previously created the documented interior NPC composition but omitted their resource-field buildings. Captured NPCs now receive one Sawmill, one Ironmine, one Quarry and Farms in remaining available field plots, all at NPC level.
11. Generic building API payloads contained stale `UNFINISHED` text for systems that had subsequently been implemented. Those false claims were removed; dedicated building interfaces remain authoritative.
12. UI dead-button scan found all static buttons wired. Map action buttons now enter the Rally Spot rather than showing a fake action notice.

## Feature audit

| Feature | Classification | Audit finding |
|---|---|---|
| Server-authoritative resources | VERIFIED MATCH | Resource mutations occur on server models/services; client renders returned state. |
| Offline resource production | VERIFIED MATCH | Timestamp-based accrual persists across logout/restart. |
| Six-minute civic tick | VERIFIED MATCH | Loyalty/population/gold tick logic uses 360-second intervals. |
| Tax income | VERIFIED MATCH | Server tick applies current population and tax rate. |
| Loyalty target | VERIFIED MATCH | Moves toward `100 - tax - grievance`. |
| Population growth/decline | VERIFIED MATCH | Uses documented tax-dependent tick rates and loyalty occupancy target. |
| Town Hall tax control | VERIFIED MATCH | Server validated/persisted. |
| Town Hall production controls | VERIFIED MATCH | Server validated and incorporated into production. |
| Town Hall Comforting | VERIFIED MATCH | Corrected in this audit; 15-minute cooldown and documented costs/effects. |
| Town Hall Levy | VERIFIED MATCH | Corrected in this audit; documented amounts, -20 loyalty and cooldown. |
| Town Hall upgrade prerequisites | VERIFIED MATCH | Corrected to Walls Lv.1..8 for TH3..10. |
| Town Hall resource-field count | UNKNOWN HISTORICAL BEHAVIOR | Project currently uses 10/13/.../37. Surviving sources conflict with tables showing 16 at TH2 and 40 at TH10. Kept centralized; not silently changed. |
| One active building construction/city | VERIFIED MATCH | Server enforced. |
| Empty city plot construction | VERIFIED MATCH | Real construction options and server transaction. |
| Building upgrade timers | VERIFIED MATCH | Persistent server timestamps and resource/item costs. |
| Generic building interface status | VERIFIED MATCH | Stale false `UNFINISHED` labels removed; dedicated interfaces are used where implemented. |
| Cottage capacity | VERIFIED MATCH | Level table and population-capacity effect implemented. |
| Warehouse allocation/capacity | VERIFIED MATCH | Four-resource allocation; gold excluded. |
| Warehouse partial-load plunder ordering | UNKNOWN HISTORICAL BEHAVIOR | Exact distribution when carry capacity is below exposed resources remains unresolved; operation refuses to invent an ordering. |
| Inn candidate capacity | VERIFIED MATCH | Candidate slots follow Inn level. |
| Inn automatic/random candidate generator | UNKNOWN HISTORICAL BEHAVIOR | Exact historical RNG/stat generation not verified. Production does not use test fixture RNG. |
| Hero Hunting refresh | UNKNOWN HISTORICAL BEHAVIOR | Refresh trigger/item is represented, but exact candidate generation remains blocked by unknown generator. |
| Feasting Hall hero capacity | VERIFIED MATCH | One normal hero per level. |
| Hero salary | VERIFIED MATCH | 20 gold × hero level/hour is charged. |
| Hero rebellion when gold is exhausted | NOT IMPLEMENTED | Reports/history show rebellion can occur; exact departure selection/timing is not verified. Current economy clamps gold at zero. |
| Hero level/XP/attribute allocation | VERIFIED MATCH | Persistent and server-authoritative. |
| Hero redistribution | UNKNOWN HISTORICAL BEHAVIOR | Safe only where original base/allocation provenance exists; legacy records are blocked rather than guessed. |
| Hero item buffs | VERIFIED MATCH | Implemented items have timestamped gameplay effects. |
| Academy research ownership | VERIFIED MATCH | Research is player-wide with local Academy applicability rules. |
| Research timers with verified definitions | VERIFIED MATCH | Persistent queue/timestamps. |
| Research entries whose exact historical timer is unresolved | UNKNOWN HISTORICAL BEHAVIOR | Remain configuration-marked and cannot start with fabricated time. |
| Barracks troop definitions | VERIFIED MATCH | 12 Age I troop types and documented base stats/times. |
| Barracks training formula | VERIFIED MATCH | `Base × .9^MilitaryScience × .995^MayorAttack`. |
| Barracks independent queues | VERIFIED MATCH | Queue is tied to each Barracks. |
| Troop population consumption | VERIFIED MATCH | Recruitment consumes civilian population; troops are not counted as current civilian population. |
| Troop food upkeep | VERIFIED MATCH | Native troops normal; outside armies 2x; allied garrison host upkeep corrected in this audit. |
| Refuge/starvation troop losses | NOT IMPLEMENTED | Historical behavior (troops leave; grievance/report) is known, but exact loss quantity/timing remains unverified. No guessed loss algorithm is present. |
| Rally Spot wave/troop limits | VERIFIED MATCH | Level controls march slots and 10,000 troops/level; War Ensign path exists. |
| Rally Spot gates | VERIFIED MATCH | Persistent server state used by defensive/scouting infrastructure. |
| Rally Spot Exercise | VERIFIED MATCH | Corrected from nonfunctional unknown response to deterministic combat simulation. |
| Medic Camp wounded storage | VERIFIED MATCH | Wounded troops persist. |
| Medic Camp exact healing gold cost | UNKNOWN HISTORICAL BEHAVIOR | Healing cost is deliberately blocked where exact cost is unresolved. |
| Map distance/travel | UNKNOWN HISTORICAL BEHAVIOR | Euclidean coordinate distance and documented troop speeds are implemented; exact original server rounding remains insufficiently verified. |
| March food requirement | UNKNOWN HISTORICAL BEHAVIOR | Uses troop upkeep over travel/camp duration; exact original dispatch rounding/formula remains under-documented. |
| Transport | VERIFIED MATCH | Corrected: resources unload, troops return, same return travel duration. |
| Reinforce own city | VERIFIED MATCH | Transfers troops/resources into owned destination city. |
| Reinforce allied city | VERIFIED MATCH | Embassy permission/capacity and same-alliance requirement; distinct garrison; host feeds troops. |
| Friendly/alliance attack restriction | VERIFIED MATCH | Server mission legality prevents attacks/scouts against friendly/allied ownership. |
| OCCUPY target legality | VERIFIED MATCH | Corrected to Flat/Valley only. |
| March recall | VERIFIED MATCH | Server transition to returning with timestamp. |
| Active march slot accounting | VERIFIED MATCH | Includes marching, pending arrival, returning, camped, garrisoned and battle-pending. |
| Wilderness ownership/bonuses | VERIFIED MATCH | City slot consumption and typed resource bonuses implemented. |
| Wilderness native defender generation | UNKNOWN HISTORICAL BEHAVIOR | Exact randomized level composition/regeneration distribution is not verified. |
| Wilderness daily level cycle | UNKNOWN HISTORICAL BEHAVIOR | Historical cycling exists; exact maintenance clock/transition behavior remains unresolved and is not fabricated. |
| Flat city founding | VERIFIED MATCH | Requires conquered Flat, title slot, 250 Workers and required resources; creates independent city state. |
| Player city abandonment -> NPC | VERIFIED MATCH | Uses source Flat level provenance where available. |
| Legacy city abandonment without Flat provenance | UNKNOWN HISTORICAL BEHAVIOR | Refuses to invent NPC level. |
| NPC fixed composition | VERIFIED MATCH | Interior structures + 20 cottages, no Warehouse; exterior resource composition corrected in this audit. |
| NPC resources/regeneration | VERIFIED MATCH | Level tables and 8-hour resource regeneration implemented. |
| NPC troop/fortification regeneration | VERIFIED MATCH | 10% per six-minute interval/full hour. |
| NPC military technologies | VERIFIED MATCH | NPC level used as technology level; historical accounts of NPC10 max tech support level-matched model. |
| NPC loyalty regeneration | VERIFIED MATCH | +3 per six-minute interval during capture state. |
| NPC attack combat | VERIFIED MATCH | Uses deterministic combat engine and persists defender/fortification losses. |
| NPC loyalty loss per successful attack | UNKNOWN HISTORICAL BEHAVIOR | Current loyalty decrement bands are not sufficiently verified. This value must remain treated as an unresolved fidelity risk. |
| NPC capture | VERIFIED MATCH | City-slot requirement, loyalty zero and documented NPC building/resource composition. |
| Player-city attack dispatch | VERIFIED MATCH | Server can create legal attack march and reserve troops/hero. |
| Player-city battle resolution | NOT IMPLEMENTED | Arrival creates `BATTLE_PENDING`; complete gates/walls/native troops/reinforcements/casualty/plunder/loyalty/conquest resolution is not yet authoritative. **Do not call PvP combat complete.** |
| Player-city scouting resolution | NOT IMPLEMENTED | Arrival currently produces an explicit unknown report instead of resolving gates/anti-scouting/defender scouts. |
| Wilderness combat through dedicated combat engine | VERIFIED MATCH | Defender combat/occupation path exists for wilderness. |
| Combat opening distance/ranged/round cap | VERIFIED MATCH | Dedicated deterministic rules engine implements documented core rules. |
| Hero Attack combat coefficient | UNKNOWN HISTORICAL BEHAVIOR | Configurable mode; exact coefficient is not asserted as historical fact. |
| Combat target-selection edge cases | UNKNOWN HISTORICAL BEHAVIOR | Some tie-breaking remains configurable/uncertain. |
| Player battle Honor calculation | NOT IMPLEMENTED | Exact Age I formula is not established; no invented points are awarded. |
| Player battle Prestige calculation | NOT IMPLEMENTED | Exact battle award/loss formula is not established; no invented points are awarded. |
| Wounded percentage vs Honor | NOT IMPLEMENTED | Historical dependency is documented, but exact formula is not implemented. |
| Walls capacity/durability | VERIFIED MATCH | Persistent wall level/capacity/durability. |
| Fortification construction | VERIFIED MATCH | Costs, space, queues and prerequisites server-enforced. |
| Fortification combat core | VERIFIED MATCH | Trap/Abatis/Tower/Log/Trebuchet types feed combat rules. |
| Machinery post-battle repair | NOT IMPLEMENTED | Research multiplier helper exists, but full player-city post-battle repair persistence is absent with PvP resolver. |
| Beacon incoming warnings | VERIFIED MATCH | Level-based incoming information exists. |
| Scouting troop quantity bands | VERIFIED MATCH | Few/Pack/Lots/Horde/Throng/Swarm/Zounds/Legion/Bulk/Giga. |
| Scout detail gate | VERIFIED MATCH | Informatics, Beacon Tower and 10 scouts/target level gate are implemented. |
| Hero Intelligence exact scouting contribution | UNKNOWN HISTORICAL BEHAVIOR | Historical contribution is documented but exact coefficient is not verified; remains explicit unknown. |
| Marketplace order book | VERIFIED MATCH | Player buy/sell orders, matching, fees and cancellation. |
| Marketplace delivery | VERIFIED MATCH | 30-minute bought-resource delivery centralized during this audit. |
| Marketplace Trade reports | NOT IMPLEMENTED | Specialized persistent trade-report category is not currently wired from market settlement. |
| Alliance creation/membership | VERIFIED MATCH | Embassy gates, one alliance/player and server permissions. |
| Alliance ranks/permissions | VERIFIED MATCH | Ranks are not cosmetic; promotion/demotion/expel/invite permissions enforced server-side. |
| Alliance diplomacy | VERIFIED MATCH | Friendly/hostile relation state affects mission legality. |
| Alliance chat/mail | VERIFIED MATCH | Membership/permissions validated server-side. |
| World/alliance/private chat | VERIFIED MATCH | Sender/channel/recipient/timestamp persisted; rate limits/block/mute/moderation infrastructure present. |
| Persistent player mail | VERIFIED MATCH | Inbox/sent/reply/delete/read status/recipient lookup/rate validation. |
| Battle/Scout/Transport/Reinforcement/System report persistence | VERIFIED MATCH | Server event snapshots persist with read/delete state. |
| Player-city Battle report completion | NOT IMPLEMENTED | Depends on missing player-city battle resolver. |
| Player-city Scout report completion | NOT IMPLEMENTED | Depends on missing anti-scouting/city scout resolver. |
| Refuge report | NOT IMPLEMENTED | Depends on unresolved starvation-loss mechanic. |
| Hero rebellion report | NOT IMPLEMENTED | Depends on unresolved insufficient-gold hero departure mechanic. |
| Quest definitions/state evaluation | VERIFIED MATCH | Requirements derive from actual state; one-time claims server enforced. |
| Quest entries with unverified reward tables | UNKNOWN HISTORICAL BEHAVIOR | Reward is explicitly withheld/marked unknown rather than invented. |
| Prestige progression | VERIFIED MATCH | Persistent progression value and verified quest/promotion uses. |
| Rank/Title promotion | VERIFIED MATCH | Server validates medal/resource/population requirements from data. |
| City ownership limits | VERIFIED MATCH | Title controls city cap up to ten. |
| Items inventory/quantity/use | VERIFIED MATCH | Persistent server inventory and idempotent use. |
| Timed item buffs | VERIFIED MATCH | Timestamped and offline-safe. |
| Aries Amulet/Wheel exact prize distribution | UNKNOWN HISTORICAL BEHAVIOR | Exact wheel slot/prize distribution not verified; no fabricated random prize table. |
| City Teleporter | VERIFIED MATCH | State-scoped unoccupied Flat, troops/garrisons home, atomic world update. |
| Advanced City Teleporter | VERIFIED MATCH | Exact Flat selection and persistent 24-hour city restriction. |
| Teleport incoming marches | VERIFIED MATCH | Existing marches remain coordinate-targeted rather than following city. |
| Beginner Protection | VERIFIED MATCH | Seven days or any TH5; server attack/scout enforcement and persisted end state. |
| Multi-city independent state | VERIFIED MATCH | Buildings/fields/resources/pop/troops/heroes/queues/fortifications/marches are city-specific. |
| UI building-click rule | VERIFIED MATCH | Occupied plot dispatches to building-specific interface. |
| UI empty-plot rule | VERIFIED MATCH | Empty plot opens authoritative construction. |
| UI map click rule | VERIFIED MATCH | Every rendered tile has a full hitbox. |
| UI static buttons | VERIFIED MATCH | Audit found no unwired static button IDs. |
| Client-only gameplay state | VERIFIED MATCH | Client state is presentation/session selection only; mutations call server endpoints. |
| Responsive information hierarchy | VERIFIED MATCH | Prior viewport audit covers required desktop/tablet/mobile sizes without document-level clipping. |
| Authentication/account authorization | NOT IMPLEMENTED | API uses player IDs and development session; production-grade authenticated account binding is absent. |
| Database schema migrations | NOT IMPLEMENTED | SQLAlchemy creates current schema; upgrade migrations for old SQLite files are absent. |
| Background scheduler | NOT IMPLEMENTED | Timed systems settle lazily on authoritative reads/actions; no independent scheduler processes elapsed events without a request. |

## Literal marker scan

### TODO / FIXME / coming soon / stub / temporary
No production-code occurrences requiring implementation were found.

### placeholder / mock / fake
The remaining `fake` occurrences are test names/comments asserting that the server must **not** fabricate unknown results. The HTML `placeholder` occurrence is the normal input `placeholder` attribute. No production fake/mock state was found.

### hardcoded / random test values
No production random-number generator is used for historical mechanics whose RNG is unknown. `seed_verified_candidate_fixture` is explicitly development/test-only. Fixed historical constants are centralized where verified; this audit moved Marketplace's 30-minute delivery to a named constant. Development seed resources/players are test/dev fixtures, not production formulas.

### stale “not implemented” text
Stale generic building-interface messages for Marketplace, Rally Spot, Town Hall and Barracks were removed because dedicated implementations now exist. Remaining non-implemented mechanics are listed explicitly above rather than hidden behind UI.

### dead buttons / empty handlers
Static HTML button IDs were cross-checked against JavaScript handlers. No static dead button was found. Dynamically generated actions were reviewed; map military actions enter the real Rally Spot.

## Historical uncertainty registry

The following must stay configuration-driven or explicitly blocked until stronger Age I evidence exists:

- Town Hall resource-field count conflict between surviving sources and the project's existing 10→37 table.
- Warehouse partial-load plunder ordering.
- Inn random candidate level/stat generator and immediate replacement RNG.
- Hero rebellion selection/timing when gold is exhausted.
- Refuge troop-loss quantity/timing when food is exhausted.
- Exact Medic Camp healing-gold formula.
- Exact march-food and travel rounding details.
- Wilderness native defender random generation and daily maintenance clock.
- NPC loyalty decrement formula after successful attacks.
- Hero Attack combat coefficient and combat target tie-break edge cases.
- Hero Intelligence scouting coefficient.
- Battle-derived Prestige/Honor and wounded-percent formulas.
- Wheel of Fortune/Aries Amulet exact prize distribution.

## Release gate

This audit **does not classify the whole recreation as complete**. Core city/economy/building/research/training/map/NPC/alliance/mail/chat/quest/progression/item/teleport/BP systems are substantially implemented, but the following historically important systems are still **NOT IMPLEMENTED** and therefore block a claim of complete Age I mechanical fidelity:

1. Full player-city battle resolution and conquest.
2. Player-city anti-scouting/scout resolution.
3. Refuge/starvation troop loss and its report.
4. Hero rebellion on insufficient gold and its report.
5. Battle-derived Honor/Prestige/wounded recovery.
6. Marketplace Trade reports.
7. Production authentication/authorization and schema migrations are engineering gaps (not Age I mechanics).
8. Independent background processing is absent; timed state is currently lazy-settled.

No new gameplay feature should be added before the mechanical blockers above are resolved or a verified historical basis is established for the unknown portions they depend on.
