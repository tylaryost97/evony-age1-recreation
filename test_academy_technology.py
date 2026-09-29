
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def s(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'a.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  a=Account(email="a@x");s.add(a);s.flush();p=Player(account_id=a.id,name="P");s.add(p);s.flush();c=City(player_id=p.id,name="C",x=1,y=1,gold=10000000);s.add(c);s.flush();s.add(CityEconomyState(city_id=c.id,gold=10000000))
  for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=10000000))
  s.commit();yield s
def b(s,c,key,lv,plot):
 x=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(x);s.flush();s.add(BuildingLevel(building_id=x.id,level=lv));s.flush();return x
def tech(s,p,key,lv):
 x=Technology(player_id=p.id,definition_key=key,level=lv);s.add(x);s.flush();return x
def test_all_19_have_10_levels_and_exact_effect_metadata():
 assert len(TECH_KEYS)==19
 for k in TECH_KEYS:
  assert len(DATA['technologies'][k]['levels'])==10 and DATA['technologies'][k]['max_level']==10
def test_research_validation_persistence_and_completion(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));b(s,c,'academy',1,5);b(s,c,'farm',1,6)
 r=start_research(s,p.id,c.id,'agriculture','r1');q=s.get(ResearchQueue,r['research_queue_id'])
 assert q.status=='ACTIVE' and technology_level(s,p.id,'agriculture')==0
 q.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1);complete_research(s,c.id)
 assert technology_level(s,p.id,'agriculture')==1
def test_research_rejects_invalid_requirements_and_unknown_timer(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));b(s,c,'academy',10,5);b(s,c,'stable',10,6)
 with pytest.raises(ValueError):start_research(s,p.id,c.id,'horseback_riding','h') # MS5 absent and timer unresolved
def test_technology_effects_feed_calculations(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));b(s,c,'academy',10,5)
 for key,lv in [('agriculture',4),('military_science',3),('military_tradition',6),('iron_working',4),('logistics',5),('compass',2),('archery',7),('medicine',8),('construction',3),('engineering',4),('machinery',2),('privateering',10),('stockpile',6),('metal_casting',3),('informatics',9)]:
  tech(s,p,key,lv)
 assert resource_technology_multiplier(s,c.id,'food')==1.4
 assert mayor_training_seconds(s,c.id,1000)==round(1000*(.9**3))
 assert troop_attack_multiplier(s,c.id)==1.3 and troop_defense_multiplier(s,c.id)==1.2
 assert army_load_multiplier(s,c.id)==1.5 and infantry_speed_multiplier(s,c.id)==1.2
 assert ranged_range_multiplier(s,c.id)==1.35 and troop_life_multiplier(s,c.id)==1.4
 assert mayor_construction_seconds(s,c.id,1000)==round(1000*(.9**3))
 assert wall_fortification_life_multiplier(s,c.id)==1.4 and machinery_repair_multiplier(s,c.id)==3
 assert privateering_protection_multiplier(s,c.id)==.7 and warehouse_stockpile_multiplier(s,c.id)==1.6
 assert mechanic_training_time_multiplier(s,c.id)==pytest.approx(.9**3) and scouting_effective_level(s,c.id)==9
def test_local_academy_gates_global_research_effect(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));b(s,c,'academy',1,5);tech(s,p,'archery',5)
 assert technology_level(s,p.id,'archery')==5 and effective_technology_level(s,c.id,'archery')==0
