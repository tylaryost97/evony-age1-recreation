
from datetime import datetime,timezone
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'m.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='m@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();cities=[]
 for i in range(2):
  c=City(player_id=p.id,name=f'C{i}',x=10+i,y=10,gold=50000,population=100+i,idle_population=50);s.add(c);s.flush();cities.append(c);s.add(CityCoordinate(city_id=c.id,x=c.x,y=c.y));s.add(PopulationState(city_id=c.id,population=c.population,idle_population=50,population_limit=1000,last_population_tick_at=datetime.now(timezone.utc)));s.add(CityEconomyState(city_id=c.id,gold=50000,last_settled_at=datetime.now(timezone.utc)))
  for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=20000+i*1000,capacity=999999,updated_at=datetime.now(timezone.utc)))
  for j in range(34):s.add(CityBuildingPlot(city_id=c.id,plot_index=j))
  for j in range(1,11):s.add(ExteriorFieldPlot(city_id=c.id,plot_index=j))
  th=Building(city_id=c.id,plot_kind='CITY',plot_index=0,definition_key='town_hall',level=1);w=Building(city_id=c.id,plot_kind='CITY',plot_index=33,definition_key='walls',level=1);s.add_all([th,w]);s.flush();s.add_all([BuildingLevel(building_id=th.id,level=1),BuildingLevel(building_id=w.id,level=1)])
 s.add(PlayerProgression(player_id=p.id,prestige=1000,honor=0,title_rank_key='Civilian|Prinzessin'))
 s.commit();yield s,p,cities;s.close()
def test_cities_are_independent_state(ctx):
 s,p,c=ctx;s.add(TroopQuantity(city_id=c[0].id,troop_type_key='worker',quantity=25));s.add(Hero(player_id=p.id,city_id=c[0].id,name='Mayor',level=1,politics=10,attack=1,intelligence=1,loyalty=70,assignment='mayor'));s.commit()
 a=city_independence_snapshot(s,p.id,c[0].id);b=city_independence_snapshot(s,p.id,c[1].id)
 assert a['city']['x']!=b['city']['x'] and a['resources']['food']!=b['resources']['food'] and a['troops']['worker']==25 and 'worker' not in b['troops'] and a['mayor']['name']=='Mayor' and b['mayor'] is None
def test_research_shared_but_local_academy_applies(ctx):
 s,p,c=ctx;s.add(Technology(player_id=p.id,definition_key='agriculture',level=1))
 b=Building(city_id=c[0].id,plot_kind='CITY',plot_index=2,definition_key='academy',level=1);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=1));s.commit()
 assert technology_level(s,p.id,'agriculture')==1 and effective_technology_level(s,c[0].id,'agriculture')==1 and effective_technology_level(s,c[1].id,'agriculture')==0
def test_founding_requires_and_consumes_gold_workers_resources(ctx):
 s,p,c=ctx;s.add(TroopQuantity(city_id=c[0].id,troop_type_key='worker',quantity=250));tile=MapTile(x=20,y=20,tile_type='FLAT',level=3,owner_player_id=p.id);s.add(tile);s.flush();s.add(Flat(map_tile_id=tile.id,level=3,city_id=c[0].id,defenders={}));s.commit()
 before=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c[0].id)).gold;r=build_city_on_flat(s,p.id,c[0].id,20,20,'New','f')
 assert r['resources_consumed']['gold']==10000 and s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c[0].id)).gold==before-10000
 nc=s.get(City,r['city_id']);assert nc.x==20 and nc.y==20 and len(s.scalars(select(CityBuildingPlot).where(CityBuildingPlot.city_id==nc.id)).all())==34
def test_founding_rejects_missing_gold(ctx):
 s,p,c=ctx;s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c[0].id)).gold=9999;s.add(TroopQuantity(city_id=c[0].id,troop_type_key='worker',quantity=250));tile=MapTile(x=21,y=20,tile_type='FLAT',level=1,owner_player_id=p.id);s.add(tile);s.flush();s.add(Flat(map_tile_id=tile.id,level=1,city_id=c[0].id,defenders={}));s.commit()
 with pytest.raises(ValueError,match='Gold'):build_city_on_flat(s,p.id,c[0].id,21,20,'No','x')
def test_overview_switch_data(ctx):
 s,p,c=ctx;rows=player_cities_overview(s,p.id);assert [x['id'] for x in rows]==[c[0].id,c[1].id] and rows[0]['name']=='C0' and rows[1]['name']=='C1'
def test_player_city_conquest_rules(ctx):
 s,p,c=ctx;a=Account(email='enemy@x');s.add(a);s.flush();enemy=Player(account_id=a.id,name='E');s.add(enemy);s.flush();e1=City(player_id=enemy.id,name='E1',x=30,y=30,loyalty=0);e2=City(player_id=enemy.id,name='E2',x=31,y=30);s.add_all([e1,e2]);s.flush();tile=MapTile(x=30,y=30,tile_type='PLAYER_CITY',owner_player_id=enemy.id);s.add(tile);s.commit()
 r=capture_player_city(s,p.id,c[0].id,e1.id);s.refresh(e1);s.refresh(tile);assert r['captured_city_id']==e1.id and e1.player_id==p.id and tile.owner_player_id==p.id
def test_only_enemy_city_cannot_be_conquered(ctx):
 s,p,c=ctx;a=Account(email='enemy@x');s.add(a);s.flush();enemy=Player(account_id=a.id,name='E');s.add(enemy);s.flush();e=City(player_id=enemy.id,name='Only',x=30,y=30,loyalty=0);s.add(e);s.commit()
 with pytest.raises(ValueError,match='only city'):capture_player_city(s,p.id,c[0].id,e.id)
