from datetime import datetime,timezone
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'v.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='v@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();s.add(PlayerProgression(player_id=p.id,title_rank_key='Knight'))
 c=City(player_id=p.id,name='Home',x=100,y=100);s.add(c);s.flush();s.add(CityEconomyState(city_id=c.id,gold=50000,last_settled_at=datetime.now(timezone.utc)));s.add(PopulationState(city_id=c.id,population=1000,idle_population=1000,population_limit=1000,last_population_tick_at=datetime.now(timezone.utc)))
 for i in range(34):s.add(CityBuildingPlot(city_id=c.id,plot_index=i))
 th=Building(city_id=c.id,plot_kind='CITY',plot_index=0,definition_key='town_hall',level=2);ac=Building(city_id=c.id,plot_kind='CITY',plot_index=1,definition_key='academy',level=10);s.add_all([th,ac]);s.flush();s.add_all([BuildingLevel(building_id=th.id,level=2),BuildingLevel(building_id=ac.id,level=10)])
 for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=50000,capacity=999999));s.add(ResourceProduction(city_id=c.id,resource_kind=k,per_hour=0));s.add(ResourceCapacity(city_id=c.id,resource_kind=k,capacity=999999))
 s.add(TroopQuantity(city_id=c.id,troop_type_key='worker',quantity=500));s.add(Technology(player_id=p.id,definition_key='informatics',level=10))
 vals=[]
 for i,typ in enumerate(AGE1_VALLEY_TYPES):
  t=MapTile(x=110+i,y=100,tile_type='VALLEY',level=i+1);s.add(t);s.flush();v=Valley(map_tile_id=t.id,valley_type=typ,level=i+1,defenders={'warrior':28+i});s.add(v);vals.append(v)
 ft=MapTile(x=120,y=100,tile_type='FLAT',level=5);s.add(ft);s.flush();f=Flat(map_tile_id=ft.id,level=5,city_id=c.id,defenders={});s.add(f);ft.owner_player_id=p.id
 s.commit();yield s,p,c,vals,f
 s.close()
def test_all_age1_types_and_exact_bonus_tables(ctx):
 s,p,c,vals,f=ctx
 assert AGE1_VALLEY_TYPES==('GRASSLAND','SWAMP','LAKE','HILL','DESERT','FOREST')
 assert [valley_bonus('GRASSLAND',i)['percent'] for i in range(1,11)]==[3,4,5,6,7,8,9,10,11,12]
 assert [valley_bonus('SWAMP',i)['percent'] for i in range(1,11)]==[5,7,9,11,13,15,17,19,21,23]
 assert [valley_bonus('LAKE',i)['percent'] for i in range(1,11)]==[8,11,14,17,20,23,26,29,32,35]
 for typ in ('HILL','DESERT','FOREST'):assert [valley_bonus(typ,i)['percent'] for i in range(1,11)]==[5,7,9,11,13,15,17,19,21,23]
def test_scout_exact_with_informatics_and_persistent_defenders(ctx):
 s,p,c,vals,f=ctx;r=scout_wilderness(s,p.id,c.id,110,100);assert r['exact'] and r['defenders']=={'warrior':28}
def test_scout_bands_when_informatics_below_valley(ctx):
 s,p,c,vals,f=ctx;tech=s.scalar(select(Technology).where(Technology.player_id==p.id,Technology.definition_key=='informatics'));tech.level=0
 r=scout_wilderness(s,p.id,c.id,115,100);assert not r['exact'] and r['defenders']['warrior'] in ('Pack','Lots')
def test_town_hall_limits_owned_valleys_and_flat_counts(ctx):
 s,p,c,vals,f=ctx
 # TH2 permits two wilderness holdings total; flat already consumes one.
 vals[0].defenders={};conquer_wilderness(s,p.id,c.id,110,100)
 vals[1].defenders={}
 with pytest.raises(ValueError,match='limit'):conquer_wilderness(s,p.id,c.id,111,100)
def test_owned_valley_bonus_integrates_existing_economy_function(ctx):
 s,p,c,vals,f=ctx;vals[2].defenders={};f.city_id=None;conquer_wilderness(s,p.id,c.id,112,100)
 assert valley_production_bonus_percent(s,c.id,'food')==valley_bonus('LAKE',3)['percent']
def test_abandon_persists_release(ctx):
 s,p,c,vals,f=ctx;vals[0].defenders={};f.city_id=None;conquer_wilderness(s,p.id,c.id,110,100);abandon_wilderness(s,p.id,c.id,110,100,'a');s.commit();assert vals[0].city_id is None
def test_flat_build_city_cost_and_level_provenance(ctx):
 s,p,c,vals,f=ctx;r=build_city_on_flat(s,p.id,c.id,120,100,'Second','b');s.commit();assert r['source_flat_level']==5 and r['workers_consumed']==250
 new=s.get(City,r['city_id']);assert (new.x,new.y)==(120,100);setting=s.scalar(select(PlayerSetting).where(PlayerSetting.key==f'city:{new.id}:founding_flat_level'));assert setting.value['level']==5
 assert s.scalar(select(TroopQuantity).where(TroopQuantity.city_id==c.id,TroopQuantity.troop_type_key=='worker')).quantity==250
 for k in ('food','lumber','stone','iron'):assert s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind==k)).quantity==40000
def test_flat_requires_title_city_slot(ctx):
 s,p,c,vals,f=ctx;s.scalar(select(PlayerProgression).where(PlayerProgression.player_id==p.id)).title_rank_key='Civilian'
 with pytest.raises(ValueError,match='title'):build_city_on_flat(s,p.id,c.id,120,100,'Nope','x')
def test_founded_flat_city_abandon_creates_same_level_npc(ctx):
 s,p,c,vals,f=ctx;r=build_city_on_flat(s,p.id,c.id,120,100,'Disposable','build');newid=r['city_id']
 out=abandon_city_to_npc(s,p.id,newid,'abandon');s.commit();s.expire_all();assert out['level']==5 and s.get(City,newid) is None
 tile=s.scalar(select(MapTile).where(MapTile.x==120,MapTile.y==100));assert tile.tile_type=='NPC_CITY';npc=s.scalar(select(NPCCity).where(NPCCity.map_tile_id==tile.id));assert npc.level==5
