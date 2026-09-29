import json
from pathlib import Path
from sqlalchemy import select,func,or_,and_
from sqlalchemy.exc import IntegrityError
from .models import OperationRequest,Resource,TroopQuantity,PlayerItem

def idempotent_operation(session,player_id,key,operation,fn):
 existing=session.scalar(select(OperationRequest).where(OperationRequest.player_id==player_id,OperationRequest.idempotency_key==key))
 if existing: return existing.response
 try:
  with session.begin_nested():
   marker=OperationRequest(player_id=player_id,idempotency_key=key,operation=operation,response={})
   session.add(marker); session.flush()
   response=fn(); marker.response=response
  session.commit(); return response
 except IntegrityError:
  session.rollback()
  existing=session.scalar(select(OperationRequest).where(OperationRequest.player_id==player_id,OperationRequest.idempotency_key==key))
  if existing:return existing.response
  raise

def spend_resources(session,city_id,costs):
 settle_economy(session,city_id)
 rows={r.kind:r for r in session.scalars(select(Resource).where(Resource.city_id==city_id)).all()}
 for kind,amount in costs.items():
  if amount<0: raise ValueError('negative cost')
  if kind not in rows or rows[kind].quantity<amount: raise ValueError(f'insufficient {kind}')
 for kind,amount in costs.items(): rows[kind].quantity-=amount

def add_troops(session,city_id,troop_key,quantity):
 if quantity<=0: raise ValueError('quantity must be positive')
 row=session.scalar(select(TroopQuantity).where(TroopQuantity.city_id==city_id,TroopQuantity.troop_type_key==troop_key))
 if not row: row=TroopQuantity(city_id=city_id,troop_type_key=troop_key,quantity=0); session.add(row)
 row.quantity+=quantity

from datetime import datetime, timezone, timedelta
from .models import City, Building, BuildingLevel, ConstructionQueue, Technology, CityEconomyState
from .definitions import DATA, building_level

def cottage_population_capacity(session, city_id):
 total=0
 buildings=session.scalars(select(Building).where(Building.city_id==city_id,Building.plot_kind=='CITY',Building.definition_key=='cottage')).all()
 for b in buildings:
  level=current_level(session,b)
  spec=building_level('cottage',level) if level>0 else None
  if spec: total+=spec['population_capacity']
 return total

def sync_population_capacity(session, city_id):
 from .models import PopulationState
 pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id))
 if not pop:
  pop=PopulationState(city_id=city_id); session.add(pop); session.flush()
 limit=cottage_population_capacity(session,city_id)
 pop.population_limit=limit
 # A completed Cottage changes housing capacity immediately, but Age I population
 # itself changes on city ticks; never fabricate instant residents.
 pop.population=min(pop.population,limit)
 pop.idle_population=min(pop.idle_population,pop.population)
 city=session.get(City,city_id)
 if city:
  city.population=pop.population; city.idle_population=pop.idle_population
 return limit

def _check_building_prerequisites(session,city_id,spec):
 buildings=session.scalars(select(Building).where(Building.city_id==city_id,Building.plot_kind=='CITY')).all()
 for req in spec.get('prerequisites',[]):
  found=max([current_level(session,b) for b in buildings if b.definition_key==req['building']] or [0])
  if found<req['level']: raise ValueError(f"Requires {DATA['buildings'][req['building']]['name']} Lv.{req['level']}")

def _spend_item_cost(session,player_id,spec):
 for item_key,amount in spec.get('item_cost',{}).items():
  row=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==item_key))
  if not row or row.quantity<amount: raise ValueError(f'insufficient {item_key}')
  row.quantity-=amount

def complete_construction(session, city_id):
 now=datetime.now(timezone.utc)
 rows=session.scalars(select(ConstructionQueue).where(ConstructionQueue.city_id==city_id,ConstructionQueue.status=='ACTIVE')).all()
 changed=False
 for q in rows:
  end=q.completes_at
  if end.tzinfo is None: end=end.replace(tzinfo=timezone.utc)
  if end<=now:
   b=session.get(Building,q.building_id)
   if b and b.plot_kind=='FIELD': accrue_resources(session,city_id,end)
   lv=session.scalar(select(BuildingLevel).where(BuildingLevel.building_id==b.id))
   if not lv: lv=BuildingLevel(building_id=b.id,level=q.target_level); session.add(lv)
   else: lv.level=q.target_level
   b.level=q.target_level; q.status='COMPLETE'; changed=True
   if b.definition_key=='town_hall':
    sync_exterior_field_unlocks(session,city_id)
    refresh_beginner_protection(session,session.get(City,city_id).player_id,end)
   if b.definition_key=='cottage': sync_population_capacity(session,city_id)
 if changed: session.commit()

def current_level(session, building):
 lv=session.scalar(select(BuildingLevel).where(BuildingLevel.building_id==building.id)); return lv.level if lv else building.level

def construction_options(session,city_id):
 complete_demolition(session,city_id)
 complete_construction(session,city_id)
 buildings=session.scalars(select(Building).where(Building.city_id==city_id,Building.plot_kind=='CITY')).all()
 levels={b.definition_key:max([current_level(session,x) for x in buildings if x.definition_key==b.definition_key] or [0]) for b in buildings}
 counts={}
 for b in buildings: counts[b.definition_key]=counts.get(b.definition_key,0)+1
 out=[]
 for key,d in DATA['buildings'].items():
  if d.get('location')!='CITY': continue
  spec=building_level(key,1); unmet=[]
  if not spec: unmet.append('Level 1 historical cost/time table not yet verified')
  if d.get('repeatability')=='HISTORICAL_VALUE_UNKNOWN' and counts.get(key,0)>0: unmet.append('Additional-instance restriction is HISTORICAL_VALUE_UNKNOWN')
  if spec:
   for req in spec.get('prerequisites',[]):
    if 'building' in req:
     if levels.get(req['building'],0)<req['level']: unmet.append(f"Requires {DATA['buildings'].get(req['building'],{}).get('name',req['building'].replace('_',' ').title())} Lv.{req['level']}")
    elif 'technology' in req:
     if effective_technology_level(session,city_id,req['technology'])<req['level']: unmet.append(f"Requires {req['technology'].replace('_',' ').title()} Lv.{req['level']}")
  out.append({'key':key,'name':d['name'],'purpose':d['purpose'],'cost':spec['cost'] if spec else 'HISTORICAL_VALUE_UNKNOWN','construction_seconds':spec['seconds'] if spec else 'HISTORICAL_VALUE_UNKNOWN','prerequisites':spec.get('prerequisites',[]) if spec else [],'available':not unmet,'unmet_requirements':unmet})
 return out

def start_construction(session,player_id,city_id,plot_index,building_key,idempotency_key):
 def work():
  complete_construction(session,city_id)
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned by player')
  if plot_index<1 or plot_index>32: raise ValueError('only the 32 general interior plots are constructible')
  if session.scalar(select(Building).where(Building.city_id==city_id,Building.plot_kind=='CITY',Building.plot_index==plot_index)): raise ValueError('plot occupied')
  if session.scalar(select(ConstructionQueue).where(ConstructionQueue.city_id==city_id,ConstructionQueue.status=='ACTIVE')): raise ValueError('Age I permits only one active building construction per city')
  option=next((x for x in construction_options(session,city_id) if x['key']==building_key),None)
  if not option: raise ValueError('unknown building')
  if not option['available']: raise ValueError('; '.join(option['unmet_requirements']))
  spec=building_level(building_key,1); spend_resources(session,city_id,spec['cost'])
  b=Building(city_id=city_id,plot_kind='CITY',plot_index=plot_index,definition_key=building_key,level=0); session.add(b); session.flush(); session.add(BuildingLevel(building_id=b.id,level=0))
  now=datetime.now(timezone.utc); effective_seconds=mayor_construction_seconds(session,city_id,spec['seconds']); q=ConstructionQueue(city_id=city_id,building_id=b.id,target_level=1,started_at=now,completes_at=now+timedelta(seconds=effective_seconds),status='ACTIVE'); session.add(q); session.flush()
  return {'building_id':b.id,'queue_id':q.id,'plot_index':plot_index,'definition_key':building_key,'target_level':1,'completes_at':q.completes_at.isoformat()}
 return idempotent_operation(session,player_id,idempotency_key,'START_CONSTRUCTION',work)

def start_upgrade(session,player_id,city_id,building_id,idempotency_key):
 def work():
  complete_construction(session,city_id); b=session.get(Building,building_id)
  if b and b.plot_kind=='FIELD': accrue_resources(session,city_id)
  if not b or b.city_id!=city_id: raise ValueError('building not found')
  if b.definition_key=='town_hall': raise ValueError('dedicated Town Hall upgrade uses its own interface')
  if session.scalar(select(ConstructionQueue).where(ConstructionQueue.city_id==city_id,ConstructionQueue.status=='ACTIVE')): raise ValueError('Age I permits only one active building construction per city')
  target=current_level(session,b)+1; spec=building_level(b.definition_key,target)
  if not spec: raise ValueError('HISTORICAL_VALUE_UNKNOWN: target level table not verified')
  _check_building_prerequisites(session,city_id,spec)
  spend_resources(session,city_id,spec['cost']); _spend_item_cost(session,player_id,spec); now=datetime.now(timezone.utc); effective_seconds=mayor_construction_seconds(session,city_id,spec['seconds']); q=ConstructionQueue(city_id=city_id,building_id=b.id,target_level=target,started_at=now,completes_at=now+timedelta(seconds=effective_seconds),status='ACTIVE'); session.add(q); session.flush(); return {'building_id':b.id,'queue_id':q.id,'target_level':target,'completes_at':q.completes_at.isoformat()}
 return idempotent_operation(session,player_id,idempotency_key,'UPGRADE_BUILDING',work)

from .models import ExteriorFieldPlot, CityEconomyState, PopulationState, ResourceProduction, PlayerItem
from .definitions import town_hall_level

def town_hall_building(session, city_id):
 return session.scalar(select(Building).where(Building.city_id==city_id,Building.plot_kind=='CITY',Building.plot_index==0,Building.definition_key=='town_hall'))

def sync_exterior_field_unlocks(session, city_id):
 th=town_hall_building(session,city_id)
 if not th: raise ValueError('Town Hall missing')
 level=current_level(session,th); spec=town_hall_level(level)
 if not spec: raise ValueError('HISTORICAL_VALUE_UNKNOWN: Town Hall level')
 allowed=spec['resource_fields']
 existing={p.plot_index:p for p in session.scalars(select(ExteriorFieldPlot).where(ExteriorFieldPlot.city_id==city_id)).all()}
 for idx in range(1,allowed+1):
  if idx not in existing: session.add(ExteriorFieldPlot(city_id=city_id,plot_index=idx))
 # Never delete occupied fields if correcting historical config; lock visibility is derived from TH level.
 session.flush(); return allowed

def start_town_hall_upgrade(session,player_id,city_id,idempotency_key):
 def work():
  complete_construction(session,city_id)
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned by player')
  if session.scalar(select(ConstructionQueue).where(ConstructionQueue.city_id==city_id,ConstructionQueue.status=='ACTIVE')): raise ValueError('Age I permits only one active building construction per city')
  th=town_hall_building(session,city_id); level=current_level(session,th); target=level+1
  spec=town_hall_level(target)
  if not spec: raise ValueError('Town Hall is at the highest configured normal Age I level')
  if spec.get('prerequisites')=='HISTORICAL_VALUE_UNKNOWN':
   raise ValueError('HISTORICAL_VALUE_UNKNOWN: exact Town Hall prerequisite table is unresolved; upgrade cannot be authoritatively started')
  _check_building_prerequisites(session,city_id,spec)
  spend_resources(session,city_id,spec['cost'])
  for item_key,amount in spec.get('item_cost',{}).items():
   row=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==item_key))
   if not row or row.quantity<amount: raise ValueError(f'insufficient {item_key}')
   row.quantity-=amount
  now=datetime.now(timezone.utc); effective_seconds=mayor_construction_seconds(session,city_id,spec['seconds']); q=ConstructionQueue(city_id=city_id,building_id=th.id,target_level=target,started_at=now,completes_at=now+timedelta(seconds=effective_seconds),status='ACTIVE'); session.add(q); session.flush()
  return {'building_id':th.id,'queue_id':q.id,'target_level':target,'completes_at':q.completes_at.isoformat()}
 return idempotent_operation(session,player_id,idempotency_key,'UPGRADE_TOWN_HALL',work)

def set_tax_rate(session,player_id,city_id,tax_rate,idempotency_key):
 def work():
  if tax_rate<0 or tax_rate>100: raise ValueError('tax rate must be between 0 and 100')
  settle_economy(session,city_id)
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned by player')
  eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id))
  if not eco: eco=CityEconomyState(city_id=city_id); session.add(eco)
  eco.tax_rate=tax_rate; city.tax_rate=tax_rate
  return {'city_id':city_id,'tax_rate':tax_rate}
 return idempotent_operation(session,player_id,idempotency_key,'SET_TAX_RATE',work)

def rename_city(session,player_id,city_id,name,idempotency_key):
 def work():
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned by player')
  clean=name.strip()
  if not clean: raise ValueError('city name cannot be empty')
  # Exact historical length/character restrictions remain unresolved; do not invent them.
  city.name=clean
  return {'city_id':city_id,'name':clean}
 return idempotent_operation(session,player_id,idempotency_key,'RENAME_CITY',work)

def set_production_rates(session,player_id,city_id,rates,idempotency_key):
 def work():
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned by player')
  accrue_resources(session,city_id)
  required={'food','lumber','stone','iron'}
  if set(rates)!=required or any((not isinstance(v,int)) or v<0 or v>100 for v in rates.values()): raise ValueError('production rates require food/lumber/stone/iron percentages from 0 to 100')
  # Persist controls separately from calculated output. Exact production formula remains unknown.
  from .models import PlayerSetting
  key=f'city:{city_id}:production_rates'; row=session.scalar(select(PlayerSetting).where(PlayerSetting.player_id==player_id,PlayerSetting.key==key))
  if not row: row=PlayerSetting(player_id=player_id,key=key,value={}); session.add(row)
  row.value=rates
  return {'city_id':city_id,'production_rates':rates}
 return idempotent_operation(session,player_id,idempotency_key,'SET_PRODUCTION_RATES',work)

WAREHOUSE_KINDS=('food','lumber','stone','iron')
def technology_level(session,player_id,key):
 t=session.scalar(select(Technology).where(Technology.player_id==player_id,Technology.definition_key==key)); return t.level if t else 0

def warehouse_base_capacity(session,city_id):
 complete_construction(session,city_id)
 total=0
 for b in session.scalars(select(Building).where(Building.city_id==city_id,Building.definition_key=='warehouse')).all():
  lv=current_level(session,b); spec=DATA['building_levels']['warehouse'].get(str(lv),{}); total+=int(spec.get('storage_capacity',0))
 return total

def warehouse_effective_capacity(session,city_id):
 city=session.get(City,city_id); base=warehouse_base_capacity(session,city_id); stock=effective_technology_level(session,city_id,'stockpile') if city else 0
 return int(base*(100+10*stock)/100)

def warehouse_allocation(session,city_id):
 from .models import WarehouseAllocation
 a=session.scalar(select(WarehouseAllocation).where(WarehouseAllocation.city_id==city_id))
 if not a:
  a=WarehouseAllocation(city_id=city_id,food_percent=100,lumber_percent=0,stone_percent=0,iron_percent=0); session.add(a); session.flush()
 return a

def set_warehouse_allocation(session,player_id,city_id,percentages,idempotency_key):
 from .models import WarehouseAllocation
 vals={k:int(percentages.get(k,0)) for k in WAREHOUSE_KINDS}
 if any(v<0 or v>100 for v in vals.values()) or sum(vals.values())!=100: raise ValueError('Warehouse allocation must total exactly 100%')
 def work():
  a=warehouse_allocation(session,city_id)
  for k,v in vals.items(): setattr(a,k+'_percent',v)
  session.flush(); return {'allocation':vals,'effective_capacity':warehouse_effective_capacity(session,city_id)}
 return idempotent_operation(session,player_id,idempotency_key,'warehouse_allocation',work)

def warehouse_protected_amounts(session,city_id,attacker_player_id=None):
 city=session.get(City,city_id); cap=warehouse_effective_capacity(session,city_id); a=warehouse_allocation(session,city_id)
 privateering=technology_level(session,attacker_player_id,'privateering') if attacker_player_id else 0
 factor=max(0,100-3*privateering)/100
 out={}
 for k in WAREHOUSE_KINDS:
  allocated=cap*getattr(a,k+'_percent')/100
  out[k]=int(allocated*factor)
 out['gold']=0
 return out

def resolve_city_plunder(session,attacker_player_id,defender_city_id,carry_capacity,idempotency_key):
 if carry_capacity<0: raise ValueError('carry_capacity must be nonnegative')
 def work():
  protected=warehouse_protected_amounts(session,defender_city_id,attacker_player_id)
  rows={r.kind:r for r in session.scalars(select(Resource).where(Resource.city_id==defender_city_id)).all()}
  city=session.get(City,defender_city_id); eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==defender_city_id))
  available={k:max(0,(rows[k].quantity if k in rows else 0)-protected[k]) for k in WAREHOUSE_KINDS}
  gold=eco.gold if eco else city.gold; available['gold']=max(0,gold)
  total_exposed=sum(available.values())
  if carry_capacity<total_exposed:
   raise ValueError('HISTORICAL_VALUE_UNKNOWN: exact Age I partial-load resource plunder distribution is not yet verified')
  taken=available.copy()
  for k,n in taken.items():
   if k in rows: rows[k].quantity-=n
   else:
    if eco: eco.gold-=n
    else: city.gold-=n
  return {'plundered':taken,'protected':protected,'carry_capacity':carry_capacity,'unused_capacity':int(carry_capacity)-total_exposed}
 return idempotent_operation(session,attacker_player_id,idempotency_key,'city_plunder',work)

# Inn / Feasting Hall recruitment. Exact Age I candidate RNG is deliberately not invented.
def _building_max_level(session,city_id,key):
 vals=[current_level(session,b) for b in session.scalars(select(Building).where(Building.city_id==city_id,Building.definition_key==key)).all()]
 return max(vals or [0])

def inn_candidate_capacity(session,city_id): return _building_max_level(session,city_id,'inn')
def feasting_hall_capacity(session,city_id): return _building_max_level(session,city_id,'feasting_hall')

def inn_candidates(session,city_id):
 from .models import InnCandidate
 complete_construction(session,city_id)
 return session.scalars(select(InnCandidate).where(InnCandidate.city_id==city_id).order_by(InnCandidate.slot_index)).all()

def seed_verified_candidate_fixture(session,city_id,slot_index,name,level,politics,attack,intelligence,generated_at=None):
 """Development/test evidence fixture only; not the production random generator."""
 from .models import InnCandidate
 generated_at=generated_at or datetime.now(timezone.utc)
 c=InnCandidate(city_id=city_id,slot_index=slot_index,name=name,level=level,politics=politics,attack=attack,intelligence=intelligence,loyalty=70,generated_at=generated_at,refreshes_at=generated_at+timedelta(hours=1),generation_source='VERIFIED_FIXTURE')
 session.add(c);session.flush();return c

def refresh_inn_candidates(session,player_id,city_id,idempotency_key,use_hero_hunting=False):
 def work():
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned by player')
  if inn_candidate_capacity(session,city_id)<1: raise ValueError('Inn required')
  # We know when/how a refresh happens, but not the original random candidate generator.
  raise ValueError('HISTORICAL_VALUE_UNKNOWN: exact Age I Inn candidate level/stat generation formula is unresolved; roster refresh cannot be fabricated')
 return idempotent_operation(session,player_id,idempotency_key,'REFRESH_INN',work)

def recruit_inn_candidate(session,player_id,city_id,candidate_id,idempotency_key):
 from .models import InnCandidate,HeroStats,HeroExperience,HeroAssignment,Hero
 def work():
  settle_economy(session,city_id)
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned by player')
  cand=session.get(InnCandidate,candidate_id)
  if not cand or cand.city_id!=city_id: raise ValueError('candidate not found')
  cap=feasting_hall_capacity(session,city_id)
  if cap<1: raise ValueError('Feasting Hall required')
  occupied=session.scalar(select(__import__('sqlalchemy').func.count(Hero.id)).where(Hero.city_id==city_id)) or 0
  if occupied>=cap: raise ValueError('Feasting Hall is full')
  fee=cand.level*DATA['hero_recruitment']['hire_gold_per_hero_level']
  eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id))
  if not eco or eco.gold<fee: raise ValueError('insufficient gold')
  eco.gold-=fee; city.gold=eco.gold
  h=Hero(player_id=player_id,city_id=city_id,name=cand.name,level=cand.level,experience=0,politics=cand.politics,attack=cand.attack,intelligence=cand.intelligence,assignment=None,base_politics=None,base_attack=None,base_intelligence=None);session.add(h);session.flush()
  session.add(HeroStats(hero_id=h.id,politics=cand.politics,attack=cand.attack,intelligence=cand.intelligence));session.add(HeroExperience(hero_id=h.id,level=cand.level,experience=0));session.add(HeroAssignment(hero_id=h.id,city_id=city_id,assignment_key='idle'))
  slot=cand.slot_index;session.delete(cand);session.flush()
  # Historical sources say replacement is immediate, but exact RNG is unknown.
  return {'hero_id':h.id,'name':h.name,'level':h.level,'employment_fee':fee,'feasting_hall_capacity':cap,'occupied_after':occupied+1,'vacated_inn_slot':slot,'replacement':'HISTORICAL_VALUE_UNKNOWN: immediate replacement required, exact candidate generator unresolved'}
 return idempotent_operation(session,player_id,idempotency_key,'RECRUIT_INN_HERO',work)


# Feasting Hall authoritative hero management and mayor effects.
def hero_salary_per_hour(hero): return int(hero.level) * 20

def _hero_status(session, hero):
 from .models import Army,March,HeroAssignment
 march=session.scalar(select(March).join(Army,March.army_id==Army.id).where(Army.hero_id==hero.id,March.status.in_(['MARCHING','RETURNING','CAMPED','ACTIVE'])))
 if march: return {'key':'march','march_id':march.id,'mission':march.mission,'arrives_at':march.arrives_at,'returns_at':march.returns_at}
 a=session.scalar(select(HeroAssignment).where(HeroAssignment.hero_id==hero.id))
 if hero.captured: return {'key':'captured'}
 if a and a.assignment_key=='mayor': return {'key':'mayor'}
 return {'key':'idle'}

def feasting_hall_roster(session,city_id):
 from .models import Hero,HeroStats,HeroExperience
 complete_construction(session,city_id)
 out=[]
 for h in session.scalars(select(Hero).where(Hero.city_id==city_id).order_by(Hero.id)).all():
  st=session.scalar(select(HeroStats).where(HeroStats.hero_id==h.id))
  xp=session.scalar(select(HeroExperience).where(HeroExperience.hero_id==h.id))
  out.append({'id':h.id,'name':h.name,'level':xp.level if xp else h.level,'experience':xp.experience if xp else h.experience,
   'politics':st.politics if st else h.politics,'attack':st.attack if st else h.attack,'intelligence':st.intelligence if st else h.intelligence,
   'loyalty':h.loyalty,'salary_per_hour':hero_salary_per_hour(h),'captured':h.captured,'status':_hero_status(session,h)})
 return out

def appoint_mayor(session,player_id,city_id,hero_id,idempotency_key):
 from .models import Hero,HeroAssignment,Army,March
 def work():
  accrue_resources(session,city_id)
  h=session.get(Hero,hero_id); city=session.get(City,city_id)
  if not city or city.player_id!=player_id or not h or h.city_id!=city_id: raise ValueError('hero not in this city')
  if h.captured: raise ValueError('captured hero cannot be mayor')
  if _hero_status(session,h)['key']=='march': raise ValueError('hero leading a march cannot be mayor')
  for a in session.scalars(select(HeroAssignment).where(HeroAssignment.city_id==city_id,HeroAssignment.assignment_key=='mayor')).all():
   a.assignment_key='idle'
  a=session.scalar(select(HeroAssignment).where(HeroAssignment.hero_id==hero_id))
  if not a: a=HeroAssignment(hero_id=hero_id,city_id=city_id,assignment_key='mayor');session.add(a)
  else: a.city_id=city_id;a.assignment_key='mayor'
  h.assignment='mayor'
  return {'hero_id':hero_id,'status':'mayor'}
 return idempotent_operation(session,player_id,idempotency_key,'APPOINT_MAYOR',work)

def remove_mayor(session,player_id,city_id,idempotency_key):
 from .models import Hero,HeroAssignment
 def work():
  accrue_resources(session,city_id)
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned by player')
  a=session.scalar(select(HeroAssignment).where(HeroAssignment.city_id==city_id,HeroAssignment.assignment_key=='mayor'))
  if a:
   h=session.get(Hero,a.hero_id);a.assignment_key='idle'
   if h: h.assignment=None
  return {'mayor':None}
 return idempotent_operation(session,player_id,idempotency_key,'REMOVE_MAYOR',work)

def current_mayor(session,city_id):
 from .models import Hero,HeroAssignment
 a=session.scalar(select(HeroAssignment).where(HeroAssignment.city_id==city_id,HeroAssignment.assignment_key=='mayor'))
 return session.get(Hero,a.hero_id) if a else None

def hero_effective_stats(session,hero_id,at=None):
 from .models import Hero,HeroStats,HeroBuff
 at=at or datetime.now(timezone.utc);h=session.get(Hero,hero_id)
 if not h:return {'politics':0,'attack':0,'intelligence':0}
 st=session.scalar(select(HeroStats).where(HeroStats.hero_id==hero_id))
 out={'politics':st.politics if st else h.politics,'attack':st.attack if st else h.attack,'intelligence':st.intelligence if st else h.intelligence}
 for b in session.scalars(select(HeroBuff).where(HeroBuff.hero_id==hero_id,HeroBuff.starts_at<=at,HeroBuff.expires_at>at)).all():
  if b.attribute_key in out:out[b.attribute_key]=int(out[b.attribute_key]*b.multiplier)
 return out

def mayor_stats(session,city_id):
 h=current_mayor(session,city_id)
 return hero_effective_stats(session,h.id) if h else {'politics':0,'attack':0,'intelligence':0}

def mayor_production_multiplier(session,city_id):
 return 1.0 + mayor_stats(session,city_id)['politics']/100.0

def mayor_construction_seconds(session,city_id,base_seconds):
 return max(1,int(round(float(base_seconds)*(0.995**mayor_stats(session,city_id)['politics'])*(0.9**effective_technology_level(session,city_id,'construction')))))

def mayor_training_seconds(session,city_id,base_seconds):
 return max(1,int(round(float(base_seconds)*(0.995**mayor_stats(session,city_id)['attack'])*(0.9**effective_technology_level(session,city_id,'military_science')))))

def mayor_research_seconds(session,city_id,base_seconds):
 return max(1,int(round(float(base_seconds)*(0.995**mayor_stats(session,city_id)['intelligence']))))

def dismiss_hero(session,player_id,city_id,hero_id,idempotency_key):
 from .models import Hero,HeroAssignment,HeroStats,HeroExperience
 def work():
  settle_economy(session,city_id)
  h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id: raise ValueError('hero not in city')
  if _hero_status(session,h)['key']=='march': raise ValueError('hero leading a march cannot be dismissed')
  if h.captured: raise ValueError('captured hero must be released, not dismissed')
  for model in (HeroAssignment,HeroStats,HeroExperience):
   row=session.scalar(select(model).where(model.hero_id==hero_id))
   if row: session.delete(row)
  session.delete(h)
  return {'dismissed_hero_id':hero_id}
 return idempotent_operation(session,player_id,idempotency_key,'DISMISS_HERO',work)

