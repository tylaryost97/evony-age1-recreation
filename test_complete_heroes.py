
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'h.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='h@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1,gold=1000000,population=1000,idle_population=1000);s.add(c);s.flush()
 s.add(CityEconomyState(city_id=c.id,gold=1000000,last_settled_at=datetime.now(timezone.utc)));s.add(PopulationState(city_id=c.id,population=1000,idle_population=1000,population_limit=1000,last_population_tick_at=datetime.now(timezone.utc)));s.add(PlayerProgression(player_id=p.id,title_rank_key='Prinzessin'))
 for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=1000000,capacity=9999999,updated_at=datetime.now(timezone.utc)))
 for key,lv,plot in [('inn',10,1),('feasting_hall',10,2),('academy',10,3),('rally_spot',10,4),('barracks',10,5)]:
  b=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv))
 h=Hero(player_id=p.id,city_id=c.id,name='H',level=10,experience=0,politics=50,attack=60,intelligence=70,loyalty=70,base_politics=50,base_attack=50,base_intelligence=50,allocated_attack=10);s.add(h);s.flush();s.add(HeroStats(hero_id=h.id,politics=50,attack=60,intelligence=70));s.add(HeroExperience(hero_id=h.id,level=10,experience=0));s.add(HeroAssignment(hero_id=h.id,city_id=c.id,assignment_key='idle'));s.commit()
 yield s,p,c,h
 s.close()
def test_xp_formula_level_and_attribute(ctx):
 s,p,c,h=ctx;assert hero_xp_for_next_level(10)==10000;add_hero_experience(s,h.id,10000);d=level_hero(s,p.id,c.id,h.id,'attack','lvl');s.refresh(h);assert d['level']==11 and d['attack']==61 and h.allocated_attack==11
def test_gold_reward_cost_loyalty_and_cooldown(ctx):
 s,p,c,h=ctx;eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id));before=eco.gold;r=reward_hero_gold(s,p.id,c.id,h.id,'r');s.refresh(h);s.refresh(eco);assert r['gold_cost']==1000 and h.loyalty==75 and eco.gold==before-1000
 with pytest.raises(ValueError,match='cooldown'):reward_hero_gold(s,p.id,c.id,h.id,'r2')
def test_age1_stat_items_feed_real_mayor_systems(ctx):
 s,p,c,h=ctx;s.scalar(select(HeroAssignment).where(HeroAssignment.hero_id==h.id)).assignment_key='mayor'
 for key in ('wealth_of_nations','excalibur','the_art_of_war'):s.add(PlayerItem(player_id=p.id,item_key=key,quantity=1))
 s.flush();base=mayor_stats(s,c.id);apply_hero_item(s,p.id,c.id,h.id,'wealth_of_nations','i1');assert mayor_stats(s,c.id)['politics']>base['politics']
 h.last_reward_at=datetime.now(timezone.utc)-timedelta(minutes=16);apply_hero_item(s,p.id,c.id,h.id,'excalibur','i2');assert mayor_training_seconds(s,c.id,10000)<int(10000*(.995**60))
 h.last_reward_at=datetime.now(timezone.utc)-timedelta(minutes=16);apply_hero_item(s,p.id,c.id,h.id,'the_art_of_war','i3');assert mayor_research_seconds(s,c.id,10000)<int(10000*(.995**70))
def test_redistribution_uses_preserved_base_and_holy_water(ctx):
 s,p,c,h=ctx;s.add(PlayerItem(player_id=p.id,item_key='holy_water',quantity=2));s.flush();r=redistribute_hero(s,p.id,c.id,h.id,'red');s.refresh(h);assert r['holy_water_consumed']==1 and h.attack==50 and h.unassigned_attribute_points==10
def test_legacy_redistribution_never_invents_base(ctx):
 s,p,c,h=ctx;h.base_attack=None;s.add(PlayerItem(player_id=p.id,item_key='holy_water',quantity=2));s.flush()
 with pytest.raises(ValueError,match='HISTORICAL_VALUE_UNKNOWN'):redistribute_hero(s,p.id,c.id,h.id,'red2')
def test_marching_hero_cannot_lead_second_march_or_be_mayor(ctx):
 s,p,c,h=ctx;a=Army(player_id=p.id,hero_id=h.id,troops={'warrior':1},resources={});s.add(a);s.flush();now=datetime.now(timezone.utc);s.add(March(army_id=a.id,source_city_id=c.id,target_x=2,target_y=2,mission='ATTACK',departed_at=now,arrives_at=now+timedelta(hours=1),status='MARCHING'));s.flush();assert hero_detail(s,p.id,c.id,h.id)['status']['key']=='march'
 with pytest.raises(ValueError,match='cannot be mayor'):appoint_mayor(s,p.id,c.id,h.id,'may')
def test_persuade_captured_hero_title_medals_gold(ctx):
 s,p,c,h=ctx;cap=capture_hero_into_city(s,p.id,c.id,'Cap',61,40,40,40,p.id);s.add(PlayerItem(player_id=p.id,item_key='rose_medal',quantity=2));s.flush();r=persuade_captured_hero(s,p.id,c.id,cap.id,'p');assert r['gold_cost']==61000 and r['medal_count']==2 and cap.loyalty==10 and not cap.captured
def test_salary_formula(ctx):
 s,p,c,h=ctx;assert hero_salary_per_hour(h)==200

def test_attack_attribute_feeds_verified_combat_attack_formula(ctx):
 s,p,c,h=ctx
 # Warrior base attack is 50. Hero A60 adds 30; MT0 => 80.
 assert combat_unit_attack(s,c.id,'warrior',h.id)==80
 s.add(Technology(player_id=p.id,definition_key='military_tradition',level=10));s.flush()
 # MT10 adds 25 more (50*10/20).
 assert combat_unit_attack(s,c.id,'warrior',h.id)==105
def test_highest_available_attack_hero_defends(ctx):
 s,p,c,h=ctx
 h2=Hero(player_id=p.id,city_id=c.id,name='Strong',level=1,attack=99,politics=1,intelligence=1);s.add(h2);s.flush();s.add(HeroStats(hero_id=h2.id,politics=1,attack=99,intelligence=1));s.add(HeroAssignment(hero_id=h2.id,city_id=c.id,assignment_key='idle'));s.flush()
 assert defending_hero(s,c.id).id==h2.id
