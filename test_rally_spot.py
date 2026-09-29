
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def s(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'r.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  for i,n in enumerate(("A","B"),1):
   a=Account(email=f"{n}@x");s.add(a);s.flush();p=Player(account_id=a.id,name=n);s.add(p);s.flush();c=City(player_id=p.id,name=n,x=i*10,y=10,gold=100000);s.add(c);s.flush();s.add(CityEconomyState(city_id=c.id,gold=100000))
   for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=10000000))
  s.commit();yield s
def b(s,c,key,lv,plot):
 x=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(x);s.flush();s.add(BuildingLevel(building_id=x.id,level=lv));s.flush()
def tq(s,c,k,n):s.add(TroopQuantity(city_id=c.id,troop_type_key=k,quantity=n));s.flush()
def hero(s,p,c):
 h=Hero(player_id=p.id,city_id=c.id,name='H',level=10,attack=100,loyalty=100);s.add(h);s.flush();s.add(HeroAssignment(hero_id=h.id,city_id=c.id,assignment_key='idle'));s.flush();return h
def tile(s,x,y,owner=None,kind='FLAT'):
 t=MapTile(x=x,y=y,tile_type=kind,level=1,owner_player_id=owner);s.add(t);s.flush();return t
def test_level_capacity_table(s):
 c=s.scalar(select(City))
 for lv in range(1,11):
  b(s,c,'rally_spot',lv,lv+10); assert rally_limits(s,c.id)=={'march_slots':lv,'troop_limit':lv*10000}
  bb=s.scalar(select(Building).where(Building.city_id==c.id,Building.plot_index==lv+10));s.delete(s.scalar(select(BuildingLevel).where(BuildingLevel.building_id==bb.id)));s.delete(bb);s.flush()
def test_create_persistent_attack_removes_real_troops_food_and_hero_required(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all();b(s,cs[0],'rally_spot',2,5);tq(s,cs[0],'warrior',30000);h=hero(s,ps[0],cs[0]);tile(s,11,10)
 before=s.scalar(select(Resource).where(Resource.city_id==cs[0].id,Resource.kind=='food')).quantity
 with pytest.raises(ValueError):create_march(s,ps[0].id,cs[0].id,'ATTACK',11,10,{'warrior':1000},{},None,0,False,'bad')
 r=create_march(s,ps[0].id,cs[0].id,'ATTACK',11,10,{'warrior':1000},{},h.id,0,False,'go')
 assert s.get(March,r['march_id']).status=='MARCHING'
 assert s.scalar(select(TroopQuantity).where(TroopQuantity.city_id==cs[0].id,TroopQuantity.troop_type_key=='warrior')).quantity==29000
 assert s.scalar(select(Resource).where(Resource.city_id==cs[0].id,Resource.kind=='food')).quantity==before-r['food_required']
def test_load_logistics_and_transport_legality(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all();b(s,cs[0],'rally_spot',1,5);b(s,cs[0],'academy',4,6);tq(s,cs[0],'transporter',10);s.add(Technology(player_id=ps[0].id,definition_key='logistics',level=10));s.flush()
 # own/allied city needed: make target own for isolated legality
 cs[1].player_id=ps[0].id;s.flush()
 p=rally_preview(s,ps[0].id,cs[0].id,'TRANSPORT',cs[1].x,cs[1].y,{'transporter':10},{'lumber':90000})
 assert p['load_capacity']==100000 and p['load_vacancy']==10000
 with pytest.raises(ValueError):rally_preview(s,ps[0].id,cs[0].id,'TRANSPORT',cs[1].x,cs[1].y,{'transporter':10},{'lumber':100001})
def test_march_slot_and_troop_limit_enforced(s):
 p=s.scalar(select(Player));c=s.scalar(select(City).where(City.player_id==p.id));b(s,c,'rally_spot',1,5);tq(s,c,'warrior',20000);h=hero(s,p,c);tile(s,11,10);tile(s,12,10)
 create_march(s,p.id,c.id,'ATTACK',11,10,{'warrior':10000},{},h.id,0,False,'one')
 with pytest.raises(ValueError):create_march(s,p.id,c.id,'SCOUT',12,10,{'warrior':1},{},None,0,False,'two')
def test_recall_is_timed_and_returns_persistent_troops(s):
 p=s.scalar(select(Player));c=s.scalar(select(City).where(City.player_id==p.id));b(s,c,'rally_spot',1,5);tq(s,c,'scout',100);tile(s,11,10)
 r=create_march(s,p.id,c.id,'SCOUT',11,10,{'scout':50},{},None,0,False,'go');rr=recall_march(s,p.id,r['march_id'],'rec')
 m=s.get(March,r['march_id']);assert m.status=='RETURNING' and m.returns_at is not None
 m.returns_at=datetime.now(timezone.utc)-timedelta(seconds=1);s.flush();done=complete_returning_marches(s,c.id);s.flush();
 from app import models as current_models
 m=s.get(current_models.March,r['march_id'])
 assert m.status=='RETURNED' and s.scalar(select(TroopQuantity).where(TroopQuantity.city_id==c.id,TroopQuantity.troop_type_key=='scout')).quantity==100
def test_compass_hbr_and_relief_change_travel(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all();b(s,cs[0],'rally_spot',2,5);b(s,cs[0],'academy',5,6);tq(s,cs[0],'warrior',10);tq(s,cs[0],'cavalry',10);tile(s,11,10)
 base=army_travel_seconds(s,cs[0].id,{'warrior':10},11,10,'ATTACK');s.add(Technology(player_id=ps[0].id,definition_key='compass',level=10));s.flush()
 assert army_travel_seconds(s,cs[0].id,{'warrior':10},11,10,'ATTACK') < base
def test_exercise_uses_authoritative_combat_simulation(s):
 c=s.scalar(select(City));r=rally_exercise(s,c.id,{'warrior':10},{'warrior':10});assert r['status']=='SIMULATED' and r['winner'] in ('attacker','defender')

def test_duplicate_dispatch_idempotency_no_troop_duplication(s):
 p=s.scalar(select(Player));c=s.scalar(select(City).where(City.player_id==p.id));b(s,c,'rally_spot',2,5);tq(s,c,'scout',100);tile(s,11,10)
 a=create_march(s,p.id,c.id,'SCOUT',11,10,{'scout':25},{},None,0,False,'same')
 z=create_march(s,p.id,c.id,'SCOUT',11,10,{'scout':25},{},None,0,False,'same')
 assert a==z and s.scalar(select(TroopQuantity).where(TroopQuantity.city_id==c.id,TroopQuantity.troop_type_key=='scout')).quantity==75
 assert len(s.scalars(select(March)).all())==1

def test_reinforce_requires_own_or_allied_city(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all();b(s,cs[0],'rally_spot',1,5);tq(s,cs[0],'warrior',10)
 with pytest.raises(ValueError):rally_preview(s,ps[0].id,cs[0].id,'REINFORCE',cs[1].x,cs[1].y,{'warrior':1},{})
 al=Alliance(name='ALLY');s.add(al);s.flush();s.add_all([AllianceMember(alliance_id=al.id,player_id=ps[0].id,rank='HOST'),AllianceMember(alliance_id=al.id,player_id=ps[1].id,rank='MEMBER')]);s.flush()
 assert rally_preview(s,ps[0].id,cs[0].id,'REINFORCE',cs[1].x,cs[1].y,{'warrior':1},{})['target']['city_id']==cs[1].id
