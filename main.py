from pathlib import Path
import os
from datetime import datetime,timezone
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, SessionLocal
from .seed import seed
from .models import (
    Player, City, CityCoordinate, Resource, ResourceProduction, ResourceCapacity,
    PopulationState, CityEconomyState, PlayerProgression, CityBuildingPlot,
    ExteriorFieldPlot, Building, BuildingLevel, ConstructionQueue, ResearchQueue,
    TrainingQueue, March, MapTile, NPCCity, Valley, Flat
)

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
from .service import alliance_detail,create_alliance,update_alliance_information,invite_to_alliance,alliance_invitations,respond_alliance_invitation,reject_alliance_application,change_alliance_rank,expel_alliance_member,leave_alliance,transfer_alliance_host,set_alliance_relation,alliance_chat,send_alliance_chat,send_alliance_mail
from .service import send_chat_message,chat_messages,set_chat_block,set_chat_mute
from .service import quest_list,claim_quest
from .service import progression_status,promote_player
from .service import player_cities_overview,city_independence_snapshot,build_city_on_flat,abandon_city_to_npc
from .service import inventory_snapshot,use_inventory_item
from .service import beginner_protection_status
from .service import town_hall_comfort,town_hall_levy
app = FastAPI(title="Age 1 Fidelity Server", version="0.2.0")
app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    seed()

def db():
    s = SessionLocal()
    try: yield s
    finally: s.close()

def city_payload(s: Session, city: City):
    from .service import settle_economy, population_breakdown, troop_food_upkeep
    econ_snapshot=settle_economy(s,city.id)
    pop_breakdown=population_breakdown(s,city.id)
    upkeep=troop_food_upkeep(s,city.id)
    coord = s.scalar(select(CityCoordinate).where(CityCoordinate.city_id == city.id))
    pop = s.scalar(select(PopulationState).where(PopulationState.city_id == city.id))
    eco = s.scalar(select(CityEconomyState).where(CityEconomyState.city_id == city.id))
    resources = s.scalars(select(Resource).where(Resource.city_id == city.id).order_by(Resource.kind)).all()
    prod = {x.resource_kind: x for x in s.scalars(select(ResourceProduction).where(ResourceProduction.city_id == city.id)).all()}
    caps = {x.resource_kind: x for x in s.scalars(select(ResourceCapacity).where(ResourceCapacity.city_id == city.id)).all()}
    return {
        "id": city.id, "name": city.name,
        "coordinates": {"x": coord.x if coord else city.x, "y": coord.y if coord else city.y},
        "resources": [{"kind": r.kind, "quantity": r.quantity,
                       "production_per_hour": ((prod.get(r.kind).per_hour if r.kind in prod else r.production_per_hour) - upkeep["total_per_hour"] if r.kind=="food" else (prod.get(r.kind).per_hour if r.kind in prod else r.production_per_hour)),
                       "gross_production_per_hour": prod.get(r.kind).per_hour if r.kind in prod else r.production_per_hour,
                       "capacity": caps.get(r.kind).capacity if r.kind in caps else r.capacity}
                      for r in resources],
        "population": {"total": pop_breakdown["population"], "idle": pop_breakdown["idle_population"], "limit": pop_breakdown["population_limit"]},
        "economy": {"gold": eco.gold if eco else city.gold, "tax_rate": eco.tax_rate if eco else city.tax_rate,
                    "loyalty": eco.loyalty if eco else city.loyalty, "grievance": eco.grievance if eco else city.grievance,
                    "public_sentiment": eco.public_sentiment if eco else city.public_sentiment},
    }

def queue_payload(s: Session, player_id: int, city_id: int):
    construction = s.scalars(select(ConstructionQueue).where(ConstructionQueue.city_id == city_id, ConstructionQueue.status == "ACTIVE")).all()
    research = s.scalars(select(ResearchQueue).where(ResearchQueue.player_id == player_id, ResearchQueue.status == "ACTIVE")).all()
    training = s.scalars(select(TrainingQueue).where(TrainingQueue.city_id == city_id, TrainingQueue.status == "ACTIVE")).all()
    marches = s.scalars(select(March).join(City, March.source_city_id == City.id).where(City.player_id == player_id, March.status != "COMPLETE")).all()
    return {
        "construction": [{"id": q.id, "target_level": q.target_level, "started_at": q.started_at, "completes_at": q.completes_at, "status": q.status} for q in construction],
        "research": [{"id": q.id, "technology_key": q.technology_key, "target_level": q.target_level, "started_at": q.started_at, "completes_at": q.completes_at, "status": q.status} for q in research],
        "training": [{"id": q.id, "troop_type_key": q.troop_type_key, "quantity": q.quantity, "started_at": q.started_at, "completes_at": q.completes_at, "status": q.status} for q in training],
        "marches": [{"id": q.id, "mission": q.mission, "target": {"x": q.target_x, "y": q.target_y}, "arrives_at": q.arrives_at, "returns_at": q.returns_at, "status": q.status} for q in marches],
    }

@app.get("/health")
def health(): return {"ok": True, "authority": "server"}

@app.get("/api/development/session")
def development_session(s: Session = Depends(db)):
    player = s.scalar(select(Player).order_by(Player.id))
    if not player: raise HTTPException(404, "No seeded player")
    cities = s.scalars(select(City).where(City.player_id == player.id).order_by(City.id)).all()
    current = cities[0]
    prog = s.scalar(select(PlayerProgression).where(PlayerProgression.player_id == player.id))
    return {"player": {"id": player.id, "name": player.name,
                       "prestige": prog.prestige if prog else player.prestige,
                       "honor": prog.honor if prog else player.honor,
                       "title_rank_key": prog.title_rank_key if prog else player.title_rank_key},
            "cities": [{"id": c.id, "name": c.name, "x": c.x, "y": c.y} for c in cities],
            "current_city": city_payload(s, current), "activity": queue_payload(s, player.id, current.id)}

@app.get("/api/players/{player_id}/cities/{city_id}/overview")
def overview(player_id: int, city_id: int, s: Session = Depends(db)):
    city = s.get(City, city_id)
    if not city or city.player_id != player_id: raise HTTPException(404, "City not found for player")
    prog = s.scalar(select(PlayerProgression).where(PlayerProgression.player_id == player_id))
    player = s.get(Player, player_id)
    return {"player": {"id": player.id, "name": player.name,
                       "prestige": prog.prestige if prog else player.prestige,
                       "honor": prog.honor if prog else player.honor,
                       "title_rank_key": prog.title_rank_key if prog else player.title_rank_key},
            "city": city_payload(s, city), "activity": queue_payload(s, player_id, city_id)}

@app.get("/api/players/{player_id}/cities/{city_id}/city-view")
def city_view(player_id: int, city_id: int, s: Session = Depends(db)):
    complete_construction(s, city_id)
    city = s.get(City, city_id)
    if not city or city.player_id != player_id: raise HTTPException(404, "City not found")
    plots = s.scalars(select(CityBuildingPlot).where(CityBuildingPlot.city_id == city_id).order_by(CityBuildingPlot.plot_index)).all()
    buildings = {b.plot_index: b for b in s.scalars(select(Building).where(Building.city_id == city_id, Building.plot_kind == "CITY")).all()}
    levels = {x.building_id: x.level for x in s.scalars(select(BuildingLevel).join(Building, BuildingLevel.building_id == Building.id).where(Building.city_id == city_id)).all()}
    return {"city": city_payload(s, city), "plots": [{"plot_index": p.plot_index, "building": None if p.plot_index not in buildings else {"id": buildings[p.plot_index].id, "definition_key": buildings[p.plot_index].definition_key, "level": levels.get(buildings[p.plot_index].id, buildings[p.plot_index].level), "dedicated": p.plot_index in (0,33)}} for p in plots]}

