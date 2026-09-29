
from datetime import datetime,timezone,timedelta
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
def test_exact_wall_table():
 exp=[(3000,1500,10000,500,1800,10000,1000),(6000,3000,20000,1000,3600,30000,3000),(12000,6000,40000,2000,7200,60000,6000),(24000,12000,80000,4000,14400,100000,10000),(48000,24000,160000,8000,28800,150000,15000),(96000,48000,320000,16000,57600,210000,21000),(192000,96000,640000,32000,115200,280000,28000),(384000,192000,1280000,64000,230400,360000,36000),(768000,384000,2560000,128000,460800,450000,45000),(1536000,768000,5120000,256000,921600,550000,55000)]
 for lv,e in enumerate(exp,1):
  d=DATA['building_levels']['walls'][str(lv)];assert (d['cost']['food'],d['cost']['lumber'],d['cost']['stone'],d['cost']['iron'],d['seconds'],d['durability'],d['fortified_spaces'])==e
 assert DATA['building_levels']['walls']['10']['item_cost']=={'michelangelos_script':1}
def test_exact_fortification_definitions():
 d=DATA['fortifications'];assert d['trap']['space']==1 and d['trap']['base_seconds']==60
 assert d['abatis']['wall_level']==2 and d['abatis']['technology_requirements']=={'metal_casting':1}
 assert d['archer_tower']['wall_level']==3 and d['archer_tower']['technology_requirements']=={'archery':3} and d['archer_tower']['life']==2000
 assert d['rolling_log']['wall_level']==5 and d['rolling_log']['technology_requirements']=={'metal_casting':5}
 assert d['defensive_trebuchet']['wall_level']==7 and d['defensive_trebuchet']['technology_requirements']=={'metal_casting':6} and d['defensive_trebuchet']['one_shot']
def test_wall_capacity_engineering_range_and_machinery(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'w.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  a=Account(email='x@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1);s.add(c);s.flush()
  for key,lv,plot in [('walls',10,33),('academy',10,2)]:b=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv))
  for key,lv in [('engineering',5),('archery',10),('machinery',10)]:s.add(Technology(player_id=p.id,definition_key=key,level=lv))
  s.flush();cap=wall_capacity(s,c.id);assert cap['spaces']==55000 and cap['effective_durability']==825000
  assert archer_tower_range(s,c.id)==2600 and fortification_repair_rate(s,c.id,'trap')==.55

def test_fortification_queue_consumes_resources_reserves_space_and_completes(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'q.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  a=Account(email='q@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1);s.add(c);s.flush()
  for key,lv,plot in [('walls',3,33),('academy',4,2)]:b=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv))
  s.add(Technology(player_id=p.id,definition_key='archery',level=3))
  for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=1000000))
  s.flush();r=build_fortification(s,p.id,c.id,'archer_tower',100,'at')
  assert wall_capacity(s,c.id)['used']==300
  q=s.get(FortificationQueue,r['queue_id']);q.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1);s.flush();complete_fortifications(s,c.id)
  f=s.scalar(select(Fortification).where(Fortification.city_id==c.id,Fortification.definition_key=='archer_tower'));assert f.quantity==100
