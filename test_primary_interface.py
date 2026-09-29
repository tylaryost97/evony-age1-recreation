import importlib, os, tempfile
from fastapi.testclient import TestClient

def fresh_app():
    path=tempfile.mktemp(suffix='.db')
    os.environ['GAME_DATABASE_URL']='sqlite:///'+path
    import app.db as db; import app.models as models; import app.seed as seed; import app.service as service; import app.main as main
    importlib.reload(db); importlib.reload(models); importlib.reload(seed); importlib.reload(service); importlib.reload(main)
    db.Base.metadata.create_all(db.engine); seed.seed()
    return TestClient(main.app), db, models

def test_primary_interface_serves_only_authoritative_initial_state():
    client,db,m=fresh_app()
    root=client.get('/'); assert root.status_code==200
    assert 'City Exterior / Fields' in root.text and '>Map<' in root.text
    session=client.get('/api/development/session').json()
    cid=session['current_city']['id']; pid=session['player']['id']
    with db.SessionLocal() as s:
        city=s.get(m.City,cid)
        food=s.query(m.Resource).filter_by(city_id=cid,kind='food').one()
        food.quantity=4321; city.gold=999999  # compatibility value must not override normalized economy state
        s.commit()
    overview=client.get(f'/api/players/{pid}/cities/{cid}/overview').json()
    assert next(x for x in overview['city']['resources'] if x['kind']=='food')['quantity']==4321
    assert overview['city']['economy']['gold']==0

def test_city_fields_and_map_are_backed_by_persisted_records():
    client,db,m=fresh_app(); session=client.get('/api/development/session').json(); cid=session['current_city']['id']; pid=session['player']['id']; c=session['current_city']['coordinates']
    city=client.get(f'/api/players/{pid}/cities/{cid}/city-view').json()
    fields=client.get(f'/api/players/{pid}/cities/{cid}/field-view').json()
    assert len(city['plots'])==34 and len(fields['plots'])==10
    assert city['plots'][0]['building']['definition_key']=='town_hall'
    assert city['plots'][33]['building']['definition_key']=='walls'
    assert all(p['building'] is None for p in city['plots'][1:33]+fields['plots'])
    world=client.get(f"/api/map?center_x={c['x']}&center_y={c['y']}&radius=6").json()
    assert any(t['tile_type']=='NPC_CITY' for t in world['tiles'])
    assert any(t['tile_type']=='VALLEY' for t in world['tiles'])
    assert any(t['tile_type']=='FLAT' for t in world['tiles'])
    assert 'not fabricated' in world['note']

def test_switching_seeded_cities_returns_distinct_authoritative_city_state():
    client,_,_=fresh_app(); session=client.get('/api/development/session').json(); pid=session['player']['id']; assert len(session['cities'])>=2
    a=client.get(f"/api/players/{pid}/cities/{session['cities'][0]['id']}/overview").json()['city']
    b=client.get(f"/api/players/{pid}/cities/{session['cities'][1]['id']}/overview").json()['city']
    assert a['id']!=b['id'] and a['coordinates']!=b['coordinates']
