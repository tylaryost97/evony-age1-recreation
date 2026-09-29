
from datetime import datetime,timezone
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'q.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();a=Account(email='q@x');s.add(a);s.flush();p=Player(account_id=a.id,name='Q');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1,population=100,idle_population=100);s.add(c);s.flush()
 s.add(PopulationState(city_id=c.id,population=100,idle_population=100,population_limit=500,last_population_tick_at=datetime.now(timezone.utc)));s.add(CityEconomyState(city_id=c.id,gold=0,last_settled_at=datetime.now(timezone.utc)))
 for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=0,capacity=999999,updated_at=datetime.now(timezone.utc)))
 s.add(PlayerProgression(player_id=p.id,prestige=0,honor=0,title_rank_key='civilian'));s.commit();yield s,p,c;s.close()
def add_building(s,c,key,lv):
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=10+len(s.scalars(select(Building)).all()),definition_key=key,level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv));s.commit()
def test_building_quest_derived_from_real_state(ctx):
 s,p,c=ctx;assert not evaluate_quest(s,p.id,'cottage_1')['completed'];add_building(s,c,'cottage',1);assert evaluate_quest(s,p.id,'cottage_1')['completed']
def test_technology_and_troop_state(ctx):
 s,p,c=ctx;s.add(Technology(player_id=p.id,definition_key='agriculture',level=1));s.add(TroopQuantity(city_id=c.id,troop_type_key='worker',quantity=10));s.commit()
 assert evaluate_quest(s,p.id,'agriculture_1')['completed'] and evaluate_quest(s,p.id,'train_workers_10')['completed']
def test_population_hero_alliance_prestige(ctx):
 s,p,c=ctx;pop=s.scalar(select(PopulationState).where(PopulationState.city_id==c.id));pop.population_limit=1000;s.add(Hero(player_id=p.id,city_id=c.id,name='H',level=1,politics=1,attack=1,intelligence=1,loyalty=70,captured=False));a=Alliance(name='A');s.add(a);s.flush();s.add(AllianceMember(alliance_id=a.id,player_id=p.id,rank='MEMBER'));s.scalar(select(PlayerProgression).where(PlayerProgression.player_id==p.id)).prestige=1000;s.commit()
 assert evaluate_quest(s,p.id,'population_1000')['completed'];assert evaluate_quest(s,p.id,'recruit_hero')['completed'];assert evaluate_quest(s,p.id,'join_alliance')['completed'];assert evaluate_quest(s,p.id,'prestige_1000')['completed']
def test_event_quest_requires_authoritative_event(ctx):
 s,p,c=ctx;assert not evaluate_quest(s,p.id,'scout_valley')['completed'];record_quest_event(s,p.id,'SCOUT_VALLEY',level=3,x=2,y=2);s.commit();assert evaluate_quest(s,p.id,'scout_valley')['completed']
def test_minimum_level_event(ctx):
 s,p,c=ctx;record_quest_event(s,p.id,'CONQUER_VALLEY',level=7);assert not evaluate_quest(s,p.id,'valley8_conquer')['completed'];record_quest_event(s,p.id,'CONQUER_VALLEY',level=8);assert evaluate_quest(s,p.id,'valley8_conquer')['completed']
def test_claim_once_and_rewards_authoritative(ctx):
 s,p,c=ctx;add_building(s,c,'cottage',1);r=claim_quest(s,p.id,'cottage_1','claim1');assert not r['duplicate']
 food=s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food'));assert food.quantity==200
 item=s.scalar(select(PlayerItem).where(PlayerItem.player_id==p.id,PlayerItem.item_key=='aries_amulet'));assert item.quantity==1
 r2=claim_quest(s,p.id,'cottage_1','claim2');assert r2['duplicate'];assert food.quantity==200
def test_idempotent_same_request(ctx):
 s,p,c=ctx;add_building(s,c,'rally_spot',1);a=claim_quest(s,p.id,'rally_1','same');b=claim_quest(s,p.id,'rally_1','same');assert a==b
def test_prerequisite_chain(ctx):
 s,p,c=ctx;add_building(s,c,'cottage',2);assert not evaluate_quest(s,p.id,'cottage_2')['completed'];claim_quest(s,p.id,'cottage_1','one');assert evaluate_quest(s,p.id,'cottage_2')['completed']
def test_unknown_reward_never_fabricated(ctx):
 s,p,c=ctx;s.add(Hero(player_id=p.id,city_id=c.id,name='H',level=1,politics=1,attack=1,intelligence=1,loyalty=70,captured=False));s.commit();q=evaluate_quest(s,p.id,'recruit_hero');assert q['reward_status']=='HISTORICAL_VALUE_UNKNOWN' and q['rewards']=={}
