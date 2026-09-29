
from datetime import datetime,timezone
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'tp.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();a=Account(email='tp@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=10,y=10);s.add(c);s.flush();s.add(CityCoordinate(city_id=c.id,x=10,y=10));s.add(MapTile(x=10,y=10,tile_type='PLAYER_CITY',owner_player_id=p.id));s.add(MapTile(x=20,y=20,tile_type='FLAT',level=3));s.add(MapTile(x=21,y=20,tile_type='FLAT',level=4));s.add(MapTile(x=220,y=20,tile_type='FLAT',level=5))
 for k in ('city_teleporter','adv_city_teleporter'):s.add(PlayerItem(player_id=p.id,item_key=k,quantity=5))
 s.commit();yield s,p,c;s.close()
def test_advanced_requires_real_unoccupied_flat(ctx):
 s,p,c=ctx
 with pytest.raises(ValueError,match='unoccupied Flat'):use_inventory_item(s,p.id,'adv_city_teleporter',{'city_id':c.id,'x':30,'y':30},'bad')
def test_atomic_world_move_and_old_flat(ctx):
 s,p,c=ctx;r=use_inventory_item(s,p.id,'adv_city_teleporter',{'city_id':c.id,'x':20,'y':20},'a');s.expire_all();c=s.get(City,c.id)
 assert (c.x,c.y)==(20,20) and (s.scalar(select(CityCoordinate).where(CityCoordinate.city_id==c.id)).x)==20
 assert s.scalar(select(MapTile).where(MapTile.x==20,MapTile.y==20)).tile_type=='PLAYER_CITY'
 assert s.scalar(select(MapTile).where(MapTile.x==10,MapTile.y==10)).tile_type=='FLAT'
def test_never_two_cities_same_coordinate(ctx):
 s,p,c=ctx;c2=City(player_id=p.id,name='Other',x=10,y=10);s.add(c2)
 with pytest.raises(Exception):s.flush()
 s.rollback()
def test_random_teleporter_requires_state_and_stays_in_state(ctx):
 s,p,c=ctx
 with pytest.raises(ValueError,match='valid Age I state'):use_inventory_item(s,p.id,'city_teleporter',{'city_id':c.id},'nostate')
 r=use_inventory_item(s,p.id,'city_teleporter',{'city_id':c.id,'state':'Saxony'},'state');assert r['state']=='Saxony' and 200<=r['x']<=399 and 0<=r['y']<=199
def test_outgoing_march_blocks_teleport(ctx):
 s,p,c=ctx;a=Army(player_id=p.id,troops={'worker':1},resources={});s.add(a);s.flush();s.add(March(army_id=a.id,source_city_id=c.id,target_x=50,target_y=50,mission='TRANSPORT',departed_at=datetime.now(timezone.utc),arrives_at=datetime.now(timezone.utc),status='MARCHING'));s.commit()
 with pytest.raises(ValueError,match='dispatched troops'):use_inventory_item(s,p.id,'adv_city_teleporter',{'city_id':c.id,'x':20,'y':20},'m')
def test_incoming_march_keeps_old_coordinate(ctx):
 s,p,c=ctx;src=City(player_id=p.id,name='Source',x=40,y=40);s.add(src);s.flush();a=Army(player_id=p.id,troops={'scout':1},resources={});s.add(a);s.flush();m=March(army_id=a.id,source_city_id=src.id,target_x=10,target_y=10,mission='SCOUT',departed_at=datetime.now(timezone.utc),arrives_at=datetime.now(timezone.utc),status='MARCHING');s.add(m);s.commit()
 r=use_inventory_item(s,p.id,'adv_city_teleporter',{'city_id':c.id,'x':20,'y':20},'inc');assert m.id in r['incoming_march_ids_continuing_to_old_coordinate'];s.expire_all();m=s.get(March,m.id);assert (m.target_x,m.target_y)==(10,10)
def test_advanced_24h_lock_blocks_march_and_reteleport(ctx):
 s,p,c=ctx;use_inventory_item(s,p.id,'adv_city_teleporter',{'city_id':c.id,'x':20,'y':20},'lock')
 with pytest.raises(ValueError,match='24-hour'):use_inventory_item(s,p.id,'adv_city_teleporter',{'city_id':c.id,'x':21,'y':20},'again')
def test_bookmarks_remain_coordinate_bookmarks(ctx):
 s,p,c=ctx;b=Bookmark(player_id=p.id,x=10,y=10,label='spot');s.add(b);s.commit();r=use_inventory_item(s,p.id,'adv_city_teleporter',{'city_id':c.id,'x':20,'y':20},'b');s.expire_all();b=s.get(Bookmark,b.id);assert (b.x,b.y)==(10,10) and r['bookmarks']=='UNCHANGED_COORDINATE_BOOKMARKS'