def release_captured_hero(session,player_id,city_id,hero_id,idempotency_key):
 from .models import Hero,HeroAssignment,HeroStats,HeroExperience
 def work():
  h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id or not h.captured: raise ValueError('captured hero not found')
  for model in (HeroAssignment,HeroStats,HeroExperience):
   row=session.scalar(select(model).where(model.hero_id==hero_id))
   if row: session.delete(row)
  session.delete(h);return {'released_hero_id':hero_id}
 return idempotent_operation(session,player_id,idempotency_key,'RELEASE_CAPTURED_HERO',work)

def capture_hero_into_city(session,player_id,city_id,name,level,politics,attack,intelligence,original_player_id=None):
 settle_economy(session,city_id)
 from .models import Hero,HeroStats,HeroExperience,HeroAssignment
 cap=feasting_hall_capacity(session,city_id)
 occupied=session.scalar(select(__import__('sqlalchemy').func.count(Hero.id)).where(Hero.city_id==city_id)) or 0
 if occupied>=cap:return None
 h=Hero(player_id=player_id,city_id=city_id,name=name,level=level,experience=0,politics=politics,attack=attack,intelligence=intelligence,loyalty=0,assignment='captured',captured=True,captured_from_player_id=original_player_id)
 session.add(h);session.flush()
 session.add(HeroStats(hero_id=h.id,politics=politics,attack=attack,intelligence=intelligence))
 session.add(HeroExperience(hero_id=h.id,level=level,experience=0))
 session.add(HeroAssignment(hero_id=h.id,city_id=city_id,assignment_key='captured'))
 return h

HERO_TITLES=['Civilian','Knight','Baronet','Baron','Viscount','Earl','Marquis','Duke','Furstin','Prinzessin']
def _persuasion_requirements(level):
 title=HERO_TITLES[min(9,max(0,level//10))]
 medal=None;count=0
 if 51<=level<=60:medal,count='cross_medal',1
 elif 61<=level<=70:medal,count='rose_medal',2
 elif 71<=level<=80:medal,count='lion_medal',3
 elif 81<=level<=90:medal,count='honor_medal',4
 elif 91<=level<=100:medal,count='courage_medal',5
 elif 101<=level<=110:medal,count='wisdom_medal',6
 elif 111<=level<=120:medal,count='freedom_medal',7
 elif 121<=level<=130:medal,count='justice_medal',8
 elif level>=131:medal,count='nation_medal',(int((level+9)//10)*10-50)//10
 return {'title':title,'medal':medal,'medal_count':count,'gold':level*1000}

def persuade_captured_hero(session,player_id,city_id,hero_id,idempotency_key):
 from .models import Hero,PlayerItem,PlayerProgression,HeroAssignment
 def work():
  settle_economy(session,city_id);h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id or not h.captured:raise ValueError('captured hero not found')
  req=_persuasion_requirements(h.level);prog=session.scalar(select(PlayerProgression).where(PlayerProgression.player_id==player_id))
  cur=(_progression(session,player_id)[2] if prog else 'Civilian')
  if cur not in HERO_TITLES or HERO_TITLES.index(cur)<HERO_TITLES.index(req['title']):raise ValueError(f"{req['title']} title required")
  if req['medal']:
   item=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==req['medal']))
   if not item or item.quantity<req['medal_count']:raise ValueError(f"{req['medal_count']} {req['medal']} required")
   item.quantity-=req['medal_count']
  eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id))
  if not eco or eco.gold<req['gold']:raise ValueError('insufficient gold')
  eco.gold-=req['gold'];session.get(City,city_id).gold=eco.gold;h.captured=False;h.loyalty=10;h.assignment=None
  a=session.scalar(select(HeroAssignment).where(HeroAssignment.hero_id==hero_id))
  if a:a.assignment_key='idle'
  return {'hero_id':hero_id,'status':'idle','loyalty':10,'gold_cost':req['gold'],'medal':req['medal'],'medal_count':req['medal_count']}
 return idempotent_operation(session,player_id,idempotency_key,'PERSUADE_CAPTURED_HERO',work)


# Embassy / alliance / foreign-garrison authoritative operations.
def embassy_level(session,city_id): return _building_max_level(session,city_id,'embassy')

def embassy_state(session,city_id):
 from .models import EmbassyState
 row=session.scalar(select(EmbassyState).where(EmbassyState.city_id==city_id))
 if not row: row=EmbassyState(city_id=city_id,allow_allied_garrison=False);session.add(row);session.flush()
 return row

def set_embassy_garrison_permission(session,player_id,city_id,allow,idempotency_key):
 def work():
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned')
  if embassy_level(session,city_id)<1: raise ValueError('Embassy level 1 required')
  row=embassy_state(session,city_id);row.allow_allied_garrison=bool(allow)
  return {'allow_allied_garrison':row.allow_allied_garrison}
 return idempotent_operation(session,player_id,idempotency_key,'EMBASSY_GARRISON_PERMISSION',work)

def _alliance_membership(session,player_id):
 from .models import AllianceMember
 return session.scalar(select(AllianceMember).where(AllianceMember.player_id==player_id))

def apply_to_alliance(session,player_id,city_id,alliance_id,idempotency_key):
 from .models import Alliance,AllianceApplication
 def work():
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned')
  if embassy_level(session,city_id)<1: raise ValueError('Embassy level 1 required')
  if _alliance_membership(session,player_id): raise ValueError('already in an alliance')
  if not session.get(Alliance,alliance_id): raise ValueError('alliance not found')
  row=session.scalar(select(AllianceApplication).where(AllianceApplication.alliance_id==alliance_id,AllianceApplication.player_id==player_id))
  if not row: row=AllianceApplication(alliance_id=alliance_id,player_id=player_id,status='PENDING');session.add(row);session.flush()
  return {'application_id':row.id,'status':row.status}
 return idempotent_operation(session,player_id,idempotency_key,'ALLIANCE_APPLY',work)

def accept_alliance_application(session,actor_player_id,application_id,idempotency_key):
 from .models import AllianceApplication,AllianceMember,Alliance
 def work():
  app=session.get(AllianceApplication,application_id)
  if not app or app.status!='PENDING': raise ValueError('pending application not found')
  actor=_alliance_membership(session,actor_player_id)
  if not actor or actor.alliance_id!=app.alliance_id or not alliance_permission(session,actor_player_id,'applications'): raise ValueError('insufficient alliance permission')
  host=session.scalar(select(AllianceMember).where(AllianceMember.alliance_id==app.alliance_id,AllianceMember.rank=='HOST'))
  host_city=session.scalar(select(City).where(City.player_id==host.player_id).order_by(City.id)) if host else None
  limit=embassy_level(session,host_city.id)*10 if host_city else 0
  count=session.scalar(select(__import__('sqlalchemy').func.count(AllianceMember.id)).where(AllianceMember.alliance_id==app.alliance_id)) or 0
  if count>=limit: raise ValueError('alliance member limit reached')
  if _alliance_membership(session,app.player_id): raise ValueError('applicant already in alliance')
  session.add(AllianceMember(alliance_id=app.alliance_id,player_id=app.player_id,rank='MEMBER'));app.status='ACCEPTED'
  return {'player_id':app.player_id,'alliance_id':app.alliance_id,'rank':'MEMBER'}
 return idempotent_operation(session,actor_player_id,idempotency_key,'ALLIANCE_ACCEPT_APPLICATION',work)

def create_alliance(session,player_id,city_id,name,idempotency_key):
 from .models import Alliance,AllianceMember
 def work():
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id: raise ValueError('city not owned')
  if embassy_level(session,city_id)<2: raise ValueError('Embassy level 2 required')
  if _alliance_membership(session,player_id): raise ValueError('already in an alliance')
  if session.scalar(select(Alliance).where(Alliance.name==name)): raise ValueError('alliance name exists')
  a=Alliance(name=name,information='');session.add(a);session.flush();session.add(AllianceMember(alliance_id=a.id,player_id=player_id,rank='HOST'));_seed_alliance_ranks(session,a.id)
  return {'alliance_id':a.id,'name':name,'rank':'HOST','member_limit':embassy_level(session,city_id)*10}
 return idempotent_operation(session,player_id,idempotency_key,'ALLIANCE_CREATE',work)

def foreign_garrisons(session,city_id):
 from .models import ForeignGarrison
 return session.scalars(select(ForeignGarrison).where(ForeignGarrison.host_city_id==city_id,ForeignGarrison.status=='GARRISONED').order_by(ForeignGarrison.id)).all()

def arrive_allied_reinforcement(session,march_id):
 from .models import March,Army,ForeignGarrison
 m=session.get(March,march_id)
 if not m or m.mission.upper()!='REINFORCE': raise ValueError('reinforcement march required')
 army=session.get(Army,m.army_id); host=session.scalar(select(City).where(City.x==m.target_x,City.y==m.target_y))
 if not army or not host: raise ValueError('invalid reinforcement')
 if embassy_level(session,host.id)<1 or not embassy_state(session,host.id).allow_allied_garrison: raise ValueError('host Embassy does not allow allied garrison')
 a1=_alliance_membership(session,army.player_id);a2=_alliance_membership(session,host.player_id)
 if not a1 or not a2 or a1.alliance_id!=a2.alliance_id: raise ValueError('reinforcement requires same alliance')
 if len(foreign_garrisons(session,host.id))>=embassy_level(session,host.id): raise ValueError('Embassy garrison wave capacity full')
 existing=session.scalar(select(ForeignGarrison).where(ForeignGarrison.army_id==army.id))
 if existing:return existing
 g=ForeignGarrison(host_city_id=host.id,owner_player_id=army.player_id,source_city_id=m.source_city_id,army_id=army.id,hero_id=army.hero_id,troops=dict(army.troops),resources=dict(army.resources),status='GARRISONED');session.add(g);m.status='GARRISONED';session.flush();return g

def return_foreign_garrison(session,actor_player_id,garrison_id,idempotency_key):
 from .models import ForeignGarrison,Army,March
 def work():
  g=session.get(ForeignGarrison,garrison_id)
  if not g or g.status!='GARRISONED': raise ValueError('garrison not found')
  host=session.get(City,g.host_city_id)
  if actor_player_id not in (g.owner_player_id,host.player_id): raise ValueError('not permitted')
  g.status='RETURNING'
  m=session.scalar(select(March).where(March.army_id==g.army_id))
  if m:m.status='RETURNING'
  return {'garrison_id':g.id,'status':'RETURNING','troops':dict(g.troops),'destination_city_id':g.source_city_id}
 return idempotent_operation(session,actor_player_id,idempotency_key,'RETURN_FOREIGN_GARRISON',work)

MARKETPLACE_DELIVERY_SECONDS=1800

def marketplace_level(session,city_id): return _building_max_level(session,city_id,'marketplace')
def _market_eco(session,city_id):
 from .models import CityEconomyState
 return session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id))
def _market_resource(session,city_id,kind):
 return session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==kind))
def market_orders(session,city_id=None):
 from .models import MarketOrder
 q=select(MarketOrder)
 if city_id is not None:q=q.where(MarketOrder.city_id==city_id)
 return session.scalars(q.order_by(MarketOrder.created_at,MarketOrder.id)).all()
def _active_market_count(session,city_id):
 from .models import MarketOrder
 return session.scalar(select(__import__('sqlalchemy').func.count(MarketOrder.id)).where(MarketOrder.city_id==city_id,MarketOrder.status.in_(['OPEN','PARTIAL']))) or 0

def place_market_order(session,player_id,city_id,side,resource_kind,quantity,price,idempotency_key):
 from .models import MarketOrder,MarketTrade
 order_side=side.upper(); order_resource=resource_kind.lower()
 def work():
  settle_economy(session,city_id)
  city=session.get(City,city_id)
  if not city or city.player_id!=player_id:raise ValueError('city not owned')
  lv=marketplace_level(session,city_id)
  if lv<1:raise ValueError('Marketplace required')
  side=order_side; resource_kind=order_resource
  if side not in ('BUY','SELL') or resource_kind not in ('food','lumber','stone','iron'):raise ValueError('invalid market order')
  if quantity<1 or quantity>10000000 or price<=0:raise ValueError('invalid quantity/price')
  if _active_market_count(session,city_id)>=lv:raise ValueError('Marketplace concurrent transaction capacity reached')
  # Age I pending market assets remain plunderable; do not escrow/remove them here.
  r=_market_resource(session,city_id,resource_kind); eco=_market_eco(session,city_id)
  gross=int(round(quantity*price)); fee=int(round(gross*0.005))
  if side=='SELL' and (not r or r.quantity<quantity):raise ValueError('insufficient resource')
  if side=='BUY' and (not eco or eco.gold<gross+fee):raise ValueError('insufficient gold')
  o=MarketOrder(player_id=player_id,city_id=city_id,side=side,resource_kind=resource_kind,quantity=quantity,remaining_quantity=quantity,price=float(price),status='OPEN');session.add(o);session.flush()
  matches=_match_market_order(session,o)
  return {'order_id':o.id,'status':o.status,'remaining_quantity':o.remaining_quantity,'matches':matches}
 return idempotent_operation(session,player_id,idempotency_key,'MARKET_PLACE_ORDER',work)

def _match_market_order(session,o):
 from .models import MarketOrder,MarketTrade
 if o.side=='BUY':
  q=select(MarketOrder).where(MarketOrder.side=='SELL',MarketOrder.resource_kind==o.resource_kind,MarketOrder.status.in_(['OPEN','PARTIAL']),MarketOrder.price<=o.price,MarketOrder.id!=o.id).order_by(MarketOrder.price,MarketOrder.created_at,MarketOrder.id)
 else:
  q=select(MarketOrder).where(MarketOrder.side=='BUY',MarketOrder.resource_kind==o.resource_kind,MarketOrder.status.in_(['OPEN','PARTIAL']),MarketOrder.price>=o.price,MarketOrder.id!=o.id).order_by(MarketOrder.price.desc(),MarketOrder.created_at,MarketOrder.id)
 out=[]
 for other in session.scalars(q).all():
  if o.remaining_quantity<=0:break
  buy=o if o.side=='BUY' else other; sell=o if o.side=='SELL' else other
  qty=min(o.remaining_quantity,other.remaining_quantity)
  # Documented crossing example executes at buyer's bid.
  px=float(buy.price); gross=int(round(qty*px)); fee=int(round(gross*0.005))
  br=_market_resource(session,buy.city_id,o.resource_kind); sr=_market_resource(session,sell.city_id,o.resource_kind); be=_market_eco(session,buy.city_id); se=_market_eco(session,sell.city_id)
  if not sr or sr.quantity<qty or not be or be.gold<gross+fee:continue
  sr.quantity-=qty; be.gold-=gross+fee; se.gold+=gross-fee
  bc=session.get(City,buy.city_id);sc=session.get(City,sell.city_id);bc.gold=be.gold;sc.gold=se.gold
  o.remaining_quantity-=qty;other.remaining_quantity-=qty
  o.status='FILLED' if o.remaining_quantity==0 else 'PARTIAL';other.status='FILLED' if other.remaining_quantity==0 else 'PARTIAL'
  t=MarketTrade(resource_kind=o.resource_kind,quantity=qty,price=px,buy_order_id=buy.id,sell_order_id=sell.id,buyer_city_id=buy.city_id,seller_city_id=sell.city_id,gold_value=gross,buyer_fee=fee,seller_fee=fee,delivers_at=datetime.now(timezone.utc)+timedelta(seconds=MARKETPLACE_DELIVERY_SECONDS),status='DELIVERY_PENDING');session.add(t);session.flush()
  out.append({'trade_id':t.id,'quantity':qty,'price':px,'delivery_seconds':MARKETPLACE_DELIVERY_SECONDS})
 return out

def cancel_market_order(session,player_id,order_id,idempotency_key):
 from .models import MarketOrder
 def work():
  o=session.get(MarketOrder,order_id)
  if not o or o.player_id!=player_id or o.status not in ('OPEN','PARTIAL'):raise ValueError('open order not found')
  o.status='CANCELLED';return {'order_id':o.id,'status':'CANCELLED','remaining_quantity':o.remaining_quantity}
 return idempotent_operation(session,player_id,idempotency_key,'MARKET_CANCEL_ORDER',work)

def settle_market_delivery(session,trade_id):
 from .models import MarketTrade
 t=session.get(MarketTrade,trade_id)
 if not t or t.status!='DELIVERY_PENDING':return t
 if t.delivers_at is None:raise ValueError('market trade is missing its persisted delivery timestamp')
 due=t.delivers_at
 if due.tzinfo is None: due=due.replace(tzinfo=timezone.utc)
 if datetime.now(timezone.utc)<due:return t
 r=_market_resource(session,t.buyer_city_id,t.resource_kind)
 if not r:r=Resource(city_id=t.buyer_city_id,kind=t.resource_kind,quantity=0);session.add(r)
 r.quantity+=t.quantity;t.status='DELIVERED';return t


TECH_KEYS=('agriculture','lumbering','masonry','mining','metal_casting','informatics','military_science','military_tradition','iron_working','logistics','compass','horseback_riding','archery','stockpile','medicine','construction','engineering','machinery','privateering')
def academy_level(session,city_id): return _building_max_level(session,city_id,'academy')
def technology_level(session,player_id,key):
 from .models import Technology
 row=session.scalar(select(Technology).where(Technology.player_id==player_id,Technology.definition_key==key))
 return row.level if row else 0
def effective_technology_level(session,city_id,key):
 city=session.get(City,city_id)
 if not city:return 0
 lvl=technology_level(session,city.player_id,key)
 if lvl<=0:return 0
 # Age I exception: Construction research applies empire-wide even without a supporting local Academy.
 if key=='construction': return lvl
 spec=DATA['technologies'][key]['levels'][str(lvl)]
 return lvl if academy_level(session,city_id)>=spec['academy_level'] else 0
def complete_research(session,city_id=None):
 from .models import ResearchQueue,Technology
 now=datetime.now(timezone.utc);q=select(ResearchQueue).where(ResearchQueue.status=='ACTIVE')
 if city_id is not None:q=q.where(ResearchQueue.city_id==city_id)
 done=[]
 for rq in session.scalars(q).all():
  due=rq.completes_at
  if due.tzinfo is None:due=due.replace(tzinfo=timezone.utc)
  if due<=now:
   if rq.technology_key in ('agriculture','lumbering','masonry','mining'): accrue_resources(session,rq.city_id,due)
   row=session.scalar(select(Technology).where(Technology.player_id==rq.player_id,Technology.definition_key==rq.technology_key))
   if not row:row=Technology(player_id=rq.player_id,definition_key=rq.technology_key,level=0);session.add(row);session.flush()
   row.level=max(row.level,rq.target_level);rq.status='COMPLETE';done.append(rq)
 return done
def _require_building(session,city_id,key,need):
 return _building_max_level(session,city_id,key)>=need
def start_research(session,player_id,city_id,key,idempotency_key):
 from .models import ResearchQueue,Technology
 def work():
  complete_research(session,city_id);city=session.get(City,city_id)
  if not city or city.player_id!=player_id:raise ValueError('city not owned')
  if key not in DATA['technologies']:raise ValueError('unknown technology')
  if session.scalar(select(ResearchQueue).where(ResearchQueue.city_id==city_id,ResearchQueue.status=='ACTIVE')):raise ValueError('research already active in city')
  if session.scalar(select(ResearchQueue).where(ResearchQueue.player_id==player_id,ResearchQueue.technology_key==key,ResearchQueue.status=='ACTIVE')):raise ValueError('technology already being researched')
  current=technology_level(session,player_id,key);target=current+1
  if target>10:raise ValueError('technology already maximum level')
  spec=DATA['technologies'][key]['levels'][str(target)]
  if spec['seconds']=='HISTORICAL_VALUE_UNKNOWN':raise ValueError('HISTORICAL_VALUE_UNKNOWN: exact Age I research timer unresolved')
  if academy_level(session,city_id)<spec['academy_level']:raise ValueError('Academy level requirement not met')
  for rk,need in spec['technology_requirements'].items():
   if technology_level(session,player_id,rk)<need:raise ValueError(f'{rk} level {need} required')
  for bk,need in spec['building_requirements'].items():
   need=target if need=='TARGET_LEVEL' else need
   if not _require_building(session,city_id,bk,need):raise ValueError(f'{bk} level {need} required')
  for kind,amt in spec['cost'].items():
   r=session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==kind))
   if not r or r.quantity<amt:raise ValueError(f'insufficient {kind}')
  eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id))
  if not eco or eco.gold<spec['gold']:raise ValueError('insufficient gold')
  for kind,amt in spec['cost'].items():session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==kind)).quantity-=amt
  eco.gold-=spec['gold'];city.gold=eco.gold
  seconds=mayor_research_seconds(session,city_id,spec['seconds']);now=datetime.now(timezone.utc)
  rq=ResearchQueue(player_id=player_id,city_id=city_id,technology_key=key,target_level=target,started_at=now,completes_at=now+timedelta(seconds=seconds),status='ACTIVE');session.add(rq);session.flush()
  return {'research_queue_id':rq.id,'technology':key,'target_level':target,'seconds':seconds,'completes_at':rq.completes_at.isoformat()}
 return idempotent_operation(session,player_id,idempotency_key,'START_RESEARCH',work)

def resource_technology_multiplier(session,city_id,kind):
 key={'food':'agriculture','lumber':'lumbering','stone':'masonry','iron':'mining'}[kind]
 return 1+0.10*effective_technology_level(session,city_id,key)
def troop_attack_multiplier(session,city_id):return 1+0.05*effective_technology_level(session,city_id,'military_tradition')
def troop_defense_multiplier(session,city_id):return 1+0.05*effective_technology_level(session,city_id,'iron_working')
def troop_life_multiplier(session,city_id):return 1+0.05*effective_technology_level(session,city_id,'medicine')
def army_load_multiplier(session,city_id):return 1+0.10*effective_technology_level(session,city_id,'logistics')
def infantry_speed_multiplier(session,city_id):return 1+0.10*effective_technology_level(session,city_id,'compass')
def mounted_mechanic_speed_multiplier(session,city_id):return 1+0.05*effective_technology_level(session,city_id,'horseback_riding')
def ranged_range_multiplier(session,city_id):return 1+0.05*effective_technology_level(session,city_id,'archery')
def warehouse_stockpile_multiplier(session,city_id):return 1+0.10*effective_technology_level(session,city_id,'stockpile')
def wall_fortification_life_multiplier(session,city_id):return 1+0.10*effective_technology_level(session,city_id,'engineering')
def machinery_repair_multiplier(session,city_id):return 1+effective_technology_level(session,city_id,'machinery')
def privateering_protection_multiplier(session,city_id):return 1-0.03*effective_technology_level(session,city_id,'privateering')
def scouting_effective_level(session,city_id):return effective_technology_level(session,city_id,'informatics')
def mechanic_training_time_multiplier(session,city_id):return 0.9**effective_technology_level(session,city_id,'metal_casting')


RALLY_MISSIONS=('ATTACK','SCOUT','REINFORCE','TRANSPORT','OCCUPY')
INFANTRY={'worker','warrior','scout','pikeman','swordsman','archer'}
MOUNTED_MECHANICS={'cavalry','cataphract','transporter','ballista','battering_ram','catapult'}
def rally_spot_level(session,city_id):return _building_max_level(session,city_id,'rally_spot')
def rally_limits(session,city_id,war_ensign=False):
 lv=rally_spot_level(session,city_id);return {'march_slots':lv,'troop_limit':int(10000*lv*(1.25 if war_ensign else 1))}
def _active_source_marches(session,city_id):
 from .models import March
 return session.scalars(select(March).where(March.source_city_id==city_id,March.status.in_(['MARCHING','CAMPED','GARRISONED','RETURNING','ARRIVED_PENDING_RESOLUTION']))).all()
def _same_alliance(session,p1,p2):
 from .models import AllianceMember
 a=session.scalar(select(AllianceMember).where(AllianceMember.player_id==p1));b=session.scalar(select(AllianceMember).where(AllianceMember.player_id==p2))
 return bool(a and b and a.alliance_id==b.alliance_id)
def _target_info(session,x,y):
 from .models import MapTile
 c=session.scalar(select(City).where(City.x==x,City.y==y))
 if c:return {'kind':'CITY','owner_player_id':c.player_id,'city_id':c.id}
 t=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y))
 if t:return {'kind':t.tile_type.upper(),'owner_player_id':t.owner_player_id,'map_tile_id':t.id,'level':t.level}
 return None
def _mission_legal(session,player_id,target,mission):
 if not target:return False
 owner=target.get('owner_player_id')
 if mission in ('REINFORCE','TRANSPORT'):
  return target['kind']=='CITY' and (owner==player_id or (owner is not None and _same_alliance(session,player_id,owner)))
 if mission=='OCCUPY':
  return target['kind'] in ('VALLEY','FLAT') and owner!=player_id and not (owner is not None and player_relationship(session,player_id,owner) in ('ALLIANCE','FRIENDLY'))
 if mission=='ATTACK':
  return owner!=player_id and not (owner is not None and player_relationship(session,player_id,owner) in ('ALLIANCE','FRIENDLY'))
 if mission=='SCOUT':
  return owner!=player_id and not (owner is not None and player_relationship(session,player_id,owner) in ('ALLIANCE','FRIENDLY'))
 return False
def _relief_multiplier(session,city_id,target):
 if target.get('kind')!='CITY':return 1
 source=session.get(City,city_id);owner=target.get('owner_player_id')
 if owner!=source.player_id and not _same_alliance(session,source.player_id,owner):return 1
 return relief_station_multiplier(session,city_id)

def march_distance(source_city,x,y):return ((source_city.x-x)**2+(source_city.y-y)**2)**0.5
def army_load_capacity(session,city_id,troops):
 total=sum(DATA['troop_types'][k]['load']*int(q) for k,q in troops.items())
 return int(total*army_load_multiplier(session,city_id))
def army_travel_seconds(session,city_id,troops,x,y,mission):
 city=session.get(City,city_id);target=_target_info(session,x,y);distance=march_distance(city,x,y)
 speeds=[]
 for k,q in troops.items():
  if int(q)<=0:continue
  speed=DATA['troop_types'][k]['speed_miles_per_1000_minutes']
  if k in INFANTRY:speed*=infantry_speed_multiplier(session,city_id)
  if k in MOUNTED_MECHANICS:speed*=mounted_mechanic_speed_multiplier(session,city_id)
  speeds.append(speed)
 if not speeds:raise ValueError('at least one troop required')
 slow=min(speeds);minutes=distance*1000/slow
 if mission in ('REINFORCE','TRANSPORT'):minutes/=_relief_multiplier(session,city_id,target)
 return max(1,int(round(minutes*60)))
def march_food_requirement(session,city_id,troops,travel_seconds,camp_seconds=0):
 # Published troop Food is hourly Age-I upkeep; dispatch requires minimum march food.
 hours=(travel_seconds+camp_seconds)/3600
 return int(__import__('math').ceil(sum(DATA['troop_types'][k]['food_upkeep_per_hour']*int(q) for k,q in troops.items())*hours))
