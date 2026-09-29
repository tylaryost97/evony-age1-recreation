from datetime import datetime,timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
from app.service import _mission_legal
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'a.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();a=Account(email='a@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1,population=1000,gold=10000,loyalty=100);s.add(c);s.flush();s.add(CityEconomyState(city_id=c.id,gold=10000,tax_rate=0,loyalty=100,grievance=20,last_settled_at=datetime.now(timezone.utc)));s.add(PopulationState(city_id=c.id,population=1000,idle_population=1000,population_limit=1000,last_population_tick_at=datetime.now(timezone.utc)))
 for k in ('food','lumber','stone','iron'):
  s.add(Resource(city_id=c.id,kind=k,quantity=10000,capacity=999999,updated_at=datetime.now(timezone.utc)));s.add(ResourceProduction(city_id=c.id,resource_kind=k,per_hour=0,last_calculated_at=datetime.now(timezone.utc)));s.add(ResourceCapacity(city_id=c.id,resource_kind=k,capacity=999999))
 s.commit();yield s,p,c;s.close()
def test_disaster_relief_verified_values(ctx):
 s,p,c=ctx;r=town_hall_comfort(s,p.id,c.id,'disaster_relief','x');assert r['cost']=={'kind':'food','amount':1000} and r['loyalty']==100 and r['grievance']==5
def test_praying_verified_values(ctx):
 s,p,c=ctx;r=town_hall_comfort(s,p.id,c.id,'praying','x');assert r['cost']=={'kind':'gold','amount':1000} and r['grievance']==15
def test_levy_amount_and_loyalty(ctx):
 s,p,c=ctx;r=town_hall_levy(s,p.id,c.id,'stone','x');assert r['amount']==500 and r['loyalty']==80
def test_exercise_is_functional(ctx):
 s,p,c=ctx;r=rally_exercise(s,c.id,{'warrior':100},{'warrior':10});assert r['status']=='SIMULATED' and r['winner'] in ('attacker','defender')
def test_occupy_restricted_to_wilderness(ctx):
 s,p,c=ctx;assert not _mission_legal(s,p.id,{'kind':'CITY','owner_player_id':999},'OCCUPY');assert _mission_legal(s,p.id,{'kind':'FLAT','owner_player_id':None},'OCCUPY')
