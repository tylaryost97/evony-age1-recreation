
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
  for i,n in enumerate(('D','A'),1):
   ac=Account(email=f'{n}@x');s.add(ac);s.flush();p=Player(account_id=ac.id,name=n);s.add(p);s.flush();c=City(player_id=p.id,name=n,x=i*10,y=10);s.add(c);s.flush();s.add(PlayerProgression(player_id=p.id,prestige=100*i,honor=10*i,title_rank_key='Knight'))
  s.commit();yield s
def b(s,c,key,lv,plot=5):
 x=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(x);s.flush();s.add(BuildingLevel(building_id=x.id,level=lv));s.flush();return x
def incoming(s,defc,attp,attc):
 h=Hero(player_id=attp.id,city_id=attc.id,name='Enemy',level=37,attack=90);s.add(h);s.flush()
 a=Army(player_id=attp.id,hero_id=h.id,troops={'archer':12345,'cavalry':678},resources={});s.add(a);s.flush();now=datetime.now(timezone.utc)
 m=March(army_id=a.id,source_city_id=attc.id,target_x=defc.x,target_y=defc.y,mission='ATTACK',departed_at=now,arrives_at=now+timedelta(hours=1),status='MARCHING');s.add(m);s.flush();return m
def test_exact_beacon_table():
 expected=[(150,1000,3000,300,450),(300,2000,6000,600,900),(600,4000,12000,1200,1800),(1200,8000,24000,2400,3600),(2400,16000,48000,4800,7200),(4800,32000,96000,9600,14400),(9600,64000,192000,19200,28800),(19200,128000,384000,38400,57600),(38400,256000,768000,76800,115200),(76800,512000,1536000,153600,230400)]
 for lv,row in enumerate(expected,1):
  d=DATA['building_levels']['beacon_tower'][str(lv)];assert (d['cost']['food'],d['cost']['lumber'],d['cost']['stone'],d['cost']['iron'],d['seconds'])==row
 assert DATA['building_levels']['beacon_tower']['1']['prerequisites']==[{'building':'barracks','level':1}]
 assert DATA['building_levels']['beacon_tower']['10']['item_cost']=={'michelangelos_script':1}
def test_alert_information_unlocks_exactly_by_level(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all();incoming(s,cs[0],ps[1],cs[1]);bld=b(s,cs[0],'beacon_tower',1)
 a=beacon_incoming_alerts(s,cs[0].id)[0];assert a=={'march_id':1,'warning':True}
 bld.level=7;s.scalar(select(BuildingLevel).where(BuildingLevel.building_id==bld.id)).level=7;s.flush();a=beacon_incoming_alerts(s,cs[0].id)[0]
 assert a['purpose']=='ATTACK' and 'arrives_at' in a and 'enemy_lord_status' in a and a['departure_location']=={'x':20,'y':10}
 assert a['arms_branch']==['archer','cavalry'] and a['troops']['archer']=='tens of thousands'
 bld.level=10;s.scalar(select(BuildingLevel).where(BuildingLevel.building_id==bld.id)).level=10;s.flush();a=beacon_incoming_alerts(s,cs[0].id)[0]
 assert a['troops']['archer']==12345 and a['hero_level']==37 and 'archery' in a['military_technology']
def test_no_tower_no_intelligence(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all();incoming(s,cs[0],ps[1],cs[1]);assert beacon_incoming_alerts(s,cs[0].id)==[]