@app.get("/api/players/{player_id}/cities/{city_id}/field-view")
def field_view(player_id: int, city_id: int, s: Session = Depends(db)):
    from .service import sync_exterior_field_unlocks,accrue_resources,resource_production_snapshot
    complete_construction(s, city_id);accrue_resources(s,city_id)
    city = s.get(City, city_id)
    if not city or city.player_id != player_id: raise HTTPException(404, "City not found")
    allowed = sync_exterior_field_unlocks(s, city_id); s.commit()
    existing={p.plot_index:p for p in s.scalars(select(ExteriorFieldPlot).where(ExteriorFieldPlot.city_id==city_id)).all()}
    buildings = {b.plot_index: b for b in s.scalars(select(Building).where(Building.city_id == city_id, Building.plot_kind == "FIELD")).all()}
    levels = {x.building_id: x.level for x in s.scalars(select(BuildingLevel).join(Building, BuildingLevel.building_id == Building.id).where(Building.city_id == city_id)).all()}
    snap=resource_production_snapshot(s,city_id)
    plots=[]
    for idx in range(1,38):
      b=buildings.get(idx);plots.append({'plot_index':idx,'locked':idx>allowed,'building':None if not b else {'id':b.id,'definition_key':b.definition_key,'level':levels.get(b.id,b.level)}})
    
    from .models import PlayerItem,Buff
    now=datetime.now(timezone.utc)
    inventory={x.item_key:x.quantity for x in s.scalars(select(PlayerItem).where(PlayerItem.player_id==player_id)).all()}
    active=[]
    for b in s.scalars(select(Buff).where(Buff.player_id==player_id,Buff.expires_at>now)).all():
      if any(b.buff_key in v for v in DATA['resource_production']['production_items'].values()):active.append({'item_key':b.buff_key,'expires_at':b.expires_at,'metadata':b.metadata_json})
    return {"city": city_payload(s, city), "town_hall_level":current_level(s,town_hall_building(s,city_id)),"available_plots":allowed,"maximum_normal_plots":37,"plots":[x for x in plots if not x['locked']],"locked_plots":[x for x in plots if x['locked']],"production":snap,"production_items":DATA['resource_production']['production_items'],"inventory":inventory,"active_production_buffs":active}


from .service import map_viewport,map_tile_payload,player_bookmarks,add_bookmark,delete_bookmark
@app.get("/api/map")
def map_view(center_x:int,center_y:int,radius:int=6,player_id:int|None=None,s:Session=Depends(db)):
 try:return map_viewport(s,player_id,center_x,center_y,radius)
 except ValueError as e:raise HTTPException(400,str(e))

@app.get("/api/map/tile/{x}/{y}")
def map_tile(x:int,y:int,player_id:int|None=None,s:Session=Depends(db)):
 try:return map_tile_payload(s,x,y,player_id)
 except ValueError as e:raise HTTPException(400,str(e))


@app.get("/")
def index(): return FileResponse(WEB / "index.html")

from pydantic import BaseModel
from .definitions import DATA
from .service import construction_options, start_construction, start_upgrade, complete_construction
from .models import Hero, TroopQuantity

class BuildRequest(BaseModel):
 plot_index:int; building_key:str; idempotency_key:str
class UpgradeRequest(BaseModel): idempotency_key:str

@app.get('/api/players/{player_id}/cities/{city_id}/construction-options')
def get_construction_options(player_id:int,city_id:int,s:Session=Depends(db)):
 city=s.get(City,city_id)
 if not city or city.player_id!=player_id: raise HTTPException(404,'City not found')
 return {'options':construction_options(s,city_id)}

@app.post('/api/players/{player_id}/cities/{city_id}/construct')
def construct(player_id:int,city_id:int,req:BuildRequest,s:Session=Depends(db)):
 try: return start_construction(s,player_id,city_id,req.plot_index,req.building_key,req.idempotency_key)
 except ValueError as e: raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/buildings/{building_id}/upgrade')
def upgrade(player_id:int,city_id:int,building_id:int,req:UpgradeRequest,s:Session=Depends(db)):
 try: return start_upgrade(s,player_id,city_id,building_id,req.idempotency_key)
 except ValueError as e: raise HTTPException(409,str(e))

@app.get('/api/players/{player_id}/cities/{city_id}/buildings/{building_id}')
def building_interface(player_id:int,city_id:int,building_id:int,s:Session=Depends(db)):
 city=s.get(City,city_id); complete_construction(s,city_id); b=s.get(Building,building_id)
 if not city or city.player_id!=player_id or not b or b.city_id!=city_id: raise HTTPException(404,'Building not found')
 lv=s.scalar(select(BuildingLevel).where(BuildingLevel.building_id==b.id)); level=lv.level if lv else b.level; d=DATA['buildings'].get(b.definition_key,{})
 payload={'id':b.id,'definition_key':b.definition_key,'name':d.get('name',b.definition_key),'purpose':d.get('purpose',''),'level':level,'interface_type':b.definition_key,'upgrade':None,'demolition':{'labor':'Available through authoritative demolition endpoint','dynamite':'UNFINISHED: item consumption flow not implemented'}}
 nxt=DATA['building_levels'].get(b.definition_key,{}).get(str(level+1)); payload['upgrade']=nxt if nxt else 'HISTORICAL_VALUE_UNKNOWN'
 if b.definition_key=='cottage':
  from .service import sync_population_capacity
  limit=sync_population_capacity(s,city_id); s.commit(); pop=s.scalar(select(PopulationState).where(PopulationState.city_id==city_id)); payload['function']={'type':'population','population_limit':limit,'population':pop.population if pop else 0,'idle_population':pop.idle_population if pop else 0,'capacity_source':'sum of all completed Cottage levels in this city'}
 elif b.definition_key=='barracks':
  troops=s.scalars(select(TroopQuantity).where(TroopQuantity.city_id==city_id)).all(); payload['function']={'type':'training','troops':[{'type':x.troop_type_key,'quantity':x.quantity} for x in troops],'training':'Available through this Barracks dedicated interface'}
 elif b.definition_key=='inn':
  heroes=s.scalars(select(Hero).where(Hero.city_id==city_id)).all(); payload['function']={'type':'hero_recruitment','endpoint':f'/api/players/{player_id}/cities/{city_id}/inn','city_heroes':[{'id':h.id,'name':h.name} for h in heroes],'recruitment':'IMPLEMENTED where historically verified; exact candidate RNG remains HISTORICAL_VALUE_UNKNOWN'}
 elif b.definition_key=='warehouse':
  from .service import warehouse_base_capacity,warehouse_effective_capacity,warehouse_allocation,warehouse_protected_amounts
  a=warehouse_allocation(s,city_id); s.commit(); payload['function']={'type':'protected_storage','base_capacity':warehouse_base_capacity(s,city_id),'effective_capacity':warehouse_effective_capacity(s,city_id),'allocation':{'food':a.food_percent,'lumber':a.lumber_percent,'stone':a.stone_percent,'iron':a.iron_percent},'protected':warehouse_protected_amounts(s,city_id),'gold_protected':0,'status':'IMPLEMENTED'}
 elif b.definition_key=='marketplace': payload['function']={'type':'market','status':'Available through Marketplace dedicated interface'}
 elif b.definition_key=='rally_spot': payload['function']={'type':'military','status':'Available through Rally Spot dedicated interface'}
 elif b.definition_key=='town_hall': payload['function']={'type':'administration','status':'Available through Town Hall dedicated interface'}
 elif b.definition_key=='walls': payload['function']={'type':'fortification','status':'IMPLEMENTED: use dedicated Walls interface'}
 else: payload['function']={'type':b.definition_key,'status':'Use the building-specific interface when available; no generic client-side mechanic is substituted.'}
 return payload

