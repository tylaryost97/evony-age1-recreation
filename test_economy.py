
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *

def setup(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'eco.db'}",connect_args={"check_same_thread":False});Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  a=Account(email='e@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush()
  c=City(player_id=p.id,name='C',x=1,y=1,population=1000,idle_population=1000,gold=0,tax_rate=50,loyalty=50);s.add(c);s.flush()
  s.add(PopulationState(city_id=c.id,population=1000,idle_population=1000,population_limit=2000,last_population_tick_at=datetime.now(timezone.utc)))
  s.add(CityEconomyState(city_id=c.id,gold=0,tax_rate=50,loyalty=50,grievance=0,last_settled_at=datetime.now(timezone.utc)))
  for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=10000,capacity=1000000,updated_at=datetime.now(timezone.utc)))
  s.commit();return S,p.id,c.id

def add_field(s,cid,key,lv=1,plot=1):
 b=Building(city_id=cid,plot_kind='FIELD',plot_index=plot,definition_key=key,level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv));s.flush();return b

def test_six_minute_tax_loyalty_population_tick(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==cid));pop=s.scalar(select(PopulationState).where(PopulationState.city_id==cid))
  now=datetime.now(timezone.utc);eco.last_settled_at=now-timedelta(minutes=6);pop.last_population_tick_at=now-timedelta(minutes=6);s.commit()
 with S() as s:
  settle_economy(s,cid,now);eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==cid));pop=s.scalar(select(PopulationState).where(PopulationState.city_id==cid))
  # loyalty already at 100-tax=50; population target is 1000, so one tick yields 50 gold.
  assert eco.loyalty==50 and pop.population==1000 and eco.gold==50

def test_loyalty_and_population_move_toward_equilibrium(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==cid));pop=s.scalar(select(PopulationState).where(PopulationState.city_id==cid))
  eco.tax_rate=0;eco.loyalty=50;pop.population=500;now=datetime.now(timezone.utc);eco.last_settled_at=now-timedelta(minutes=6);pop.last_population_tick_at=now-timedelta(minutes=6);s.commit()
 with S() as s:
  settle_economy(s,cid,now);eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==cid));pop=s.scalar(select(PopulationState).where(PopulationState.city_id==cid))
  assert eco.loyalty==51 and pop.population==600

def test_population_really_limits_resource_labor(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  pop=s.scalar(select(PopulationState).where(PopulationState.city_id==cid));pop.population=5
  add_field(s,cid,'farm',10);s.flush();snap=resource_production_snapshot(s,cid)
  assert snap['labor_factor']<1 and snap['idle_population']==0 and snap['resources']['food']['effective_per_hour']<snap['resources']['food']['base_per_hour']

def test_troop_upkeep_is_net_food_and_outside_is_double(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  s.add(TroopQuantity(city_id=cid,troop_type_key='warrior',quantity=100));s.flush()
  assert troop_food_upkeep(s,cid)['garrisoned_per_hour']==300
  a=Army(player_id=pid,troops={'warrior':10},resources={});s.add(a);s.flush();now=datetime.now(timezone.utc)
  s.add(March(army_id=a.id,source_city_id=cid,target_x=2,target_y=2,mission='ATTACK',departed_at=now,arrives_at=now+timedelta(hours=1),status='MARCHING'));s.flush()
  assert troop_food_upkeep(s,cid)['outside_per_hour']==60

def test_offline_food_production_and_upkeep_settle_together(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  add_field(s,cid,'farm',1);s.add(TroopQuantity(city_id=cid,troop_type_key='warrior',quantity=10));s.flush()
  eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==cid));now=datetime.now(timezone.utc);settle_economy(s,cid,now);rp=s.scalar(select(ResourceProduction).where(ResourceProduction.city_id==cid,ResourceProduction.resource_kind=='food'));food=s.scalar(select(Resource).where(Resource.city_id==cid,Resource.kind=='food'));food.quantity=0;before=0
  eco.last_settled_at=now-timedelta(hours=2);rp.last_calculated_at=now-timedelta(hours=2);s.flush();settle_economy(s,cid,now);s.expire_all();food=s.scalar(select(Resource).where(Resource.city_id==cid,Resource.kind=='food'))
  # Lv1 farm 100/h - 10 warriors*3/h = 70/h => +140
  assert food.quantity==before+140

def test_hero_salary_reduces_real_gold(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  h=Hero(player_id=pid,city_id=cid,name='H',level=10);s.add(h);eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==cid));eco.gold=1000
  now=datetime.now(timezone.utc);eco.last_settled_at=now-timedelta(hours=1);pop=s.scalar(select(PopulationState).where(PopulationState.city_id==cid));pop.last_population_tick_at=now;s.flush();settle_economy(s,cid,now);s.expire_all();eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==cid))
  assert eco.gold==800

def test_warehouse_protection_is_in_economy_snapshot(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  b=Building(city_id=cid,plot_kind='CITY',plot_index=3,definition_key='warehouse',level=1);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=1));s.flush()
  snap=economy_snapshot(s,cid);assert snap['warehouse_capacity']==10000 and 'food' in snap['warehouse_protected']

def test_economy_debug_lists_modifier_components(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  add_field(s,cid,'farm',1);s.flush();d=economy_debug(s,cid)
  f=d['resources']['food'];assert all(k in f for k in ('base_per_hour','production_percent','technology_bonus_percent','mayor_bonus_percent','valley_bonus_percent','item_bonus_percent','population_factor','effective_per_hour'))
  assert 'tax' in d['formulae'] and d['troop_food']['total_per_hour']>=0

def test_simultaneous_settlement_cannot_double_generate(tmp_path):
 S,pid,cid=setup(tmp_path)
 with S() as s:
  add_field(s,cid,'farm',1);now=datetime.now(timezone.utc);settle_economy(s,cid,now)
  food=s.scalar(select(Resource).where(Resource.city_id==cid,Resource.kind=='food'));food.quantity=0
  eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==cid));rp=s.scalar(select(ResourceProduction).where(ResourceProduction.city_id==cid,ResourceProduction.resource_kind=='food'))
  start=now-timedelta(hours=1);eco.last_settled_at=start;rp.last_calculated_at=start;s.commit()
 def run():
  with S() as s:
   settle_economy(s,cid,now);s.commit()
 with ThreadPoolExecutor(max_workers=2) as ex:list(ex.map(lambda _:run(),range(2)))
 with S() as s:
  food=s.scalar(select(Resource).where(Resource.city_id==cid,Resource.kind=='food'))
  # Exactly one hour of Lv1 farm production, not two.
  assert food.quantity==100
