import os,tempfile,threading,importlib
from sqlalchemy import select

def fresh():
 p=tempfile.mktemp(suffix='.db'); os.environ['GAME_DATABASE_URL']='sqlite:///'+p
 import app.db as db; import app.models as m; import app.service as svc
 importlib.reload(db); importlib.reload(m); importlib.reload(svc); db.Base.metadata.create_all(db.engine)
 with db.SessionLocal() as s:
  a=m.Account(email='x@y.invalid'); s.add(a);s.flush();pl=m.Player(account_id=a.id,name='p');s.add(pl);s.flush();c=m.City(player_id=pl.id,name='c',x=1,y=1);s.add(c);s.flush();r=m.Resource(city_id=c.id,kind='food',quantity=100,capacity=100);s.add(r);s.commit();return p,db,m,svc,pl.id,c.id

def test_persistence_survives_new_session():
 _,db,m,_,_,cid=fresh()
 with db.SessionLocal() as s: s.get(m.City,cid).gold=77;s.commit()
 with db.SessionLocal() as s: assert s.get(m.City,cid).gold==77

def test_duplicate_request_only_mutates_once():
 _,db,m,svc,pid,cid=fresh(); results=[]
 def work():
  with db.SessionLocal() as s:
   try: results.append(svc.idempotent_operation(s,pid,'same','train',lambda:(svc.spend_resources(s,cid,{'food':10}),svc.add_troops(s,cid,'test',5),{'ok':True})[-1]))
   except Exception as e: results.append(type(e).__name__)
 ts=[threading.Thread(target=work) for _ in range(8)]
 [t.start() for t in ts];[t.join() for t in ts]
 with db.SessionLocal() as s:
  assert s.scalar(select(m.Resource).where(m.Resource.city_id==cid,m.Resource.kind=='food')).quantity==90
  assert s.scalar(select(m.TroopQuantity).where(m.TroopQuantity.city_id==cid,m.TroopQuantity.troop_type_key=='test')).quantity==5
  assert s.scalar(select(m.OperationRequest).where(m.OperationRequest.player_id==pid,m.OperationRequest.idempotency_key=='same')).response=={'ok':True}

def test_duplicate_callers_converge_on_same_result():
 _,db,m,svc,pid,cid=fresh(); results=[]; lock=threading.Lock()
 def work():
  with db.SessionLocal() as s:
   try:
    value=svc.idempotent_operation(s,pid,'converge','train',lambda:(svc.spend_resources(s,cid,{'food':10}),svc.add_troops(s,cid,'test',5),{'ok':True})[-1])
   except Exception as e: value={'error':type(e).__name__}
   with lock: results.append(value)
 ts=[threading.Thread(target=work) for _ in range(8)]
 [t.start() for t in ts]; [t.join() for t in ts]
 assert results == [{'ok':True}]*8

def test_requested_model_tables_exist():
 _,db,_,_,_,_=fresh()
 expected={'accounts','players','player_settings','cities','city_coordinates','city_building_plots','exterior_field_plots','buildings','building_levels','construction_queues','resources','resource_production','resource_capacity','population_state','city_economy_state','heroes','hero_stats','hero_experience','hero_assignments','troop_quantities','training_queues','technologies','research_queues','map_tiles','npc_cities','valleys','flats','marches','armies','march_missions','battles','battle_rounds','fortifications','alliances','alliance_members','alliance_ranks','mail','battle_reports','scout_reports','transport_reports','quest_progress','player_items','buffs','player_progression','bookmarks','operation_requests'}
 from sqlalchemy import inspect
 assert expected <= set(inspect(db.engine).get_table_names())