def rally_preview(session,player_id,city_id,mission,x,y,troops,resources=None,camp_seconds=0,war_ensign=False):
 resources=resources or {};mission=mission.upper();city=session.get(City,city_id)
 if not city or city.player_id!=player_id:raise ValueError('city not owned')
 lv=rally_spot_level(session,city_id)
 if lv<1:raise ValueError('Rally Spot required')
 if mission not in RALLY_MISSIONS:raise ValueError('invalid mission')
 target=_target_info(session,x,y)
 if not _mission_legal(session,player_id,target,mission):raise ValueError('illegal mission for destination')
 if camp_seconds<0 or camp_seconds>86340:raise ValueError('camp time must be 0 through 23:59')
 total=sum(int(v) for v in troops.values())
 limit=rally_limits(session,city_id,war_ensign)['troop_limit']
 if total<1 or total>limit:raise ValueError('Rally Spot troop limit exceeded')
 for k,q in troops.items():
  if k not in DATA['troop_types'] or int(q)<0:raise ValueError('invalid troop selection')
  row=session.scalar(select(TroopQuantity).where(TroopQuantity.city_id==city_id,TroopQuantity.troop_type_key==k))
  if not row or row.quantity<int(q):raise ValueError(f'insufficient {k}')
 travel=army_travel_seconds(session,city_id,troops,x,y,mission);load=army_load_capacity(session,city_id,troops)
 sent=sum(int(v) for v in resources.values())
 if any(k not in ('food','lumber','stone','iron') or int(v)<0 for k,v in resources.items()):raise ValueError('invalid carried resource')
 if sent>load:raise ValueError('resources exceed army carrying capacity')
 food=march_food_requirement(session,city_id,troops,travel,camp_seconds)
 return {'distance':march_distance(city,x,y),'travel_seconds':travel,'camp_seconds':camp_seconds,'arrival_seconds':travel+camp_seconds,'return_travel_seconds':travel,'load_capacity':load,'load_used':sent,'load_vacancy':load-sent,'food_required':food,'target':target,'troop_limit':limit,'march_slots':lv}


BEGINNER_PROTECTION_SECONDS=7*24*60*60
def ensure_beginner_protection(session,player_id,at=None):
 from .models import BeginnerProtection,Player,Account
 at=at or datetime.now(timezone.utc);bp=session.scalar(select(BeginnerProtection).where(BeginnerProtection.player_id==player_id))
 if bp:return bp
 p=session.get(Player,player_id)
 if not p:raise ValueError('player not found')
 account=session.get(Account,p.account_id);start=account.created_at or at
 if start.tzinfo is None:start=start.replace(tzinfo=timezone.utc)
 bp=BeginnerProtection(player_id=player_id,started_at=start,expires_at=start+timedelta(seconds=BEGINNER_PROTECTION_SECONDS));session.add(bp);session.flush();return bp

def refresh_beginner_protection(session,player_id,at=None):
 from .models import BeginnerProtection
 at=at or datetime.now(timezone.utc);bp=ensure_beginner_protection(session,player_id,at)
 if bp.ended_at:return bp
 exp=bp.expires_at if bp.expires_at.tzinfo else bp.expires_at.replace(tzinfo=timezone.utc)
 reason=None
 # Any city reaching Town Hall 5 ends account/player protection.
 cities=session.scalars(select(City).where(City.player_id==player_id)).all()
 if any((town_hall_building(session,c.id) is not None and current_level(session,town_hall_building(session,c.id))>=5) for c in cities):reason='TOWN_HALL_LEVEL_5'
 elif at>=exp:reason='SEVEN_DAYS_EXPIRED'
 if reason:
  bp.ended_at=at;bp.end_reason=reason
  if bp.notified_at is None:
   try:create_system_mail(session,player_id,'Beginner Protection ended','Your Beginner Protection period has ended.','BEGINNER_PROTECTION_ENDED',at)
   except Exception:pass
   bp.notified_at=at
  session.flush()
 return bp

def beginner_protection_status(session,player_id,at=None):
 at=at or datetime.now(timezone.utc);bp=refresh_beginner_protection(session,player_id,at)
 active=bp.ended_at is None
 exp=bp.expires_at if bp.expires_at.tzinfo else bp.expires_at.replace(tzinfo=timezone.utc)
 return {'active':active,'started_at':bp.started_at,'expires_at':bp.expires_at,'ended_at':bp.ended_at,'end_reason':bp.end_reason,
         'seconds_remaining':max(0,int((exp-at).total_seconds())) if active else 0,
         'rules':{'player_city_attack':False if active else True,'player_city_scout':False if active else True,'npc_city_attack':False if active else True,'npc_city_scout':False if active else True,'wilderness_attack':True,'wilderness_scout':True},
         'early_end':'ANY_TOWN_HALL_LEVEL_5'}

def _enforce_beginner_protection_march(session,player_id,mission,target,at=None):
 status=beginner_protection_status(session,player_id,at)
 mission=mission.upper();kind=(target or {}).get('kind','').upper()
 if status['active'] and kind in ('CITY','PLAYER_CITY','NPC','NPC_CITY') and mission in ('ATTACK','OCCUPY','SCOUT'):
  raise ValueError('Beginner Protection prevents scouting or attacking cities')
 owner=(target or {}).get('owner_player_id')
 if owner is not None and owner!=player_id and kind in ('CITY','PLAYER_CITY') and mission in ('ATTACK','OCCUPY','SCOUT'):
  if beginner_protection_status(session,owner,at)['active']:raise ValueError('target player is under Beginner Protection')

def create_march(session,player_id,city_id,mission,x,y,troops,resources,hero_id,camp_seconds,war_ensign,idempotency_key):
 from .models import Army,March,Hero,PlayerItem,MarchMission
 def work():
  settle_economy(session,city_id)
  city=session.get(City,city_id)
  from .models import Buff
  now=datetime.now(timezone.utc)
  for lock in session.scalars(select(Buff).where(Buff.player_id==player_id,Buff.buff_key=='advanced_teleport_march_lock')).all():
   ex=lock.expires_at if lock.expires_at.tzinfo else lock.expires_at.replace(tzinfo=timezone.utc)
   if ex>now and int((lock.metadata_json or {}).get('city_id',-1))==city_id:raise ValueError('advanced teleport march restriction active')
  target=_target_info(session,x,y)
  _enforce_beginner_protection_march(session,player_id,mission,target,now)
  preview=rally_preview(session,player_id,city_id,mission,x,y,troops,resources,camp_seconds,war_ensign)
  if len(_active_source_marches(session,city_id))>=preview['march_slots']:raise ValueError('Rally Spot march slots full')
  mission_u=mission.upper();hero=None
  if hero_id is not None:
   hero=session.get(Hero,hero_id)
   if not hero or hero.player_id!=player_id or hero.city_id!=city_id or hero.captured:raise ValueError('hero unavailable')
   if _hero_status(session,hero)['key']!='idle':raise ValueError('hero unavailable')
  if mission_u in ('ATTACK','OCCUPY') and not hero:raise ValueError(f'{mission_u.title()} requires a hero')
  if mission_u=='SCOUT' and int(troops.get('scout',0))<1:raise ValueError('Scout mission requires Scouts')
  if war_ensign:
   item=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key.in_(['war_ensign','war_rally_flag'])))
   if not item or item.quantity<1:raise ValueError('War Ensign required')
   item.quantity-=1
  # Revalidate and atomically remove source troops/resources + deployment food.
  for k,q in troops.items():
   row=session.scalar(select(TroopQuantity).where(TroopQuantity.city_id==city_id,TroopQuantity.troop_type_key==k));row.quantity-=int(q)
  for k,amt in resources.items():
   row=session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==k))
   if not row or row.quantity<int(amt):raise ValueError(f'insufficient {k}')
  foodrow=session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind=='food'))
  carried_food=int(resources.get('food',0))
  # Carried food and dispatch food are distinct costs.
  need=preview['food_required']+carried_food
  if not foodrow or foodrow.quantity<need:raise ValueError('insufficient food for march and carried cargo')
  for k,amt in resources.items():
   if k!='food':session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==k)).quantity-=int(amt)
  foodrow.quantity-=need
  army=Army(player_id=player_id,hero_id=hero_id,troops={k:int(v) for k,v in troops.items() if int(v)>0},resources={k:int(v) for k,v in resources.items() if int(v)>0});session.add(army);session.flush()
  now=datetime.now(timezone.utc);arrival=now+timedelta(seconds=preview['arrival_seconds'])
  march=March(army_id=army.id,source_city_id=city_id,target_x=x,target_y=y,mission=mission_u,departed_at=now,arrives_at=arrival,returns_at=None,status='MARCHING',camp_seconds=camp_seconds,distance=preview['distance'],travel_seconds=preview['travel_seconds'],food_cost=preview['food_required'],return_city_id=city_id,return_x=city.x,return_y=city.y);session.add(march);session.flush()
  session.add(MarchMission(march_id=march.id,mission_key=mission_u,mission_state={'phase':'OUTBOUND'}));session.flush()
  return {'march_id':march.id,'army_id':army.id,'status':'MARCHING','arrives_at':arrival.isoformat(),**preview}
 return idempotent_operation(session,player_id,idempotency_key,'CREATE_MARCH',work)

def recall_march(session,player_id,march_id,idempotency_key):
 from .models import March,Army
 def work():
  m=session.get(March,march_id);a=session.get(Army,m.army_id) if m else None
  if not m or not a or a.player_id!=player_id:raise ValueError('march not found')
  if m.status not in ('MARCHING','CAMPED','GARRISONED','ARRIVED_PENDING_RESOLUTION'):raise ValueError('march cannot be recalled')
  now=datetime.now(timezone.utc)
  if m.status=='MARCHING':
   departed=m.departed_at if m.departed_at.tzinfo else m.departed_at.replace(tzinfo=timezone.utc)
   elapsed=max(1,int((now-departed).total_seconds()))
   # If still in camp-time staging, it has not covered map distance yet.
   map_elapsed=max(1,min(m.travel_seconds,max(0,elapsed-m.camp_seconds)))
   ret=max(1,map_elapsed)
  else:ret=max(1,m.travel_seconds)
  m.status='RETURNING';m.recalled_at=now;m.returns_at=now+timedelta(seconds=ret)
  return {'march_id':m.id,'status':'RETURNING','returns_at':m.returns_at.isoformat()}
 return idempotent_operation(session,player_id,idempotency_key,'RECALL_MARCH',work)

def complete_returning_marches(session,city_id=None):
 from .models import March,Army,Hero
 q=select(March).where(March.status=='RETURNING'); 
 if city_id is not None:q=q.where(March.source_city_id==city_id)
 now=datetime.now(timezone.utc);done=[]
 for m in session.scalars(q).all():
  due=m.returns_at
  if due is None:continue
  if due.tzinfo is None:due=due.replace(tzinfo=timezone.utc)
  if due>now:continue
  a=session.get(Army,m.army_id)
  for k,n in a.troops.items():
   row=session.scalar(select(TroopQuantity).where(TroopQuantity.city_id==m.source_city_id,TroopQuantity.troop_type_key==k))
   if not row:row=TroopQuantity(city_id=m.source_city_id,troop_type_key=k,quantity=0);session.add(row)
   row.quantity+=int(n)
  for k,n in a.resources.items():
   row=session.scalar(select(Resource).where(Resource.city_id==m.source_city_id,Resource.kind==k))
   if not row:row=Resource(city_id=m.source_city_id,kind=k,quantity=0);session.add(row)
   row.quantity+=int(n)
  m.status='RETURNED';done.append(m)
 return done

def rally_open_gates(session,player_id,city_id,open_gates,idempotency_key):
 from .models import RallySpotState
 def work():
  c=session.get(City,city_id)
  if not c or c.player_id!=player_id:raise ValueError('city not owned')
  row=session.scalar(select(RallySpotState).where(RallySpotState.city_id==city_id))
  if not row:row=RallySpotState(city_id=city_id);session.add(row)
  row.open_gates=bool(open_gates);return {'open_gates':row.open_gates}
 return idempotent_operation(session,player_id,idempotency_key,'RALLY_OPEN_GATES',work)

def heal_wounded(session,player_id,city_id,selections,idempotency_key):
 from .models import WoundedTroop
 def work():
  c=session.get(City,city_id)
  if not c or c.player_id!=player_id:raise ValueError('city not owned')
  # Historical Medic Camp heals for gold, but exact per-unit Age-I gold table is not verified.
  raise ValueError('HISTORICAL_VALUE_UNKNOWN: exact Age I Medic Camp healing gold costs are unresolved')
 return idempotent_operation(session,player_id,idempotency_key,'HEAL_WOUNDED',work)

def rally_exercise(session,city_id,attacker,defender):
 from .combat import simulateBattle,Age1CombatRules
 defs=DATA['troop_types'];zero={k:0 for k in ('military_tradition','iron_working','medicine','archery','compass','horseback_riding')}
 result=simulateBattle({'unit_definitions':defs,'attacker':{'troops':{k:int(v) for k,v in attacker.items() if int(v)>0},'technologies':zero,'hero_attack':0},'defender':{'troops':{k:int(v) for k,v in defender.items() if int(v)>0},'technologies':zero,'hero_attack':0,'fortifications':{},'wall_level':0}},Age1CombatRules(hero_attack_mode='disabled'))
 return {'status':'SIMULATED','winner':result.winner,'rounds':result.rounds,'attacker_survivors':result.attacker_survivors,'defender_survivors':result.defender_survivors,'attacker_losses':result.attacker_losses,'defender_losses':result.defender_losses}

BARRACK_TROOPS=('worker','warrior','scout','pikeman','swordsman','archer','cavalry','cataphract','transporter','ballista','battering_ram','catapult')
def barracks_level(session,barracks_id):
 b=session.get(Building,barracks_id)
 if not b or b.definition_key!='barracks':return 0
 return current_level(session,b)
def troop_prerequisite_status(session,city_id,barracks_id,troop_key):
 if troop_key not in DATA['troop_types']:raise ValueError('unknown troop type')
 spec=DATA['troop_types'][troop_key];bl=barracks_level(session,barracks_id);missing=[]
 if bl<spec['barracks_level']:missing.append({'type':'building','key':'barracks','required':spec['barracks_level'],'current':bl})
 for key,need in spec['technology_requirements'].items():
  cur=effective_technology_level(session,city_id,key)
  if cur<need:missing.append({'type':'technology','key':key,'required':need,'current':cur})
 return missing

def complete_training(session,city_id=None,barracks_id=None):
 from .models import TrainingQueue
 now=datetime.now(timezone.utc); completed=[]
 q=select(TrainingQueue).where(TrainingQueue.status.in_(['ACTIVE','QUEUED']))
 if city_id is not None:q=q.where(TrainingQueue.city_id==city_id)
 if barracks_id is not None:q=q.where(TrainingQueue.barracks_id==barracks_id)
 rows=session.scalars(q.order_by(TrainingQueue.barracks_id,TrainingQueue.id)).all()
 by={}
 for row in rows:by.setdefault(row.barracks_id,[]).append(row)
 for bid,items in by.items():
  # Recover legacy/queued state and process as much elapsed offline time as possible.
  active=next((x for x in items if x.status=='ACTIVE'),None)
  if active is None and items:
   first=items[0];first.status='ACTIVE';first.started_at=first.started_at or first.queued_at;first.completes_at=first.started_at+timedelta(seconds=first.duration_seconds);active=first
  while active:
   due=active.completes_at
   if due is None:break
   if due.tzinfo is None:due=due.replace(tzinfo=timezone.utc)
   if due>now:break
   tq=session.scalar(select(TroopQuantity).where(TroopQuantity.city_id==active.city_id,TroopQuantity.troop_type_key==active.troop_type_key))
   if not tq:tq=TroopQuantity(city_id=active.city_id,troop_type_key=active.troop_type_key,quantity=0);session.add(tq)
   tq.quantity+=active.quantity
   # Age I mayor receives training XP when the batch finishes.
   mayor=current_mayor(session,active.city_id)
   if mayor:
    xp_per={'worker':1.125,'warrior':1.525,'scout':3.475,'pikeman':4.5,'swordsman':6.75,'archer':7,'cavalry':14.25,'cataphract':43.75,'transporter':14.875,'ballista':50,'battering_ram':68.75,'catapult':145}.get(active.troop_type_key,0)
    if xp_per:add_hero_experience(session,mayor.id,xp_per*active.quantity)
   active.status='COMPLETE';completed.append(active)
   nxt=next((x for x in items if x.status=='QUEUED' and x.id>active.id),None)
   if not nxt:active=None;break
   nxt.status='ACTIVE';nxt.started_at=due;nxt.completes_at=due+timedelta(seconds=nxt.duration_seconds);active=nxt
 return completed

def barracks_queue(session,barracks_id):
 from .models import TrainingQueue
 b=session.get(Building,barracks_id)
 if not b:return []
 complete_training(session,b.city_id,barracks_id)
 return session.scalars(select(TrainingQueue).where(TrainingQueue.barracks_id==barracks_id,TrainingQueue.status.in_(['ACTIVE','QUEUED'])).order_by(TrainingQueue.id)).all()

def train_troops(session,player_id,city_id,barracks_id,troop_key,quantity,idempotency_key):
 from .models import TrainingQueue,PopulationState
 def work():
  settle_economy(session,city_id)
  complete_training(session,city_id,barracks_id)
  city=session.get(City,city_id);b=session.get(Building,barracks_id)
  if not city or city.player_id!=player_id or not b or b.city_id!=city_id or b.definition_key!='barracks':raise ValueError('Barracks not found')
  if quantity<1:raise ValueError('quantity must be positive')
  spec=DATA['troop_types'].get(troop_key)
  if not spec:raise ValueError('unknown troop type')
  missing=troop_prerequisite_status(session,city_id,barracks_id,troop_key)
  if missing:raise ValueError('missing prerequisites: '+','.join(f"{x['key']} {x['required']}" for x in missing))
  level=barracks_level(session,barracks_id);queue=barracks_queue(session,barracks_id)
  if len(queue)>=level:raise ValueError('Barracks training queue full')
  costs={k:int(v)*quantity for k,v in spec['cost'].items()}
  for kind,amt in costs.items():
   r=session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==kind))
   if not r or r.quantity<amt:raise ValueError(f'insufficient {kind}')
  pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id))
  needpop=spec['population']*quantity
  if not pop or pop.idle_population<needpop:raise ValueError('insufficient idle population')
  for kind,amt in costs.items():session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==kind)).quantity-=amt
  pop.idle_population-=needpop;pop.population-=needpop;city.idle_population=pop.idle_population;city.population=pop.population
  stats=mayor_stats(session,city_id);ms=effective_technology_level(session,city_id,'military_science')
  duration=max(1,int(round(spec['base_training_seconds']*quantity*(0.9**ms)*(0.995**stats['attack']))))
  now=datetime.now(timezone.utc);active=next((x for x in queue if x.status=='ACTIVE'),None)
  status='QUEUED';started=None;completes=None
  if active is None and not queue:
   status='ACTIVE';started=now;completes=now+timedelta(seconds=duration)
  row=TrainingQueue(city_id=city_id,barracks_id=barracks_id,troop_type_key=troop_key,quantity=quantity,hero_attack_snapshot=stats['attack'],military_science_snapshot=ms,duration_seconds=duration,queued_at=now,started_at=started,completes_at=completes,status=status);session.add(row);session.flush()
  return {'training_queue_id':row.id,'barracks_id':barracks_id,'troop_type':troop_key,'quantity':quantity,'status':status,'duration_seconds':duration,'completes_at':None if completes is None else completes.isoformat(),'hero_attack':stats['attack'],'military_science':ms}
 return idempotent_operation(session,player_id,idempotency_key,'TRAIN_TROOPS',work)


def beacon_tower_level(session,city_id):return _building_max_level(session,city_id,'beacon_tower')
def _approx_enemy_count(n):
 if n<100:return 'few'
 if n<1000:return 'hundreds'
 if n<10000:return 'thousands'
 if n<100000:return 'tens of thousands'
 return '100,000+'
def beacon_incoming_alerts(session,city_id):
 from .models import March,Army,Hero,Player,PlayerProgression,Technology
 city=session.get(City,city_id)
 if not city:return []
 lv=beacon_tower_level(session,city_id)
 if lv<1:return []
 rows=session.scalars(select(March).where(March.target_x==city.x,March.target_y==city.y,March.status.in_(['MARCHING','CAMPED']))).all()
 out=[]
 for m in rows:
  army=session.get(Army,m.army_id)
  if not army or army.player_id==city.player_id:continue
  # Allied transport/reinforcement is not an invasion warning.
  if m.mission in ('REINFORCE','TRANSPORT') and _same_alliance(session,army.player_id,city.player_id):continue
  a={'march_id':m.id,'warning':True}
  if lv>=2:a['purpose']=m.mission
  if lv>=3:a['arrives_at']=m.arrives_at.isoformat() if m.arrives_at else None
  if lv>=4:
   prog=session.scalar(select(PlayerProgression).where(PlayerProgression.player_id==army.player_id))
   a['enemy_lord_status']={'prestige':prog.prestige if prog else None,'honor':prog.honor if prog else None,'title_rank':prog.title_rank_key if prog else None}
  if lv>=5:
   src=session.get(City,m.source_city_id);a['departure_location']={'x':src.x,'y':src.y} if src else None
  if lv>=6:a['arms_branch']=sorted([k for k,v in army.troops.items() if int(v)>0])
  if lv>=7:a['troops']={k:_approx_enemy_count(int(v)) for k,v in army.troops.items() if int(v)>0}
  if lv>=8:a['troops']={k:int(v) for k,v in army.troops.items() if int(v)>0}
  if lv>=9:
   h=session.get(Hero,army.hero_id) if army.hero_id else None;a['hero_level']=h.level if h else None
  if lv>=10:
   a['military_technology']={k:technology_level(session,army.player_id,k) for k in ('military_science','military_tradition','iron_working','logistics','compass','horseback_riding','archery','medicine')}
  out.append(a)
 return out

def forge_level(session,city_id):return _building_max_level(session,city_id,'forge')

def stable_level(session,city_id):return _building_max_level(session,city_id,'stable')

def workshop_level(session,city_id):return _building_max_level(session,city_id,'workshop')

def relief_station_level(session,city_id):return _building_max_level(session,city_id,'relief_station')
def relief_station_multiplier(session,city_id):
 lv=relief_station_level(session,city_id);return {0:1,1:2,2:2,3:2,4:3,5:4,6:4,7:4,8:5,9:5,10:6}.get(lv,1)


def walls_level(session,city_id):return _building_max_level(session,city_id,'walls')
def wall_capacity(session,city_id):
 from .models import Fortification
 lv=walls_level(session,city_id)
 if lv<1:return {'durability':0,'effective_durability':0,'spaces':0,'used':0,'vacant':0,'queue_slots':0}
 d=DATA['building_levels']['walls'][str(lv)]
 used=0
 for f in session.scalars(select(Fortification).where(Fortification.city_id==city_id)).all():used+=DATA['fortifications'][f.definition_key]['space']*f.quantity
 from .models import FortificationQueue
 for q in session.scalars(select(FortificationQueue).where(FortificationQueue.city_id==city_id,FortificationQueue.status.in_(['ACTIVE','QUEUED']))).all():used+=DATA['fortifications'][q.definition_key]['space']*q.quantity
 dur=d['durability'];return {'durability':dur,'effective_durability':int(dur*wall_fortification_life_multiplier(session,city_id)),'spaces':d['fortified_spaces'],'used':used,'vacant':d['fortified_spaces']-used,'queue_slots':lv}
def fortification_prerequisites(session,city_id,key):
 d=DATA['fortifications'][key];missing=[]
 if walls_level(session,city_id)<d['wall_level']:missing.append({'type':'walls','required':d['wall_level']})
 for k,v in d.get('technology_requirements',{}).items():
  if effective_technology_level(session,city_id,k)<v:missing.append({'type':'technology','key':k,'required':v})
 return missing
def complete_fortifications(session,city_id):
 from .models import FortificationQueue,Fortification
 now=datetime.now(timezone.utc);rows=session.scalars(select(FortificationQueue).where(FortificationQueue.city_id==city_id,FortificationQueue.status.in_(['ACTIVE','QUEUED'])).order_by(FortificationQueue.id)).all()
 changed=True
 while changed:
  changed=False;active=next((q for q in rows if q.status=='ACTIVE'),None)
  if active:
   due=active.completes_at
   if due.tzinfo is None:due=due.replace(tzinfo=timezone.utc)
   if due<=now:
    f=session.scalar(select(Fortification).where(Fortification.city_id==city_id,Fortification.definition_key==active.definition_key))
    if not f:f=Fortification(city_id=city_id,definition_key=active.definition_key,quantity=0);session.add(f)
    f.quantity+=active.quantity;active.status='COMPLETE';changed=True
  if not next((q for q in rows if q.status=='ACTIVE'),None):
   nxt=next((q for q in rows if q.status=='QUEUED'),None)
   if nxt:
    prev_done=max([q.completes_at for q in rows if q.status=='COMPLETE' and q.completes_at] or [now])
    st=max(now,prev_done.replace(tzinfo=timezone.utc) if prev_done.tzinfo is None else prev_done)
    nxt.status='ACTIVE';nxt.started_at=st;nxt.completes_at=st+timedelta(seconds=nxt.duration_seconds);changed=True
 return rows
def fortification_build_seconds(session,city_id,key,base_seconds):
 d=DATA['fortifications'][key]
 construction=effective_technology_level(session,city_id,'construction')
 politics=mayor_stats(session,city_id)['politics']
 divisor=float(d.get('politics_exponent_divisor',1))
 return max(1,int(base_seconds*(0.9**construction)*(0.995**(politics/divisor))))
def build_fortification(session,player_id,city_id,key,quantity,idempotency_key):
 from .models import FortificationQueue
 def work():
  complete_fortifications(session,city_id);c=session.get(City,city_id)
  if not c or c.player_id!=player_id:raise ValueError('city not owned')
  if key not in DATA['fortifications'] or quantity<1:raise ValueError('invalid fortification')
  missing=fortification_prerequisites(session,city_id,key)
  if missing:raise ValueError('missing prerequisites: '+str(missing))
  cap=wall_capacity(session,city_id);queue=session.scalars(select(FortificationQueue).where(FortificationQueue.city_id==city_id,FortificationQueue.status.in_(['ACTIVE','QUEUED']))).all()
  if len(queue)>=cap['queue_slots']:raise ValueError('Wall fortification queue full')
  d=DATA['fortifications'][key];needspace=d['space']*quantity
  if needspace>cap['vacant']:raise ValueError('insufficient fortified space')
  costs={k:v*quantity for k,v in d['cost'].items()}
  for k,v in costs.items():
   r=session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==k))
   if not r or r.quantity<v:raise ValueError(f'insufficient {k}')
  for k,v in costs.items():session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==k)).quantity-=v
  duration=fortification_build_seconds(session,city_id,key,d['base_seconds']*quantity);now=datetime.now(timezone.utc)
  active=next((x for x in queue if x.status=='ACTIVE'),None);status='ACTIVE' if active is None and not queue else 'QUEUED'
  row=FortificationQueue(city_id=city_id,definition_key=key,quantity=quantity,started_at=now if status=='ACTIVE' else now,completes_at=now+timedelta(seconds=duration) if status=='ACTIVE' else now,status=status,position=len(queue)+1);row.duration_seconds=duration
  # duration_seconds is supplied dynamically for compatibility until migration column below.
  session.add(row);session.flush()
  return {'queue_id':row.id,'type':key,'quantity':quantity,'status':status,'duration_seconds':duration}
 return idempotent_operation(session,player_id,idempotency_key,'BUILD_FORTIFICATION',work)