from .models import PlayerSetting, PlayerItem, Technology
from .definitions import town_hall_level
from .service import town_hall_building, sync_exterior_field_unlocks, start_town_hall_upgrade, set_tax_rate, rename_city, set_production_rates, current_level

class TaxRequest(BaseModel):
 tax_rate:int; idempotency_key:str
class RenameCityRequest(BaseModel):
 name:str; idempotency_key:str
class ProductionRequest(BaseModel):
 food:int; lumber:int; stone:int; iron:int; idempotency_key:str

@app.get('/api/players/{player_id}/cities/{city_id}/town-hall')
def town_hall_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 complete_construction(s,city_id)
 city=s.get(City,city_id)
 if not city or city.player_id!=player_id: raise HTTPException(404,'City not found')
 th=town_hall_building(s,city_id)
 if not th: raise HTTPException(500,'Dedicated Town Hall missing')
 level=current_level(s,th); spec=town_hall_level(level); nxt=town_hall_level(level+1)
 allowed=sync_exterior_field_unlocks(s,city_id); s.commit()
 pop=s.scalar(select(PopulationState).where(PopulationState.city_id==city_id)); eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==city_id))
 key=f'city:{city_id}:production_rates'; setting=s.scalar(select(PlayerSetting).where(PlayerSetting.player_id==player_id,PlayerSetting.key==key)); rates=setting.value if setting else {'food':100,'lumber':100,'stone':100,'iron':100}
 q=s.scalar(select(ConstructionQueue).where(ConstructionQueue.city_id==city_id,ConstructionQueue.building_id==th.id,ConstructionQueue.status=='ACTIVE'))
 return {'id':th.id,'name':'Town Hall','level':level,'permanent_dedicated':True,
  'resource_fields':{'available':allowed,'progression':[town_hall_level(x)['resource_fields'] for x in range(1,11)]},
  'valley_limit':spec['valley_limit'],'population':{'limit':pop.population_limit if pop else 0,'total':pop.population if pop else city.population,'idle':pop.idle_population if pop else city.idle_population},
  'public_state':{'tax_rate':eco.tax_rate if eco else city.tax_rate,'loyalty':eco.loyalty if eco else city.loyalty,'grievance':eco.grievance if eco else city.grievance,'public_sentiment':eco.public_sentiment if eco else city.public_sentiment,'gold':eco.gold if eco else city.gold},
  'production_rates':rates,
  'upgrade':None if not nxt else {'target_level':level+1,'cost':nxt['cost'],'seconds':nxt['seconds'],'prerequisites':nxt['prerequisites'],'item_cost':nxt.get('item_cost',{}),'can_start':nxt['prerequisites']!='HISTORICAL_VALUE_UNKNOWN'},
  'active_upgrade':None if not q else {'target_level':q.target_level,'started_at':q.started_at,'completes_at':q.completes_at},
  'actions':{'tax_rate':'IMPLEMENTED','rename_city':'IMPLEMENTED','production_controls':'IMPLEMENTED: authoritative elapsed-time resource production','comforting':'IMPLEMENTED','levy':'IMPLEMENTED'}}

