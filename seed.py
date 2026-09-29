from .db import Base,engine,SessionLocal
from .models import *
from datetime import timedelta

def seed():
 Base.metadata.create_all(engine)
 with SessionLocal() as s:
  if s.query(Account).count(): return
  players=[]
  for i,name in enumerate(['Aurelius','Boudica','Cyrus'],1):
   a=Account(email=f'dev{i}@example.invalid'); s.add(a); s.flush()
   p=Player(account_id=a.id,name=name); s.add(p); s.flush(); players.append(p)
   s.add(PlayerProgression(player_id=p.id))
   s.add(BeginnerProtection(player_id=p.id,started_at=a.created_at,expires_at=a.created_at+timedelta(days=7)))
   s.add(PlayerSetting(player_id=p.id,key='development_seed',value={'seeded':True}))
  cities=[City(player_id=players[0].id,name='Alpha',x=100,y=100),City(player_id=players[0].id,name='Beta',x=103,y=101),City(player_id=players[1].id,name='Gamma',x=110,y=108),City(player_id=players[2].id,name='Delta',x=120,y=115)]
  s.add_all(cities); s.flush()
  for c in cities:
   s.add(CityCoordinate(city_id=c.id,x=c.x,y=c.y)); s.add(PopulationState(city_id=c.id)); s.add(CityEconomyState(city_id=c.id))
   for i in range(34): s.add(CityBuildingPlot(city_id=c.id,plot_index=i))
   for i in range(1,11): s.add(ExteriorFieldPlot(city_id=c.id,plot_index=i))
   th=Building(city_id=c.id,plot_kind='CITY',plot_index=0,definition_key='town_hall',level=1); wall=Building(city_id=c.id,plot_kind='CITY',plot_index=33,definition_key='walls',level=1); s.add_all([th,wall]); s.flush(); s.add_all([BuildingLevel(building_id=th.id,level=1),BuildingLevel(building_id=wall.id,level=1)])
   for kind in ['food','lumber','stone','iron']:
    s.add(Resource(city_id=c.id,kind=kind,quantity=2000000,capacity=2000000)); s.add(ResourceProduction(city_id=c.id,resource_kind=kind,per_hour=0)); s.add(ResourceCapacity(city_id=c.id,resource_kind=kind,capacity=2000000))
  # Development world patch. CUSTOM_SERVER_RULE: DOUBLE NPC DENSITY.
  # Historical Age I did not expose a canonical fixed NPC percentage; this seed deliberately uses 2 NPCs for every baseline NPC slot in our deterministic fixture.
  specs=[(101,100,'NPC_CITY',1,None),(102,100,'NPC_CITY',2,None),(103,100,'FLAT',1,None),(104,100,'VALLEY',1,'FOREST'),(105,100,'VALLEY',2,'DESERT'),(106,100,'VALLEY',3,'HILL'),(107,100,'VALLEY',4,'LAKE'),(108,100,'VALLEY',5,'SWAMP'),(109,100,'VALLEY',6,'GRASSLAND'),(110,100,'FLAT',6,None),
   (99,99,'FLAT',2,None),(100,99,'NPC_CITY',3,None),(101,99,'NPC_CITY',4,None)]
  for tx,ty,kind,lv,vtype in specs:
   # Player cities take precedence at their persistent coordinates.
   if s.query(City).filter(City.x==tx,City.y==ty).first():continue
   t=MapTile(x=tx,y=ty,tile_type=kind,level=lv);s.add(t);s.flush()
   if kind=='NPC_CITY':
    n=NPCCity(map_tile_id=t.id,level=lv);s.add(n);s.flush()
    from .npc import initialize_npc
    initialize_npc(n,force=True)
   elif kind=='VALLEY':s.add(Valley(map_tile_id=t.id,valley_type=vtype,level=lv,defenders=({'warrior':28,'pikeman':9} if lv==1 else {'pikeman':51} if lv==2 else {})))
   elif kind=='FLAT':s.add(Flat(map_tile_id=t.id,level=lv,defenders=({'warrior':28,'pikeman':9} if lv==1 else {})))
  s.commit()
if __name__=='__main__': seed()