def archer_tower_range(session,city_id):
 return int(1300*(1+0.05*(walls_level(session,city_id)+effective_technology_level(session,city_id,'archery'))))
def fortification_repair_rate(session,city_id,key):
 base={'trap':.05,'abatis':.05,'archer_tower':0,'rolling_log':.07,'defensive_trebuchet':.08}[key]
 return base*(1+effective_technology_level(session,city_id,'machinery'))


def complete_demolition(session,city_id=None):
 from .models import DemolitionQueue
 q=select(DemolitionQueue).where(DemolitionQueue.status=='ACTIVE')
 if city_id is not None:q=q.where(DemolitionQueue.city_id==city_id)
 now=datetime.now(timezone.utc);done=[]
 for row in session.scalars(q).all():
  due=row.completes_at
  if due.tzinfo is None:due=due.replace(tzinfo=timezone.utc)
  if due>now:continue
  b=session.get(Building,row.building_id)
  if not b:row.status='COMPLETE';continue
  if b.plot_kind=='FIELD':accrue_resources(session,row.city_id,due)
  for k,v in row.refund.items():
   r=session.scalar(select(Resource).where(Resource.city_id==row.city_id,Resource.kind==k))
   if not r:r=Resource(city_id=row.city_id,kind=k,quantity=0);session.add(r)
   r.quantity+=int(v)
  if row.to_level<=0 and b.definition_key!='walls':
   bl=session.scalars(select(BuildingLevel).where(BuildingLevel.building_id==b.id)).all()
   for x in bl:session.delete(x)
   session.delete(b)
  else:
   b.level=max(0,row.to_level);bl=session.scalar(select(BuildingLevel).where(BuildingLevel.building_id==b.id))
   if bl:bl.level=b.level
  row.status='COMPLETE';done.append(row)
  if b.definition_key=='cottage':sync_population_capacity(session,row.city_id)
 return done
def _demolition_level_spec(b):
 return building_level(b.definition_key,b.level)
def start_demolish_one_level(session,player_id,city_id,building_id,idempotency_key):
 from .models import DemolitionQueue
 def work():
  complete_demolition(session,city_id);c=session.get(City,city_id);b=session.get(Building,building_id)
  if not c or c.player_id!=player_id or not b or b.city_id!=city_id:raise ValueError('building not found')
  if b.plot_kind=='FIELD':accrue_resources(session,city_id)
  if b.definition_key=='town_hall':raise ValueError('Town Hall cannot be demolished')
  if b.definition_key=='barracks':
   from .models import TrainingQueue
   if session.scalar(select(TrainingQueue).where(TrainingQueue.barracks_id==b.id,TrainingQueue.status.in_(['ACTIVE','QUEUED']))):raise ValueError('cannot demolish Barracks with active training')
  if b.definition_key=='walls' and b.level>1:
   current=wall_capacity(session,city_id);nextspace=DATA['building_levels']['walls'][str(b.level-1)]['fortified_spaces']
   if current['used']>nextspace:raise ValueError('fortifications exceed lower Wall capacity')
  if b.level<1:raise ValueError('building already level 0')
  if session.scalar(select(ConstructionQueue).where(ConstructionQueue.city_id==city_id,ConstructionQueue.status=='ACTIVE')) or session.scalar(select(DemolitionQueue).where(DemolitionQueue.city_id==city_id,DemolitionQueue.status=='ACTIVE')):raise ValueError('city construction/demolition already active')
  spec=_demolition_level_spec(b)
  if not spec:raise ValueError('HISTORICAL_VALUE_UNKNOWN: level construction table unavailable for demolition')
  refund={k:int(v*0.30) for k,v in spec['cost'].items()}
  duration=mayor_construction_seconds(session,city_id,spec['seconds']);now=datetime.now(timezone.utc)
  row=DemolitionQueue(city_id=city_id,building_id=b.id,from_level=b.level,to_level=b.level-1,started_at=now,completes_at=now+timedelta(seconds=duration),refund=refund,status='ACTIVE');session.add(row);session.flush()
  return {'demolition_id':row.id,'from_level':b.level,'to_level':b.level-1,'refund':refund,'seconds':duration,'completes_at':row.completes_at.isoformat()}
 return idempotent_operation(session,player_id,idempotency_key,'DEMOLISH_ONE_LEVEL',work)
def dynamite_building(session,player_id,city_id,building_id,idempotency_key):
 from .models import PlayerItem,DemolitionQueue
 def work():
  complete_demolition(session,city_id);c=session.get(City,city_id);b=session.get(Building,building_id)
  if not c or c.player_id!=player_id or not b or b.city_id!=city_id:raise ValueError('building not found')
  if b.plot_kind=='FIELD':accrue_resources(session,city_id)
  if b.definition_key=='town_hall':raise ValueError('Town Hall cannot be demolished')
  if b.definition_key=='walls':raise ValueError('HISTORICAL_VALUE_UNKNOWN: complete Dynamite behavior for dedicated Walls is unresolved')
  if b.definition_key=='barracks':
   from .models import TrainingQueue
   if session.scalar(select(TrainingQueue).where(TrainingQueue.barracks_id==b.id,TrainingQueue.status.in_(['ACTIVE','QUEUED']))):raise ValueError('cannot demolish Barracks with active training')
  if session.scalar(select(ConstructionQueue).where(ConstructionQueue.city_id==city_id,ConstructionQueue.status=='ACTIVE')) or session.scalar(select(DemolitionQueue).where(DemolitionQueue.city_id==city_id,DemolitionQueue.status=='ACTIVE')):raise ValueError('city construction/demolition already active')
  item=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key=='dynamite'))
  if not item or item.quantity<1:raise ValueError('Dynamite required')
  item.quantity-=1
  key=b.definition_key
  for bl in session.scalars(select(BuildingLevel).where(BuildingLevel.building_id==b.id)).all():session.delete(bl)
  session.delete(b);session.flush()
  if key=='cottage':sync_population_capacity(session,city_id)
  return {'building_id':building_id,'status':'DEMOLISHED','refund':{},'dynamite_consumed':1}
 return idempotent_operation(session,player_id,idempotency_key,'DYNAMITE_BUILDING',work)

RESOURCE_FIELD_KEYS=('farm','sawmill','quarry','ironmine')
RESOURCE_KINDS=('food','lumber','stone','iron')
RESOURCE_BUILDING_FOR={'food':'farm','lumber':'sawmill','stone':'quarry','iron':'ironmine'}

def production_percentages(session,city_id):
 from .models import PlayerSetting
 city=session.get(City,city_id); key=f'city:{city_id}:production_rates'
 row=session.scalar(select(PlayerSetting).where(PlayerSetting.player_id==city.player_id,PlayerSetting.key==key)) if city else None
 vals=row.value if row else {}
 return {k:max(0,min(100,int(vals.get(k,100)))) for k in RESOURCE_KINDS}

def resource_field_totals(session,city_id):
 out={k:{'base_per_hour':0.0,'labor':0.0,'capacity':0,'fields':0} for k in RESOURCE_KINDS}
 for b in session.scalars(select(Building).where(Building.city_id==city_id,Building.plot_kind=='FIELD',Building.definition_key.in_(RESOURCE_FIELD_KEYS))).all():
  lv=current_level(session,b)
  if lv<=0:continue
  d=DATA['building_levels'][b.definition_key].get(str(lv)); kind=DATA['buildings'][b.definition_key]['resource_kind']
  if d:
   out[kind]['base_per_hour']+=float(d['production_per_hour']);out[kind]['labor']+=float(d['labor']);out[kind]['capacity']+=int(d['storage_capacity']);out[kind]['fields']+=1
 return out

def valley_production_bonus_percent(session,city_id,kind):
 from .models import Valley
 type_kind={'grassland':'food','swamp':'food','lake':'food','hill':'iron','desert':'stone','forest':'lumber'}
 table=DATA['resource_production']['valley_bonus_table'];total=0
 for v in session.scalars(select(Valley).where(Valley.city_id==city_id)).all():
  if type_kind.get(v.valley_type.lower())==kind and v.valley_type.lower() in table and 1<=v.level<=10:total+=table[v.valley_type.lower()][v.level-1]
 return total

def resource_item_bonus_percent(session,city_id,kind,at=None):
 from .models import Buff
 at=at or datetime.now(timezone.utc);city=session.get(City,city_id)
 if not city:return 0
 total=0
 for b in session.scalars(select(Buff).where(Buff.player_id==city.player_id)).all():
  st=b.starts_at if b.starts_at.tzinfo else b.starts_at.replace(tzinfo=timezone.utc);ex=b.expires_at if b.expires_at.tzinfo else b.expires_at.replace(tzinfo=timezone.utc)
  if not(st<=at<ex):continue
  md=b.metadata_json or {}; target_city=md.get('city_id')
  if target_city is not None and int(target_city)!=city_id:continue
  spec=DATA['resource_production']['production_items'].get(kind,{}).get(b.buff_key)
  if spec:total+=int(spec['percent'])
 return total

def resource_production_snapshot(session,city_id,at=None):
 at=at or datetime.now(timezone.utc);city=session.get(City,city_id)
 if not city:raise ValueError('city not found')
 totals=resource_field_totals(session,city_id);rates=production_percentages(session,city_id);politics=mayor_stats(session,city_id)['politics']
 pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id));population=pop.population if pop else city.population
 labor_by={k:totals[k]['labor']*rates[k]/100.0 for k in RESOURCE_KINDS};required=sum(labor_by.values())
 # Age I assigns population to production by the Town Hall percentages. If assigned labor exceeds current population,
 # all assigned resource work is proportionally constrained rather than fabricating workers.
 labor_factor=min(1.0,(population/required)) if required>0 else 1.0
 out={}
 tech_by=DATA['resource_production']['technology_by_resource']
 for k in RESOURCE_KINDS:
  tech=effective_technology_level(session,city_id,tech_by[k]);valley=valley_production_bonus_percent(session,city_id,k);item=resource_item_bonus_percent(session,city_id,k,at)
  base=totals[k]['base_per_hour']; percent=rates[k]
  # Documented Age I bonuses are percentages of base production; the Town Hall production rate controls assigned labor/output.
  bonus_percent=10*tech+politics+valley+item
  effective=(base*(1.0+bonus_percent/100.0))*(percent/100.0)*labor_factor
  out[k]={**totals[k],'production_percent':percent,'assigned_labor':labor_by[k],'technology_level':tech,'technology_bonus_percent':10*tech,'mayor_politics':politics,'mayor_bonus_percent':politics,'valley_bonus_percent':valley,'item_bonus_percent':item,'population_factor':labor_factor,'effective_per_hour':effective}
 return {'resources':out,'population':population,'assigned_labor':required,'idle_population':max(0,int(population-required*labor_factor)),'labor_factor':labor_factor,'calculated_at':at}

def _ensure_resource_rows(session,city_id,at):
 from .models import ResourceProduction,ResourceCapacity
 rs={x.kind:x for x in session.scalars(select(Resource).where(Resource.city_id==city_id)).all()};ps={x.resource_kind:x for x in session.scalars(select(ResourceProduction).where(ResourceProduction.city_id==city_id)).all()};cs={x.resource_kind:x for x in session.scalars(select(ResourceCapacity).where(ResourceCapacity.city_id==city_id)).all()}
 for k in RESOURCE_KINDS:
  if k not in rs:rs[k]=Resource(city_id=city_id,kind=k,quantity=0,capacity=0,updated_at=at);session.add(rs[k])
  if k not in ps:ps[k]=ResourceProduction(city_id=city_id,resource_kind=k,per_hour=0,fractional_remainder=0,last_calculated_at=at);session.add(ps[k])
  if k not in cs:cs[k]=ResourceCapacity(city_id=city_id,resource_kind=k,capacity=0);session.add(cs[k])
 session.flush();return rs,ps,cs

def accrue_resources(session,city_id,now=None):
 from .models import ResourceProduction,Buff
 now=now or datetime.now(timezone.utc);rs,ps,cs=_ensure_resource_rows(session,city_id,now);city=session.get(City,city_id)
 for k in RESOURCE_KINDS:
  row=ps[k];last=row.last_calculated_at or now
  if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
  if now<last:continue
  points=[last,now]
  if city:
   for b in session.scalars(select(Buff).where(Buff.player_id==city.player_id)).all():
    if b.buff_key not in DATA['resource_production']['production_items'].get(k,{}):continue
    st=b.starts_at if b.starts_at.tzinfo else b.starts_at.replace(tzinfo=timezone.utc);ex=b.expires_at if b.expires_at.tzinfo else b.expires_at.replace(tzinfo=timezone.utc)
    if last<st<now:points.append(st)
    if last<ex<now:points.append(ex)
  points=sorted(set(points));raw=float(row.fractional_remainder or 0)
  for a,z in zip(points,points[1:]):
   mid=a+(z-a)/2;snap_mid=resource_production_snapshot(session,city_id,mid);raw+=(snap_mid['resources'][k]['effective_per_hour']-(troop_food_upkeep(session,city_id)['total_per_hour'] if k=='food' else 0))*(z-a).total_seconds()/3600.0
  whole=int(raw);row.fractional_remainder=raw-whole
  snap=resource_production_snapshot(session,city_id,now);cap=int(snap['resources'][k]['capacity']);cs[k].capacity=cap;rs[k].capacity=cap
  if whole!=0:rs[k].quantity=max(0,min(cap,rs[k].quantity+whole))
  rate=snap['resources'][k]['effective_per_hour'];row.per_hour=rate;row.last_calculated_at=now;rs[k].production_per_hour=rate;rs[k].updated_at=now
 snap=resource_production_snapshot(session,city_id,now);pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id))
 if pop:pop.idle_population=snap['idle_population'];city=session.get(City,city_id);city.idle_population=pop.idle_population
 session.flush();return snap

def field_construction_options(session,city_id):
 complete_construction(session,city_id);allowed=sync_exterior_field_unlocks(session,city_id);out=[]
 for key in RESOURCE_FIELD_KEYS:
  d=DATA['buildings'][key];spec=DATA['building_levels'][key]['1'];out.append({'key':key,'name':d['name'],'purpose':d['purpose'],'cost':spec['cost'],'seconds':spec['seconds'],'labor':spec['labor'],'production_per_hour':spec['production_per_hour'],'storage_capacity':spec['storage_capacity'],'available':True})
 return {'allowed_plots':allowed,'options':out}

def start_field_construction(session,player_id,city_id,plot_index,building_key,idempotency_key):
 def work():
  complete_construction(session,city_id);accrue_resources(session,city_id)
  city=session.get(City,city_id);allowed=sync_exterior_field_unlocks(session,city_id)
  if not city or city.player_id!=player_id:raise ValueError('city not owned by player')
  if building_key not in RESOURCE_FIELD_KEYS:raise ValueError('only Farm, Sawmill, Quarry, or Iron Mine may occupy resource fields')
  if plot_index<1 or plot_index>allowed:raise ValueError('resource plot is locked by Town Hall level')
  if session.scalar(select(Building).where(Building.city_id==city_id,Building.plot_kind=='FIELD',Building.plot_index==plot_index)):raise ValueError('resource plot occupied')
  if session.scalar(select(ConstructionQueue).where(ConstructionQueue.city_id==city_id,ConstructionQueue.status=='ACTIVE')):raise ValueError('Age I permits only one active building construction per city')
  spec=DATA['building_levels'][building_key]['1'];spend_resources(session,city_id,spec['cost']);b=Building(city_id=city_id,plot_kind='FIELD',plot_index=plot_index,definition_key=building_key,level=0);session.add(b);session.flush();session.add(BuildingLevel(building_id=b.id,level=0));now=datetime.now(timezone.utc);seconds=mayor_construction_seconds(session,city_id,spec['seconds']);q=ConstructionQueue(city_id=city_id,building_id=b.id,target_level=1,started_at=now,completes_at=now+timedelta(seconds=seconds),status='ACTIVE');session.add(q);session.flush();return {'building_id':b.id,'queue_id':q.id,'plot_index':plot_index,'definition_key':building_key,'target_level':1,'completes_at':q.completes_at.isoformat()}
 return idempotent_operation(session,player_id,idempotency_key,'START_FIELD_CONSTRUCTION',work)

def apply_production_item(session,player_id,city_id,item_key,idempotency_key):
 from .models import Buff,PlayerItem
 def work():
  accrue_resources(session,city_id);city=session.get(City,city_id)
  if not city or city.player_id!=player_id:raise ValueError('city not owned by player')
  kind=next((k for k,v in DATA['resource_production']['production_items'].items() if item_key in v),None)
  if not kind:raise ValueError('not a verified Age I resource-production item')
  inv=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==item_key))
  if not inv or inv.quantity<1:raise ValueError(f'{item_key} required')
  inv.quantity-=1;spec=DATA['resource_production']['production_items'][kind][item_key];now=datetime.now(timezone.utc)
  active=session.scalar(select(Buff).where(Buff.player_id==player_id,Buff.buff_key==item_key,Buff.expires_at>now))
  if active:
   ex=active.expires_at if active.expires_at.tzinfo else active.expires_at.replace(tzinfo=timezone.utc);active.expires_at=ex+timedelta(seconds=spec['seconds']);active.metadata_json={'city_id':city_id,'resource_kind':kind}
  else:
   active=Buff(player_id=player_id,buff_key=item_key,starts_at=now,expires_at=now+timedelta(seconds=spec['seconds']),metadata_json={'city_id':city_id,'resource_kind':kind});session.add(active)
  session.flush();return {'item':item_key,'resource_kind':kind,'bonus_percent':spec['percent'],'expires_at':active.expires_at.isoformat()}
 return idempotent_operation(session,player_id,idempotency_key,'APPLY_PRODUCTION_ITEM',work)


ECONOMY_TICK_SECONDS=360

def troop_population_cost(session,city_id):
 from .models import TrainingQueue
 total=0
 for row in session.scalars(select(TroopQuantity).where(TroopQuantity.city_id==city_id)).all():
  spec=DATA['troop_types'].get(row.troop_type_key)
  if spec:total+=int(spec['population'])*int(row.quantity)
 for q in session.scalars(select(TrainingQueue).where(TrainingQueue.city_id==city_id,TrainingQueue.status.in_(['ACTIVE','QUEUED']))).all():
  spec=DATA['troop_types'].get(q.troop_type_key)
  if spec:total+=int(spec['population'])*int(q.quantity)
 return total

def troop_food_upkeep(session,city_id):
 """Age I hourly food upkeep: garrisoned at 1x; this city's armies outside at 2x."""
 from .models import Army,March,ForeignGarrison
 garrisoned=0
 for row in session.scalars(select(TroopQuantity).where(TroopQuantity.city_id==city_id)).all():
  spec=DATA['troop_types'].get(row.troop_type_key)
  if spec:garrisoned+=int(spec['food_upkeep_per_hour'])*int(row.quantity)
 # Allied reinforcements consume the host city's food at normal in-city upkeep.
 for g in session.scalars(select(ForeignGarrison).where(ForeignGarrison.host_city_id==city_id,ForeignGarrison.status=='GARRISONED')).all():
  for key,n in (g.troops or {}).items():
   spec=DATA['troop_types'].get(key)
   if spec:garrisoned+=int(spec['food_upkeep_per_hour'])*int(n)
 outside=0;seen=set()
 for march in session.scalars(select(March).where(March.source_city_id==city_id,March.status.in_(['MARCHING','CAMPED','RETURNING','ARRIVED_PENDING_RESOLUTION']))).all():
  if march.army_id in seen:continue
  seen.add(march.army_id);army=session.get(Army,march.army_id)
  if not army:continue
  for key,n in (army.troops or {}).items():
   spec=DATA['troop_types'].get(key)
   if spec:outside+=int(spec['food_upkeep_per_hour'])*int(n)*2
 return {'garrisoned_per_hour':garrisoned,'outside_per_hour':outside,'total_per_hour':garrisoned+outside}

def hero_salary_per_hour_city(session,city_id):
 from .models import Hero
 return sum(20*int(h.level) for h in session.scalars(select(Hero).where(Hero.city_id==city_id)).all())

def population_breakdown(session,city_id,at=None):
 at=at or datetime.now(timezone.utc);pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id));city=session.get(City,city_id)
 population=int(pop.population if pop else city.population);limit=int(pop.population_limit if pop else cottage_population_capacity(session,city_id))
 snap=resource_production_snapshot(session,city_id,at);working=int(sum(v['assigned_labor'] for v in snap['resources'].values())*snap['labor_factor'])
 troop_pop=troop_population_cost(session,city_id)
 # Troop population is historical population consumed when recruited, not part of current civilian population.
 idle=population-working
 return {'population':population,'population_limit':limit,'working_population':working,'idle_population':idle,'troop_population':troop_pop}

def _tax_population_delta(limit,tax_rate,increasing):
 # Documented six-minute Age I table is linear: +5% at tax0 -> 0 at tax100; decrease inverse.
 pct=((100-tax_rate) if increasing else tax_rate)*0.05/100.0
 return max(0,int(limit*pct))

def _run_city_tick(session,city_id,eco,pop):
 tax=int(eco.tax_rate);target=max(0,min(100,100-tax-int(eco.grievance)))
 if eco.loyalty<target:eco.loyalty+=1
 elif eco.loyalty>target:eco.loyalty-=1
 limit=int(pop.population_limit);target_pop=int(limit*eco.loyalty/100)
 if pop.population<target_pop:pop.population=min(target_pop,pop.population+_tax_population_delta(limit,tax,True))
 elif pop.population>target_pop:pop.population=max(0,pop.population-_tax_population_delta(limit,tax,False))
 # One tick pays 1/10 of current hourly tax income.
 gross=float(pop.population)*tax/100.0/10.0
 raw=float(eco.gold_fractional or 0)+gross;whole=int(raw);eco.gold_fractional=raw-whole;eco.gold+=whole
 return {'tax_gold':whole,'target_loyalty':target,'target_population':target_pop}

def economy_snapshot(session,city_id,at=None):
 at=at or datetime.now(timezone.utc);city=session.get(City,city_id)
 if not city:raise ValueError('city not found')
 eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id));pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id))
 prod=resource_production_snapshot(session,city_id,at);pb=population_breakdown(session,city_id,at);up=troop_food_upkeep(session,city_id);salary=hero_salary_per_hour_city(session,city_id)
 warehouse=warehouse_effective_capacity(session,city_id);protected=warehouse_protected_amounts(session,city_id)
 return {'city_id':city_id,'resources':prod['resources'],'population':pb,'tax_rate':eco.tax_rate if eco else city.tax_rate,'loyalty':eco.loyalty if eco else city.loyalty,'grievance':eco.grievance if eco else city.grievance,'gold':eco.gold if eco else city.gold,'gross_gold_per_hour':pb['population']*(eco.tax_rate if eco else city.tax_rate)/100.0,'hero_salary_per_hour':salary,'net_gold_per_hour':pb['population']*(eco.tax_rate if eco else city.tax_rate)/100.0-salary,'troop_food':up,'gross_food_per_hour':prod['resources']['food']['effective_per_hour'],'net_food_per_hour':prod['resources']['food']['effective_per_hour']-up['total_per_hour'],'warehouse_capacity':warehouse,'warehouse_protected':protected,'calculated_at':at}

