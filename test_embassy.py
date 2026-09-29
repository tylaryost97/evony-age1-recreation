
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *

@pytest.fixture
def s(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'e.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  for i,n in enumerate(("A","B","C"),1):
   a=Account(email=f"{n}@x");s.add(a);s.flush();p=Player(account_id=a.id,name=n);s.add(p);s.flush();c=City(player_id=p.id,name=n,x=i,y=i,gold=0);s.add(c);s.flush()
  s.commit();yield s
def emb(s,c,lv,plot=5):
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key='embassy',level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv));s.flush()
def test_embassy_all_levels(s):
 c=s.scalar(select(City))
 for lv in range(1,11):
  emb(s,c,lv,lv+5);assert embassy_level(s,c.id)==lv
  b=s.scalar(select(Building).where(Building.city_id==c.id,Building.plot_index==lv+5));s.delete(s.scalar(select(BuildingLevel).where(BuildingLevel.building_id==b.id)));s.delete(b);s.flush()
def test_join_create_and_permissions(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all()
 emb(s,cs[0],2);emb(s,cs[1],1)
 a=create_alliance(s,ps[0].id,cs[0].id,"ALLY","ca")
 ap=apply_to_alliance(s,ps[1].id,cs[1].id,a["alliance_id"],"ap")
 accept_alliance_application(s,ps[0].id,ap["application_id"],"accept")
 assert s.scalar(select(AllianceMember).where(AllianceMember.player_id==ps[1].id)).alliance_id==a["alliance_id"]
def test_foreign_garrison_is_not_native_and_returnable(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all()
 emb(s,cs[0],2);emb(s,cs[1],1);a=create_alliance(s,ps[0].id,cs[0].id,"ALLY","ca")
 ap=apply_to_alliance(s,ps[1].id,cs[1].id,a["alliance_id"],"ap");accept_alliance_application(s,ps[0].id,ap["application_id"],"accept")
 set_embassy_garrison_permission(s,ps[0].id,cs[0].id,True,"allow")
 tq=TroopQuantity(city_id=cs[0].id,troop_type_key="archer",quantity=100);s.add(tq)
 army=Army(player_id=ps[1].id,troops={"archer":5000},resources={"food":10000});s.add(army);s.flush();now=datetime.now(timezone.utc)
 m=March(army_id=army.id,source_city_id=cs[1].id,target_x=cs[0].x,target_y=cs[0].y,mission="REINFORCE",departed_at=now,arrives_at=now,status="MARCHING");s.add(m);s.flush()
 g=arrive_allied_reinforcement(s,m.id)
 assert g.troops["archer"]==5000 and tq.quantity==100
 assert return_foreign_garrison(s,ps[0].id,g.id,"sendhome")["status"]=="RETURNING"
def test_garrison_wave_capacity(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all()
 emb(s,cs[0],1);emb(s,cs[1],1);a=create_alliance(s,ps[0].id,cs[0].id,"ALLY","ca") if False else None
 # establish alliance directly to isolate capacity
 al=Alliance(name="X");s.add(al);s.flush();s.add_all([AllianceMember(alliance_id=al.id,player_id=ps[0].id,rank="HOST"),AllianceMember(alliance_id=al.id,player_id=ps[1].id,rank="MEMBER")]);set_embassy_garrison_permission(s,ps[0].id,cs[0].id,True,"allow")
 for n in range(2):
  army=Army(player_id=ps[1].id,troops={"warrior":10},resources={});s.add(army);s.flush();now=datetime.now(timezone.utc);m=March(army_id=army.id,source_city_id=cs[1].id,target_x=cs[0].x,target_y=cs[0].y,mission="REINFORCE",departed_at=now,arrives_at=now,status="MARCHING");s.add(m);s.flush()
  if n==0: assert arrive_allied_reinforcement(s,m.id)
  else:
   with pytest.raises(ValueError):arrive_allied_reinforcement(s,m.id)
