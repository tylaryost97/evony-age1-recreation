
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'m.db'}",connect_args={'check_same_thread':False});Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='m@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush()
 c=City(player_id=p.id,name='A',x=100,y=100,population=1000,idle_population=1000);d=City(player_id=p.id,name='B',x=110,y=100,population=1000,idle_population=1000);s.add_all([c,d]);s.flush()
 for city in (c,d):
  s.add(CityEconomyState(city_id=city.id,gold=100000,last_settled_at=datetime.now(timezone.utc)));s.add(PopulationState(city_id=city.id,population=1000,idle_population=1000,population_limit=1000,last_population_tick_at=datetime.now(timezone.utc)))
  for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=city.id,kind=k,quantity=1000000,capacity=9999999,updated_at=datetime.now(timezone.utc)))
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=1,definition_key='rally_spot',level=2);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=2))
 for k,n in [('scout',1000),('warrior',1000),('transporter',1000)]:s.add(TroopQuantity(city_id=c.id,troop_type_key=k,quantity=n))
 h=Hero(player_id=p.id,city_id=c.id,name='H',level=10,attack=80);s.add(h);s.flush();s.add(HeroAssignment(hero_id=h.id,city_id=c.id,assignment_key='idle'))
 tile=MapTile(x=105,y=100,tile_type='FLAT',level=1);s.add(tile);s.flush();s.add(Flat(map_tile_id=tile.id,level=1,defenders={}))
 s.commit();yield s,p,c,d,h,S;s.close()
def test_persisted_march_contract_and_return_destination(ctx):
 s,p,c,d,h,S=ctx;r=create_march(s,p.id,c.id,'SCOUT',105,100,{'scout':10},{},None,0,False,'a');m=s.get(March,r['march_id']);ms=s.scalar(select(MarchMission).where(MarchMission.march_id==m.id));q=march_payload(s,m)
 assert q['unique_id']==m.id and q['origin_city_id']==c.id and q['destination']=={'x':105,'y':100} and q['return_destination']['city_id']==c.id and ms.mission_key=='SCOUT'
def test_rally_level_two_allows_two_not_three(ctx):
 s,p,c,d,h,S=ctx
 create_march(s,p.id,c.id,'SCOUT',105,100,{'scout':10},{},None,0,False,'1')
 create_march(s,p.id,c.id,'TRANSPORT',d.x,d.y,{'transporter':1},{},None,0,False,'2')
 with pytest.raises(ValueError,match='slots full'):create_march(s,p.id,c.id,'TRANSPORT',d.x,d.y,{'transporter':1},{},None,0,False,'3')
def test_scout_requires_scouts_and_attack_requires_hero(ctx):
 s,p,c,d,h,S=ctx
 with pytest.raises(ValueError,match='requires Scouts'):create_march(s,p.id,c.id,'SCOUT',105,100,{'warrior':1},{},None,0,False,'s')
 with pytest.raises(ValueError,match='requires a hero'):create_march(s,p.id,c.id,'ATTACK',105,100,{'warrior':1},{},None,0,False,'a')
def test_arrival_is_processed_exactly_once_and_report_not_duplicated(ctx):
 s,p,c,d,h,S=ctx;r=create_march(s,p.id,c.id,'SCOUT',105,100,{'scout':10},{},None,0,False,'a');m=s.get(March,r['march_id']);future=m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1)
 one=resolve_march_arrival(s,m.id,future);two=resolve_march_arrival(s,m.id,future)
 assert one['status']=='RETURNING' and two['already_processed'] and s.scalar(select(func.count(ScoutReport.id)))==1
def test_offline_due_processor_resolves_and_returns(ctx):
 s,p,c,d,h,S=ctx;r=create_march(s,p.id,c.id,'SCOUT',105,100,{'scout':10},{},None,0,False,'a');m=s.get(March,r['march_id']);arr=m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1)
 process_due_marches(s,arr,p.id);ret=m.returns_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1);process_due_marches(s,ret,p.id);assert m.status=='RETURNED'
def test_transport_delivers_once(ctx):
 s,p,c,d,h,S=ctx;before=s.scalar(select(Resource).where(Resource.city_id==d.id,Resource.kind=='lumber')).quantity
 r=create_march(s,p.id,c.id,'TRANSPORT',d.x,d.y,{'transporter':10},{'lumber':100},None,0,False,'t');m=s.get(March,r['march_id']);resolve_march_arrival(s,m.id,m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1))
 after=s.scalar(select(Resource).where(Resource.city_id==d.id,Resource.kind=='lumber')).quantity;assert after==before+100 and m.status=='RETURNING' and s.scalar(select(func.count(TransportReport.id)))==1
def test_reinforce_between_own_cities_transfers_troops(ctx):
 s,p,c,d,h,S=ctx;r=create_march(s,p.id,c.id,'REINFORCE',d.x,d.y,{'warrior':10},{},None,0,False,'r');m=s.get(March,r['march_id']);resolve_march_arrival(s,m.id,m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1));assert m.status=='COMPLETED';q=s.scalar(select(TroopQuantity).where(TroopQuantity.city_id==d.id,TroopQuantity.troop_type_key=='warrior'));assert q and q.quantity>=10
def test_empty_wilderness_occupy_camps_and_persists_ownership(ctx):
 s,p,c,d,h,S=ctx
 th=Building(city_id=c.id,plot_kind='CITY',plot_index=0,definition_key='town_hall',level=2);s.add(th);s.flush();s.add(BuildingLevel(building_id=th.id,level=2));s.flush()
 r=create_march(s,p.id,c.id,'OCCUPY',105,100,{'warrior':10},{},h.id,0,False,'o');m=s.get(March,r['march_id']);resolve_march_arrival(s,m.id,m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1));f=s.scalar(select(Flat).join(MapTile,Flat.map_tile_id==MapTile.id).where(MapTile.x==105,MapTile.y==100));assert m.status=='CAMPED' and f.city_id==c.id
def test_recall_sets_real_return_arrival(ctx):
 s,p,c,d,h,S=ctx;r=create_march(s,p.id,c.id,'SCOUT',105,100,{'scout':10},{},None,0,False,'a');m=s.get(March,r['march_id']);out=recall_march(s,p.id,m.id,'rec');assert out['status']=='RETURNING' and m.returns_at is not None
