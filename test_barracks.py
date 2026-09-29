from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def s(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'b.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  a=Account(email='a@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1,population=100000,idle_population=100000);s.add(c);s.flush();s.add(PopulationState(city_id=c.id,population=100000,idle_population=100000,population_limit=100000))
  for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=100000000))
  s.commit();yield s
def b(s,c,key,lv,plot):
 x=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(x);s.flush();s.add(BuildingLevel(building_id=x.id,level=lv));s.flush();return x
def tech(s,p,k,l):s.add(Technology(player_id=p.id,definition_key=k,level=l));s.flush()
def test_exact_unit_definitions():
 exp={
 'worker':(1,{},50,150,0,10,1,50,100,5,10,200,2,180,10),'warrior':(1,{},80,100,0,50,1,25,200,50,50,20,3,200,20),'scout':(2,{'informatics':1},120,200,0,150,1,100,100,20,20,5,5,3000,20),'pikeman':(2,{'military_tradition':1},150,500,0,100,1,150,300,150,150,40,6,300,50),'swordsman':(3,{'iron_working':1},200,150,0,400,1,225,350,100,250,30,7,275,30),'archer':(4,{'archery':1},300,350,0,300,2,350,250,120,50,25,9,250,1200),'cavalry':(5,{'horseback_riding':1},1000,600,0,500,3,500,500,250,180,100,18,1000,100),'cataphract':(7,{'iron_working':5,'horseback_riding':5},2000,500,0,2500,6,1500,1000,350,350,80,35,750,80),'transporter':(6,{'logistics':1,'metal_casting':3},600,1500,0,350,4,1000,700,10,60,5000,10,150,10),'ballista':(9,{'metal_casting':5,'archery':6},2500,3000,0,1800,5,3000,320,450,160,35,50,100,1400),'battering_ram':(9,{'metal_casting':8},4000,6000,0,1500,10,4500,5000,250,160,45,100,120,600),'catapult':(10,{'metal_casting':10,'archery':10},5000,5000,8000,1200,8,6000,480,600,200,75,250,80,1500)}
 assert set(DATA['troop_types'])==set(exp)
 for k,v in exp.items():
  x=DATA['troop_types'][k]; got=(x['barracks_level'],x['technology_requirements'],x['cost']['food'],x['cost']['lumber'],x['cost']['stone'],x['cost']['iron'],x['population'],x['base_training_seconds'],x['life'],x['attack'],x['defense'],x['load'],x['food_upkeep_per_hour'],x['speed_miles_per_1000_minutes'],x['range']);assert got==v
def test_barracks_levels_and_multiple_allowed(s):
 c=s.scalar(select(City));r=b(s,c,'rally_spot',1,2);a=b(s,c,'barracks',1,3);z=b(s,c,'barracks',10,4)
 assert barracks_level(s,a.id)==1 and barracks_level(s,z.id)==10 and DATA['buildings']['barracks']['repeatability']=='MULTIPLE_VERIFIED'
 assert DATA['building_levels']['barracks']['10']['troop_queue_slots']==10
def test_prerequisites_hide_not_unlock_by_icon(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));br=b(s,c,'barracks',10,3);b(s,c,'academy',10,4)
 miss=troop_prerequisite_status(s,c.id,br.id,'catapult');assert {x['key'] for x in miss}=={'metal_casting','archery'}
 tech(s,p,'metal_casting',10);tech(s,p,'archery',10);assert troop_prerequisite_status(s,c.id,br.id,'catapult')==[]
def test_training_consumes_resources_population_and_formula(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));br=b(s,c,'barracks',4,3);b(s,c,'academy',4,4);tech(s,p,'archery',1);tech(s,p,'military_science',3)
 h=Hero(player_id=p.id,city_id=c.id,name='Mayor',attack=100);s.add(h);s.flush();s.add(HeroAssignment(hero_id=h.id,city_id=c.id,assignment_key='mayor'));s.flush()
 before=s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food')).quantity
 r=train_troops(s,p.id,c.id,br.id,'archer',10,'train');q=s.get(TrainingQueue,r['training_queue_id'])
 assert r['duration_seconds']==round(350*10*(.9**3)*(.995**100));assert q.status=='ACTIVE'
 assert s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food')).quantity==before-3000
 pop=s.scalar(select(PopulationState).where(PopulationState.city_id==c.id));assert pop.idle_population==99980 and pop.population==99980
def test_each_barracks_has_independent_queue_and_level_capacity(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));a=b(s,c,'barracks',1,3);z=b(s,c,'barracks',2,4)
 train_troops(s,p.id,c.id,a.id,'warrior',1,'a1')
 with pytest.raises(ValueError):train_troops(s,p.id,c.id,a.id,'worker',1,'a2')
 train_troops(s,p.id,c.id,z.id,'warrior',1,'z1');r=train_troops(s,p.id,c.id,z.id,'worker',1,'z2')
 assert r['status']=='QUEUED' and len(barracks_queue(s,z.id))==2
def test_offline_completion_cascades_and_enters_inventory(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));br=b(s,c,'barracks',2,3)
 a=train_troops(s,p.id,c.id,br.id,'warrior',2,'a');z=train_troops(s,p.id,c.id,br.id,'worker',3,'z');q=s.get(TrainingQueue,a['training_queue_id']);q.completes_at=datetime.now(timezone.utc)-timedelta(seconds=200);s.flush();complete_training(s,c.id,br.id);s.flush()
 # enough offline elapsed to complete first and begin/possibly complete second depending duration
 tq=s.scalar(select(TroopQuantity).where(TroopQuantity.city_id==c.id,TroopQuantity.troop_type_key=='warrior'));assert tq.quantity==2
 q2=s.get(TrainingQueue,z['training_queue_id']);assert q2.status in ('ACTIVE','COMPLETE')
def test_idempotent_training_does_not_double_spend(s):
 p=s.scalar(select(Player));c=s.scalar(select(City));br=b(s,c,'barracks',2,3);before=s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food')).quantity
 a=train_troops(s,p.id,c.id,br.id,'warrior',10,'same');z=train_troops(s,p.id,c.id,br.id,'warrior',10,'same');assert a==z
 assert s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food')).quantity==before-800
 assert len(s.scalars(select(TrainingQueue)).all())==1