def settle_economy(session,city_id,now=None):
 """Single authoritative elapsed-time settlement. Conditional clock claim prevents double generation."""
 from sqlalchemy import update
 now=now or datetime.now(timezone.utc);city=session.get(City,city_id)
 if not city:raise ValueError('city not found')
 eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id));pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id))
 if not eco:eco=CityEconomyState(city_id=city_id,gold=city.gold,tax_rate=city.tax_rate,loyalty=city.loyalty,grievance=city.grievance,last_settled_at=now);session.add(eco);session.flush()
 if not pop:pop=PopulationState(city_id=city_id,population=city.population,idle_population=city.idle_population,population_limit=cottage_population_capacity(session,city_id),last_population_tick_at=now);session.add(pop);session.flush()
 last=eco.last_settled_at or now
 if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
 if now<=last:return economy_snapshot(session,city_id,now)
 # Atomic ownership of this interval. Concurrent stale callers get rowcount=0 and cannot generate it twice.
 old_db=eco.last_settled_at
 claim=session.execute(update(CityEconomyState).where(CityEconomyState.id==eco.id,CityEconomyState.last_settled_at==old_db).values(last_settled_at=now))
 if claim.rowcount!=1:
  session.expire_all();return economy_snapshot(session,city_id,now)
 # Resources including troop food upkeep are settled for elapsed time.
 accrue_resources(session,city_id,now)
 elapsed=(now-last).total_seconds()
 # Six-minute civic ticks, preserving remainder by advancing last_population_tick_at only whole ticks.
 pt=pop.last_population_tick_at or last
 if pt.tzinfo is None:pt=pt.replace(tzinfo=timezone.utc)
 ticks=max(0,int((now-pt).total_seconds()//ECONOMY_TICK_SECONDS))
 tax_added=0
 for _ in range(ticks):tax_added+=_run_city_tick(session,city_id,eco,pop)['tax_gold']
 if ticks:pop.last_population_tick_at=pt+timedelta(seconds=ticks*ECONOMY_TICK_SECONDS)
 # Hero salary is continuous and offsets tax gold. Exact insufficient-gold consequence is not verified: clamp at zero.
 salary_raw=float(eco.hero_salary_fractional or 0)+hero_salary_per_hour_city(session,city_id)*elapsed/3600.0
 salary_whole=int(salary_raw);eco.hero_salary_fractional=salary_raw-salary_whole
 eco.gold=max(0,eco.gold-salary_whole)
 eco.last_settled_at=now
 city.gold=eco.gold;city.tax_rate=eco.tax_rate;city.loyalty=eco.loyalty;city.grievance=eco.grievance;city.population=pop.population
 snap=resource_production_snapshot(session,city_id,now);working=int(sum(v['assigned_labor'] for v in snap['resources'].values())*snap['labor_factor']);pop.idle_population=pop.population-working;city.idle_population=pop.idle_population
 session.flush();return economy_snapshot(session,city_id,now)

def economy_debug(session,city_id,at=None):
 snap=settle_economy(session,city_id,at)
 snap['formulae']={'resource':'base × production% × population_factor × (1 + technology + mayor politics + valley + item buffs)','tax':'each 6-minute tick: current population × tax rate / 100 / 10','loyalty':'moves 1/tick toward 100 - tax - grievance','population':'moves each tick toward loyalty occupancy using documented tax-dependent +/- percentages','food_net':'gross food production - garrison upkeep - 2× outside-army upkeep','hero_salary':'20 × hero level / hour'}
 snap['historical_unknowns']=['Exact Age I refugee troop-loss quantity when food reaches zero','Exact consequence/timing when gold is insufficient for hero salary']
 return snap


HERO_REWARD_COOLDOWN_SECONDS=900
HERO_EXP_ITEMS={'anabasis':1000,'epitome_of_military_science':10000,'on_war':100000}
HERO_STAT_ITEMS={'the_art_of_war':('intelligence',1.25),'wealth_of_nations':('politics',1.25),'excalibur':('attack',1.25)}

def hero_xp_for_next_level(level):return 100*int(level)*int(level)

def hero_detail(session,player_id,city_id,hero_id):
 from .models import Hero,HeroExperience
 h=session.get(Hero,hero_id)
 if not h or h.player_id!=player_id or h.city_id!=city_id:raise ValueError('hero not in city')
 xp=session.scalar(select(HeroExperience).where(HeroExperience.hero_id==hero_id));effective=hero_effective_stats(session,hero_id)
 return {'id':h.id,'name':h.name,'level':h.level,'experience':xp.experience if xp else h.experience,'experience_needed':hero_xp_for_next_level(h.level),'unassigned_attribute_points':h.unassigned_attribute_points,'politics':h.politics,'attack':h.attack,'intelligence':h.intelligence,'effective_stats':effective,'loyalty':h.loyalty,'captured':h.captured,'status':_hero_status(session,h),'salary_per_hour':hero_salary_per_hour(h)}

def add_hero_experience(session,hero_id,amount):
 from .models import Hero,HeroExperience
 h=session.get(Hero,hero_id)
 if not h or amount<0:raise ValueError('hero not found/invalid experience')
 xp=session.scalar(select(HeroExperience).where(HeroExperience.hero_id==hero_id))
 if not xp:xp=HeroExperience(hero_id=hero_id,level=h.level,experience=h.experience);session.add(xp)
 raw=float(h.experience_fractional or 0)+float(amount);whole=int(raw);h.experience_fractional=raw-whole;xp.experience+=whole;h.experience=xp.experience
 return {'hero_id':hero_id,'experience':xp.experience,'can_level':xp.experience>=hero_xp_for_next_level(h.level)}

def level_hero(session,player_id,city_id,hero_id,attribute,idempotency_key):
 from .models import Hero,HeroExperience,HeroStats
 def work():
  settle_economy(session,city_id);h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id or h.captured:raise ValueError('hero unavailable')
  if attribute not in ('politics','attack','intelligence'):raise ValueError('invalid attribute')
  xp=session.scalar(select(HeroExperience).where(HeroExperience.hero_id==hero_id))
  need=hero_xp_for_next_level(h.level)
  if not xp or xp.experience<need:raise ValueError('insufficient hero experience')
  xp.experience-=need;h.experience=xp.experience;h.level+=1;xp.level=h.level
  setattr(h,attribute,getattr(h,attribute)+1);setattr(h,'allocated_'+attribute,getattr(h,'allocated_'+attribute)+1);st=session.scalar(select(HeroStats).where(HeroStats.hero_id==hero_id))
  if st:setattr(st,attribute,getattr(st,attribute)+1)
  return hero_detail(session,player_id,city_id,hero_id)
 return idempotent_operation(session,player_id,idempotency_key,'LEVEL_HERO',work)

def assign_hero_points(session,player_id,city_id,hero_id,politics,attack,intelligence,idempotency_key):
 from .models import Hero,HeroStats
 def work():
  h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id or h.captured:raise ValueError('hero unavailable')
  vals=[int(politics),int(attack),int(intelligence)]
  if any(v<0 for v in vals) or sum(vals)!=h.unassigned_attribute_points:raise ValueError('must allocate exactly all available attribute points')
  h.politics+=vals[0];h.attack+=vals[1];h.intelligence+=vals[2];h.allocated_politics+=vals[0];h.allocated_attack+=vals[1];h.allocated_intelligence+=vals[2];h.unassigned_attribute_points=0
  st=session.scalar(select(HeroStats).where(HeroStats.hero_id==hero_id))
  if st:st.politics=h.politics;st.attack=h.attack;st.intelligence=h.intelligence
  return hero_detail(session,player_id,city_id,hero_id)
 return idempotent_operation(session,player_id,idempotency_key,'ASSIGN_HERO_POINTS',work)

def redistribute_hero(session,player_id,city_id,hero_id,idempotency_key):
 from .models import Hero,HeroStats,PlayerItem
 def work():
  settle_economy(session,city_id);h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id or h.captured or _hero_status(session,h)['key']=='march':raise ValueError('hero unavailable')
  if None in (h.base_politics,h.base_attack,h.base_intelligence):
   raise ValueError('HISTORICAL_VALUE_UNKNOWN: this legacy/Inn hero does not preserve original base-attribute provenance required for lossless Age I redistribution')
  waters=max(1,(h.level+9)//10);item=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key=='holy_water'))
  if not item or item.quantity<waters:raise ValueError(f'{waters} Holy Water required')
  item.quantity-=waters;h.politics=h.base_politics;h.attack=h.base_attack;h.intelligence=h.base_intelligence
  h.unassigned_attribute_points=h.allocated_politics+h.allocated_attack+h.allocated_intelligence
  h.allocated_politics=h.allocated_attack=h.allocated_intelligence=0
  st=session.scalar(select(HeroStats).where(HeroStats.hero_id==hero_id))
  if st:st.politics=h.politics;st.attack=h.attack;st.intelligence=h.intelligence
  return {'holy_water_consumed':waters,**hero_detail(session,player_id,city_id,hero_id)}
 return idempotent_operation(session,player_id,idempotency_key,'REDISTRIBUTE_HERO',work)

def reward_hero_gold(session,player_id,city_id,hero_id,idempotency_key):
 from .models import Hero
 def work():
  settle_economy(session,city_id);h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id or h.captured:raise ValueError('hero unavailable')
  now=datetime.now(timezone.utc);last=h.last_reward_at
  if last and last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
  if last and (now-last).total_seconds()<HERO_REWARD_COOLDOWN_SECONDS:raise ValueError('hero reward cooldown active')
  cost=100*h.level;eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id))
  if not eco or eco.gold<cost:raise ValueError('insufficient gold')
  eco.gold-=cost;session.get(City,city_id).gold=eco.gold;h.loyalty=min(100,h.loyalty+5);h.last_reward_at=now
  return {'hero_id':hero_id,'gold_cost':cost,'loyalty':h.loyalty,'cooldown_seconds':900}
 return idempotent_operation(session,player_id,idempotency_key,'REWARD_HERO_GOLD',work)

def apply_hero_item(session,player_id,city_id,hero_id,item_key,idempotency_key):
 from .models import Hero,PlayerItem,HeroBuff
 def work():
  h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id or h.captured:raise ValueError('hero unavailable')
  item=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==item_key))
  if not item or item.quantity<1:raise ValueError('item unavailable')
  if item_key in HERO_EXP_ITEMS:
   item.quantity-=1;return {'item':item_key,**add_hero_experience(session,hero_id,HERO_EXP_ITEMS[item_key])}
  if item_key in HERO_STAT_ITEMS:
   now=datetime.now(timezone.utc);last=h.last_reward_at
   if last and last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
   if last and (now-last).total_seconds()<900:raise ValueError('hero reward cooldown active')
   attr,mult=HERO_STAT_ITEMS[item_key];existing=session.scalar(select(HeroBuff).where(HeroBuff.hero_id==hero_id,HeroBuff.buff_key==item_key))
   if existing:existing.starts_at=now;existing.expires_at=now+timedelta(days=7)
   else:session.add(HeroBuff(hero_id=hero_id,buff_key=item_key,attribute_key=attr,multiplier=mult,starts_at=now,expires_at=now+timedelta(days=7)))
   item.quantity-=1;h.last_reward_at=now;return {'item':item_key,'attribute':attr,'multiplier':mult,'expires_at':(now+timedelta(days=7)).isoformat()}
  raise ValueError('item is not an Age I hero improvement item')
 return idempotent_operation(session,player_id,idempotency_key,'APPLY_HERO_ITEM',work)

def rename_hero(session,player_id,city_id,hero_id,name,idempotency_key):
 from .models import Hero
 def work():
  h=session.get(Hero,hero_id)
  if not h or h.player_id!=player_id or h.city_id!=city_id:raise ValueError('hero not in city')
  name=name.strip()
  if not name or len(name)>64:raise ValueError('invalid hero name')
  h.name=name;return {'hero_id':hero_id,'name':name}
 return idempotent_operation(session,player_id,idempotency_key,'RENAME_HERO',work)

def combat_unit_attack(session,city_id,unit_key,hero_id=None,at=None):
 """Verified Age I attack contribution used by battle resolver."""
 from .models import HeroBuff
 base=int(DATA['troop_types'][unit_key]['attack']);hero_attack=0
 if hero_id:
  hero_attack=hero_effective_stats(session,hero_id,at)['attack']
  # Age I battle calculators document Excalibur as +25 attack points in battle, not the +25% Feasting Hall display.
  at=at or datetime.now(timezone.utc)
  exc=session.scalar(select(HeroBuff).where(HeroBuff.hero_id==hero_id,HeroBuff.buff_key=='excalibur',HeroBuff.starts_at<=at,HeroBuff.expires_at>at))
  if exc:
   raw=hero_effective_stats(session,hero_id,at)['attack'];base_stat=int(raw/1.25)
   hero_attack=base_stat+25
 mt=effective_technology_level(session,city_id,'military_tradition')
 return base+int(base*hero_attack/100)+int(base*mt/20)

def defending_hero(session,city_id):
 from .models import Hero
 heroes=[h for h in session.scalars(select(Hero).where(Hero.city_id==city_id,Hero.captured==False)).all() if _hero_status(session,h)['key'] in ('idle','mayor')]
 return max(heroes,key=lambda h:hero_effective_stats(session,h.id)['attack'],default=None)

def hero_scout_intelligence(session,hero_id):
 return hero_effective_stats(session,hero_id)['intelligence']


WORLD_MIN=0
WORLD_MAX=799
WORLD_SIZE=800
VALLEY_TYPES=('FOREST','DESERT','HILL','LAKE','GRASSLAND')

def validate_world_coordinate(x,y):
 x=int(x);y=int(y)
 if not (WORLD_MIN<=x<=WORLD_MAX and WORLD_MIN<=y<=WORLD_MAX):raise ValueError('coordinates must be between 0 and 799')
 return x,y

def map_tile_payload(session,x,y,viewer_player_id=None):
 from .models import MapTile,NPCCity,Valley,Flat,City,Player
 x,y=validate_world_coordinate(x,y)
 city=session.scalar(select(City).where(City.x==x,City.y==y))
 if city:
  owner=session.get(Player,city.player_id)
  return {'x':x,'y':y,'tile_type':'PLAYER_CITY','city_id':city.id,'name':city.name,'owner_player_id':city.player_id,'owner_name':owner.name if owner else None,'level':None,
   'actions':_map_actions(viewer_player_id,'PLAYER_CITY',city.player_id,session)}
 t=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y))
 if not t:return {'x':x,'y':y,'tile_type':'UNSEEDED','level':None,'actions':[]}
 out={'x':x,'y':y,'tile_id':t.id,'tile_type':t.tile_type,'level':t.level,'owner_player_id':t.owner_player_id}
 if t.tile_type=='NPC_CITY':
  from .npc import regenerate_npc
  n=session.scalar(select(NPCCity).where(NPCCity.map_tile_id==t.id));out['level']=n.level if n else t.level
  if n:
   regenerate_npc(n);out.update({'npc_id':n.id,'loyalty':n.loyalty,'resources':dict(n.resources),'troops':dict(n.troops),'fortifications':dict(n.fortifications)})
 elif t.tile_type=='VALLEY':
  v=session.scalar(select(Valley).where(Valley.map_tile_id==t.id))
  if v:out.update({'valley_type':v.valley_type,'level':v.level,'occupied_by_city_id':v.city_id})
 elif t.tile_type=='FLAT':
  f=session.scalar(select(Flat).where(Flat.map_tile_id==t.id));out.update({'level':f.level,'occupied_by_city_id':f.city_id}) if f else None
 out['actions']=_map_actions(viewer_player_id,t.tile_type,t.owner_player_id,session)
 return out

def _map_actions(viewer_player_id,tile_type,owner_player_id=None,session=None):
 if tile_type=='UNSEEDED':return []
 if tile_type=='PLAYER_CITY':
  if owner_player_id==viewer_player_id:return ['ENTER']
  if session is not None and player_relationship(session,viewer_player_id,owner_player_id) in ('ALLIANCE','FRIENDLY'):return ['VIEW']
  return ['SCOUT','ATTACK']
 if tile_type=='NPC_CITY':return ['SCOUT','ATTACK']
 if tile_type in ('FLAT','VALLEY'):return ['SCOUT','ATTACK']
 return []

def map_viewport(session,player_id,center_x,center_y,radius=6):
 center_x,center_y=validate_world_coordinate(center_x,center_y);radius=max(2,min(int(radius),12))
 minx=max(0,center_x-radius);maxx=min(799,center_x+radius);miny=max(0,center_y-radius);maxy=min(799,center_y+radius)
 return {'center':{'x':center_x,'y':center_y},'bounds':{'min_x':minx,'max_x':maxx,'min_y':miny,'max_y':maxy},
  'width':maxx-minx+1,'height':maxy-miny+1,'note':'Persistent coordinate world; unseeded coordinates are explicit UNSEEDED tiles. World objects are not fabricated.','tiles':[map_tile_payload(session,x,y,player_id) for y in range(miny,maxy+1) for x in range(minx,maxx+1)],'marches':active_marches_for_player(session,player_id) if player_id is not None else []}

def player_bookmarks(session,player_id):
 from .models import Bookmark
 return [{'id':b.id,'x':b.x,'y':b.y,'label':b.label} for b in session.scalars(select(Bookmark).where(Bookmark.player_id==player_id).order_by(Bookmark.id)).all()]

def add_bookmark(session,player_id,x,y,label,idempotency_key):
 from .models import Bookmark,Player
 def work():
  if not session.get(Player,player_id):raise ValueError('player not found')
  x2,y2=validate_world_coordinate(x,y);old=session.scalar(select(Bookmark).where(Bookmark.player_id==player_id,Bookmark.x==x2,Bookmark.y==y2))
  if old:return {'id':old.id,'x':old.x,'y':old.y,'label':old.label}
  b=Bookmark(player_id=player_id,x=x2,y=y2,label=(label or f'{x2},{y2}')[:64]);session.add(b);session.flush();return {'id':b.id,'x':b.x,'y':b.y,'label':b.label}
 return idempotent_operation(session,player_id,idempotency_key,'MAP_BOOKMARK_ADD',work)

def delete_bookmark(session,player_id,bookmark_id,idempotency_key):
 from .models import Bookmark
 def work():
  b=session.get(Bookmark,bookmark_id)
  if not b or b.player_id!=player_id:raise ValueError('bookmark not found')
  session.delete(b);return {'deleted_bookmark_id':bookmark_id}
 return idempotent_operation(session,player_id,idempotency_key,'MAP_BOOKMARK_DELETE',work)

AGE1_VALLEY_TYPES=('GRASSLAND','SWAMP','LAKE','HILL','DESERT','FOREST')
VALLEY_RESOURCE={'GRASSLAND':'food','SWAMP':'food','LAKE':'food','HILL':'iron','DESERT':'stone','FOREST':'lumber'}
VALLEY_BONUSES={
 'GRASSLAND':[3,4,5,6,7,8,9,10,11,12],
 'SWAMP':[5,7,9,11,13,15,17,19,21,23],
 'LAKE':[8,11,14,17,20,23,26,29,32,35],
 'HILL':[5,7,9,11,13,15,17,19,21,23],
 'DESERT':[5,7,9,11,13,15,17,19,21,23],
 'FOREST':[5,7,9,11,13,15,17,19,21,23],
}
SCOUT_BANDS=((1,24,'Few'),(25,49,'Pack'),(50,99,'Lots'),(100,249,'Horde'),(250,499,'Throng'),(500,999,'Swarm'),(1000,2499,'Zounds'),(2500,4999,'Legion'),(5000,9999,'Bulk'),(10000,10**18,'Giga'))
TITLE_CITY_CAP={'Civilian':1,'Knight':2,'Baronet':3,'Baron':4,'Viscount':5,'Earl':6,'Marquis':7,'Duke':8,'Furstin':9,'Prinzessin':10}

def valley_capacity(session,city_id):
 return current_level(session,town_hall_building(session,city_id))
def occupied_wilderness(session,city_id):
 from .models import Valley,Flat
 return session.scalars(select(Valley).where(Valley.city_id==city_id)).all()+session.scalars(select(Flat).where(Flat.city_id==city_id)).all()
def valley_bonus(type_key,level):
 key=type_key.upper();return {'resource':VALLEY_RESOURCE.get(key),'percent':VALLEY_BONUSES.get(key,[0]*10)[int(level)-1] if 1<=int(level)<=10 else 0}
def _scout_band(n):
 for lo,hi,label in SCOUT_BANDS:
  if lo<=n<=hi:return label
 return 'Giga'
def wilderness_detail(session,player_id,x,y):
 from .models import MapTile,Valley,Flat,City,Player
 t=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y))
 if not t or t.tile_type not in ('VALLEY','FLAT'):raise ValueError('wilderness not found')
 obj=session.scalar(select(Valley).where(Valley.map_tile_id==t.id)) if t.tile_type=='VALLEY' else session.scalar(select(Flat).where(Flat.map_tile_id==t.id))
 owner_city=session.get(City,obj.city_id) if obj and obj.city_id else None;owner=session.get(Player,owner_city.player_id) if owner_city else None
 bonus=valley_bonus(obj.valley_type,obj.level) if t.tile_type=='VALLEY' else {'resource':None,'percent':0}
 return {'x':x,'y':y,'kind':t.tile_type,'level':obj.level,'valley_type':getattr(obj,'valley_type',None),'bonus':bonus,'owner_city_id':obj.city_id,'owner_player_id':owner_city.player_id if owner_city else None,'owner_name':owner.name if owner else None,'defenders_present':sum((obj.defenders or {}).values())>0}
def scout_wilderness(session,player_id,city_id,x,y):
 from .models import City,MapTile,Valley,Flat
 city=session.get(City,city_id)
 if not city or city.player_id!=player_id:raise ValueError('city not owned')
 t=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y));obj=None
 if t and t.tile_type=='VALLEY':obj=session.scalar(select(Valley).where(Valley.map_tile_id==t.id))
 elif t and t.tile_type=='FLAT':obj=session.scalar(select(Flat).where(Flat.map_tile_id==t.id))
 if not obj:raise ValueError('wilderness not found')
 info=effective_technology_level(session,city_id,'informatics');troops=obj.defenders or {}
 exact=info>=obj.level
 return {'target':wilderness_detail(session,player_id,x,y),'informatics':info,'defenders':({k:int(v) for k,v in troops.items()} if exact else {k:_scout_band(int(v)) for k,v in troops.items()}),'exact':exact}
def conquer_wilderness(session,player_id,city_id,x,y,army_id=None):
 """Called only after the battle resolver has established victory; does not fabricate combat."""
 from .models import City,MapTile,Valley,Flat,March
 city=session.get(City,city_id)
 if not city or city.player_id!=player_id:raise ValueError('city not owned')
 t=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y));obj=None
 if t and t.tile_type=='VALLEY':obj=session.scalar(select(Valley).where(Valley.map_tile_id==t.id))
 elif t and t.tile_type=='FLAT':obj=session.scalar(select(Flat).where(Flat.map_tile_id==t.id))
 if not obj:raise ValueError('wilderness not found')
 if len(occupied_wilderness(session,city_id))>=valley_capacity(session,city_id) and obj.city_id!=city_id:raise ValueError('Town Hall valley limit reached')
 if sum((obj.defenders or {}).values())>0:raise ValueError('wilderness defenders remain; battle victory required')
 obj.city_id=city_id;t.owner_player_id=player_id
 if army_id:
  march=session.scalar(select(March).where(March.army_id==army_id,March.target_x==x,March.target_y==y))
  if march:march.status='CAMPED'
 return wilderness_detail(session,player_id,x,y)
def abandon_wilderness(session,player_id,city_id,x,y,idempotency_key):
 from .models import City,MapTile,Valley,Flat
 def work():
  city=session.get(City,city_id);t=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y))
  if not city or city.player_id!=player_id or not t:raise ValueError('not owned')
  obj=session.scalar(select(Valley).where(Valley.map_tile_id==t.id)) if t.tile_type=='VALLEY' else session.scalar(select(Flat).where(Flat.map_tile_id==t.id)) if t.tile_type=='FLAT' else None
  if not obj or obj.city_id!=city_id:raise ValueError('wilderness not owned by city')
  obj.city_id=None;t.owner_player_id=None
  # Age I immediately regenerated defenders on abandon. Exact force-generation distribution is not sufficiently verified, so preserve/reset configured native force fixture rather than inventing quantities.
  if not obj.defenders: obj.defenders={}
  obj.defenders_updated_at=datetime.now(timezone.utc)
  return {'x':x,'y':y,'abandoned':True,'defenders_regenerated':bool(obj.defenders)}
 return idempotent_operation(session,player_id,idempotency_key,'ABANDON_WILDERNESS',work)
def player_city_cap(session,player_id):
 from .models import PlayerProgression
 p,rank,title=_progression(session,player_id);return TITLE_DEFS[title]['city_limit']
def build_city_on_flat(session,player_id,source_city_id,x,y,name,idempotency_key):
 from .models import City,MapTile,Flat,TroopQuantity,Resource,CityCoordinate,PopulationState,CityEconomyState,CityBuildingPlot,ExteriorFieldPlot,Building,BuildingLevel,ResourceProduction,ResourceCapacity,PlayerSetting
 def work():
  settle_economy(session,source_city_id);source=session.get(City,source_city_id)
  if not source or source.player_id!=player_id:raise ValueError('source city not owned')
  if session.scalar(select(func.count(City.id)).where(City.player_id==player_id))>=player_city_cap(session,player_id):raise ValueError('title does not permit another city')
  t=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y));f=session.scalar(select(Flat).where(Flat.map_tile_id==t.id)) if t and t.tile_type=='FLAT' else None
  if not f or f.city_id!=source_city_id:raise ValueError('flat must first be conquered by source city')
  workers=session.scalar(select(TroopQuantity).where(TroopQuantity.city_id==source_city_id,TroopQuantity.troop_type_key=='worker'))
  if not workers or workers.quantity<250:raise ValueError('250 Workers required')
  rows={r.kind:r for r in session.scalars(select(Resource).where(Resource.city_id==source_city_id)).all()}
  if any(k not in rows or rows[k].quantity<10000 for k in ('food','lumber','stone','iron')):raise ValueError('10,000 Food, Lumber, Stone and Iron required')
  eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==source_city_id))
  if not eco or eco.gold<10000:raise ValueError('10,000 Gold required')
  workers.quantity-=250
  for k in ('food','lumber','stone','iron'):rows[k].quantity-=10000
  eco.gold-=10000;source.gold=eco.gold
  level=f.level;session.delete(f);t.tile_type='PLAYER_CITY';t.level=0;t.owner_player_id=player_id;session.flush()
  c=City(player_id=player_id,name=name.strip()[:32] or 'New City',x=x,y=y);session.add(c);session.flush();session.add(PlayerSetting(player_id=player_id,key=f'city:{c.id}:founding_flat_level',value={'level':level}));session.add(CityCoordinate(city_id=c.id,x=x,y=y));session.add(PopulationState(city_id=c.id));session.add(CityEconomyState(city_id=c.id))
  for i in range(34):session.add(CityBuildingPlot(city_id=c.id,plot_index=i))
  for i in range(1,11):session.add(ExteriorFieldPlot(city_id=c.id,plot_index=i))
  th=Building(city_id=c.id,plot_kind='CITY',plot_index=0,definition_key='town_hall',level=1);wall=Building(city_id=c.id,plot_kind='CITY',plot_index=33,definition_key='walls',level=1);session.add_all([th,wall]);session.flush();session.add_all([BuildingLevel(building_id=th.id,level=1),BuildingLevel(building_id=wall.id,level=1)])
  for k in ('food','lumber','stone','iron'):session.add(Resource(city_id=c.id,kind=k,quantity=0,capacity=0));session.add(ResourceProduction(city_id=c.id,resource_kind=k,per_hour=0));session.add(ResourceCapacity(city_id=c.id,resource_kind=k,capacity=0))
  return {'city_id':c.id,'x':x,'y':y,'source_flat_level':level,'workers_consumed':250,'resources_consumed':{**{k:10000 for k in ('food','lumber','stone','iron')},'gold':10000}}
 return idempotent_operation(session,player_id,idempotency_key,'BUILD_CITY_ON_FLAT',work)
def abandon_city_to_npc(session,player_id,city_id,idempotency_key):
 from .models import City,MapTile,NPCCity,March,PlayerSetting,Valley,Flat
 from .db import Base
 def work():
  cities=session.scalars(select(City).where(City.player_id==player_id)).all();c=session.get(City,city_id)
  if not c or c.player_id!=player_id:raise ValueError('city not owned')
  if len(cities)<=1:raise ValueError('last city cannot be abandoned')
  active=session.scalar(select(March).where(March.source_city_id==city_id,March.status.in_(['MARCHING','CAMPED','GARRISONED','RETURNING','ARRIVED_PENDING_RESOLUTION'])))
  if active:raise ValueError('recall/resolve city armies before abandoning')
  setting=session.scalar(select(PlayerSetting).where(PlayerSetting.player_id==player_id,PlayerSetting.key==f'city:{city_id}:founding_flat_level'))
  if not setting:raise ValueError('HISTORICAL_VALUE_UNKNOWN: legacy city founding flat level unavailable')
  lv=int(setting.value['level']);x,y=c.x,c.y
  # Owned wilderness is released when its owning city disappears.
  for v in session.scalars(select(Valley).where(Valley.city_id==city_id)).all():v.city_id=None;session.get(MapTile,v.map_tile_id).owner_player_id=None
  for f in session.scalars(select(Flat).where(Flat.city_id==city_id)).all():f.city_id=None;session.get(MapTile,f.map_tile_id).owner_player_id=None
  session.flush()
  # Recursively remove city-owned rows while preserving world wilderness rows just released above.
  meta=Base.metadata;city_table=meta.tables['cities'];preserve={'valleys','flats'}
  def remove_children(table,pk):
   for child in meta.tables.values():
    if child.name in preserve:continue
    for fk in child.foreign_keys:
     if fk.column.table is table and fk.column.name=='id':
      ids=[r[0] for r in session.execute(select(child.c.id).where(child.c[fk.parent.name]==pk)).all()] if 'id' in child.c else []
      for cid in ids:remove_children(child,cid)
      session.execute(child.delete().where(child.c[fk.parent.name]==pk))
  remove_children(city_table,city_id)
  session.execute(PlayerSetting.__table__.delete().where(PlayerSetting.player_id==player_id,PlayerSetting.key==f'city:{city_id}:founding_flat_level'))
  session.execute(city_table.delete().where(city_table.c.id==city_id));session.flush()
  tile=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y))
  if tile: tile.tile_type='NPC_CITY';tile.level=lv;tile.owner_player_id=None
  else: tile=MapTile(x=x,y=y,tile_type='NPC_CITY',level=lv,owner_player_id=None);session.add(tile);session.flush()
  npc=NPCCity(map_tile_id=tile.id,level=lv);session.add(npc);session.flush()
  from .npc import initialize_npc
  initialize_npc(npc,force=True)
  return {'npc_created':True,'x':x,'y':y,'level':lv,'source_city_id':city_id}
 return idempotent_operation(session,player_id,idempotency_key,'ABANDON_CITY_TO_NPC',work)


ACTIVE_MARCH_STATUSES=('MARCHING','ARRIVED_PENDING_RESOLUTION','RETURNING','CAMPED','GARRISONED','BATTLE_PENDING')
def march_payload(session,march):
 from .models import Army
 a=session.get(Army,march.army_id);now=datetime.now(timezone.utc)
 due=march.returns_at if march.status=='RETURNING' else march.arrives_at
 if due and due.tzinfo is None:due=due.replace(tzinfo=timezone.utc)
 return {'id':march.id,'unique_id':march.id,'origin_city_id':march.source_city_id,'destination':{'x':march.target_x,'y':march.target_y},
  'mission':march.mission,'hero_id':a.hero_id if a else None,'troops':a.troops if a else {},'resource_cargo':a.resources if a else {},
  'departure':march.departed_at,'arrival':march.arrives_at,'return_destination':{'city_id':march.return_city_id or march.source_city_id,'x':march.return_x,'y':march.return_y},
  'return_arrival':march.returns_at,'status':march.status,'seconds_remaining':max(0,int((due-now).total_seconds())) if due else None,
  'distance':march.distance,'travel_seconds':march.travel_seconds,'arrival_processed_at':march.arrival_processed_at}

