from datetime import datetime,timezone,timedelta
from sqlalchemy import select
from test_primary_interface import fresh_app

CAP={1:100,2:300,3:600,4:1000,5:1500,6:2100,7:2800,8:3600,9:4500,10:5500}
COST={n:{'food':100*2**(n-1),'lumber':500*2**(n-1),'stone':100*2**(n-1),'iron':50*2**(n-1)} for n in range(1,11)}

def ids(c):
 d=c.get('/api/development/session').json(); return d['player']['id'],d['current_city']['id']

def add_cottage(db,m,cid,plot,level):
 with db.SessionLocal() as s:
  b=m.Building(city_id=cid,plot_kind='CITY',plot_index=plot,definition_key='cottage',level=level);s.add(b);s.flush();s.add(m.BuildingLevel(building_id=b.id,level=level));s.commit();return b.id

def set_th(db,m,cid,level):
 with db.SessionLocal() as s:
  b=s.scalar(select(m.Building).where(m.Building.city_id==cid,m.Building.definition_key=='town_hall')); b.level=level
  lv=s.scalar(select(m.BuildingLevel).where(m.BuildingLevel.building_id==b.id));lv.level=level;s.commit()

def test_all_ten_cottage_historical_tables():
 c,db,m=fresh_app(); from app.definitions import DATA
 for level in range(1,11):
  x=DATA['building_levels']['cottage'][str(level)]
  assert x['cost']==COST[level]; assert x['seconds']==75*2**(level-1); assert x['population_capacity']==CAP[level]
  assert x['prerequisites']==([] if level<=2 else [{'building':'town_hall','level':level-1}])
 assert DATA['building_levels']['cottage']['10']['item_cost']=={'michelangelos_script':1}

def test_population_limit_sums_different_numbers_and_levels_of_cottages():
 c,db,m=fresh_app(); pid,cid=ids(c)
 a=add_cottage(db,m,cid,1,1); b=add_cottage(db,m,cid,2,4); d=add_cottage(db,m,cid,3,7)
 r=c.get(f'/api/players/{pid}/cities/{cid}/buildings/{a}').json(); assert r['function']['population_limit']==100+1000+2800
 overview=c.get(f'/api/players/{pid}/cities/{cid}/overview').json(); assert overview['city']['population']['limit']==3900

def test_cottage_completion_immediately_changes_capacity_but_not_instant_population():
 c,db,m=fresh_app(); pid,cid=ids(c)
 with db.SessionLocal() as s:
  pop=s.scalar(select(m.PopulationState).where(m.PopulationState.city_id==cid));pop.population=80;pop.idle_population=50;s.commit()
 r=c.post(f'/api/players/{pid}/cities/{cid}/construct',json={'plot_index':5,'building_key':'cottage','idempotency_key':'c1'}); assert r.status_code==200,r.text
 with db.SessionLocal() as s:
  q=s.get(m.ConstructionQueue,r.json()['queue_id']);q.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1);s.commit()
 d=c.get(f'/api/players/{pid}/cities/{cid}/city-view').json()['city']['population']; assert d=={'total':80,'idle':80,'limit':100}

def test_cottage_upgrade_requires_town_hall_and_spends_script_at_level_10():
 c,db,m=fresh_app(); pid,cid=ids(c); bid=add_cottage(db,m,cid,6,2)
 # Level 3 requires TH2; seed TH1 must reject.
 r=c.post(f'/api/players/{pid}/cities/{cid}/buildings/{bid}/upgrade',json={'idempotency_key':'c3'}); assert r.status_code==409 and 'Town Hall Lv.2' in r.text
 set_th(db,m,cid,9)
 with db.SessionLocal() as s:
  b=s.get(m.Building,bid);b.level=9;lv=s.scalar(select(m.BuildingLevel).where(m.BuildingLevel.building_id==bid));lv.level=9;s.add(m.PlayerItem(player_id=pid,item_key='michelangelos_script',quantity=1));s.commit()
 r=c.post(f'/api/players/{pid}/cities/{cid}/buildings/{bid}/upgrade',json={'idempotency_key':'c10'}); assert r.status_code==200,r.text
 with db.SessionLocal() as s:
  item=s.scalar(select(m.PlayerItem).where(m.PlayerItem.player_id==pid,m.PlayerItem.item_key=='michelangelos_script')); assert item.quantity==0

def test_capacity_drop_clamps_population_and_idle_to_real_housing():
 c,db,m=fresh_app(); pid,cid=ids(c); bid=add_cottage(db,m,cid,7,4)
 c.get(f'/api/players/{pid}/cities/{cid}/buildings/{bid}')
 with db.SessionLocal() as s:
  pop=s.scalar(select(m.PopulationState).where(m.PopulationState.city_id==cid));pop.population=900;pop.idle_population=700
  b=s.get(m.Building,bid);b.level=1;lv=s.scalar(select(m.BuildingLevel).where(m.BuildingLevel.building_id==bid));lv.level=1;s.commit()
 d=c.get(f'/api/players/{pid}/cities/{cid}/buildings/{bid}').json()['function']; assert d['population_limit']==100; assert d['population']==100; assert d['idle_population']==100
