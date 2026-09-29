"""Pure deterministic Evony Age I combat simulation.

No SQLAlchemy/UI imports.  All disputed behavior lives in Age1CombatRules.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from math import ceil
from copy import deepcopy
from typing import Any

INFANTRY={"worker","warrior","scout","pikeman","swordsman","archer","transporter"}
MOUNTED={"cavalry","cataphract"}
SIEGE={"ballista","battering_ram","catapult"}
RANGED={"archer","ballista","catapult"}
FORTS={"trap","abatis","archer_tower","rolling_log","defensive_trebuchet"}

@dataclass(frozen=True)
class Age1CombatRules:
    ruleset_id:str="age1-community-documented-v1"
    max_rounds:int=100
    opening_distance_base:int=200
    simultaneous_fire:bool=True
    ranged_damage_modifier:float=.5
    military_tradition_per_level:float=.05
    iron_working_per_level:float=.05
    medicine_per_level:float=.05
    archery_range_per_level:float=.05
    compass_speed_per_level:float=.10
    horseback_speed_per_level:float=.05
    # Community documentation agrees Hero Attack modifies combat, but surviving sources
    # do not establish one exact multiplier with the same confidence as technologies.
    hero_attack_mode:str="HISTORICAL_VALUE_UNKNOWN"
    hero_attack_per_point:float|None=None
    target_rule:str="NEAREST_IN_RANGE_THEN_DOCUMENTED_PRIORITY"
    movement_rule:str="MOVE_TOWARD_NEAREST_ENEMY_UNTIL_IN_RANGE"
    one_shot_fortifications:bool=True
    obstacle_casualty_rule:str="ONE_DEVICE_ONE_ELIGIBLE_CASUALTY_PROPORTIONAL"
    defender_wins_round_cap:bool=True
    # Published community combat formula and interaction table.
    casualty_rounding:str="CEIL_ANY_PARTIAL_UNIT"
    disputed_notes:dict=field(default_factory=lambda:{
      "hero_attack":"Hero Attack is documented as affecting army combat, but exact Age I multiplier is not sufficiently verified.",
      "target_selection":"Layering proves one stack targets one enemy stack per round; exact tie-break priority is community-derived/disputed.",
      "movement":"Range/speed round movement is documented; exact movement ordering at equal distances is disputed.",
      "fortifications":"Trap/Abatis one-use eligibility is documented. Default one-device/one-casualty proportional allocation follows surviving Trap observations; exact overmatch behavior and Abatis loss curve remain disputed and configurable.",
      "honor_prestige":"Exact PvP honor/prestige formulas are not sufficiently verified and are not fabricated.",
      "plunder":"Capacity/protection inputs can be resolved deterministically, but city post-battle plunder ordering needs the campaign adapter."
    })

@dataclass
class BattleStack:
    unit:str
    count:int
    side:str
    position:float
    life:float
    attack:float
    defense:float
    range:float
    speed:float
    fortification:bool=False
    one_shot:bool=False
    fired:bool=False

@dataclass
class BattleResult:
    ruleset_id:str
    winner:str
    reason:str
    rounds:int
    opening_distance:float
    attacker_initial:dict
    defender_initial:dict
    attacker_survivors:dict
    defender_survivors:dict
    attacker_losses:dict
    defender_losses:dict
    fortification_survivors:dict
    round_log:list
    plunder:dict
    honor_delta:dict
    prestige_delta:dict
    uncertainties:list

# Community-documented interaction multipliers from Age I combat research.
def interaction(attacker:str, defender:str)->float:
    if defender=="worker": return .96
    if defender=="scout": return .97
    if defender=="pikeman" and attacker=="swordsman": return 1.10
    if defender=="archer" and attacker in {"cavalry","cataphract"}: return 1.20
    if defender=="cavalry":
        if attacker=="pikeman": return 1.80
        if attacker=="archer": return 2.00
        if attacker=="ballista": return 2.00
        if attacker=="catapult": return 2.00
    if defender=="cataphract" and attacker=="pikeman": return 1.80
    return 1.0

def _hero_attack_multiplier(hero_attack:int,rules:Age1CombatRules)->float:
    if rules.hero_attack_mode=="DISABLED_UNTIL_VERIFIED": return 1.0
    if rules.hero_attack_mode=="LINEAR_CONFIGURED" and rules.hero_attack_per_point is not None:
        return 1.0+hero_attack*rules.hero_attack_per_point
    # Explicitly neutral rather than inventing a coefficient.
    return 1.0

def _stats(unit,base,tech,hero_attack,rules,wall_level=0):
    atk=base["attack"]*(1+tech.get("military_tradition",0)*rules.military_tradition_per_level)*_hero_attack_multiplier(hero_attack,rules)
    defense=base["defense"]*(1+tech.get("iron_working",0)*rules.iron_working_per_level)
    life=base["life"]*(1+tech.get("medicine",0)*rules.medicine_per_level)
    rng=float(base["range"]); speed=float(base["speed"])
    if unit in RANGED:rng*=1+tech.get("archery",0)*rules.archery_range_per_level
    if unit=="archer_tower":rng=1300*(1+.05*(wall_level+tech.get("archery",0)))
    if unit in INFANTRY:speed*=1+tech.get("compass",0)*rules.compass_speed_per_level
    if unit in MOUNTED|SIEGE:speed*=1+tech.get("horseback_riding",0)*rules.horseback_speed_per_level
    return life,atk,defense,rng,speed

FORT_STATS={
 "trap":{"life":1,"attack":0,"defense":0,"range":5000,"speed":0},
 "abatis":{"life":1,"attack":0,"defense":0,"range":5000,"speed":0},
 "archer_tower":{"life":2000,"attack":300,"defense":360,"range":1300,"speed":0},
 "rolling_log":{"life":1,"attack":500,"defense":0,"range":1300,"speed":0},
 "defensive_trebuchet":{"life":1,"attack":800,"defense":0,"range":5000,"speed":0},
}
TARGET_PRIORITY=["scout","cavalry","cataphract","pikeman","swordsman","warrior","worker","archer","transporter","ballista","battering_ram","catapult","archer_tower","rolling_log","defensive_trebuchet","trap","abatis"]

def _eligible(attacker:BattleStack,target:BattleStack)->bool:
    if attacker.unit=="trap": return target.unit in {"worker","warrior","scout","pikeman","swordsman","archer"}
    if attacker.unit=="abatis": return target.unit in MOUNTED
    if attacker.unit=="defensive_trebuchet": return target.unit in SIEGE
    return True

def _target(stack,enemies,rules):
    living=[e for e in enemies if e.count>0 and _eligible(stack,e)]
    if not living:return None
    # Nearest enemy layer is the mechanically important layering behavior.
    distances=[(abs(stack.position-e.position),TARGET_PRIORITY.index(e.unit) if e.unit in TARGET_PRIORITY else 999,e.unit,e) for e in living]
    distances.sort(key=lambda x:(x[0],x[1],x[2]))
    return distances[0][3]

def _kill_count(attacker,target,rules):
    if attacker.count<=0:return 0
    if attacker.unit in {"trap","abatis"}:
        if rules.obstacle_casualty_rule=="ONE_DEVICE_ONE_ELIGIBLE_CASUALTY_PROPORTIONAL":
            return min(target.count,attacker.count)
        if rules.obstacle_casualty_rule=="DISABLED_UNTIL_VERIFIED":
            return 0
        raise ValueError("unknown obstacle_casualty_rule")
    ranged=rules.ranged_damage_modifier if attacker.unit in RANGED else 1.0
    effective_def=max(0.0,1-target.defense/1000.0)
    raw=attacker.count*attacker.attack*interaction(attacker.unit,target.unit)*ranged*effective_def/target.life
    return min(target.count,max(0,ceil(raw)))

def _make_stacks(side,army,defs,tech,hero,rules,position,wall_level=0,forts=None):
    out=[]
    for unit,count in sorted(army.items()):
        if count<=0:continue
        b=defs[unit]; base={"life":b["life"],"attack":b["attack"],"defense":b["defense"],"range":b["range"],"speed":b["speed_miles_per_1000_minutes"]}
        life,atk,deff,rng,spd=_stats(unit,base,tech,hero,rules,wall_level)
        out.append(BattleStack(unit,count,side,position,life,atk,deff,rng,spd))
    if side=="defender":
      for unit,count in sorted((forts or {}).items()):
        if count<=0:continue
        b=FORT_STATS[unit];life,atk,deff,rng,spd=_stats(unit,b,tech,hero,rules,wall_level)
        out.append(BattleStack(unit,count,side,position,life,atk,deff,rng,spd,True,unit in {"trap","abatis","rolling_log","defensive_trebuchet"}))
    return out

def simulateBattle(input:dict, ruleset:Age1CombatRules|None=None)->BattleResult:
    rules=ruleset or Age1CombatRules()
    defs=input["unit_definitions"]
    ai={k:int(v) for k,v in input["attacker"]["troops"].items() if int(v)>0};di={k:int(v) for k,v in input["defender"]["troops"].items() if int(v)>0}
    forts={k:int(v) for k,v in input["defender"].get("fortifications",{}).items() if int(v)>0}
    at=input["attacker"].get("technologies",{});dt=input["defender"].get("technologies",{})
    ah=int(input["attacker"].get("hero_attack",0));dh=int(input["defender"].get("hero_attack",0));wall=int(input["defender"].get("wall_level",0))
    # Determine modified maximum range before placing stacks.
    ranges=[]
    for u in ai:ranges.append(_stats(u,{"life":defs[u]["life"],"attack":defs[u]["attack"],"defense":defs[u]["defense"],"range":defs[u]["range"],"speed":defs[u]["speed_miles_per_1000_minutes"]},at,ah,rules)[3])
    for u in di:ranges.append(_stats(u,{"life":defs[u]["life"],"attack":defs[u]["attack"],"defense":defs[u]["defense"],"range":defs[u]["range"],"speed":defs[u]["speed_miles_per_1000_minutes"]},dt,dh,rules,wall)[3])
    for u in forts:ranges.append(_stats(u,FORT_STATS[u],dt,dh,rules,wall)[3])
    opening=rules.opening_distance_base+(max(ranges) if ranges else 0)
    A=_make_stacks("attacker",ai,defs,at,ah,rules,0)
    D=_make_stacks("defender",di,defs,dt,dh,rules,opening,wall,forts)
    log=[]
    for rnd in range(1,rules.max_rounds+1):
      if not any(x.count for x in A) or not any(x.count for x in D):break
      events=[]; planned=[]
      # Movement first for stacks that cannot currently attack their selected nearest layer.
      for stack,enemies,direction in [(x,D,1) for x in A]+[(x,A,-1) for x in D]:
        if stack.count<=0 or stack.fortification:continue
        target=_target(stack,enemies,rules)
        if target and abs(stack.position-target.position)>stack.range:
          before=stack.position
          move=min(stack.speed,max(0,abs(stack.position-target.position)-stack.range))
          stack.position+=direction*move
          events.append({"phase":"move","unit":stack.unit,"side":stack.side,"from":before,"to":stack.position})
      # Simultaneous targeting/fire from pre-casualty counts.
      for stack,enemies in [(x,D) for x in A]+[(x,A) for x in D]:
        if stack.count<=0 or (stack.one_shot and stack.fired):continue
        if stack.unit in {"trap","abatis"} and rules.obstacle_casualty_rule=="ONE_DEVICE_ONE_ELIGIBLE_CASUALTY_PROPORTIONAL":
          eligible=[e for e in enemies if e.count>0 and _eligible(stack,e) and abs(stack.position-e.position)<=stack.range]
          if eligible:
            devices=stack.count
            total=sum(e.count for e in eligible)
            allocations=[]
            used=0
            for e in eligible:
              k=min(e.count,int(devices*e.count/total));allocations.append([e,k]);used+=k
            # Deterministic remainder to largest eligible layers, then documented priority.
            for e,k in sorted(allocations,key=lambda z:(-z[0].count,TARGET_PRIORITY.index(z[0].unit) if z[0].unit in TARGET_PRIORITY else 999)):
              if used>=devices:break
              extra=min(e.count-k,devices-used)
              for row in allocations:
               if row[0] is e:row[1]+=extra;break
              used+=extra
            for e,k in allocations:
              if k:planned.append((e,k,stack))
            stack.fired=True
          continue
        target=_target(stack,enemies,rules)
        if target and abs(stack.position-target.position)<=stack.range:
          kills=_kill_count(stack,target,rules)
          if kills:planned.append((target,kills,stack))
      losses={}
      for target,kills,source in planned:
        actual=min(target.count,kills);target.count-=actual
        if source.one_shot:source.fired=True;source.count=0
        losses[(target.side,target.unit)]=losses.get((target.side,target.unit),0)+actual
        events.append({"phase":"attack","attacker_side":source.side,"attacker":source.unit,"target":target.unit,"target_side":target.side,"kills":actual,"distance":abs(source.position-target.position),"attack":source.attack,"target_defense":target.defense,"target_life":target.life,"interaction":interaction(source.unit,target.unit),"ranged_modifier":rules.ranged_damage_modifier if source.unit in RANGED else 1.0})
      log.append({"round":rnd,"events":events,"losses":{f"{k[0]}:{k[1]}":v for k,v in losses.items()}})
    rounds=len(log); aliveA=any(x.count>0 for x in A);aliveD=any(x.count>0 for x in D)
    if aliveA and not aliveD:winner,reason="attacker","DEFENDER_ELIMINATED"
    elif aliveD and not aliveA:winner,reason="defender","ATTACKER_ELIMINATED"
    elif not aliveA and not aliveD:winner,reason="defender","MUTUAL_ELIMINATION_DEFENDER_HOLDS"
    elif aliveA and aliveD and rounds>=rules.max_rounds:winner,reason="defender","ROUND_CAP_DEFENDER_WINS"
    else:winner,reason="draw","NO_COMBATANTS"
    def surv(stacks,fort=False):return {x.unit:x.count for x in stacks if x.count>0 and x.fortification==fort}
    AS=surv(A);DS=surv(D);FS=surv(D,True)
    def losses(initial,survivors):return {k:int(v)-int(survivors.get(k,0)) for k,v in initial.items()}
    uncertainties=[k for k,v in rules.disputed_notes.items() if k in {"hero_attack","target_selection","movement","fortifications","honor_prestige","plunder"}]
    return BattleResult(rules.ruleset_id,winner,reason,rounds,opening,deepcopy(ai),deepcopy(di),AS,DS,losses(ai,AS),losses(di,DS),FS,log,{},{"attacker":"HISTORICAL_VALUE_UNKNOWN","defender":"HISTORICAL_VALUE_UNKNOWN"},{"attacker":"HISTORICAL_VALUE_UNKNOWN","defender":"HISTORICAL_VALUE_UNKNOWN"},uncertainties)

# snake_case alias for Python callers; requested public contract remains simulateBattle.
simulate_battle=simulateBattle
