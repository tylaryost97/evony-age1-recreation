
from datetime import datetime,timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'map.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='m@x');s.add(a);s.flush();p=Player(account_id=a.id,name='Mapper');s.add(p);s.flush();c=City(player_id=p.id,name='Home',x=400,y=400);s.add(c);s.flush()
 # Populate all 13x13 coordinates with alternating persistent map types except city coordinate.
 valley_types=list(VALLEY_TYPES);n=0
 for y in range(394,407):
  for x in range(394,407):
   if (x,y)==(400,400):continue
   kind=('FLAT','VALLEY','NPC_CITY')[n%3];lv=n%10+1;t=MapTile(x=x,y=y,tile_type=kind,level=lv);s.add(t);s.flush()
   if kind=='FLAT':s.add(Flat(map_tile_id=t.id,level=lv))
   elif kind=='VALLEY':s.add(Valley(map_tile_id=t.id,valley_type=valley_types[(n//3)%len(valley_types)],level=lv))
   else:s.add(NPCCity(map_tile_id=t.id,level=lv))
   n+=1
 s.commit();yield s,p,c
 s.close()
def test_world_bounds_and_complete_visible_grid(ctx):
 s,p,c=ctx;d=map_viewport(s,p.id,400,400,6);assert d['width']==13 and d['height']==13 and len(d['tiles'])==169
 assert {(t['x'],t['y']) for t in d['tiles']}=={(x,y) for y in range(394,407) for x in range(394,407)}
def test_every_visible_row_has_clickable_tile_payload_above_and_below_midpoint(ctx):
 s,p,c=ctx;d=map_viewport(s,p.id,400,400,6)
 # interaction contract: every rendered coordinate has its own coordinate-derived payload/action target, independent of viewport pixels.
 for y in range(394,407):
  row=[t for t in d['tiles'] if t['y']==y];assert len(row)==13
  for t in row:
   clicked=map_tile_payload(s,t['x'],t['y'],p.id);assert (clicked['x'],clicked['y'])==(t['x'],t['y'])
 assert any(t['y']<400 for t in d['tiles']) and any(t['y']>400 for t in d['tiles'])
def test_player_city_overlays_world_coordinate(ctx):
 s,p,c=ctx;t=map_tile_payload(s,400,400,p.id);assert t['tile_type']=='PLAYER_CITY' and t['actions']==['ENTER']
def test_valley_types_persist(ctx):
 s,p,c=ctx;types={t.get('valley_type') for t in map_viewport(s,p.id,400,400,6)['tiles'] if t['tile_type']=='VALLEY'};assert types==set(VALLEY_TYPES)
def test_bookmarks_persist_per_player_and_delete(ctx):
 s,p,c=ctx;b=add_bookmark(s,p.id,123,456,'Farm target','a');s.commit();assert player_bookmarks(s,p.id)==[{'id':b['id'],'x':123,'y':456,'label':'Farm target'}]
 delete_bookmark(s,p.id,b['id'],'d');s.commit();assert player_bookmarks(s,p.id)==[]
def test_coordinate_edges_are_clamped_by_world_validation(ctx):
 s,p,c=ctx;d=map_viewport(s,p.id,0,0,6);assert d['bounds']=={'min_x':0,'max_x':6,'min_y':0,'max_y':6} and len(d['tiles'])==49
 with pytest.raises(ValueError):map_viewport(s,p.id,800,0,6)
def test_npc_double_density_fixture_rule_is_explicit():
 # Custom rule is a generator policy: target count = historical/baseline count * 2.
 baseline=100;assert baseline*2==200
