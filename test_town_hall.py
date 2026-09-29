from datetime import datetime,timezone,timedelta
from sqlalchemy import select
from test_primary_interface import fresh_app

def ids(client):
 d=client.get('/api/development/session').json(); return d['player']['id'],d['current_city']['id']

def set_th_level(db,m,cid,level):
 with db.SessionLocal() as s:
  th=s.scalar(select(m.Building).where(m.Building.city_id==cid,m.Building.definition_key=='town_hall'))
  th.level=level; lv=s.scalar(select(m.BuildingLevel).where(m.BuildingLevel.building_id==th.id));lv.level=level;s.commit()

def test_town_hall_is_permanent_dedicated_structure():
 c,db,m=fresh_app(); pid,cid=ids(c); d=c.get(f'/api/players/{pid}/cities/{cid}/city-view').json(); th=d['plots'][0]['building']
 assert th['definition_key']=='town_hall' and th['dedicated'] is True
 r=c.post(f'/api/players/{pid}/cities/{cid}/buildings/{th["id"]}/upgrade',json={'idempotency_key':'generic-th'})
 assert r.status_code==409

def test_exact_required_resource_field_progression_all_levels():
 c,db,m=fresh_app(); pid,cid=ids(c); expected={1:10,2:13,3:16,4:19,5:22,6:25,7:28,8:31,9:34,10:37}
 for level,count in expected.items():
  set_th_level(db,m,cid,level)
  th=c.get(f'/api/players/{pid}/cities/{cid}/town-hall').json(); fields=c.get(f'/api/players/{pid}/cities/{cid}/field-view').json()
  assert th['resource_fields']['available']==count
  assert len(fields['plots'])==count
 assert th['resource_fields']['progression']==list(expected.values())

def test_town_hall_level_tables_costs_times_and_verified_wall_prereqs():
 c,db,m=fresh_app(); from app.definitions import DATA
 expected={2:1800,3:3600,4:7200,5:14400,6:28800,7:57600,8:115200,9:230400,10:460800}
 for level,seconds in expected.items():
  x=DATA['town_hall_levels'][str(level)]; assert x['seconds']==seconds; assert x['resource_fields']==10+3*(level-1)
  assert set(x['cost'])=={'food','lumber','stone','iron'}
 assert DATA['town_hall_levels']['2']['prerequisites']==[]
 for level in range(3,10): assert DATA['town_hall_levels'][str(level)]['prerequisites']==[{'building':'walls','level':level-2}]
 assert DATA['town_hall_levels']['10']['prerequisites']==[{'building':'walls','level':8}]
 assert DATA['town_hall_levels']['10']['item_cost']=={'michelangelos_script':1}

def test_level_two_upgrade_spends_authoritatively_and_persists_timer():
 c,db,m=fresh_app(); pid,cid=ids(c)
 with db.SessionLocal() as s: before={r.kind:r.quantity for r in s.scalars(select(m.Resource).where(m.Resource.city_id==cid)).all()}
 a=c.post(f'/api/players/{pid}/cities/{cid}/town-hall/upgrade',json={'idempotency_key':'th2'}); assert a.status_code==200,a.text
 b=c.post(f'/api/players/{pid}/cities/{cid}/town-hall/upgrade',json={'idempotency_key':'th2'}); assert b.json()==a.json()
 with db.SessionLocal() as s:
  after={r.kind:r.quantity for r in s.scalars(select(m.Resource).where(m.Resource.city_id==cid)).all()}; q=s.scalar(select(m.ConstructionQueue).where(m.ConstructionQueue.city_id==cid,m.ConstructionQueue.status=='ACTIVE'))
  assert before['food']-after['food']==400 and before['lumber']-after['lumber']==6000 and before['stone']-after['stone']==5000 and before['iron']-after['iron']==200
  delta=(q.completes_at-q.started_at).total_seconds(); assert delta==1800

def test_town_hall_admin_controls_persist():
 c,db,m=fresh_app(); pid,cid=ids(c)
 assert c.post(f'/api/players/{pid}/cities/{cid}/town-hall/tax',json={'tax_rate':20,'idempotency_key':'tax'}).status_code==200
 assert c.post(f'/api/players/{pid}/cities/{cid}/town-hall/rename',json={'name':'New Alpha','idempotency_key':'rename'}).status_code==200
 body={'food':90,'lumber':80,'stone':70,'iron':60,'idempotency_key':'prod'}; assert c.post(f'/api/players/{pid}/cities/{cid}/town-hall/production',json=body).status_code==200
 d=c.get(f'/api/players/{pid}/cities/{cid}/town-hall').json(); assert d['public_state']['tax_rate']==20; assert d['production_rates']=={'food':90,'lumber':80,'stone':70,'iron':60}
 overview=c.get(f'/api/players/{pid}/cities/{cid}/overview').json(); assert overview['city']['name']=='New Alpha'

def test_verified_town_hall_prerequisite_is_enforced():
 c,db,m=fresh_app(); pid,cid=ids(c); set_th_level(db,m,cid,2)
 d=c.get(f'/api/players/{pid}/cities/{cid}/town-hall').json(); assert d['upgrade']['prerequisites']==[{'building':'walls','level':1}]
 with db.SessionLocal() as s:
  w=s.scalar(select(m.Building).where(m.Building.city_id==cid,m.Building.definition_key=='walls'));w.level=0;wl=s.scalar(select(m.BuildingLevel).where(m.BuildingLevel.building_id==w.id));wl.level=0;s.commit()
 r=c.post(f'/api/players/{pid}/cities/{cid}/town-hall/upgrade',json={'idempotency_key':'th3'}); assert r.status_code==409 and 'requires walls lv.1' in r.text.lower()

def test_completed_town_hall_upgrade_unlocks_fields_and_survives_reopen():
 c,db,m=fresh_app(); pid,cid=ids(c)
 r=c.post(f'/api/players/{pid}/cities/{cid}/town-hall/upgrade',json={'idempotency_key':'finish-th2'}); assert r.status_code==200
 with db.SessionLocal() as s:
  q=s.scalar(select(m.ConstructionQueue).where(m.ConstructionQueue.city_id==cid,m.ConstructionQueue.status=='ACTIVE')); q.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1); s.commit()
 assert len(c.get(f'/api/players/{pid}/cities/{cid}/field-view').json()['plots'])==13
 with db.SessionLocal() as s:
  th=s.scalar(select(m.Building).where(m.Building.city_id==cid,m.Building.definition_key=='town_hall')); assert th.level==2
  assert len(s.scalars(select(m.ExteriorFieldPlot).where(m.ExteriorFieldPlot.city_id==cid,m.ExteriorFieldPlot.plot_index<=13)).all())==13