@app.post('/api/players/{player_id}/cities/{city_id}/town-hall/upgrade')
def upgrade_town_hall(player_id:int,city_id:int,req:UpgradeRequest,s:Session=Depends(db)):
 try:return start_town_hall_upgrade(s,player_id,city_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/town-hall/tax')
def town_hall_tax(player_id:int,city_id:int,req:TaxRequest,s:Session=Depends(db)):
 try:return set_tax_rate(s,player_id,city_id,req.tax_rate,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/town-hall/rename')
def town_hall_rename(player_id:int,city_id:int,req:RenameCityRequest,s:Session=Depends(db)):
 try:return rename_city(s,player_id,city_id,req.name,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/town-hall/production')
def town_hall_production(player_id:int,city_id:int,req:ProductionRequest,s:Session=Depends(db)):
 try:return set_production_rates(s,player_id,city_id,{'food':req.food,'lumber':req.lumber,'stone':req.stone,'iron':req.iron},req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .service import warehouse_base_capacity,warehouse_effective_capacity,warehouse_allocation,warehouse_protected_amounts,set_warehouse_allocation
class WarehouseAllocationRequest(BaseModel):
 food:int; lumber:int; stone:int; iron:int; idempotency_key:str

@app.get('/api/players/{player_id}/cities/{city_id}/warehouse')
def warehouse_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 complete_construction(s,city_id); city=s.get(City,city_id)
 if not city or city.player_id!=player_id: raise HTTPException(404,'City not found')
 a=warehouse_allocation(s,city_id); s.commit()
 stock=s.scalar(select(Technology).where(Technology.player_id==player_id,Technology.definition_key=='stockpile'))
 return {'base_capacity':warehouse_base_capacity(s,city_id),'effective_capacity':warehouse_effective_capacity(s,city_id),'stockpile_level':stock.level if stock else 0,'allocation':{'food':a.food_percent,'lumber':a.lumber_percent,'stone':a.stone_percent,'iron':a.iron_percent},'protected_without_privateering':warehouse_protected_amounts(s,city_id),'gold_protected':0,'rules':{'multiple_warehouses':'IMPLEMENTED','stockpile':'10% capacity per level','privateering':'attacker reduces effective protection 3 percentage points per level','gold':'never protected'}}

@app.post('/api/players/{player_id}/cities/{city_id}/warehouse/allocation')
def warehouse_set_allocation(player_id:int,city_id:int,req:WarehouseAllocationRequest,s:Session=Depends(db)):
 city=s.get(City,city_id)
 if not city or city.player_id!=player_id: raise HTTPException(404,'City not found')
 try:return set_warehouse_allocation(s,player_id,city_id,{'food':req.food,'lumber':req.lumber,'stone':req.stone,'iron':req.iron},req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .models import InnCandidate
from .service import inn_candidates,inn_candidate_capacity,feasting_hall_capacity,recruit_inn_candidate,refresh_inn_candidates
class RecruitHeroRequest(BaseModel): idempotency_key:str
class RefreshInnRequest(BaseModel): idempotency_key:str; use_hero_hunting:bool=False

@app.get('/api/players/{player_id}/cities/{city_id}/inn')
def inn_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 city=s.get(City,city_id)
 if not city or city.player_id!=player_id: raise HTTPException(404,'City not found')
 complete_construction(s,city_id)
 inn_level=inn_candidate_capacity(s,city_id); fh=feasting_hall_capacity(s,city_id); candidates=inn_candidates(s,city_id)
 heroes=s.scalars(select(Hero).where(Hero.city_id==city_id)).all()
 return {'building':'Inn','level':inn_level,'candidate_capacity':inn_level,'automatic_refresh_seconds':3600,'candidate_generation_formula':'HISTORICAL_VALUE_UNKNOWN','feasting_hall':{'level':fh,'capacity':fh,'occupied':len(heroes),'vacancies':max(0,fh-len(heroes))},'candidates':[{'id':c.id,'slot':c.slot_index,'name':c.name,'level':c.level,'politics':c.politics,'attack':c.attack,'intelligence':c.intelligence,'loyalty':c.loyalty,'employment_fee':c.level*1000,'generated_at':c.generated_at,'refreshes_at':c.refreshes_at,'generation_source':c.generation_source} for c in candidates], 'refresh':{'automatic':'hourly','hero_hunting':'verified item-triggered immediate refresh','status':'UNFINISHED: exact candidate RNG HISTORICAL_VALUE_UNKNOWN'}}

@app.post('/api/players/{player_id}/cities/{city_id}/inn/candidates/{candidate_id}/recruit')
def recruit_candidate(player_id:int,city_id:int,candidate_id:int,req:RecruitHeroRequest,s:Session=Depends(db)):
 try:return recruit_inn_candidate(s,player_id,city_id,candidate_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/inn/refresh')
def refresh_inn(player_id:int,city_id:int,req:RefreshInnRequest,s:Session=Depends(db)):
 try:return refresh_inn_candidates(s,player_id,city_id,req.idempotency_key,req.use_hero_hunting)
 except ValueError as e:raise HTTPException(409,str(e))


from .service import feasting_hall_roster,appoint_mayor,remove_mayor,dismiss_hero,release_captured_hero,mayor_stats,mayor_production_multiplier
class HeroActionRequest(BaseModel): idempotency_key:str

@app.get('/api/players/{player_id}/cities/{city_id}/feasting-hall')
def feasting_hall_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 city=s.get(City,city_id)
 if not city or city.player_id!=player_id: raise HTTPException(404,'City not found')
 level=feasting_hall_capacity(s,city_id); roster=feasting_hall_roster(s,city_id); ms=mayor_stats(s,city_id)
 return {'building':'Feasting Hall','level':level,'capacity':level,'occupied':len(roster),'vacancies':max(0,level-len(roster)),
 'heroes':roster,'mayor_effects':{'stats':ms,'resource_production_multiplier':mayor_production_multiplier(s,city_id),
 'construction_factor':0.995**ms['politics'],'training_factor':0.995**ms['attack'],'research_factor':0.995**ms['intelligence']},
 'captured_hero':{'vacancy_required':True,'initial_loyalty':0,'persuasion_fee':'hero_level * 1000 gold','title_requirement':'HISTORICAL_VALUE_UNKNOWN'},
 'salary':'20 * hero level gold/hour'}

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/appoint-mayor')
def api_appoint_mayor(player_id:int,city_id:int,hero_id:int,req:HeroActionRequest,s:Session=Depends(db)):
 try:return appoint_mayor(s,player_id,city_id,hero_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/remove-mayor')
def api_remove_mayor(player_id:int,city_id:int,req:HeroActionRequest,s:Session=Depends(db)):
 try:return remove_mayor(s,player_id,city_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/dismiss')
def api_dismiss_hero(player_id:int,city_id:int,hero_id:int,req:HeroActionRequest,s:Session=Depends(db)):
 try:return dismiss_hero(s,player_id,city_id,hero_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/release')
def api_release_hero(player_id:int,city_id:int,hero_id:int,req:HeroActionRequest,s:Session=Depends(db)):
 try:return release_captured_hero(s,player_id,city_id,hero_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))


from .models import Alliance,AllianceMember,AllianceApplication,EmbassyState,ForeignGarrison
from .service import embassy_level,embassy_state,foreign_garrisons,set_embassy_garrison_permission,apply_to_alliance,accept_alliance_application,create_alliance,return_foreign_garrison
class EmbassyPermissionRequest(BaseModel): allow:bool; idempotency_key:str
class AllianceApplyRequest(BaseModel): alliance_id:int; idempotency_key:str
class AllianceCreateRequest(BaseModel): name:str; idempotency_key:str
class AllianceApplicationAction(BaseModel): idempotency_key:str
class GarrisonReturnRequest(BaseModel): idempotency_key:str

@app.get('/api/players/{player_id}/cities/{city_id}/embassy')
def embassy_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 city=s.get(City,city_id)
 if not city or city.player_id!=player_id: raise HTTPException(404,'City not found')
 complete_construction(s,city_id);level=embassy_level(s,city_id);state=embassy_state(s,city_id);membership=s.scalar(select(AllianceMember).where(AllianceMember.player_id==player_id))
 gs=foreign_garrisons(s,city_id)
 return {'building':'Embassy','level':level,'garrison_capacity':level,'garrisoned_waves':len(gs),'allow_allied_garrison':state.allow_allied_garrison,
 'alliance':None if not membership else {'alliance_id':membership.alliance_id,'rank':membership.rank},
 'permissions':{'join_or_apply':level>=1,'create_alliance':level>=2},
 'garrisons':[{'id':g.id,'owner_player_id':g.owner_player_id,'source_city_id':g.source_city_id,'hero_id':g.hero_id,'troops':g.troops,'resources':g.resources,'status':g.status,'defense_only':True} for g in gs],
 'rules':{'host_city_feeds_garrison':True,'foreign_troops_remain_foreign':True,'host_can_send_home':True,'owner_can_recall':True}}

@app.post('/api/players/{player_id}/cities/{city_id}/embassy/garrison-permission')
def embassy_permission(player_id:int,city_id:int,req:EmbassyPermissionRequest,s:Session=Depends(db)):
 try:return set_embassy_garrison_permission(s,player_id,city_id,req.allow,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/embassy/alliance/apply')
def embassy_apply(player_id:int,city_id:int,req:AllianceApplyRequest,s:Session=Depends(db)):
 try:return apply_to_alliance(s,player_id,city_id,req.alliance_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/embassy/alliance/create')
def embassy_create(player_id:int,city_id:int,req:AllianceCreateRequest,s:Session=Depends(db)):
 try:return create_alliance(s,player_id,city_id,req.name,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/embassy/alliance/applications/{application_id}/accept')
def embassy_accept(player_id:int,application_id:int,req:AllianceApplicationAction,s:Session=Depends(db)):
 try:return accept_alliance_application(s,player_id,application_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/embassy/garrisons/{garrison_id}/return')
def embassy_return(player_id:int,city_id:int,garrison_id:int,req:GarrisonReturnRequest,s:Session=Depends(db)):
 try:return return_foreign_garrison(s,player_id,garrison_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .models import MarketOrder,MarketTrade
from .service import marketplace_level,market_orders,place_market_order,cancel_market_order,settle_market_delivery
class MarketOrderRequest(BaseModel): side:str; resource_kind:str; quantity:int; price:float; idempotency_key:str
class MarketCancelRequest(BaseModel): idempotency_key:str
@app.get('/api/players/{player_id}/cities/{city_id}/marketplace')
def marketplace_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 city=s.get(City,city_id)
 if not city or city.player_id!=player_id:raise HTTPException(404,'City not found')
 lv=marketplace_level(s,city_id);orders=market_orders(s,city_id)
 return {'building':'Marketplace','level':lv,'concurrent_capacity':lv,'max_quantity':10000000,'fee_rate':0.005,'resources':['food','lumber','stone','iron'],
 'orders':[{'id':o.id,'side':o.side,'resource':o.resource_kind,'quantity':o.quantity,'remaining':o.remaining_quantity,'price':o.price,'status':o.status} for o in orders]}
@app.post('/api/players/{player_id}/cities/{city_id}/marketplace/orders')
def market_place(player_id:int,city_id:int,req:MarketOrderRequest,s:Session=Depends(db)):
 try:return place_market_order(s,player_id,city_id,req.side,req.resource_kind,req.quantity,req.price,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/marketplace/orders/{order_id}/cancel')
def market_cancel(player_id:int,city_id:int,order_id:int,req:MarketCancelRequest,s:Session=Depends(db)):
 try:return cancel_market_order(s,player_id,order_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .service import TECH_KEYS,academy_level,technology_level,effective_technology_level,complete_research,start_research
class ResearchStartRequest(BaseModel): idempotency_key:str
@app.get('/api/players/{player_id}/cities/{city_id}/academy')
def academy_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 city=s.get(City,city_id)
 if not city or city.player_id!=player_id:raise HTTPException(404,'City not found')
 complete_research(s,city_id);lv=academy_level(s,city_id)
 active=s.scalar(select(ResearchQueue).where(ResearchQueue.city_id==city_id,ResearchQueue.status=='ACTIVE'))
 techs=[]
 for key in TECH_KEYS:
  gl=technology_level(s,player_id,key); eff=effective_technology_level(s,city_id,key); nxt=DATA['technologies'][key]['levels'].get(str(gl+1))
  techs.append({'key':key,'name':DATA['technologies'][key]['name'],'level':gl,'effective_level_in_city':eff,'max_level':10,'next':nxt})
 return {'building':'Academy','level':lv,'research_location':'Academy','active_research':None if not active else {'technology':active.technology_key,'target_level':active.target_level,'completes_at':active.completes_at},'technologies':techs}
@app.post('/api/players/{player_id}/cities/{city_id}/academy/research/{technology_key}')
def academy_start_research(player_id:int,city_id:int,technology_key:str,req:ResearchStartRequest,s:Session=Depends(db)):
 try:return start_research(s,player_id,city_id,technology_key,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .models import Army,RallySpotState,WoundedTroop,Hero,TroopQuantity
from .service import rally_spot_level,rally_limits,rally_preview,create_march,recall_march,complete_returning_marches,rally_open_gates,rally_exercise,process_due_marches,active_marches_for_player,march_payload
class MarchPreviewRequest(BaseModel):
 mission:str; target_x:int; target_y:int; troops:dict[str,int]; resources:dict[str,int]={}; camp_seconds:int=0; war_ensign:bool=False
class MarchCreateRequest(MarchPreviewRequest):
 hero_id:int|None=None; idempotency_key:str
class RecallRequest(BaseModel):idempotency_key:str
class GatesRequest(BaseModel):open_gates:bool;idempotency_key:str
class ExerciseRequest(BaseModel):attacker:dict[str,int];defender:dict[str,int]
@app.get('/api/players/{player_id}/cities/{city_id}/rally-spot')
def rally_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 process_due_marches(s,player_id=player_id);lv=rally_spot_level(s,city_id);limits=rally_limits(s,city_id)
 rs=s.scalar(select(RallySpotState).where(RallySpotState.city_id==city_id))
 troops=s.scalars(select(TroopQuantity).where(TroopQuantity.city_id==city_id)).all()
 heroes=s.scalars(select(Hero).where(Hero.city_id==city_id,Hero.player_id==player_id)).all()
 marches=s.scalars(select(March).where(March.source_city_id==city_id,March.status!='RETURNED').order_by(March.id)).all()
 wounded=s.scalars(select(WoundedTroop).where(WoundedTroop.city_id==city_id)).all()
 return {'building':'Rally Spot','level':lv,**limits,'open_gates':bool(rs and rs.open_gates),'missions':['ATTACK','SCOUT','REINFORCE','TRANSPORT'],
 'troops':{x.troop_type_key:x.quantity for x in troops},
 'heroes':[{'id':h.id,'name':h.name,'level':h.level,'status':h.assignment or 'idle','captured':h.captured} for h in heroes],
 'marches':[march_payload(s,x) for x in marches],
 'medic_camp':{'wounded':{x.troop_type_key:x.quantity for x in wounded},'healing_cost':'HISTORICAL_VALUE_UNKNOWN'},
 'exercise':{'available':True,'authoritative':False,'uses_players_research_for_both_sides':True}}
@app.post('/api/players/{player_id}/cities/{city_id}/rally-spot/preview')
def rally_preview_api(player_id:int,city_id:int,req:MarchPreviewRequest,s:Session=Depends(db)):
 try:return rally_preview(s,player_id,city_id,req.mission,req.target_x,req.target_y,req.troops,req.resources,req.camp_seconds,req.war_ensign)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/rally-spot/marches')
def rally_create_api(player_id:int,city_id:int,req:MarchCreateRequest,s:Session=Depends(db)):
 try:return create_march(s,player_id,city_id,req.mission,req.target_x,req.target_y,req.troops,req.resources,req.hero_id,req.camp_seconds,req.war_ensign,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/rally-spot/marches/{march_id}/recall')
def rally_recall_api(player_id:int,city_id:int,march_id:int,req:RecallRequest,s:Session=Depends(db)):
 try:return recall_march(s,player_id,march_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/rally-spot/open-gates')
def rally_gates_api(player_id:int,city_id:int,req:GatesRequest,s:Session=Depends(db)):
 try:return rally_open_gates(s,player_id,city_id,req.open_gates,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/rally-spot/exercise')
def rally_exercise_api(player_id:int,city_id:int,req:ExerciseRequest,s:Session=Depends(db)):
 return rally_exercise(s,city_id,req.attacker,req.defender)

from .service import BARRACK_TROOPS,barracks_level,barracks_queue,troop_prerequisite_status,train_troops,complete_training
class BarracksTrainRequest(BaseModel):
 quantity:int; idempotency_key:str
@app.get('/api/players/{player_id}/cities/{city_id}/barracks/{barracks_id}')
def barracks_interface(player_id:int,city_id:int,barracks_id:int,s:Session=Depends(db)):
 city=s.get(City,city_id);b=s.get(Building,barracks_id)
 if not city or city.player_id!=player_id or not b or b.city_id!=city_id or b.definition_key!='barracks':raise HTTPException(404,'Barracks not found')
 complete_training(s,city_id,barracks_id);lv=barracks_level(s,barracks_id);q=barracks_queue(s,barracks_id)
 troops=[]
 for key in BARRACK_TROOPS:
  spec=DATA['troop_types'][key];missing=troop_prerequisite_status(s,city_id,barracks_id,key)
  troops.append({'key':key,**spec,'available':not missing,'missing_prerequisites':missing})
 inv=s.scalars(select(TroopQuantity).where(TroopQuantity.city_id==city_id)).all()
 return {'building':'Barracks','barracks_id':barracks_id,'level':lv,'queue_capacity':lv,'queue_used':len(q),'inventory':{x.troop_type_key:x.quantity for x in inv},'queue':[{'id':x.id,'troop_type':x.troop_type_key,'quantity':x.quantity,'status':x.status,'duration_seconds':x.duration_seconds,'started_at':x.started_at,'completes_at':x.completes_at,'hero_attack_snapshot':x.hero_attack_snapshot,'military_science_snapshot':x.military_science_snapshot} for x in q],'troops':troops}
@app.post('/api/players/{player_id}/cities/{city_id}/barracks/{barracks_id}/train/{troop_key}')
def barracks_train(player_id:int,city_id:int,barracks_id:int,troop_key:str,req:BarracksTrainRequest,s:Session=Depends(db)):
 try:return train_troops(s,player_id,city_id,barracks_id,troop_key,req.quantity,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .service import beacon_tower_level,beacon_incoming_alerts
@app.get('/api/players/{player_id}/cities/{city_id}/beacon-tower')
def beacon_tower_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 lv=beacon_tower_level(s,city_id)
 return {'building':'Beacon Tower','level':lv,'level_effect':DATA['building_levels']['beacon_tower'].get(str(lv),{}).get('alert_unlock'),'incoming':beacon_incoming_alerts(s,city_id)}

from .service import forge_level
@app.get('/api/players/{player_id}/cities/{city_id}/forge')
def forge_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 lv=forge_level(s,city_id)
 return {'building':'Forge','level':lv,'military_science_supported_level':lv,'workshop_unlocked':lv>=2,'dependencies':['Military Science level N requires Forge level N','Workshop construction requires Forge level 2']}

from .service import stable_level
@app.get('/api/players/{player_id}/cities/{city_id}/stable')
def stable_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 lv=stable_level(s,city_id)
 return {'building':'Stable','level':lv,'horseback_riding_supported_level':lv,'relief_station_unlocked':lv>=1,'cavalry_training_speed_bonus':0,'note':'Age I evidence says Stable level does not reduce cavalry/cataphract training time.'}

from .service import workshop_level
@app.get('/api/players/{player_id}/cities/{city_id}/workshop')
def workshop_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 lv=workshop_level(s,city_id)
 return {'building':'Workshop','level':lv,'metal_casting_supported_level':lv,'walls_unlocked':lv>=1,'dependencies':['Metal Casting level N requires Workshop level N','Walls require Workshop level 1','Mechanical troop/fortification unlocks use Metal Casting prerequisites, not an invented Workshop bonus']}

from .service import relief_station_level,relief_station_multiplier
@app.get('/api/players/{player_id}/cities/{city_id}/relief-station')
def relief_station_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 lv=relief_station_level(s,city_id)
 return {'building':'Relief Station','level':lv,'speed_multiplier':relief_station_multiplier(s,city_id),'applies_to':['Transport to own/allied city','Reinforce own/allied city'],'does_not_apply_to':['Attack','Scout','Enemy city','Valley/NPC attack'],'sending_city_controls_speed':True}

from .models import FortificationQueue
from .service import walls_level,wall_capacity,fortification_prerequisites,complete_fortifications,build_fortification,archer_tower_range,fortification_repair_rate
class FortificationBuildRequest(BaseModel):definition_key:str;quantity:int;idempotency_key:str
@app.get('/api/players/{player_id}/cities/{city_id}/walls')
def walls_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 complete_fortifications(s,city_id);lv=walls_level(s,city_id);cap=wall_capacity(s,city_id)
 forts=s.scalars(select(Fortification).where(Fortification.city_id==city_id)).all();qs=s.scalars(select(FortificationQueue).where(FortificationQueue.city_id==city_id,FortificationQueue.status.in_(['ACTIVE','QUEUED'])).order_by(FortificationQueue.id)).all()
 defs=[]
 for k,d in DATA['fortifications'].items():defs.append({'key':k,**d,'missing_prerequisites':fortification_prerequisites(s,city_id,k),'repair_rate':fortification_repair_rate(s,city_id,k),'effective_range':archer_tower_range(s,city_id) if k=='archer_tower' else d.get('range')})
 return {'building':'Walls','level':lv,**cap,'fortifications':{x.definition_key:x.quantity for x in forts},'definitions':defs,'queue':[{'id':q.id,'type':q.definition_key,'quantity':q.quantity,'status':q.status,'completes_at':q.completes_at} for q in qs],'defensive_interaction':{'engineering_life_multiplier':wall_fortification_life_multiplier(s,city_id),'archer_tower_range':archer_tower_range(s,city_id),'machinery_repairs':True,'100_round_wall_rule':True}}
@app.post('/api/players/{player_id}/cities/{city_id}/walls/fortifications')
def walls_build(player_id:int,city_id:int,req:FortificationBuildRequest,s:Session=Depends(db)):
 try:return build_fortification(s,player_id,city_id,req.definition_key,req.quantity,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .service import complete_demolition,start_demolish_one_level,dynamite_building
class DemolishRequest(BaseModel):idempotency_key:str
@app.post('/api/players/{player_id}/cities/{city_id}/buildings/{building_id}/demolish-one-level')
def demolish_one(player_id:int,city_id:int,building_id:int,req:DemolishRequest,s:Session=Depends(db)):
 try:return start_demolish_one_level(s,player_id,city_id,building_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/buildings/{building_id}/dynamite')
def demolish_dynamite(player_id:int,city_id:int,building_id:int,req:DemolishRequest,s:Session=Depends(db)):
 try:return dynamite_building(s,player_id,city_id,building_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .service import field_construction_options,start_field_construction,apply_production_item
class FieldConstructRequest(BaseModel):
 building_key:str
 idempotency_key:str
class ProductionItemRequest(BaseModel):
 item_key:str
 idempotency_key:str
@app.get('/api/players/{player_id}/cities/{city_id}/field-construction-options')
def field_options(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 return field_construction_options(s,city_id)
@app.post('/api/players/{player_id}/cities/{city_id}/fields/{plot_index}/construct')
def field_construct(player_id:int,city_id:int,plot_index:int,req:FieldConstructRequest,s:Session=Depends(db)):
 try:return start_field_construction(s,player_id,city_id,plot_index,req.building_key,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/production-item')
def production_item(player_id:int,city_id:int,req:ProductionItemRequest,s:Session=Depends(db)):
 try:return apply_production_item(s,player_id,city_id,req.item_key,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

from .service import settle_economy,economy_debug
@app.get('/api/players/{player_id}/cities/{city_id}/economy')
def economy_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 return settle_economy(s,city_id)

@app.get('/api/dev/players/{player_id}/cities/{city_id}/economy-debug')
def economy_debug_interface(player_id:int,city_id:int,s:Session=Depends(db)):
 if os.getenv('DEVELOPMENT_MODE','0').lower() not in ('1','true','yes'):raise HTTPException(404,'Not found')
 c=s.get(City,city_id)
 if not c or c.player_id!=player_id:raise HTTPException(404,'City not found')
 return economy_debug(s,city_id)

@app.get('/api/dev/status')
def development_status():
 if os.getenv('DEVELOPMENT_MODE','0').lower() not in ('1','true','yes'):raise HTTPException(404,'Not found')
 return {'development_mode':True}

from .service import hero_detail,level_hero,assign_hero_points,redistribute_hero,reward_hero_gold,apply_hero_item,rename_hero,persuade_captured_hero
class HeroLevelRequest(BaseModel):attribute:str;idempotency_key:str
class HeroPointsRequest(BaseModel):politics:int;attack:int;intelligence:int;idempotency_key:str
class HeroItemRequest(BaseModel):item_key:str;idempotency_key:str
class HeroRenameRequest(BaseModel):name:str;idempotency_key:str

@app.get('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}')
def api_hero_detail(player_id:int,city_id:int,hero_id:int,s:Session=Depends(db)):
 try:return hero_detail(s,player_id,city_id,hero_id)
 except ValueError as e:raise HTTPException(404,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/level')
def api_hero_level(player_id:int,city_id:int,hero_id:int,req:HeroLevelRequest,s:Session=Depends(db)):
 try:return level_hero(s,player_id,city_id,hero_id,req.attribute,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/assign-points')
def api_hero_points(player_id:int,city_id:int,hero_id:int,req:HeroPointsRequest,s:Session=Depends(db)):
 try:return assign_hero_points(s,player_id,city_id,hero_id,req.politics,req.attack,req.intelligence,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/redistribute')
def api_hero_redistribute(player_id:int,city_id:int,hero_id:int,req:HeroActionRequest,s:Session=Depends(db)):
 try:return redistribute_hero(s,player_id,city_id,hero_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/reward-gold')
def api_hero_reward_gold(player_id:int,city_id:int,hero_id:int,req:HeroActionRequest,s:Session=Depends(db)):
 try:return reward_hero_gold(s,player_id,city_id,hero_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/item')
def api_hero_item(player_id:int,city_id:int,hero_id:int,req:HeroItemRequest,s:Session=Depends(db)):
 try:return apply_hero_item(s,player_id,city_id,hero_id,req.item_key,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/rename')
def api_hero_rename(player_id:int,city_id:int,hero_id:int,req:HeroRenameRequest,s:Session=Depends(db)):
 try:return rename_hero(s,player_id,city_id,hero_id,req.name,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.post('/api/players/{player_id}/cities/{city_id}/feasting-hall/heroes/{hero_id}/persuade')
def api_hero_persuade(player_id:int,city_id:int,hero_id:int,req:HeroActionRequest,s:Session=Depends(db)):
 try:return persuade_captured_hero(s,player_id,city_id,hero_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

class MapBookmarkRequest(BaseModel):
 x:int;y:int;label:str|None=None;idempotency_key:str
class MapBookmarkDeleteRequest(BaseModel):idempotency_key:str

@app.get('/api/players/{player_id}/map/bookmarks')
def api_map_bookmarks(player_id:int,s:Session=Depends(db)):return {'bookmarks':player_bookmarks(s,player_id)}

@app.post('/api/players/{player_id}/map/bookmarks')
def api_map_bookmark_add(player_id:int,req:MapBookmarkRequest,s:Session=Depends(db)):
 try:return add_bookmark(s,player_id,req.x,req.y,req.label,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.delete('/api/players/{player_id}/map/bookmarks/{bookmark_id}')
def api_map_bookmark_delete(player_id:int,bookmark_id:int,idempotency_key:str,s:Session=Depends(db)):
 try:return delete_bookmark(s,player_id,bookmark_id,idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
from .service import wilderness_detail,scout_wilderness,abandon_wilderness,build_city_on_flat
class WildernessActionRequest(BaseModel):
 city_id:int;idempotency_key:str
class FlatBuildCityRequest(BaseModel):
 source_city_id:int;name:str;idempotency_key:str
@app.get('/api/players/{player_id}/map/wilderness/{x}/{y}')
def api_wilderness(player_id:int,x:int,y:int,s:Session=Depends(db)):
 try:return wilderness_detail(s,player_id,x,y)
 except ValueError as e:raise HTTPException(404,str(e))
@app.post('/api/players/{player_id}/map/wilderness/{x}/{y}/scout')
def api_wilderness_scout(player_id:int,x:int,y:int,req:WildernessActionRequest,s:Session=Depends(db)):
 try:return scout_wilderness(s,player_id,req.city_id,x,y)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/map/wilderness/{x}/{y}/abandon')
def api_wilderness_abandon(player_id:int,x:int,y:int,req:WildernessActionRequest,s:Session=Depends(db)):
 try:return abandon_wilderness(s,player_id,req.city_id,x,y,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/map/flats/{x}/{y}/build-city')
def api_flat_build_city(player_id:int,x:int,y:int,req:FlatBuildCityRequest,s:Session=Depends(db)):
 try:return build_city_on_flat(s,player_id,req.source_city_id,x,y,req.name,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
from .service import abandon_city_to_npc
class CityAbandonRequest(BaseModel):idempotency_key:str
@app.post('/api/players/{player_id}/cities/{city_id}/abandon-to-npc')
def api_city_abandon_to_npc(player_id:int,city_id:int,req:CityAbandonRequest,s:Session=Depends(db)):
 try:return abandon_city_to_npc(s,player_id,city_id,req.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/players/{player_id}/marches')
def api_player_marches(player_id:int,s:Session=Depends(db)):
 process_due_marches(s,player_id=player_id)
 return {'marches':active_marches_for_player(s,player_id)}

@app.post('/api/players/{player_id}/marches/process-due')
def api_process_due_marches(player_id:int,s:Session=Depends(db)):
 return {'processed':process_due_marches(s,player_id=player_id)}
from .service import list_reports,get_report,delete_report
@app.get('/api/players/{player_id}/reports')
def api_reports(player_id:int,kind:str|None=None,unread_only:bool=False,s:Session=Depends(db)):
 return {'reports':list_reports(s,player_id,kind,not unread_only)}
@app.get('/api/players/{player_id}/reports/{kind}/{report_id}')
def api_report(player_id:int,kind:str,report_id:int,s:Session=Depends(db)):
 try:return get_report(s,player_id,kind,report_id,True)
 except ValueError as e:raise HTTPException(404,str(e))
@app.delete('/api/players/{player_id}/reports/{kind}/{report_id}')
def api_delete_report(player_id:int,kind:str,report_id:int,s:Session=Depends(db)):
 try:return delete_report(s,player_id,kind,report_id)
 except ValueError as e:raise HTTPException(404,str(e))

# Persistent player mail
from .service import player_recipient_lookup,send_player_mail,mail_box,read_mail,delete_mail
class MailComposeRequest(BaseModel):
 recipient:str
 subject:str
 body:str
 idempotency_key:str
 reply_to_mail_id:int|None=None

@app.get('/api/players/{player_id}/mail/recipients')
def mail_recipients(player_id:int,q:str,s:Session=Depends(db)):
 if not s.get(Player,player_id):raise HTTPException(404,'Player not found')
 try:return {'recipients':player_recipient_lookup(s,q)}
 except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/players/{player_id}/mail')
def mail_list(player_id:int,box:str='inbox',limit:int=100,offset:int=0,s:Session=Depends(db)):
 try:return {'box':box,'messages':mail_box(s,player_id,box,limit,offset)}
 except ValueError as e:raise HTTPException(400,str(e))

@app.get('/api/players/{player_id}/mail/{mail_id}')
def mail_get(player_id:int,mail_id:int,s:Session=Depends(db)):
 try:return read_mail(s,player_id,mail_id)
 except ValueError as e:raise HTTPException(404,str(e))

@app.post('/api/players/{player_id}/mail')
def mail_send(player_id:int,req:MailComposeRequest,s:Session=Depends(db)):
 try:return send_player_mail(s,player_id,req.recipient,req.subject,req.body,req.idempotency_key,req.reply_to_mail_id)
 except ValueError as e:raise HTTPException(429 if 'rate limit' in str(e) else 409,str(e))

@app.delete('/api/players/{player_id}/mail/{mail_id}')
def mail_delete(player_id:int,mail_id:int,box:str='inbox',s:Session=Depends(db)):
 try:return delete_mail(s,player_id,mail_id,box)
 except ValueError as e:raise HTTPException(404,str(e))

class AllianceCreateRequest(BaseModel): city_id:int;name:str;idempotency_key:str
class AllianceInfoRequest(BaseModel): information:str
class AllianceInviteRequest(BaseModel): player_name:str
class AllianceRespondRequest(BaseModel): accept:bool
class AllianceRankRequest(BaseModel): target_player_id:int;direction:str
class AllianceTargetRequest(BaseModel): target_player_id:int
class AllianceRelationRequest(BaseModel): other_alliance_id:int;state:str
class AllianceChatRequest(BaseModel): body:str
class AllianceMailRequest(BaseModel): subject:str;body:str

@app.get('/api/players/{player_id}/alliance')
def api_alliance(player_id:int,s:Session=Depends(db)):return alliance_detail(s,player_id)
@app.post('/api/players/{player_id}/alliance')
def api_alliance_create(player_id:int,r:AllianceCreateRequest,s:Session=Depends(db)):
 try:return create_alliance(s,player_id,r.city_id,r.name.strip(),r.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.patch('/api/players/{player_id}/alliance/information')
def api_alliance_info(player_id:int,r:AllianceInfoRequest,s:Session=Depends(db)):
 try:return update_alliance_information(s,player_id,r.information)
 except ValueError as e:raise HTTPException(403,str(e))
@app.post('/api/players/{player_id}/alliance/invitations')
def api_alliance_invite(player_id:int,r:AllianceInviteRequest,s:Session=Depends(db)):
 try:return invite_to_alliance(s,player_id,r.player_name)
 except ValueError as e:raise HTTPException(403,str(e))
@app.get('/api/players/{player_id}/alliance/invitations')
def api_alliance_invitations(player_id:int,s:Session=Depends(db)):return {'invitations':alliance_invitations(s,player_id)}
@app.post('/api/players/{player_id}/alliance/invitations/{invitation_id}')
def api_alliance_invitation_response(player_id:int,invitation_id:int,r:AllianceRespondRequest,s:Session=Depends(db)):
 try:return respond_alliance_invitation(s,player_id,invitation_id,r.accept)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/alliance/applications/{application_id}/reject')
def api_alliance_reject_application(player_id:int,application_id:int,s:Session=Depends(db)):
 try:return reject_alliance_application(s,player_id,application_id)
 except ValueError as e:raise HTTPException(403,str(e))
@app.post('/api/players/{player_id}/alliance/rank')
def api_alliance_rank(player_id:int,r:AllianceRankRequest,s:Session=Depends(db)):
 try:return change_alliance_rank(s,player_id,r.target_player_id,r.direction)
 except ValueError as e:raise HTTPException(403,str(e))
@app.post('/api/players/{player_id}/alliance/expel')
def api_alliance_expel(player_id:int,r:AllianceTargetRequest,s:Session=Depends(db)):
 try:return expel_alliance_member(s,player_id,r.target_player_id)
 except ValueError as e:raise HTTPException(403,str(e))
@app.post('/api/players/{player_id}/alliance/leave')
def api_alliance_leave(player_id:int,s:Session=Depends(db)):
 try:return leave_alliance(s,player_id)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/alliance/transfer-host')
def api_alliance_transfer(player_id:int,r:AllianceTargetRequest,s:Session=Depends(db)):
 try:return transfer_alliance_host(s,player_id,r.target_player_id)
 except ValueError as e:raise HTTPException(403,str(e))
@app.post('/api/players/{player_id}/alliance/relation')
def api_alliance_relation(player_id:int,r:AllianceRelationRequest,s:Session=Depends(db)):
 try:return set_alliance_relation(s,player_id,r.other_alliance_id,r.state)
 except ValueError as e:raise HTTPException(403,str(e))
@app.get('/api/players/{player_id}/alliance/chat')
def api_alliance_chat(player_id:int,s:Session=Depends(db)):
 try:return {'messages':alliance_chat(s,player_id)}
 except ValueError as e:raise HTTPException(403,str(e))
@app.post('/api/players/{player_id}/alliance/chat')
def api_alliance_chat_send(player_id:int,r:AllianceChatRequest,s:Session=Depends(db)):
 try:return send_alliance_chat(s,player_id,r.body)
 except ValueError as e:raise HTTPException(429 if 'rate limit' in str(e) else 403,str(e))
@app.post('/api/players/{player_id}/alliance/mail')
def api_alliance_mail(player_id:int,r:AllianceMailRequest,s:Session=Depends(db)):
 try:return send_alliance_mail(s,player_id,r.subject,r.body)
 except ValueError as e:raise HTTPException(403,str(e))

class ChatSendRequest(BaseModel):
 channel:str
 body:str
 recipient:str|None=None
class ChatPreferenceRequest(BaseModel):
 player_name:str
 enabled:bool=True
@app.get('/api/players/{player_id}/chat')
def api_chat(player_id:int,channel:str='WORLD',since_id:int=0,limit:int=100,whisper_with:str|None=None,s:Session=Depends(db)):
 try:return {'messages':chat_messages(s,player_id,channel,since_id,limit,whisper_with)}
 except ValueError as e:raise HTTPException(403,str(e))
@app.post('/api/players/{player_id}/chat')
def api_chat_send(player_id:int,r:ChatSendRequest,s:Session=Depends(db)):
 try:return send_chat_message(s,player_id,r.channel,r.body,r.recipient)
 except ValueError as e:raise HTTPException(429 if 'rate limit' in str(e) else 403,str(e))
@app.post('/api/players/{player_id}/chat/block')
def api_chat_block(player_id:int,r:ChatPreferenceRequest,s:Session=Depends(db)):
 try:return set_chat_block(s,player_id,r.player_name,r.enabled)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/chat/mute')
def api_chat_mute(player_id:int,r:ChatPreferenceRequest,s:Session=Depends(db)):
 try:return set_chat_mute(s,player_id,r.player_name,r.enabled)
 except ValueError as e:raise HTTPException(409,str(e))

class QuestClaimRequest(BaseModel): idempotency_key:str
@app.get('/api/players/{player_id}/quests')
def api_quests(player_id:int,s:Session=Depends(db)):
 try:return {'quests':quest_list(s,player_id)}
 except ValueError as e:raise HTTPException(400,str(e))
@app.post('/api/players/{player_id}/quests/{quest_key}/claim')
def api_quest_claim(player_id:int,quest_key:str,r:QuestClaimRequest,s:Session=Depends(db)):
 try:return claim_quest(s,player_id,quest_key,r.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

class PromotionRequest(BaseModel):
 city_id:int
 kind:str
 target:str
 idempotency_key:str
@app.get('/api/players/{player_id}/progression')
def api_progression(player_id:int,city_id:int|None=None,s:Session=Depends(db)):
 try:return progression_status(s,player_id,city_id)
 except ValueError as e:raise HTTPException(400,str(e))
@app.post('/api/players/{player_id}/progression/promote')
def api_promote(player_id:int,r:PromotionRequest,s:Session=Depends(db)):
 try:return promote_player(s,player_id,r.city_id,r.kind,r.target,r.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

class FoundCityRequest(BaseModel):
 source_city_id:int
 x:int
 y:int
 name:str
 idempotency_key:str
class AbandonCityRequest(BaseModel): idempotency_key:str
@app.get('/api/players/{player_id}/cities')
def api_player_cities(player_id:int,s:Session=Depends(db)):
 return {'cities':player_cities_overview(s,player_id)}
@app.get('/api/players/{player_id}/cities/{city_id}/independent-state')
def api_city_independent_state(player_id:int,city_id:int,s:Session=Depends(db)):
 try:return city_independence_snapshot(s,player_id,city_id)
 except ValueError as e:raise HTTPException(404,str(e))
@app.post('/api/players/{player_id}/cities/found')
def api_found_city(player_id:int,r:FoundCityRequest,s:Session=Depends(db)):
 try:return build_city_on_flat(s,player_id,r.source_city_id,r.x,r.y,r.name,r.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/abandon')
def api_abandon_city(player_id:int,city_id:int,r:AbandonCityRequest,s:Session=Depends(db)):
 try:return abandon_city_to_npc(s,player_id,city_id,r.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

class ItemUseRequest(BaseModel):
 target:dict={}
 idempotency_key:str
@app.get('/api/players/{player_id}/items')
def api_items(player_id:int,s:Session=Depends(db)):
 return inventory_snapshot(s,player_id)
@app.post('/api/players/{player_id}/items/{item_key}/use')
def api_use_item(player_id:int,item_key:str,r:ItemUseRequest,s:Session=Depends(db)):
 try:return use_inventory_item(s,player_id,item_key,r.target,r.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))

@app.get('/api/players/{player_id}/beginner-protection')
def api_beginner_protection(player_id:int,s:Session=Depends(db)):
 return beginner_protection_status(s,player_id)

class TownHallActionRequest(BaseModel):
 action:str
 idempotency_key:str
@app.post('/api/players/{player_id}/cities/{city_id}/town-hall/comfort')
def town_hall_comfort_api(player_id:int,city_id:int,r:TownHallActionRequest,s:Session=Depends(db)):
 try:return town_hall_comfort(s,player_id,city_id,r.action,r.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
@app.post('/api/players/{player_id}/cities/{city_id}/town-hall/levy')
def town_hall_levy_api(player_id:int,city_id:int,r:TownHallActionRequest,s:Session=Depends(db)):
 try:return town_hall_levy(s,player_id,city_id,r.action,r.idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e))
