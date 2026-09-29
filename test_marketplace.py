
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def s(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'m.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  for i,n in enumerate(("Buyer","Seller"),1):
   a=Account(email=f"{n}@x");s.add(a);s.flush();p=Player(account_id=a.id,name=n);s.add(p);s.flush();c=City(player_id=p.id,name=n,x=i,y=i,gold=1000000);s.add(c);s.flush();s.add(CityEconomyState(city_id=c.id,gold=1000000))
   for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=1000000))
  s.commit();yield s
def market(s,c,lv):
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=8,definition_key='marketplace',level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv));s.flush()
def test_levels_capacity(s):
 c=s.scalar(select(City))
 for lv in range(1,11):
  market(s,c,lv);assert marketplace_level(s,c.id)==lv
  b=s.scalar(select(Building).where(Building.city_id==c.id,Building.definition_key=='marketplace'));s.delete(s.scalar(select(BuildingLevel).where(BuildingLevel.building_id==b.id)));s.delete(b);s.flush()
def test_match_real_resources_gold_and_delivery(s):
 ps=s.scalars(select(Player).order_by(Player.id)).all();cs=s.scalars(select(City).order_by(City.id)).all();market(s,cs[0],4);market(s,cs[1],4)
 sell=place_market_order(s,ps[1].id,cs[1].id,'SELL','lumber',10000,1.0,'sell')
 buy=place_market_order(s,ps[0].id,cs[0].id,'BUY','lumber',10000,1.1,'buy')
 tr=s.scalar(select(MarketTrade));assert tr.price==1.1 and tr.quantity==10000 and tr.status=='DELIVERY_PENDING'
 assert _res(s,cs[1].id,'lumber').quantity==990000
 assert _res(s,cs[0].id,'lumber').quantity==1000000
 tr.delivers_at=datetime.now(timezone.utc)-timedelta(seconds=1);settle_market_delivery(s,tr.id);assert _res(s,cs[0].id,'lumber').quantity==1010000
def _res(s,c,k):return s.scalar(select(Resource).where(Resource.city_id==c,Resource.kind==k))
def test_cancel_and_idempotency(s):
 p=s.scalar(select(Player));c=s.scalar(select(City).where(City.player_id==p.id));market(s,c,2)
 a=place_market_order(s,p.id,c.id,'SELL','food',100,99,'same');b=place_market_order(s,p.id,c.id,'SELL','food',100,99,'same')
 assert a==b and len(market_orders(s,c.id))==1
 assert cancel_market_order(s,p.id,a['order_id'],'cancel')['status']=='CANCELLED'
def test_level_capacity_and_max_trade(s):
 p=s.scalar(select(Player));c=s.scalar(select(City).where(City.player_id==p.id));market(s,c,1)
 place_market_order(s,p.id,c.id,'SELL','stone',10,99,'a')
 with pytest.raises(ValueError):place_market_order(s,p.id,c.id,'SELL','iron',10,99,'b')
 with pytest.raises(ValueError):place_market_order(s,p.id,c.id,'SELL','iron',10000001,1,'c')
