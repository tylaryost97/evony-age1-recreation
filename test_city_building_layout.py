from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from test_primary_interface import fresh_app

def finish(db,m,city_id):
 with db.SessionLocal() as s:
  q=s.scalar(select(m.ConstructionQueue).where(m.ConstructionQueue.city_id==city_id,m.ConstructionQueue.status=='ACTIVE')); assert q
  q.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1); s.commit()

def build(client,pid,cid,plot,key,idem):
 r=client.post(f'/api/players/{pid}/cities/{cid}/construct',json={'plot_index':plot,'building_key':key,'idempotency_key':idem}); assert r.status_code==200,r.text; return r.json()

def test_city_has_34_locations_two_dedicated():
 client,_,_=fresh_app(); d=client.get('/api/development/session').json(); pid=d['player']['id'];cid=d['current_city']['id']; view=client.get(f'/api/players/{pid}/cities/{cid}/city-view').json()
 assert len(view['plots'])==34; assert view['plots'][0]['building']['definition_key']=='town_hall'; assert view['plots'][33]['building']['definition_key']=='walls'; assert all(x['building'] is None for x in view['plots'][1:33])

def test_player_can_choose_repeated_barracks_on_arbitrary_general_plots():
 client,db,m=fresh_app(); d=client.get('/api/development/session').json(); pid=d['player']['id'];cid=d['current_city']['id']
 build(client,pid,cid,12,'rally_spot','rally'); finish(db,m,cid); client.get(f'/api/players/{pid}/cities/{cid}/city-view')
 for idx in (3,19,27): build(client,pid,cid,idx,'barracks',f'b{idx}'); finish(db,m,cid); client.get(f'/api/players/{pid}/cities/{cid}/city-view')
 with db.SessionLocal() as s: assert {b.plot_index for b in s.scalars(select(m.Building).where(m.Building.city_id==cid,m.Building.definition_key=='barracks')).all()}=={3,19,27}

def test_repeated_cottages_and_warehouses_are_not_slot_bound():
 client,db,m=fresh_app(); d=client.get('/api/development/session').json(); pid=d['player']['id'];cid=d['current_city']['id']
 for key,plots in [('cottage',(2,8,31)),('warehouse',(4,21))]:
  for idx in plots: build(client,pid,cid,idx,key,f'{key}{idx}'); finish(db,m,cid); client.get(f'/api/players/{pid}/cities/{cid}/city-view')
  with db.SessionLocal() as s: assert {b.plot_index for b in s.scalars(select(m.Building).where(m.Building.city_id==cid,m.Building.definition_key==key)).all()}==set(plots)

def test_duplicate_construction_request_spends_once():
 client,db,m=fresh_app(); d=client.get('/api/development/session').json(); pid=d['player']['id'];cid=d['current_city']['id']
 with db.SessionLocal() as s: before=s.scalar(select(m.Resource).where(m.Resource.city_id==cid,m.Resource.kind=='lumber')).quantity
 a=build(client,pid,cid,5,'cottage','same'); b=build(client,pid,cid,5,'cottage','same'); assert a==b
 with db.SessionLocal() as s:
  after=s.scalar(select(m.Resource).where(m.Resource.city_id==cid,m.Resource.kind=='lumber')).quantity; assert before-after==500; assert len(s.scalars(select(m.Building).where(m.Building.city_id==cid,m.Building.plot_index==5)).all())==1