def active_marches_for_player(session,player_id):
 from .models import March,Army
 rows=session.scalars(select(March).join(Army,Army.id==March.army_id).where(Army.player_id==player_id,March.status.in_(ACTIVE_MARCH_STATUSES)).order_by(March.id)).all()
 return [march_payload(session,m) for m in rows]

def _create_report(session,cls,player_id,payload):
 import copy
 r=cls(player_id=player_id,payload=copy.deepcopy(payload));session.add(r);session.flush();return r

def _start_return(session,march,now=None):
 now=now or datetime.now(timezone.utc);march.status='RETURNING';march.returns_at=now+timedelta(seconds=max(1,march.travel_seconds));return march

def _deliver_army_to_city(session,army,city_id,include_resources=True):
 from .models import TroopQuantity,Resource
 for k,n in (army.troops or {}).items():
  row=session.scalar(select(TroopQuantity).where(TroopQuantity.city_id==city_id,TroopQuantity.troop_type_key==k))
  if not row:row=TroopQuantity(city_id=city_id,troop_type_key=k,quantity=0);session.add(row)
  row.quantity+=int(n)
 if include_resources:
  for k,n in (army.resources or {}).items():
   row=session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==k))
   if not row:row=Resource(city_id=city_id,kind=k,quantity=0,capacity=0);session.add(row)
   row.quantity+=int(n)
 army.troops={};army.resources={}

def resolve_march_arrival(session,march_id,now=None):
 """Authoritative one-shot arrival transition. Caller must commit transaction."""
 from sqlalchemy import update
 from .models import March,Army,ScoutReport,TransportReport,BattleReport,City,MapTile,Valley,Flat,ForeignGarrison,MarchMission
 now=now or datetime.now(timezone.utc);m=session.get(March,march_id)
 if not m:raise ValueError('march not found')
 due=m.arrives_at
 if due.tzinfo is None:due=due.replace(tzinfo=timezone.utc)
 if due>now:return {'march_id':m.id,'status':m.status,'due':False}
 if m.arrival_processed_at is not None:return {'march_id':m.id,'status':m.status,'already_processed':True}
 # Atomic claim means two workers cannot both deliver/report/conquer.
 claim=session.execute(update(March).where(March.id==m.id,March.arrival_processed_at.is_(None),March.status=='MARCHING').values(arrival_processed_at=now,status='ARRIVED_PENDING_RESOLUTION',resolution_key=f'arrival:{m.id}'))
 if claim.rowcount!=1:
  session.expire_all();m=session.get(March,march_id);return {'march_id':m.id,'status':m.status,'already_processed':True}
 session.expire(m);a=session.get(Army,m.army_id);player_id=a.player_id;target=_target_info(session,m.target_x,m.target_y)
 state=session.scalar(select(MarchMission).where(MarchMission.march_id==m.id))
 if not state:state=MarchMission(march_id=m.id,mission_key=m.mission,mission_state={});session.add(state)
 result={'mission':m.mission,'target':{'x':m.target_x,'y':m.target_y}}
 if m.mission=='SCOUT':
  if target and target['kind'] in ('VALLEY','FLAT'):
   payload=scout_wilderness(session,player_id,m.source_city_id,m.target_x,m.target_y)
  elif target and target['kind']=='NPC_CITY':
   payload=npc_scout_payload(session,player_id,m.source_city_id,m.target_x,m.target_y,now,a.hero_id,sum(int(v) for k,v in (a.troops or {}).items() if k=='scout'))
  else:
   payload={'target':target,'status':'HISTORICAL_VALUE_UNKNOWN','note':'City scouting detail requires target Beacon/gates/defending scout resolution in the combat/scouting phase.'}
  rep=_create_report(session,ScoutReport,player_id,{'march_id':m.id,**payload});result['report_id']=rep.id;_start_return(session,m,now)
 elif m.mission=='TRANSPORT':
  if not target or target['kind']!='CITY':raise ValueError('transport target no longer valid')
  delivered_troops=dict(a.troops or {});delivered_resources=dict(a.resources or {});dest=session.get(City,target['city_id'])
  # Transport unloads resources only; the escort/transport troops return to their source city.
  for k,n in delivered_resources.items():
   row=session.scalar(select(Resource).where(Resource.city_id==target['city_id'],Resource.kind==k))
   if not row:row=Resource(city_id=target['city_id'],kind=k,quantity=0);session.add(row)
   row.quantity+=int(n)
  a.resources={}
  rep=_create_report(session,TransportReport,player_id,{'march_id':m.id,'mission':'TRANSPORT','time':now.isoformat(),'origin_city_id':m.source_city_id,'destination':{'city_id':dest.id,'name':dest.name,'x':dest.x,'y':dest.y},'troops':delivered_troops,'resources':delivered_resources,'delivered':True,'troops_returning':True});result['report_id']=rep.id;_start_return(session,m,now)
 elif m.mission=='REINFORCE':
  if not target or target['kind']!='CITY':raise ValueError('reinforce target no longer valid')
  rr=reinforcement_report(session,player_id,m,target['city_id'])
  if target.get('owner_player_id')==player_id:
   _deliver_army_to_city(session,a,target['city_id'],True);m.status='COMPLETED';result['transferred_city_id']=target['city_id']
  else:
   g=arrive_allied_reinforcement(session,m.id);result['garrisoned_city_id']=target['city_id'];result['garrison_id']=g.id
  result['report_id']=rr.id
 elif m.mission in ('ATTACK','OCCUPY'):
  if target and target['kind']=='NPC_CITY':
   npc=npc_city_at(session,m.target_x,m.target_y,now);npc_result=resolve_npc_attack(session,m,npc,now);result.update(npc_result)
  # Wilderness can be authoritatively occupied only after its persisted defenders are gone.
  elif target and target['kind'] in ('VALLEY','FLAT'):
   tile=session.get(MapTile,target['map_tile_id']);obj=session.scalar(select(Valley).where(Valley.map_tile_id==tile.id)) if target['kind']=='VALLEY' else session.scalar(select(Flat).where(Flat.map_tile_id==tile.id))
   if sum((obj.defenders or {}).values())==0:
    conquered=conquer_wilderness(session,player_id,m.source_city_id,m.target_x,m.target_y,a.id);result['conquered']=conquered;m.status='CAMPED'
    rep=_create_report(session,BattleReport,player_id,{'march_id':m.id,'result':'OCCUPIED_WITHOUT_REMAINING_DEFENDERS','target':conquered});result['report_id']=rep.id
   else:
    # Do not fabricate battle casualties before the dedicated Age-I round resolver exists.
    battle=Battle(march_id=m.id,outcome={'status':'PENDING_COMBAT','target':target,'defenders':obj.defenders});session.add(battle);session.flush()
    rep=_create_report(session,BattleReport,player_id,{'march_id':m.id,'result':'PENDING_COMBAT','battle_id':battle.id});result.update({'battle_id':battle.id,'report_id':rep.id});m.status='BATTLE_PENDING'
  else:
   battle=Battle(march_id=m.id,outcome={'status':'PENDING_COMBAT','target':target});session.add(battle);session.flush()
   rep=_create_report(session,BattleReport,player_id,{'march_id':m.id,'result':'PENDING_COMBAT','battle_id':battle.id});result.update({'battle_id':battle.id,'report_id':rep.id});m.status='BATTLE_PENDING'
 else:raise ValueError('unsupported mission')
 state.mission_state=result;session.flush();session.refresh(m);return {'march_id':m.id,'status':m.status,**result}

def process_due_marches(session,now=None,player_id=None):
 from .models import March,Army
 now=now or datetime.now(timezone.utc)
 q=select(March).where(March.status=='MARCHING',March.arrives_at<=now)
 if player_id is not None:q=q.join(Army,Army.id==March.army_id).where(Army.player_id==player_id)
 results=[]
 for m in session.scalars(q.order_by(March.arrives_at,March.id)).all():results.append(resolve_march_arrival(session,m.id,now))
 # Returns are also authoritative elapsed-time transitions.
 rq=select(March).where(March.status=='RETURNING',March.returns_at<=now)
 if player_id is not None:rq=rq.join(Army,Army.id==March.army_id).where(Army.player_id==player_id)
 for m in session.scalars(rq).all():
  a=session.get(Army,m.army_id);_deliver_army_to_city(session,a,m.return_city_id or m.source_city_id,True);m.status='RETURNED';results.append({'march_id':m.id,'status':'RETURNED'})
 return results

def recall_authoritative_march(session,player_id,march_id,idempotency_key):
 # Reuses Age-I elapsed-distance recall calculation and keeps one authoritative return transition.
 return recall_march(session,player_id,march_id,idempotency_key)


def npc_city_at(session,x,y,now=None):
 from .models import MapTile,NPCCity
 from .npc import regenerate_npc
 t=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y,MapTile.tile_type=='NPC_CITY'))
 if not t:return None
 n=session.scalar(select(NPCCity).where(NPCCity.map_tile_id==t.id))
 if n:regenerate_npc(n,now)
 return n

def npc_scout_payload(session,player_id,source_city_id,x,y,now=None,hero_id=None,scout_count=0):
 from .npc import npc_snapshot
 n=npc_city_at(session,x,y,now)
 if not n:raise ValueError('NPC city not found')
 snap=npc_snapshot(n);detail=scout_detail_level(session,source_city_id,n.level,hero_id,scout_count,True)
 def band(v):
  if v==0:return 'None'
  for lim,name in [(25,'Few'),(50,'Pack'),(100,'Lots'),(250,'Horde'),(500,'Throng'),(1000,'Swarm'),(2500,'Zounds'),(5000,'Legion'),(10000,'Bulk')]:
   if v<lim:return name
  return 'Giga'
 base={'target':'NPC_CITY','location':{'x':x,'y':y},'level':n.level,'scouting':detail,'loyalty':n.loyalty}
 if detail['exact_numbers']:return {**base,'exact':True,'resources':snap['resources'],'troops':snap['troops'],'fortifications':snap['fortifications']}
 return {**base,'exact':False,'troops':{k:band(v) for k,v in snap['troops'].items()},'fortifications':{k:band(v) for k,v in snap['fortifications'].items()},'resources':'DETAIL_REQUIRES_HIGHER_SCOUTING'}

def npc_battle_input(session,march,npc):
 from .models import Army,Hero
 from .combat import Age1CombatRules
 army=session.get(Army,march.army_id);hero=session.get(Hero,army.hero_id) if army.hero_id else None
 tech={k:technology_level(session,army.player_id,k) for k in ('military_tradition','iron_working','medicine','archery','compass','horseback_riding')}
 defs=DATA['troop_types']
 # NPC internal technologies are level-matched as their buildings/technology progression is level-based.
 npc_tech={k:npc.level for k in ('military_tradition','iron_working','medicine','archery','compass','horseback_riding')}
 return {'unit_definitions':defs,'attacker':{'troops':dict(army.troops),'technologies':tech,'hero_attack':hero.attack if hero else 0},'defender':{'troops':dict(npc.troops),'technologies':npc_tech,'hero_attack':0,'fortifications':dict(npc.fortifications),'wall_level':npc.level}}

def npc_plunder(session,army,npc):
 """No warehouse/privateering protection. Gold and resources are limited by surviving army load."""
 from .models import March
 load=sum(DATA['troop_types'][k]['load']*int(q) for k,q in (army.troops or {}).items())
 # Logistics affects carrying capacity through the same player-city multiplier already used by marches.
 load=int(load*army_load_multiplier(session,session.get(March,session.scalar(select(March.id).where(March.army_id==army.id))).source_city_id)) if load else 0
 cur=dict(npc.resources);loot={};remaining=load
 # Deterministic Age-I resource ordering is not strongly documented; keep it centralized and explicit.
 for k in ('gold','food','lumber','stone','iron'):
  take=min(int(cur.get(k,0)),remaining);loot[k]=take;cur[k]=int(cur.get(k,0))-take;remaining-=take
  if remaining<=0:break
 npc.resources=cur
 cargo=dict(army.resources or {})
 for k,v in loot.items():cargo[k]=cargo.get(k,0)+v
 army.resources=cargo
 return loot

def resolve_npc_attack(session,march,npc,now=None):
 from .combat import simulateBattle,Age1CombatRules
 from .models import Army,Battle,BattleRound,BattleReport,Hero,HeroExperience,PlayerProgression
 now=now or datetime.now(timezone.utc);army=session.get(Army,march.army_id)
 result=simulateBattle(npc_battle_input(session,march,npc),Age1CombatRules())
 army.troops=dict(result.attacker_survivors);npc.troops=dict(result.defender_survivors);npc.fortifications=dict(result.fortification_survivors);npc.defenders_updated_at=now
 battle=Battle(march_id=march.id,outcome={'status':'RESOLVED','target':'NPC_CITY','npc_level':npc.level,'winner':result.winner,'reason':result.reason,'rounds':result.rounds,'attacker_losses':result.attacker_losses,'defender_losses':result.defender_losses,'fortification_survivors':result.fortification_survivors,'plunder':{},'prestige':'HISTORICAL_VALUE_UNKNOWN'})
 session.add(battle);session.flush()
 for rd in result.round_log:session.add(BattleRound(battle_id=battle.id,round_number=rd['round'],state=rd))
 loot={}
 if result.winner=='attacker':
  loot=npc_plunder(session,army,npc);battle.outcome={**battle.outcome,'plunder':loot}
  # Successful attacks reduce NPC loyalty. Surviving sources agree on repeated-wave conquest but conflict on exact loss bands; isolate it.
  npc.loyalty=max(0,npc.loyalty-(3 if npc.loyalty>50 else 2));npc.loyalty_updated_at=now
  if npc.loyalty==0 and session.scalar(select(func.count(City.id)).where(City.player_id==army.player_id))<player_city_cap(session,army.player_id):
   battle.outcome={**battle.outcome,'conquest':capture_npc_city(session,army.player_id,march.source_city_id,npc)}
  # NPC battle hero XP exists, but exact casualty->XP formula is handled by the combat/hero fidelity gate, not invented here.
 march.status='RETURNING';march.returns_at=now+timedelta(seconds=max(1,march.travel_seconds))
 rep=_create_report(session,BattleReport,army.player_id,{'march_id':march.id,'battle_id':battle.id,'time':now.isoformat(),'location':{'x':march.target_x,'y':march.target_y},'attacker':{'player_id':army.player_id,'hero_id':army.hero_id,'troops':result.attacker_initial},'defender':{'type':'NPC_CITY','level':npc.level,'troops':result.defender_initial},'outcome':result.winner,'rounds':result.rounds,'attacker_losses':result.attacker_losses,'attacker_survivors':result.attacker_survivors,'defender_losses':result.defender_losses,'defender_survivors':result.defender_survivors,'fortifications':{'survivors':result.fortification_survivors},'resources_captured':loot,'prestige_change':'HISTORICAL_VALUE_UNKNOWN','honor_change':'HISTORICAL_VALUE_UNKNOWN','uncertainties':result.uncertainties})
 return {'battle_id':battle.id,'report_id':rep.id,'winner':result.winner,'loot':loot,'npc_loyalty':npc.loyalty}

def capture_npc_city(session,player_id,source_city_id,npc):
 from .models import MapTile,City,CityCoordinate,CityBuildingPlot,ExteriorFieldPlot,Building,BuildingLevel,Resource,ResourceProduction,ResourceCapacity,PopulationState,CityEconomyState,TroopQuantity
 if npc.loyalty>0:raise ValueError('NPC loyalty must be zero')
 if session.scalar(select(func.count(City.id)).where(City.player_id==player_id))>=player_city_cap(session,player_id):raise ValueError('title does not permit another city')
 tile=session.get(MapTile,npc.map_tile_id);level=npc.level
 city=City(player_id=player_id,name=f'Captured NPC {level}',x=tile.x,y=tile.y,population=0,idle_population=0,gold=int(npc.resources.get('gold',0)),loyalty=0);session.add(city);session.flush();session.add(CityCoordinate(city_id=city.id,x=tile.x,y=tile.y));session.add(PopulationState(city_id=city.id));session.add(CityEconomyState(city_id=city.id,gold=int(npc.resources.get('gold',0)),loyalty=0))
 for i in range(34):session.add(CityBuildingPlot(city_id=city.id,plot_index=i))
 # NPC internal buildings are all their NPC level; retain an Age-I composition with 20 cottages plus unique structures.
 keys=['town_hall','walls','academy','forge','embassy','workshop','feasting_hall','stable','inn','rally_spot','barracks','relief_station','beacon_tower']+['cottage']*20
 for i,key in enumerate(keys[:34]):
  plot=0 if key=='town_hall' else 33 if key=='walls' else i
  b=Building(city_id=city.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=level);session.add(b);session.flush();session.add(BuildingLevel(building_id=b.id,level=level))
 field_count=min(37,10+3*(level-1))
 for i in range(1,field_count+1):
  session.add(ExteriorFieldPlot(city_id=city.id,plot_index=i))
  key='sawmill' if i==1 else 'ironmine' if i==2 else 'quarry' if i==3 else 'farm'
  fb=Building(city_id=city.id,plot_kind='FIELD',plot_index=i,definition_key=key,level=level);session.add(fb);session.flush();session.add(BuildingLevel(building_id=fb.id,level=level))
 for k in ('food','lumber','stone','iron'):
  q=int(npc.resources.get(k,0));session.add(Resource(city_id=city.id,kind=k,quantity=q,capacity=q));session.add(ResourceProduction(city_id=city.id,resource_kind=k,per_hour=0));session.add(ResourceCapacity(city_id=city.id,resource_kind=k,capacity=q))
 tile.tile_type='PLAYER_CITY';tile.owner_player_id=player_id;tile.level=0;session.delete(npc);session.flush();return {'captured_city_id':city.id,'level':level,'x':tile.x,'y':tile.y}

REPORT_MODELS={}
def _report_models():
 from .models import BattleReport,ScoutReport,TransportReport,ReinforcementReport,SystemReport
 return {'battle':BattleReport,'scout':ScoutReport,'transport':TransportReport,'reinforcement':ReinforcementReport,'system':SystemReport}

def report_snapshot(session,kind,report):
 return {'id':report.id,'kind':kind,'created_at':report.created_at,'read':report.read,'payload':report.payload}

def list_reports(session,player_id,kind=None,include_read=True):
 models=_report_models(); selected={kind:models[kind]} if kind else models; out=[]
 for k,cls in selected.items():
  q=select(cls).where(cls.player_id==player_id,cls.deleted_at.is_(None))
  if not include_read:q=q.where(cls.read==False)
  out.extend(report_snapshot(session,k,r) for r in session.scalars(q).all())
 return sorted(out,key=lambda r:r['created_at'],reverse=True)

def get_report(session,player_id,kind,report_id,mark_read=True):
 cls=_report_models().get(kind)
 if not cls:raise ValueError('invalid report kind')
 r=session.get(cls,report_id)
 if not r or r.player_id!=player_id or r.deleted_at is not None:raise ValueError('report not found')
 if mark_read:r.read=True
 return report_snapshot(session,kind,r)

def delete_report(session,player_id,kind,report_id):
 cls=_report_models().get(kind)
 if not cls:raise ValueError('invalid report kind')
 r=session.get(cls,report_id)
 if not r or r.player_id!=player_id or r.deleted_at is not None:raise ValueError('report not found')
 r.deleted_at=datetime.now(timezone.utc);return {'deleted':True,'id':report_id,'kind':kind}

def create_system_report(session,player_id,event_type,payload):
 from .models import SystemReport
 return _create_report(session,SystemReport,player_id,{'event_type':event_type,**payload})

def beacon_level(session,city_id):
 b=session.scalar(select(Building).where(Building.city_id==city_id,Building.definition_key=='beacon_tower'))
 return b.level if b else 0

def scout_detail_level(session,city_id,target_level,hero_id=None,scout_count=0,is_enemy_city=False):
 """Age-I report disclosure gate. Exact hero-intelligence contribution is disputed and not converted to a fabricated level."""
 info=effective_technology_level(session,city_id,'informatics'); beacon=beacon_level(session,city_id)
 effective=min(info,beacon) if is_enemy_city else info
 enough_scouts=scout_count>=max(1,target_level*10)
 return {'informatics':info,'beacon_tower':beacon,'effective_detail_level':effective,'target_level':target_level,'enough_scouts':enough_scouts,'exact_numbers':effective>=target_level and enough_scouts,'hero_intelligence_effect':'HISTORICAL_VALUE_UNKNOWN' if hero_id else None}

def reinforcement_report(session,player_id,march,target_city_id,event='ARRIVED'):
 from .models import ReinforcementReport,Army,City,Hero
 a=session.get(Army,march.army_id);c=session.get(City,target_city_id);h=session.get(Hero,a.hero_id) if a and a.hero_id else None
 return _create_report(session,ReinforcementReport,player_id,{'event':event,'march_id':march.id,'location':{'x':c.x,'y':c.y,'city_id':c.id,'name':c.name},'time':datetime.now(timezone.utc).isoformat(),'hero':{'id':h.id,'name':h.name,'level':h.level} if h else None,'troops':dict(a.troops or {}),'resources':dict(a.resources or {})})


MAIL_SUBJECT_MAX=120
MAIL_BODY_MAX=5000
MAIL_SEND_WINDOW_SECONDS=60
MAIL_SEND_WINDOW_MAX=10
MAIL_RECIPIENT_WINDOW_MAX=5

def _clean_mail_text(value,limit,field,allow_empty=False):
 if not isinstance(value,str):raise ValueError(f'{field} must be text')
 value=value.replace('\r\n','\n').replace('\r','\n').strip()
 if not allow_empty and not value:raise ValueError(f'{field} is required')
 if len(value)>limit:raise ValueError(f'{field} exceeds {limit} characters')
 # reject non-printing controls except newline/tab
 if any(ord(ch)<32 and ch not in '\n\t' for ch in value):raise ValueError(f'{field} contains invalid control characters')
 return value

def player_recipient_lookup(session,query,limit=10):
 from .models import Player
 q=_clean_mail_text(query,64,'query')
 if len(q)<2:raise ValueError('recipient lookup requires at least 2 characters')
 rows=session.scalars(select(Player).where(Player.name.ilike(f'{q}%')).order_by(Player.name).limit(min(max(limit,1),20))).all()
 return [{'id':p.id,'name':p.name} for p in rows]

def _mail_rate_check(session,sender_id,recipient_id,at):
 from .models import Mail
 cutoff=at-timedelta(seconds=MAIL_SEND_WINDOW_SECONDS)
 sent=session.scalar(select(func.count(Mail.id)).where(Mail.sender_player_id==sender_id,Mail.created_at>=cutoff)) or 0
 to_one=session.scalar(select(func.count(Mail.id)).where(Mail.sender_player_id==sender_id,Mail.recipient_player_id==recipient_id,Mail.created_at>=cutoff)) or 0
 if sent>=MAIL_SEND_WINDOW_MAX:raise ValueError('mail rate limit exceeded; try again shortly')
 if to_one>=MAIL_RECIPIENT_WINDOW_MAX:raise ValueError('recipient mail rate limit exceeded; try again shortly')

def send_player_mail(session,sender_id,recipient_name,subject,body,idempotency_key,reply_to_mail_id=None,at=None):
 from .models import Mail,Player
 at=at or datetime.now(timezone.utc);key=_clean_mail_text(idempotency_key,128,'idempotency_key')
 existing=session.scalar(select(Mail).where(Mail.sender_player_id==sender_id,Mail.idempotency_key==key))
 if existing:return {'mail_id':existing.id,'duplicate':True,'timestamp':existing.created_at}
 sender=session.get(Player,sender_id)
 if not sender:raise ValueError('sender not found')
 name=_clean_mail_text(recipient_name,64,'recipient')
 recipient=session.scalar(select(Player).where(func.lower(Player.name)==name.lower()))
 if not recipient:raise ValueError('recipient not found')
 if recipient.id==sender_id:raise ValueError('cannot send mail to yourself')
 subj=_clean_mail_text(subject,MAIL_SUBJECT_MAX,'subject');text=_clean_mail_text(body,MAIL_BODY_MAX,'body')
 parent=None
 if reply_to_mail_id is not None:
  parent=session.get(Mail,reply_to_mail_id)
  if not parent or parent.recipient_player_id!=sender_id or parent.recipient_deleted:raise ValueError('reply target not found')
  if parent.sender_player_id is None:raise ValueError('system mail cannot be replied to')
  if parent.sender_player_id!=recipient.id:raise ValueError('reply recipient must match original sender')
 _mail_rate_check(session,sender_id,recipient.id,at)
 row=Mail(sender_player_id=sender_id,recipient_player_id=recipient.id,subject=subj,body=text,created_at=at,read=False,reply_to_mail_id=parent.id if parent else None,idempotency_key=key)
 session.add(row)
 try:session.commit()
 except IntegrityError:
  session.rollback();row=session.scalar(select(Mail).where(Mail.sender_player_id==sender_id,Mail.idempotency_key==key))
  if row:return {'mail_id':row.id,'duplicate':True,'timestamp':row.created_at}
  raise
 return {'mail_id':row.id,'duplicate':False,'timestamp':row.created_at}

def create_system_mail(session,recipient_id,subject,body,system_kind,at=None):
 """Internal-only adapter. No HTTP endpoint accepts sender/system_kind."""
 from .models import Mail,Player
 if not session.get(Player,recipient_id):raise ValueError('recipient not found')
 subj=_clean_mail_text(subject,MAIL_SUBJECT_MAX,'subject');text=_clean_mail_text(body,MAIL_BODY_MAX,'body')
 kind=_clean_mail_text(system_kind,64,'system_kind')
 row=Mail(sender_player_id=None,recipient_player_id=recipient_id,subject=subj,body=text,created_at=at or datetime.now(timezone.utc),read=False,system_kind=kind)
 session.add(row);session.flush();return row

def mail_box(session,player_id,box='inbox',limit=100,offset=0):
 from .models import Mail,Player
 if not session.get(Player,player_id):raise ValueError('player not found')
 if box=='inbox':q=select(Mail).where(Mail.recipient_player_id==player_id,Mail.recipient_deleted==False)
 elif box=='sent':q=select(Mail).where(Mail.sender_player_id==player_id,Mail.sender_deleted==False)
 else:raise ValueError('invalid mailbox')
 rows=session.scalars(q.order_by(Mail.created_at.desc(),Mail.id.desc()).offset(max(0,offset)).limit(min(max(1,limit),100))).all()
 ids={x for m in rows for x in (m.sender_player_id,m.recipient_player_id) if x}
 names={p.id:p.name for p in session.scalars(select(Player).where(Player.id.in_(ids))).all()} if ids else {}
 return [{'id':m.id,'sender':names.get(m.sender_player_id,'System'),'sender_player_id':m.sender_player_id,'recipient':names.get(m.recipient_player_id),'recipient_player_id':m.recipient_player_id,'subject':m.subject,'body':m.body,'timestamp':m.created_at,'read':m.read if box=='inbox' else True,'reply_to_mail_id':m.reply_to_mail_id,'system_kind':m.system_kind} for m in rows]

