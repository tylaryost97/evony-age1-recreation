
from datetime import datetime,timezone,timedelta
from sqlalchemy import select
from app.models import *
from app.service import *
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base

@pytest.fixture
def session(tmp_path):
 engine=create_engine(f"sqlite:///{tmp_path/'fh.db'}",connect_args={"check_same_thread":False})
 Base.metadata.create_all(engine); S=sessionmaker(engine,expire_on_commit=False)
 with S() as s:
  a=Account(email="fh@test.invalid");s.add(a);s.flush();p=Player(account_id=a.id,name="FH");s.add(p);s.flush()
  c=City(player_id=p.id,name="FH City",x=900,y=900,gold=1000000);s.add(c);s.flush()
  s.add(CityEconomyState(city_id=c.id,gold=1000000));s.commit();yield s

def add_building(s,city,key,level,plot):
 b=Building(city_id=city.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=level);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=level));s.flush();return b

def addhero(s,p,c,name,level,pol,atk,intel):
 h=Hero(player_id=p.id,city_id=c.id,name=name,level=level,politics=pol,attack=atk,intelligence=intel,loyalty=70);s.add(h);s.flush()
 s.add(HeroStats(hero_id=h.id,politics=pol,attack=atk,intelligence=intel));s.add(HeroExperience(hero_id=h.id,level=level,experience=123));s.add(HeroAssignment(hero_id=h.id,city_id=c.id,assignment_key='idle'));s.flush();return h

def test_capacity_all_levels(session):
 p=session.scalar(select(Player)); c=session.scalar(select(City).where(City.player_id==p.id))
 for level in range(1,11):
  b=add_building(session,c,'feasting_hall',level,20+level)
  assert feasting_hall_capacity(session,c.id)==level
  session.delete(session.scalar(select(BuildingLevel).where(BuildingLevel.building_id==b.id)));session.delete(b);session.flush()

def test_roster_salary_and_mayor_effects(session):
 p=session.scalar(select(Player));c=session.scalar(select(City).where(City.player_id==p.id));add_building(session,c,'feasting_hall',3,20)
 h=addhero(session,p,c,'Pol',10,100,20,30)
 r=feasting_hall_roster(session,c.id)[0]
 assert r['salary_per_hour']==200 and r['experience']==123 and r['loyalty']==70
 appoint_mayor(session,p.id,c.id,h.id,'mayor1')
 assert mayor_production_multiplier(session,c.id)==2.0
 assert mayor_construction_seconds(session,c.id,1000)==round(1000*(.995**100))
 assert mayor_training_seconds(session,c.id,1000)==round(1000*(.995**20))
 assert mayor_research_seconds(session,c.id,1000)==round(1000*(.995**30))

def test_march_status_blocks_mayor_and_dismiss(session):
 p=session.scalar(select(Player));c=session.scalar(select(City).where(City.player_id==p.id));add_building(session,c,'feasting_hall',2,20);h=addhero(session,p,c,'Marcher',3,20,80,10)
 a=Army(player_id=p.id,hero_id=h.id,troops={},resources={});session.add(a);session.flush()
 now=datetime.now(timezone.utc);session.add(March(army_id=a.id,source_city_id=c.id,target_x=1,target_y=1,mission='ATTACK',departed_at=now,arrives_at=now+timedelta(hours=1),returns_at=now+timedelta(hours=2),status='MARCHING'));session.flush()
 assert feasting_hall_roster(session,c.id)[0]['status']['key']=='march'
 import pytest
 with pytest.raises(ValueError): appoint_mayor(session,p.id,c.id,h.id,'m2')
 with pytest.raises(ValueError): dismiss_hero(session,p.id,c.id,h.id,'d2')

def test_capture_requires_vacancy(session):
 p=session.scalar(select(Player));c=session.scalar(select(City).where(City.player_id==p.id));add_building(session,c,'feasting_hall',1,20)
 h=capture_hero_into_city(session,p.id,c.id,'Captured',5,40,50,30)
 assert h and h.captured and h.loyalty==0
 assert capture_hero_into_city(session,p.id,c.id,'NoSeat',2,1,1,1) is None
 release_captured_hero(session,p.id,c.id,h.id,'release1')
 assert capture_hero_into_city(session,p.id,c.id,'NowSeat',2,1,1,1) is not None
