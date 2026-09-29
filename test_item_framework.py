
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'i.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();a=Account(email='i@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=10,y=10,population=100,gold=10000);s.add(c);s.flush();s.add(CityCoordinate(city_id=c.id,x=10,y=10));s.add(PopulationState(city_id=c.id,population=100,idle_population=100,population_limit=1000,last_population_tick_at=datetime.now(timezone.utc)));s.add(CityEconomyState(city_id=c.id,gold=10000,last_settled_at=datetime.now(timezone.utc)))
 for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=10000,capacity=999999,updated_at=datetime.now(timezone.utc)));s.add(ResourceProduction(city_id=c.id,resource_kind=k,per_hour=0,last_calculated_at=datetime.now(timezone.utc)));s.add(ResourceCapacity(city_id=c.id,resource_kind=k,capacity=999999))
 tile=MapTile(x=10,y=10,tile_type='PLAYER_CITY',owner_player_id=p.id);s.add(tile)
 for k in ITEM_DEFINITIONS:s.add(PlayerItem(player_id=p.id,item_key=k,quantity=10))
 s.commit();yield s,p,c;s.close()
def test_inventory_quantities(ctx):
 s,p,c=ctx;x=inventory_snapshot(s,p.id);assert next(i for i in x['items'] if i['key']=='beginner_guidelines')['quantity']==10
def test_guideline_reduces_construction_timer(ctx):
 s,p,c=ctx;b=Building(city_id=c.id,plot_kind='CITY',plot_index=2,definition_key='cottage',level=1);s.add(b);s.flush();now=datetime.now(timezone.utc);q=ConstructionQueue(city_id=c.id,building_id=b.id,target_level=2,started_at=now,completes_at=now+timedelta(hours=2),status='ACTIVE');s.add(q);s.commit();before=q.completes_at
 use_inventory_item(s,p.id,'beginner_guidelines',{'type':'construction','id':q.id},'a');s.expire_all();q=s.get(ConstructionQueue,q.id);assert ((before.replace(tzinfo=None)-q.completes_at.replace(tzinfo=None)).total_seconds())==900
def test_napoleon_once_per_training_group(ctx):
 s,p,c=ctx;now=datetime.now(timezone.utc);q=TrainingQueue(city_id=c.id,troop_type_key='worker',quantity=10,queued_at=now,started_at=now,completes_at=now+timedelta(hours=1),status='ACTIVE');s.add(q);s.commit();use_inventory_item(s,p.id,'napoleons_diary',{'type':'training','id':q.id},'n1')
 with pytest.raises(ValueError,match='already applied'):use_inventory_item(s,p.id,'napoleons_diary',{'type':'training','id':q.id},'n2')
def test_production_buff_persists_and_stacking_blocked(ctx):
 s,p,c=ctx;r=use_inventory_item(s,p.id,'plowshares',{'city_id':c.id},'p1');s.commit();assert datetime.fromisoformat(r['expires_at'])>datetime.now(timezone.utc)
 assert resource_item_bonus_percent(s,c.id,'food')==25
 with pytest.raises(ValueError,match='already active'):use_inventory_item(s,p.id,'iron_rake',{'city_id':c.id},'p2')
def test_hero_xp_and_timed_buff(ctx):
 s,p,c=ctx;h=Hero(player_id=p.id,city_id=c.id,name='H',level=1,experience=0,politics=10,attack=10,intelligence=10,loyalty=70);s.add(h);s.flush();s.add(HeroExperience(hero_id=h.id,level=1,experience=0));s.commit()
 use_inventory_item(s,p.id,'anabasis',{'city_id':c.id,'hero_id':h.id},'h1');s.expire_all();h=s.get(Hero,h.id);assert h.experience==1000
 use_inventory_item(s,p.id,'excalibur',{'city_id':c.id,'hero_id':h.id},'h2');assert hero_effective_stats(s,h.id)['attack']==12
def test_civil_code_actual_population_effect(ctx):
 s,p,c=ctx;r=use_inventory_item(s,p.id,'civil_code',{'city_id':c.id},'cc');s.expire_all();c=s.get(City,c.id);assert r['population_added']==200 and c.population==300
def test_advanced_teleport_moves_city_releases_valley_and_creates_lock(ctx):
 s,p,c=ctx;vt=MapTile(x=11,y=10,tile_type='VALLEY',level=1,owner_player_id=p.id);dest=MapTile(x=20,y=20,tile_type='FLAT',level=1,owner_player_id=None);s.add_all([vt,dest]);s.flush();v=Valley(map_tile_id=vt.id,valley_type='FOREST',level=1,city_id=c.id,defenders={});s.add(v);s.commit()
 r=use_inventory_item(s,p.id,'adv_city_teleporter',{'city_id':c.id,'x':20,'y':20},'tp');s.expire_all();c=s.get(City,c.id);v=s.get(Valley,v.id);assert (c.x,c.y)==(20,20) and v.city_id is None and r['march_lock_expires_at']
def test_medals_not_directly_consumable(ctx):
 s,p,c=ctx
 with pytest.raises(ValueError,match='associated game mechanic'):use_inventory_item(s,p.id,'cross_medal',{},'m')
def test_unknown_amulet_prize_not_fabricated(ctx):
 s,p,c=ctx
 with pytest.raises(ValueError,match='associated game mechanic'):use_inventory_item(s,p.id,'aries_amulet',{},'amu')
def test_idempotent_use(ctx):
 s,p,c=ctx;r1=use_inventory_item(s,p.id,'civil_code',{'city_id':c.id},'same');r2=use_inventory_item(s,p.id,'civil_code',{'city_id':c.id},'same');assert r1==r2