def read_mail(session,player_id,mail_id):
 from .models import Mail,Player
 m=session.get(Mail,mail_id)
 if not m or (m.recipient_player_id!=player_id and m.sender_player_id!=player_id):raise ValueError('mail not found')
 if m.recipient_player_id==player_id:
  if m.recipient_deleted:raise ValueError('mail not found')
  m.read=True
 elif m.sender_deleted:raise ValueError('mail not found')
 session.commit()
 names={p.id:p.name for p in session.scalars(select(Player).where(Player.id.in_([x for x in (m.sender_player_id,m.recipient_player_id) if x]))).all()}
 return {'id':m.id,'sender':names.get(m.sender_player_id,'System'),'sender_player_id':m.sender_player_id,'recipient':names.get(m.recipient_player_id),'recipient_player_id':m.recipient_player_id,'subject':m.subject,'body':m.body,'timestamp':m.created_at,'read':m.read,'reply_to_mail_id':m.reply_to_mail_id,'system_kind':m.system_kind}

def delete_mail(session,player_id,mail_id,box):
 from .models import Mail
 m=session.get(Mail,mail_id)
 if not m:raise ValueError('mail not found')
 if box=='inbox':
  if m.recipient_player_id!=player_id:raise ValueError('mail not found')
  m.recipient_deleted=True
 elif box=='sent':
  if m.sender_player_id!=player_id:raise ValueError('mail not found')
  m.sender_deleted=True
 else:raise ValueError('invalid mailbox')
 # Physical cleanup only after no player-visible copy remains. System mail has no Sent copy.
 if m.recipient_deleted and (m.sender_player_id is None or m.sender_deleted):session.delete(m)
 session.commit();return {'deleted':True,'mail_id':mail_id,'box':box}


ALLIANCE_RANK_ORDER=('MEMBER','OFFICER','PRESBYTER','VICE_HOST','HOST')
ALLIANCE_PERMISSIONS={
 'MEMBER':{'chat':True,'alliance_mail':False,'invite':False,'applications':False,'promote':False,'demote':False,'expel':False,'diplomacy':False,'edit_info':False},
 'OFFICER':{'chat':True,'alliance_mail':False,'invite':True,'applications':False,'promote':False,'demote':False,'expel':False,'diplomacy':False,'edit_info':False},
 'PRESBYTER':{'chat':True,'alliance_mail':True,'invite':True,'applications':True,'promote':True,'demote':True,'expel':True,'diplomacy':False,'edit_info':False},
 'VICE_HOST':{'chat':True,'alliance_mail':True,'invite':True,'applications':True,'promote':True,'demote':True,'expel':True,'diplomacy':True,'edit_info':True},
 'HOST':{'chat':True,'alliance_mail':True,'invite':True,'applications':True,'promote':True,'demote':True,'expel':True,'diplomacy':True,'edit_info':True,'leadership':True},
}
def _seed_alliance_ranks(session,alliance_id):
 from .models import AllianceRank
 for key in ALLIANCE_RANK_ORDER:
  row=session.scalar(select(AllianceRank).where(AllianceRank.alliance_id==alliance_id,AllianceRank.rank_key==key))
  if not row:session.add(AllianceRank(alliance_id=alliance_id,rank_key=key,permissions=ALLIANCE_PERMISSIONS[key]))
 session.flush()

def alliance_permission(session,player_id,permission):
 from .models import AllianceRank
 mem=_alliance_membership(session,player_id)
 if not mem:return False
 _seed_alliance_ranks(session,mem.alliance_id)
 rank=session.scalar(select(AllianceRank).where(AllianceRank.alliance_id==mem.alliance_id,AllianceRank.rank_key==mem.rank))
 return bool((rank.permissions or {}).get(permission,False))

def require_alliance_permission(session,player_id,permission):
 mem=_alliance_membership(session,player_id)
 if not mem:raise ValueError('not in an alliance')
 if not alliance_permission(session,player_id,permission):raise ValueError('insufficient alliance permission')
 return mem

def alliance_detail(session,player_id):
 from .models import Alliance,AllianceMember,Player,AllianceRelation
 mem=_alliance_membership(session,player_id)
 if not mem:return {'alliance':None}
 a=session.get(Alliance,mem.alliance_id);_seed_alliance_ranks(session,a.id)
 members=session.scalars(select(AllianceMember).where(AllianceMember.alliance_id==a.id)).all()
 players={p.id:p for p in session.scalars(select(Player).where(Player.id.in_([m.player_id for m in members]))).all()}
 rels=session.scalars(select(AllianceRelation).where(AllianceRelation.alliance_id==a.id)).all()
 return {'alliance':{'id':a.id,'name':a.name,'information':a.information,'my_rank':mem.rank,'permissions':ALLIANCE_PERMISSIONS[mem.rank],
  'members':[{'player_id':m.player_id,'name':players[m.player_id].name,'rank':m.rank} for m in sorted(members,key=lambda x:(-ALLIANCE_RANK_ORDER.index(x.rank),players[x.player_id].name))],
  'relations':[{'alliance_id':r.other_alliance_id,'state':r.state} for r in rels]}}

def update_alliance_information(session,player_id,information):
 from .models import Alliance
 mem=require_alliance_permission(session,player_id,'edit_info')
 text=_clean_mail_text(information,2000,'alliance information',allow_empty=True)
 a=session.get(Alliance,mem.alliance_id);a.information=text;session.commit();return {'information':text}

def invite_to_alliance(session,actor_id,player_name):
 from .models import AllianceInvitation,Player
 mem=require_alliance_permission(session,actor_id,'invite');p=session.scalar(select(Player).where(func.lower(Player.name)==player_name.strip().lower()))
 if not p:raise ValueError('player not found')
 if _alliance_membership(session,p.id):raise ValueError('player already in alliance')
 row=session.scalar(select(AllianceInvitation).where(AllianceInvitation.alliance_id==mem.alliance_id,AllianceInvitation.player_id==p.id))
 if row and row.status=='PENDING':return {'invitation_id':row.id,'status':'PENDING'}
 if row:row.status='PENDING';row.inviter_player_id=actor_id;row.created_at=datetime.now(timezone.utc)
 else:row=AllianceInvitation(alliance_id=mem.alliance_id,inviter_player_id=actor_id,player_id=p.id);session.add(row)
 session.commit();return {'invitation_id':row.id,'status':'PENDING'}

def alliance_invitations(session,player_id):
 from .models import AllianceInvitation,Alliance
 rows=session.scalars(select(AllianceInvitation).where(AllianceInvitation.player_id==player_id,AllianceInvitation.status=='PENDING')).all()
 return [{'id':r.id,'alliance_id':r.alliance_id,'alliance_name':session.get(Alliance,r.alliance_id).name,'created_at':r.created_at} for r in rows]

def respond_alliance_invitation(session,player_id,invitation_id,accept):
 from .models import AllianceInvitation,AllianceMember
 inv=session.get(AllianceInvitation,invitation_id)
 if not inv or inv.player_id!=player_id or inv.status!='PENDING':raise ValueError('pending invitation not found')
 if accept:
  if _alliance_membership(session,player_id):raise ValueError('already in alliance')
  inv.status='ACCEPTED';session.add(AllianceMember(alliance_id=inv.alliance_id,player_id=player_id,rank='MEMBER'))
 else:inv.status='REJECTED'
 session.commit();return {'status':inv.status,'alliance_id':inv.alliance_id}

def reject_alliance_application(session,actor_id,application_id):
 from .models import AllianceApplication
 app=session.get(AllianceApplication,application_id);mem=require_alliance_permission(session,actor_id,'applications')
 if not app or app.alliance_id!=mem.alliance_id or app.status!='PENDING':raise ValueError('pending application not found')
 app.status='REJECTED';session.commit();return {'status':'REJECTED'}

def change_alliance_rank(session,actor_id,target_player_id,direction):
 from .models import AllianceMember
 actor=require_alliance_permission(session,actor_id,'promote' if direction=='promote' else 'demote')
 target=_alliance_membership(session,target_player_id)
 if not target or target.alliance_id!=actor.alliance_id:raise ValueError('target is not an alliance member')
 if target.rank=='HOST':raise ValueError('Host rank changes only through leadership transfer')
 ai=ALLIANCE_RANK_ORDER.index(actor.rank);ti=ALLIANCE_RANK_ORDER.index(target.rank)
 if ti>=ai:raise ValueError('cannot change equal or higher rank')
 ni=ti+(1 if direction=='promote' else -1)
 if ni<0 or ni>=len(ALLIANCE_RANK_ORDER)-0:raise ValueError('invalid rank change')
 if ALLIANCE_RANK_ORDER[ni]=='HOST':raise ValueError('Host rank requires leadership transfer')
 target.rank=ALLIANCE_RANK_ORDER[ni];session.commit();return {'player_id':target.player_id,'rank':target.rank}

def expel_alliance_member(session,actor_id,target_player_id):
 actor=require_alliance_permission(session,actor_id,'expel');target=_alliance_membership(session,target_player_id)
 if not target or target.alliance_id!=actor.alliance_id:raise ValueError('target is not an alliance member')
 if ALLIANCE_RANK_ORDER.index(target.rank)>=ALLIANCE_RANK_ORDER.index(actor.rank):raise ValueError('cannot expel equal or higher rank')
 session.delete(target);session.commit();return {'expelled':target_player_id}

def leave_alliance(session,player_id):
 mem=_alliance_membership(session,player_id)
 if not mem:raise ValueError('not in an alliance')
 if mem.rank=='HOST':raise ValueError('Host must transfer leadership before leaving')
 session.delete(mem);session.commit();return {'left':True}

def transfer_alliance_host(session,host_id,target_player_id):
 host=require_alliance_permission(session,host_id,'leadership');target=_alliance_membership(session,target_player_id)
 if not target or target.alliance_id!=host.alliance_id:raise ValueError('target is not an alliance member')
 host.rank='VICE_HOST';target.rank='HOST';session.commit();return {'host_player_id':target_player_id}

def alliance_relation(session,a_id,b_id):
 from .models import AllianceRelation
 if a_id==b_id:return 'MEMBER'
 r=session.scalar(select(AllianceRelation).where(AllianceRelation.alliance_id==a_id,AllianceRelation.other_alliance_id==b_id))
 return r.state if r else 'NEUTRAL'

def set_alliance_relation(session,actor_id,other_alliance_id,state):
 from .models import Alliance,AllianceRelation
 mem=require_alliance_permission(session,actor_id,'diplomacy');state=state.upper()
 if state not in ('FRIENDLY','NEUTRAL','HOSTILE'):raise ValueError('invalid diplomatic state')
 if other_alliance_id==mem.alliance_id or not session.get(Alliance,other_alliance_id):raise ValueError('invalid alliance')
 def setone(a,b):
  r=session.scalar(select(AllianceRelation).where(AllianceRelation.alliance_id==a,AllianceRelation.other_alliance_id==b))
  if state=='NEUTRAL':
   if r:session.delete(r)
  elif r:r.state=state;r.updated_at=datetime.now(timezone.utc)
  else:session.add(AllianceRelation(alliance_id=a,other_alliance_id=b,state=state))
 setone(mem.alliance_id,other_alliance_id);setone(other_alliance_id,mem.alliance_id);session.commit()
 return {'other_alliance_id':other_alliance_id,'state':state}

def player_relationship(session,viewer_id,other_id):
 if viewer_id==other_id:return 'SELF'
 a=_alliance_membership(session,viewer_id);b=_alliance_membership(session,other_id)
 if a and b:
  if a.alliance_id==b.alliance_id:return 'ALLIANCE'
  return alliance_relation(session,a.alliance_id,b.alliance_id)
 return 'NEUTRAL'

def send_alliance_chat(session,player_id,body,at=None):
 from .models import AllianceChatMessage
 mem=require_alliance_permission(session,player_id,'chat');text=_clean_mail_text(body,500,'chat message');now=at or datetime.now(timezone.utc)
 recent=session.scalar(select(func.count(AllianceChatMessage.id)).where(AllianceChatMessage.player_id==player_id,AllianceChatMessage.created_at>=now-timedelta(seconds=10))) or 0
 if recent>=5:raise ValueError('alliance chat rate limit exceeded')
 row=AllianceChatMessage(alliance_id=mem.alliance_id,player_id=player_id,body=text,created_at=now);session.add(row);session.commit();return {'id':row.id,'timestamp':row.created_at}

def alliance_chat(session,player_id,limit=100):
 from .models import AllianceChatMessage,Player
 mem=_alliance_membership(session,player_id)
 if not mem:raise ValueError('not in an alliance')
 rows=session.scalars(select(AllianceChatMessage).where(AllianceChatMessage.alliance_id==mem.alliance_id).order_by(AllianceChatMessage.id.desc()).limit(min(max(limit,1),100))).all()[::-1]
 names={p.id:p.name for p in session.scalars(select(Player).where(Player.id.in_([r.player_id for r in rows]))).all()} if rows else {}
 return [{'id':r.id,'player_id':r.player_id,'player':names.get(r.player_id),'body':r.body,'timestamp':r.created_at} for r in rows]

def send_alliance_mail(session,actor_id,subject,body):
 from .models import AllianceMember
 mem=require_alliance_permission(session,actor_id,'alliance_mail');subj=_clean_mail_text(subject,MAIL_SUBJECT_MAX,'subject');text=_clean_mail_text(body,MAIL_BODY_MAX,'body')
 members=session.scalars(select(AllianceMember).where(AllianceMember.alliance_id==mem.alliance_id,AllianceMember.player_id!=actor_id)).all()
 rows=[create_system_mail(session,m.player_id,subj,text,'ALLIANCE_MAIL') for m in members];session.commit();return {'recipients':len(rows)}


CHAT_CHANNELS=('WORLD','ALLIANCE','WHISPER')
CHAT_MESSAGE_MAX=500
CHAT_RATE_WINDOW=10
CHAT_RATE_MAX=5
def _active_chat_suspension(session,player_id,at):
 from .models import ChatModerationAction
 rows=session.scalars(select(ChatModerationAction).where(ChatModerationAction.target_player_id==player_id,ChatModerationAction.action.in_(['MUTE','SUSPEND'])).order_by(ChatModerationAction.id.desc())).all()
 return next((r for r in rows if r.expires_at is None or (r.expires_at.replace(tzinfo=timezone.utc) if r.expires_at.tzinfo is None else r.expires_at)>at),None)
def send_chat_message(session,sender_id,channel,body,recipient_name=None,at=None):
 from .models import ChatMessage,Player
 at=at or datetime.now(timezone.utc);channel=channel.upper()
 if channel not in CHAT_CHANNELS:raise ValueError('invalid chat channel')
 sender=session.get(Player,sender_id)
 if not sender:raise ValueError('sender not found')
 suspension=_active_chat_suspension(session,sender_id,at)
 if suspension:raise ValueError('chat sending is restricted by moderation')
 text=_clean_mail_text(body,CHAT_MESSAGE_MAX,'message')
 recent=session.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.sender_player_id==sender_id,ChatMessage.created_at>=at-timedelta(seconds=CHAT_RATE_WINDOW))) or 0
 if recent>=CHAT_RATE_MAX:raise ValueError('chat rate limit exceeded')
 recipient=None;alliance_id=None
 if channel=='ALLIANCE':
  mem=_alliance_membership(session,sender_id)
  if not mem:raise ValueError('alliance membership required')
  alliance_id=mem.alliance_id
 elif channel=='WHISPER':
  if not recipient_name:raise ValueError('whisper recipient required')
  recipient=session.scalar(select(Player).where(func.lower(Player.name)==recipient_name.strip().lower()))
  if not recipient or recipient.id==sender_id:raise ValueError('invalid whisper recipient')
  from .models import ChatBlock
  if session.scalar(select(ChatBlock).where(ChatBlock.player_id==recipient.id,ChatBlock.blocked_player_id==sender_id)):raise ValueError('recipient is not accepting whispers from this player')
 row=ChatMessage(sender_player_id=sender_id,channel=channel,recipient_player_id=recipient.id if recipient else None,alliance_id=alliance_id,body=text,created_at=at)
 session.add(row);session.commit()
 return {'id':row.id,'channel':channel,'timestamp':row.created_at}

def chat_messages(session,player_id,channel,since_id=0,limit=100,whisper_with=None):
 from .models import ChatMessage,ChatBlock,ChatMute,Player
 channel=channel.upper()
 if channel not in CHAT_CHANNELS:raise ValueError('invalid chat channel')
 viewer=session.get(Player,player_id)
 if not viewer:raise ValueError('player not found')
 q=select(ChatMessage).where(ChatMessage.channel==channel,ChatMessage.id>max(0,since_id),ChatMessage.moderated==False)
 if channel=='ALLIANCE':
  mem=_alliance_membership(session,player_id)
  if not mem:raise ValueError('alliance membership required')
  q=q.where(ChatMessage.alliance_id==mem.alliance_id)
 elif channel=='WHISPER':
  q=q.where(or_(and_(ChatMessage.sender_player_id==player_id),and_(ChatMessage.recipient_player_id==player_id)))
  if whisper_with:
   other=session.scalar(select(Player).where(func.lower(Player.name)==whisper_with.strip().lower()))
   if not other:raise ValueError('player not found')
   q=q.where(or_(and_(ChatMessage.sender_player_id==player_id,ChatMessage.recipient_player_id==other.id),and_(ChatMessage.sender_player_id==other.id,ChatMessage.recipient_player_id==player_id)))
 blocked=set(session.scalars(select(ChatBlock.blocked_player_id).where(ChatBlock.player_id==player_id)).all())
 muted=set(session.scalars(select(ChatMute.muted_player_id).where(ChatMute.player_id==player_id)).all())
 rows=session.scalars(q.order_by(ChatMessage.id).limit(min(max(limit,1),200))).all()
 rows=[r for r in rows if r.sender_player_id not in blocked|muted]
 ids={r.sender_player_id for r in rows}|{r.recipient_player_id for r in rows if r.recipient_player_id}
 names={p.id:p.name for p in session.scalars(select(Player).where(Player.id.in_(ids))).all()} if ids else {}
 return [{'id':r.id,'sender_player_id':r.sender_player_id,'sender':names.get(r.sender_player_id),'timestamp':r.created_at,'channel':r.channel,'recipient_player_id':r.recipient_player_id,'recipient':names.get(r.recipient_player_id) if r.recipient_player_id else None,'body':r.body} for r in rows]

def set_chat_block(session,player_id,target_name,blocked=True):
 from .models import ChatBlock,Player
 target=session.scalar(select(Player).where(func.lower(Player.name)==target_name.strip().lower()))
 if not target or target.id==player_id:raise ValueError('invalid player')
 row=session.scalar(select(ChatBlock).where(ChatBlock.player_id==player_id,ChatBlock.blocked_player_id==target.id))
 if blocked and not row:session.add(ChatBlock(player_id=player_id,blocked_player_id=target.id))
 if not blocked and row:session.delete(row)
 session.commit();return {'player':target.name,'blocked':blocked}
def set_chat_mute(session,player_id,target_name,muted=True):
 from .models import ChatMute,Player
 target=session.scalar(select(Player).where(func.lower(Player.name)==target_name.strip().lower()))
 if not target or target.id==player_id:raise ValueError('invalid player')
 row=session.scalar(select(ChatMute).where(ChatMute.player_id==player_id,ChatMute.muted_player_id==target.id))
 if muted and not row:session.add(ChatMute(player_id=player_id,muted_player_id=target.id))
 if not muted and row:session.delete(row)
 session.commit();return {'player':target.name,'muted':muted}
def moderate_chat_message(session,message_id,moderator_label,reason):
 from .models import ChatMessage,ChatModerationAction
 m=session.get(ChatMessage,message_id)
 if not m:raise ValueError('message not found')
 m.moderated=True;m.moderation_reason=_clean_mail_text(reason,200,'reason')
 session.add(ChatModerationAction(moderator_label=moderator_label,target_player_id=m.sender_player_id,action='REMOVE_MESSAGE',reason=m.moderation_reason));session.commit();return {'removed':True}
def restrict_chat_player(session,target_player_id,moderator_label,reason,minutes=None):
 from .models import ChatModerationAction,Player
 if not session.get(Player,target_player_id):raise ValueError('player not found')
 expires=datetime.now(timezone.utc)+timedelta(minutes=minutes) if minutes else None
 row=ChatModerationAction(moderator_label=moderator_label,target_player_id=target_player_id,action='MUTE',reason=_clean_mail_text(reason,500,'reason'),expires_at=expires);session.add(row);session.commit();return {'restricted':True,'expires_at':expires}


QUEST_DEFINITIONS=json.loads((Path(__file__).resolve().parents[1]/'game_definitions'/'quests.json').read_text())
QUEST_BY_KEY={q['key']:q for q in QUEST_DEFINITIONS['quests']}

def _quest_progress_row(session,player_id,key):
 from .models import QuestProgress
 row=session.scalar(select(QuestProgress).where(QuestProgress.player_id==player_id,QuestProgress.quest_key==key))
 if not row:row=QuestProgress(player_id=player_id,quest_key=key,state={},completed=False,claimed=False);session.add(row);session.flush()
 return row
def _player_cities(session,player_id):return session.scalars(select(City).where(City.player_id==player_id)).all()
def _quest_requirement(session,player_id,req,state):
 cities=_player_cities(session,player_id);typ=req['type']
 if typ=='building_level':
  ids=[c.id for c in cities]
  best=session.scalar(select(func.max(Building.level)).where(Building.city_id.in_(ids),Building.definition_key==req['building'])) if ids else 0
  return (best or 0)>=req['level'],best or 0
 if typ=='technology_level':
  t=session.scalar(select(Technology).where(Technology.player_id==player_id,Technology.definition_key==req['technology']))
  v=t.level if t else 0;return v>=req['level'],v
 if typ=='troop_quantity':
  ids=[c.id for c in cities];v=session.scalar(select(func.sum(TroopQuantity.quantity)).where(TroopQuantity.city_id.in_(ids),TroopQuantity.troop_type_key==req['troop'])) if ids else 0
  v=v or 0;return v>=req['quantity'],v
 if typ=='resource_amount':
  ids=[c.id for c in cities];v=session.scalar(select(func.sum(Resource.quantity)).where(Resource.city_id.in_(ids),Resource.kind==req['resource'])) if ids else 0
  v=float(v or 0);return v>=req['amount'],v
 if typ=='population_limit':
  ids=[c.id for c in cities];v=session.scalar(select(func.sum(PopulationState.population_limit)).where(PopulationState.city_id.in_(ids))) if ids else 0
  v=v or 0;return v>=req['amount'],v
 if typ=='hero_count':
  from .models import Hero
  ids=[c.id for c in cities];v=session.scalar(select(func.count(Hero.id)).where(Hero.city_id.in_(ids))) if ids else 0
  return v>=req['count'],v
 if typ=='alliance_member':
  v=_alliance_membership(session,player_id) is not None;return v,v
 if typ=='prestige':
  from .models import PlayerProgression
  prog=session.scalar(select(PlayerProgression).where(PlayerProgression.player_id==player_id));v=prog.prestige if prog else 0;return v>=req['amount'],v
 if typ=='military_event':
  events=(state or {}).get('events',{}).get(req['event'],[])
  if req.get('minimum_level') is not None:events=[e for e in events if int(e.get('level',0))>=req['minimum_level']]
  return len(events)>=req.get('count',1),len(events)
 raise ValueError(f"unknown quest requirement type {typ}")
def evaluate_quest(session,player_id,key):
 q=QUEST_BY_KEY[key];row=_quest_progress_row(session,player_id,key)
 prereqs=q.get('requires_quests',[])
 prereq_ok=all((_quest_progress_row(session,player_id,k).claimed) for k in prereqs)
 details=[];ok=prereq_ok
 for req in q['requirements']:
  met,value=_quest_requirement(session,player_id,req,row.state or {});details.append({'requirement':req,'met':met,'value':value});ok=ok and met
 row.completed=bool(ok);session.flush()
 return {'key':key,'category':q['category'],'name':q['name'],'completed':row.completed,'claimed':row.claimed,'requirements':details,'rewards':q.get('rewards',{}),'reward_status':q.get('reward_status','VERIFIED'),'prerequisites_met':prereq_ok}
def quest_list(session,player_id):
 return [evaluate_quest(session,player_id,q['key']) for q in QUEST_DEFINITIONS['quests']]
def record_quest_event(session,player_id,event,**metadata):
 # Events are authoritative adapters called only by server gameplay resolution.
 for q in QUEST_DEFINITIONS['quests']:
  if not any(r['type']=='military_event' and r['event']==event for r in q['requirements']):continue
  row=_quest_progress_row(session,player_id,q['key']);st=dict(row.state or {});events=dict(st.get('events',{}));lst=list(events.get(event,[]));lst.append({'at':datetime.now(timezone.utc).isoformat(),**metadata});events[event]=lst;st['events']=events;row.state=st
 session.flush()
def claim_quest(session,player_id,key,idempotency_key):
 if key not in QUEST_BY_KEY:raise ValueError('quest not found')
 def work():
  q=QUEST_BY_KEY[key];row=_quest_progress_row(session,player_id,key);status=evaluate_quest(session,player_id,key)
  if row.claimed:return {'quest_key':key,'claimed':True,'duplicate':True}
  if not status['completed']:raise ValueError('quest is not complete')
  rewards=q.get('rewards',{})
  cities=_player_cities(session,player_id)
  if not cities:raise ValueError('player has no city')
  city=cities[0]
  for kind,amount in rewards.get('resources',{}).items():
   r=session.scalar(select(Resource).where(Resource.city_id==city.id,Resource.kind==kind));r.quantity+=amount
  if rewards.get('gold'):
   eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city.id));eco.gold+=rewards['gold'];city.gold=eco.gold
  if rewards.get('population'):
   pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city.id));pop.population=min(pop.population_limit,pop.population+rewards['population']);city.population=pop.population
  for item,qty in rewards.get('items',{}).items():
   pi=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==item))
   if pi:pi.quantity+=qty
   else:session.add(PlayerItem(player_id=player_id,item_key=item,quantity=qty))
  if rewards.get('prestige'):
   from .models import PlayerProgression
   prog=session.scalar(select(PlayerProgression).where(PlayerProgression.player_id==player_id))
   if not prog:prog=PlayerProgression(player_id=player_id,prestige=0,honor=0,title_rank_key='Civilian|Civilian');session.add(prog)
   prog.prestige+=rewards['prestige']
  row.claimed=True;row.completed=True;session.flush()
  return {'quest_key':key,'claimed':True,'duplicate':False,'rewards':rewards}
 return idempotent_operation(session,player_id,idempotency_key,'claim_quest',work)


PROGRESSION_DEFINITIONS=json.loads((Path(__file__).resolve().parents[1]/'game_definitions'/'progression.json').read_text())
RANK_DEFS={x['key']:x for x in PROGRESSION_DEFINITIONS['ranks']}
TITLE_DEFS={x['key']:x for x in PROGRESSION_DEFINITIONS['titles']}
RANK_ORDER=[x['key'] for x in sorted(PROGRESSION_DEFINITIONS['ranks'],key=lambda x:x['order'])]
TITLE_ORDER=[x['key'] for x in sorted(PROGRESSION_DEFINITIONS['titles'],key=lambda x:x['order'])]

def _progression(session,player_id):
 from .models import PlayerProgression
 p=session.scalar(select(PlayerProgression).where(PlayerProgression.player_id==player_id))
 if not p:p=PlayerProgression(player_id=player_id,prestige=0,honor=0,title_rank_key='Civilian|Civilian');session.add(p);session.flush()
 raw=p.title_rank_key or 'Civilian|Civilian'
 if '|' in raw:rank,title=raw.split('|',1)
 else:rank,title='Civilian',raw
 if rank not in RANK_DEFS:rank='Civilian'
 if title not in TITLE_DEFS:title='Civilian'
 return p,rank,title
def _set_progression_keys(p,rank,title):p.title_rank_key=f'{rank}|{title}'
def progression_status(session,player_id,city_id=None):
 p,rank,title=_progression(session,player_id)
 cities=_player_cities(session,player_id);city=session.get(City,city_id) if city_id else (cities[0] if cities else None)
 if city and city.player_id!=player_id:raise ValueError('city not owned')
 nxt_rank=RANK_ORDER[RANK_ORDER.index(rank)+1] if RANK_ORDER.index(rank)+1<len(RANK_ORDER) else None
 nxt_title=TITLE_ORDER[TITLE_ORDER.index(title)+1] if TITLE_ORDER.index(title)+1<len(TITLE_ORDER) else None
 return {'prestige':p.prestige,'honor':p.honor,'rank':rank,'title':title,'city_limit':TITLE_DEFS[title]['city_limit'],'cities_owned':len(cities),
  'rank_promotion':promotion_preview(session,player_id,'RANK',nxt_rank,city.id if city else None) if nxt_rank else None,
  'title_promotion':promotion_preview(session,player_id,'TITLE',nxt_title,city.id if city else None) if nxt_title else None}
def _item_quantity(session,player_id,key):
 row=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==key));return row.quantity if row else 0
def promotion_preview(session,player_id,kind,target_key,city_id):
 p,rank,title=_progression(session,player_id);kind=kind.upper();defs=RANK_DEFS if kind=='RANK' else TITLE_DEFS;order=RANK_ORDER if kind=='RANK' else TITLE_ORDER;current=rank if kind=='RANK' else title
 if target_key not in defs:raise ValueError('promotion not found')
 if order.index(target_key)!=order.index(current)+1:raise ValueError('only the next promotion may be claimed')
 d=defs[target_key];req=d.get('requirements',{});city=session.get(City,city_id) if city_id else None
 if not city or city.player_id!=player_id:raise ValueError('owned city required for promotion')
 settle_economy(session,city.id);eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city.id))
 checks=[]
 def add(t,need,have,consume=False):checks.append({'type':t,'required':need,'current':have,'satisfied':have>=need if isinstance(need,(int,float)) else have==need,'consumed_on_promotion':consume})
 if 'gold' in req:add('gold',req['gold'],int(eco.gold if eco else city.gold),True)
 if 'town_hall' in req:add('town_hall',req['town_hall'],current_level(session,town_hall_building(session,city.id)),False)
 if 'prestige' in req:add('prestige',req['prestige'],p.prestige,False)
 if 'rank' in req:add('rank',req['rank'],rank,False);checks[-1]['satisfied']=RANK_ORDER.index(rank)>=RANK_ORDER.index(req['rank'])
 for medal,count in req.get('medals',{}).items():add(f'medal:{medal}',count,_item_quantity(session,player_id,medal),True)
 return {'kind':kind,'current':current,'next':target_key,'requirements':checks,'satisfied':all(x['satisfied'] for x in checks),'rewards':d.get('rewards',{}),'city_limit':d.get('city_limit')}
def promote_player(session,player_id,city_id,kind,target_key,idempotency_key):
 def work():
  preview=promotion_preview(session,player_id,kind,target_key,city_id)
  if not preview['satisfied']:raise ValueError('promotion requirements not satisfied')
  p,rank,title=_progression(session,player_id);d=(RANK_DEFS if kind.upper()=='RANK' else TITLE_DEFS)[target_key];req=d.get('requirements',{})
  eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id));eco.gold-=req.get('gold',0);session.get(City,city_id).gold=eco.gold
  for medal,count in req.get('medals',{}).items():
   item=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==medal));item.quantity-=count
  if kind.upper()=='RANK':rank=target_key
  else:title=target_key
  _set_progression_keys(p,rank,title)
  rewards=d.get('rewards',{});p.prestige+=rewards.get('prestige',0)
  for key,qty in rewards.get('items',{}).items():
   item=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==key))
   if item:item.quantity+=qty
   else:session.add(PlayerItem(player_id=player_id,item_key=key,quantity=qty))
  session.flush();return {'promoted':True,'rank':rank,'title':title,'prestige':p.prestige,'city_limit':TITLE_DEFS[title]['city_limit'],'rewards':rewards}
 return idempotent_operation(session,player_id,idempotency_key,f'PROMOTE_{kind.upper()}_{target_key}',work)

def player_cities_overview(session,player_id):
 from .models import City,ConstructionQueue,ResearchQueue,TrainingQueue,March,Army,HeroAssignment
 process_due_marches(session)
 rows=session.scalars(select(City).where(City.player_id==player_id).order_by(City.id)).all();out=[]
 for c in rows:
  complete_construction(session,c.id);complete_research(session,c.id);complete_training(session,c.id);settle_economy(session,c.id)
  out.append({'id':c.id,'name':c.name,'x':c.x,'y':c.y,'population':c.population,'idle_population':c.idle_population,'gold':c.gold,
   'town_hall_level':current_level(session,town_hall_building(session,c.id)),
   'construction_active':session.scalar(select(func.count(ConstructionQueue.id)).where(ConstructionQueue.city_id==c.id,ConstructionQueue.status=='ACTIVE')) or 0,
   'research_active':session.scalar(select(func.count(ResearchQueue.id)).where(ResearchQueue.city_id==c.id,ResearchQueue.status=='ACTIVE')) or 0,
   'training_active':session.scalar(select(func.count(TrainingQueue.id)).where(TrainingQueue.city_id==c.id,TrainingQueue.status=='ACTIVE')) or 0,
   'marches_active':session.scalar(select(func.count(March.id)).join(Army,Army.id==March.army_id).where(March.source_city_id==c.id,March.status.in_(ACTIVE_MARCH_STATUSES))) or 0})
 return out

def city_independence_snapshot(session,player_id,city_id):
 from .models import Resource,TroopQuantity,Hero,HeroAssignment,Fortification,ConstructionQueue,ResearchQueue,TrainingQueue,March,Army
 c=session.get(City,city_id)
 if not c or c.player_id!=player_id:raise ValueError('city not owned')
 settle_economy(session,city_id);complete_construction(session,city_id);complete_research(session,city_id);complete_training(session,city_id);process_due_marches(session)
 resources={r.kind:r.quantity for r in session.scalars(select(Resource).where(Resource.city_id==city_id)).all()}
 troops={r.troop_type_key:r.quantity for r in session.scalars(select(TroopQuantity).where(TroopQuantity.city_id==city_id)).all()}
 heroes=session.scalars(select(Hero).where(Hero.city_id==city_id)).all()
 mayor=next((h for h in heroes if h.assignment=='mayor'),None)
 return {'city':{'id':c.id,'name':c.name,'x':c.x,'y':c.y,'population':c.population,'idle_population':c.idle_population,'gold':c.gold,'tax_rate':c.tax_rate,'loyalty':c.loyalty,'grievance':c.grievance},
  'resources':resources,'troops':troops,'heroes':[{'id':h.id,'name':h.name,'level':h.level,'assignment':h.assignment} for h in heroes],
  'mayor':{'id':mayor.id,'name':mayor.name} if mayor else None,
  'fortifications':{f.kind:f.quantity for f in session.scalars(select(Fortification).where(Fortification.city_id==city_id)).all()},
  'effective_technology':{k:effective_technology_level(session,city_id,k) for k in DATA['technologies']},
  'queues':{'construction':session.scalar(select(func.count(ConstructionQueue.id)).where(ConstructionQueue.city_id==city_id,ConstructionQueue.status=='ACTIVE')) or 0,
            'research':session.scalar(select(func.count(ResearchQueue.id)).where(ResearchQueue.city_id==city_id,ResearchQueue.status=='ACTIVE')) or 0,
            'training':session.scalar(select(func.count(TrainingQueue.id)).where(TrainingQueue.city_id==city_id,TrainingQueue.status=='ACTIVE')) or 0},
  'marches':[march_payload(session,m) for m in session.scalars(select(March).join(Army,Army.id==March.army_id).where(March.source_city_id==city_id,March.status.in_(ACTIVE_MARCH_STATUSES))).all()]}

def capture_player_city(session,attacker_player_id,source_city_id,target_city_id):
 from .models import City,CityCoordinate,MapTile,Hero,Army,March
 source=session.get(City,source_city_id);target=session.get(City,target_city_id)
 if not source or source.player_id!=attacker_player_id:raise ValueError('source city not owned')
 if not target or target.player_id==attacker_player_id:raise ValueError('invalid target city')
 if target.loyalty>0:raise ValueError('target loyalty must be zero')
 if session.scalar(select(func.count(City.id)).where(City.player_id==target.player_id))<=1:raise ValueError("a player's only city cannot be conquered")
 if session.scalar(select(func.count(City.id)).where(City.player_id==attacker_player_id))>=player_city_cap(session,attacker_player_id):raise ValueError('title does not permit another city')
 old_owner=target.player_id
 session.execute(City.__table__.update().where(City.__table__.c.id==target_city_id).values(player_id=attacker_player_id))
 target.player_id=attacker_player_id
 tile=session.scalar(select(MapTile).where(MapTile.x==target.x,MapTile.y==target.y))
 if tile:tile.owner_player_id=attacker_player_id
 session.flush()
 # Resident heroes change city ownership context only if they are not captured/marching; exact hero capture selection remains combat-owned.
 # Active outgoing armies remain owned by their original player and return handling must resolve independently.
 return {'captured_city_id':target.id,'previous_owner_player_id':old_owner,'new_owner_player_id':attacker_player_id,'x':target.x,'y':target.y}


ITEM_DEFINITIONS=json.loads((Path(__file__).resolve().parents[1]/'game_definitions'/'items.json').read_text())['items']

def inventory_snapshot(session,player_id,at=None):
 from .models import PlayerItem,Buff,HeroBuff
 at=at or datetime.now(timezone.utc);rows={r.item_key:r.quantity for r in session.scalars(select(PlayerItem).where(PlayerItem.player_id==player_id)).all()}
 buffs=[]
 for b in session.scalars(select(Buff).where(Buff.player_id==player_id)).all():
  ex=b.expires_at if b.expires_at.tzinfo else b.expires_at.replace(tzinfo=timezone.utc)
  if ex>at:buffs.append({'buff_key':b.buff_key,'starts_at':b.starts_at,'expires_at':b.expires_at,'metadata':b.metadata_json})
 return {'items':[{'key':k,'name':d['name'],'category':d['category'],'quantity':rows.get(k,0),'usable_directly':d.get('usable_directly',True),'implemented':d.get('implemented',True),'targets':d.get('targets',[]),'historical_effect':d.get('historical_effect')} for k,d in ITEM_DEFINITIONS.items() if rows.get(k,0)>0],
         'active_buffs':buffs}

def _consume_item(session,player_id,key,count=1):
 from .models import PlayerItem
 row=session.scalar(select(PlayerItem).where(PlayerItem.player_id==player_id,PlayerItem.item_key==key))
 if not row or row.quantity<count:raise ValueError('item unavailable')
 row.quantity-=count;return row

def _queue_for_item(session,player_id,target_type,target_id):
 from .models import ResearchQueue,TrainingQueue
 models={'construction':ConstructionQueue,'research':ResearchQueue,'training':TrainingQueue}
 if target_type=='fortification':
  from .models import FortificationQueue
  model=FortificationQueue
 else:model=models.get(target_type)
 if not model:raise ValueError('invalid queue target')
 q=session.get(model,target_id)
 if not q:raise ValueError('queue target not found')
 city=session.get(City,q.city_id)
 if not city or city.player_id!=player_id:raise ValueError('queue target not owned')
 if q.status not in ('ACTIVE','QUEUED'):raise ValueError('queue is not active')
 return q

def _apply_queue_speedup(session,player_id,item_key,spec,target_type,target_id,now):
 from .models import ItemApplication
 q=_queue_for_item(session,player_id,target_type,target_id)
 if spec.get('once_per_target') and session.scalar(select(ItemApplication).where(ItemApplication.item_key==item_key,ItemApplication.target_type==target_type,ItemApplication.target_id==target_id)):raise ValueError('item already applied to this queue')
 if not q.completes_at:raise ValueError('queue has not started')
 due=q.completes_at if q.completes_at.tzinfo else q.completes_at.replace(tzinfo=timezone.utc);remaining=max(0,(due-now).total_seconds());eff=spec['effect']
 reduction=eff.get('seconds',0) if eff['type']=='queue_reduce_seconds' else remaining*eff['percent']/100
 q.completes_at=max(now,due-timedelta(seconds=reduction))
 if spec.get('once_per_target'):session.add(ItemApplication(player_id=player_id,item_key=item_key,target_type=target_type,target_id=target_id))
 _consume_item(session,player_id,item_key)
 return {'target_type':target_type,'target_id':target_id,'completes_at':q.completes_at.isoformat(),'seconds_reduced':min(remaining,reduction)}

def _apply_production_item(session,player_id,item_key,spec,city_id,now):
 from .models import Buff
 city=session.get(City,city_id)
 if not city or city.player_id!=player_id:raise ValueError('city not owned')
 accrue_resources(session,city_id,now)
 group=spec['stack_group']
 for b in session.scalars(select(Buff).where(Buff.player_id==player_id)).all():
  ex=b.expires_at if b.expires_at.tzinfo else b.expires_at.replace(tzinfo=timezone.utc);md=b.metadata_json or {}
  if ex>now and md.get('stack_group')==group and int(md.get('city_id',-1))==city_id:raise ValueError('a production item for this resource is already active in this city')
 eff=spec['effect'];ex=now+timedelta(seconds=eff['duration_seconds'])
 session.add(Buff(player_id=player_id,buff_key=item_key,starts_at=now,expires_at=ex,metadata_json={'city_id':city_id,'stack_group':group}))
 _consume_item(session,player_id,item_key);return {'buff_key':item_key,'city_id':city_id,'expires_at':ex.isoformat()}

AGE1_STATES={
 'Friesland':(0,199,0,199),'Saxony':(200,399,0,199),'North March':(400,599,0,199),'Bohemia':(600,799,0,199),
 'Lower Lorraine':(0,199,200,399),'Franconia':(200,399,200,399),'Thuringia':(400,599,200,399),'Moravia':(600,799,200,399),
 'Upper Lorraine':(0,199,400,599),'Swabia':(200,399,400,599),'Bavaria':(400,599,400,599),'Carinthia':(600,799,400,599),
 'Burgundy':(0,199,600,799),'Lombardy':(200,399,600,799),'Tuscany':(400,599,600,799),'Romagna':(600,799,600,799)}
def age1_state_at(x,y):
 for name,(x0,x1,y0,y1) in AGE1_STATES.items():
  if x0<=x<=x1 and y0<=y<=y1:return name
 return None

def _teleport_city(session,player_id,city_id,x=None,y=None,state_name=None,now=None):
 from .models import MapTile,CityCoordinate,March,Valley,Flat,Buff,ForeignGarrison
 from sqlalchemy import update
 now=now or datetime.now(timezone.utc);c=session.get(City,city_id)
 if not c or c.player_id!=player_id:raise ValueError('city not owned')
 # Both historical teleporters require all of this city's dispatched troops home and no foreign garrison stationed there.
 if session.scalar(select(March).where(March.source_city_id==city_id,March.status.in_(ACTIVE_MARCH_STATUSES))):raise ValueError('all dispatched troops must be home before teleporting')
 if session.scalar(select(ForeignGarrison).where(ForeignGarrison.host_city_id==city_id,ForeignGarrison.status=='GARRISONED')):raise ValueError('garrisoned allied troops must be recalled before teleporting')
 # An Advanced Teleporter's post-use 24h restriction also prevents teleporting away during the restriction.
 for lock in session.scalars(select(Buff).where(Buff.player_id==player_id,Buff.buff_key=='advanced_teleport_march_lock')).all():
  ex=lock.expires_at if lock.expires_at.tzinfo else lock.expires_at.replace(tzinfo=timezone.utc)
  if ex>now and int((lock.metadata_json or {}).get('city_id',-1))==city_id:raise ValueError('advanced teleport 24-hour restriction active')
 old_x,old_y=c.x,c.y
 if x is None:
  if state_name not in AGE1_STATES:raise ValueError('City Teleporter requires a valid Age I state')
  x0,x1,y0,y1=AGE1_STATES[state_name]
  # Choose among currently legal Flat tiles in the selected state. The exact server RNG is not reconstructed;
  # this deterministic selection is isolated and does not alter legality or permit non-Flats.
  flats=session.scalars(select(MapTile).where(MapTile.x>=x0,MapTile.x<=x1,MapTile.y>=y0,MapTile.y<=y1,MapTile.tile_type=='FLAT',MapTile.owner_player_id.is_(None)).order_by(MapTile.id)).all()
  if not flats:raise ValueError('no unoccupied Flat is available in the selected state')
  tile=flats[(city_id+int(now.timestamp()))%len(flats)];x,y=tile.x,tile.y
 else:
  x=int(x);y=int(y)
  if not(0<=x<800 and 0<=y<800):raise ValueError('coordinates out of bounds')
  tile=session.scalar(select(MapTile).where(MapTile.x==x,MapTile.y==y))
  if not tile or tile.tile_type!='FLAT' or tile.owner_player_id is not None:raise ValueError('Advanced City Teleporter destination must be an unoccupied Flat')
 if (x,y)==(old_x,old_y):raise ValueError('destination is current city location')
 # Atomic compare-and-swap claim. A concurrent teleport/founding cannot claim the same coordinate.
 claimed=session.execute(update(MapTile).where(MapTile.id==tile.id,MapTile.tile_type=='FLAT',MapTile.owner_player_id.is_(None)).values(tile_type='PLAYER_CITY',owner_player_id=player_id))
 if claimed.rowcount!=1:raise ValueError('destination was occupied concurrently')
 old=session.scalar(select(MapTile).where(MapTile.x==old_x,MapTile.y==old_y))
 if not old or old.tile_type!='PLAYER_CITY':raise ValueError('current city world tile missing')
 # Incoming marches remain coordinate-targeted. After the move they continue toward the old coordinate rather than following the city.
 incoming=session.scalars(select(March).where(March.target_x==old_x,March.target_y==old_y,March.status.in_(('MARCHING','ARRIVED_PENDING_RESOLUTION')))).all()
 # Teleportation drops all valleys/flats held by this city; city fields/buildings/queues stay with the city.
 for v in session.scalars(select(Valley).where(Valley.city_id==city_id)).all():
  v.city_id=None;vt=session.get(MapTile,v.map_tile_id);vt.owner_player_id=None
 for f in session.scalars(select(Flat).where(Flat.city_id==city_id)).all():
  f.city_id=None;ft=session.get(MapTile,f.map_tile_id);ft.owner_player_id=None
 old.tile_type='FLAT';old.owner_player_id=None
 c.x=x;c.y=y;coord=session.scalar(select(CityCoordinate).where(CityCoordinate.city_id==city_id))
 if coord:coord.x=x;coord.y=y
 else:session.add(CityCoordinate(city_id=city_id,x=x,y=y))
 session.flush()
 return {'city_id':city_id,'old_x':old_x,'old_y':old_y,'x':x,'y':y,'state':age1_state_at(x,y),
         'incoming_march_ids_continuing_to_old_coordinate':[m.id for m in incoming],
         'bookmarks':'UNCHANGED_COORDINATE_BOOKMARKS','valleys_released':True}

def use_inventory_item(session,player_id,item_key,target,idempotency_key):
 if item_key not in ITEM_DEFINITIONS:raise ValueError('unknown item')
 spec=ITEM_DEFINITIONS[item_key]
 if not spec.get('usable_directly',True):raise ValueError('item is consumed by its associated game mechanic, not directly')
 target=target or {}
 typ=spec['effect']['type']
 if typ in ('hero_xp','hero_attribute_buff'):
  return apply_hero_item(session,player_id,int(target.get('city_id',0)),int(target.get('hero_id',0)),item_key,idempotency_key)
 if typ=='hero_redistribute':
  return redistribute_hero(session,player_id,int(target.get('city_id',0)),int(target.get('hero_id',0)),idempotency_key)
 if typ=='instant_demolition_no_refund':
  return dynamite_building(session,player_id,int(target.get('city_id',0)),int(target.get('building_id',0)),idempotency_key)
 def work():
  now=datetime.now(timezone.utc);eff=spec['effect'];typ=eff['type']
  if typ.startswith('queue_reduce_'):return {'item_key':item_key,**_apply_queue_speedup(session,player_id,item_key,spec,target.get('type'),int(target.get('id',0)),now)}
  if typ=='production':return {'item_key':item_key,**_apply_production_item(session,player_id,item_key,spec,int(target.get('city_id',0)),now)}
  if typ=='population_add':
   city_id=int(target.get('city_id',0));c=session.get(City,city_id)
   if not c or c.player_id!=player_id:raise ValueError('city not owned')
   pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id));add=max(eff['minimum'],int(pop.population_limit*eff['percent_limit']/100));before=pop.population;pop.population=min(pop.population_limit,pop.population+add);c.population=pop.population
   if pop.population==before:raise ValueError('population already at limit')
   _consume_item(session,player_id,item_key);return {'item_key':item_key,'city_id':city_id,'population_added':pop.population-before}
  if typ=='loyalty_grievance':
   city_id=int(target.get('city_id',0));c=session.get(City,city_id)
   if not c or c.player_id!=player_id:raise ValueError('city not owned')
   eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id));c.loyalty=eff['loyalty'];c.grievance=eff['grievance'];eco.loyalty=eff['loyalty'];eco.grievance=eff['grievance'];_consume_item(session,player_id,item_key);return {'item_key':item_key,'city_id':city_id,'loyalty':100,'grievance':0}
  if typ in ('random_teleport','specific_teleport'):
   city_id=int(target.get('city_id',0));out=_teleport_city(session,player_id,city_id,target.get('x') if typ=='specific_teleport' else None,target.get('y') if typ=='specific_teleport' else None,target.get('state') if typ=='random_teleport' else None,now)
   if typ=='specific_teleport':
    from .models import Buff
    session.add(Buff(player_id=player_id,buff_key='advanced_teleport_march_lock',starts_at=now,expires_at=now+timedelta(hours=24),metadata_json={'city_id':city_id,'stack_group':'teleport_march_lock'}))
   _consume_item(session,player_id,item_key);return {'item_key':item_key,**out,'march_lock_expires_at':(now+timedelta(hours=24)).isoformat() if typ=='specific_teleport' else None}
  if typ=='inn_refresh':raise ValueError('HISTORICAL_VALUE_UNKNOWN: exact Inn candidate generation is unresolved, so Hero Hunting cannot fabricate a roster')
  raise ValueError('item effect not directly implemented')
 return idempotent_operation(session,player_id,idempotency_key,'USE_ITEM_'+item_key,work)
TOWN_HALL_ACTION_COOLDOWN_SECONDS=900
COMFORT_RULES={'disaster_relief':{'cost_kind':'food','cost_factor':1.0,'loyalty':5,'grievance':-15},'praying':{'cost_kind':'gold','cost_factor':1.0,'loyalty':25,'grievance':-5},'blessing':{'cost_kind':'gold','cost_factor':0.1,'food_factor':10.0},'population_raising':{'cost_kind':'food','cost_factor':5.0,'population_factor':0.05}}
LEVY_RULES={'gold':0.10,'food':1.0,'lumber':1.0,'stone':0.50,'iron':0.40}
def _town_hall_action_cooldown(session,player_id,city_id,group,now):
 from .models import OperationRequest
 prefix=f'townhall:{city_id}:{group}:'
 rows=session.scalars(select(OperationRequest).where(OperationRequest.player_id==player_id,OperationRequest.operation.like(prefix+'%')).order_by(OperationRequest.created_at.desc(),OperationRequest.id.desc())).all()
 # idempotent_operation inserts the current marker before executing this rule; ignore that marker.
 if len(rows)<=1:return 0
 t=rows[1].created_at
 if t.tzinfo is None:t=t.replace(tzinfo=timezone.utc)
 return max(0,int(TOWN_HALL_ACTION_COOLDOWN_SECONDS-(now-t).total_seconds()))
def town_hall_comfort(session,player_id,city_id,action,idempotency_key):
 action=str(action).lower()
 if action not in COMFORT_RULES:raise ValueError('invalid comforting action')
 def work():
  now=datetime.now(timezone.utc);settle_economy(session,city_id,now);c=session.get(City,city_id)
  if not c or c.player_id!=player_id:raise ValueError('city not owned')
  wait=_town_hall_action_cooldown(session,player_id,city_id,'comfort',now)
  if wait:raise ValueError(f'Comforting cooldown active ({wait}s remaining)')
  eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id));pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id));limit=int(pop.population_limit);rule=COMFORT_RULES[action];cost=int(limit*rule.get('cost_factor',0));kind=rule['cost_kind']
  if kind=='gold':
   if eco.gold<cost:raise ValueError('insufficient gold')
   eco.gold-=cost;c.gold=eco.gold
  else:spend_resources(session,city_id,{kind:cost})
  if 'loyalty' in rule:eco.loyalty=max(0,min(100,eco.loyalty+rule['loyalty']))
  if 'grievance' in rule:eco.grievance=max(0,min(100,eco.grievance+rule['grievance']))
  if 'food_factor' in rule:
   row=session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind=='food'));row.quantity+=int(limit*rule['food_factor'])
  if 'population_factor' in rule:pop.population=min(limit,pop.population+int(limit*rule['population_factor']))
  c.loyalty=eco.loyalty;c.grievance=eco.grievance;c.population=pop.population
  return {'action':action,'cost':{'kind':kind,'amount':cost},'loyalty':eco.loyalty,'grievance':eco.grievance,'population':pop.population,'cooldown_seconds':900}
 return idempotent_operation(session,player_id,idempotency_key,f'townhall:{city_id}:comfort:{action}',work)
def town_hall_levy(session,player_id,city_id,resource_kind,idempotency_key):
 resource_kind=str(resource_kind).lower()
 if resource_kind not in LEVY_RULES:raise ValueError('invalid levy resource')
 def work():
  now=datetime.now(timezone.utc);settle_economy(session,city_id,now);c=session.get(City,city_id)
  if not c or c.player_id!=player_id:raise ValueError('city not owned')
  wait=_town_hall_action_cooldown(session,player_id,city_id,'levy',now)
  if wait:raise ValueError(f'Levy cooldown active ({wait}s remaining)')
  eco=session.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id));pop=session.scalar(select(PopulationState).where(PopulationState.city_id==city_id));amount=int(pop.population*LEVY_RULES[resource_kind])
  if resource_kind=='gold':eco.gold+=amount;c.gold=eco.gold
  else:
   row=session.scalar(select(Resource).where(Resource.city_id==city_id,Resource.kind==resource_kind))
   if not row:row=Resource(city_id=city_id,kind=resource_kind,quantity=0);session.add(row)
   row.quantity+=amount
  eco.loyalty=max(0,eco.loyalty-20);c.loyalty=eco.loyalty
  return {'resource':resource_kind,'amount':amount,'loyalty':eco.loyalty,'cooldown_seconds':900}
 return idempotent_operation(session,player_id,idempotency_key,f'townhall:{city_id}:levy:{resource_kind}',work)


