import pytest
from sqlalchemy import select
from test_primary_interface import fresh_app
from app.models import City,Building,BuildingLevel,CityEconomyState,Hero,PlayerItem
from app.service import seed_verified_candidate_fixture,recruit_inn_candidate,feasting_hall_capacity,start_upgrade
from app.definitions import DATA

def city(s): return s.scalar(select(City).order_by(City.id))
def add(s,c,key,plot,lv):
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv));s.commit();return b

def test_inn_levels_1_to_10_table():
 expected=[(300,2000,1000,400,240),(600,4000,2000,800,480),(1200,8000,4000,1600,960),(2400,16000,8000,3200,1920),(4800,32000,16000,6400,3840),(9600,64000,32000,12800,7680),(19200,128000,64000,25600,15360),(38400,256000,128000,51200,30720),(76800,512000,256000,102400,61440),(153600,1024000,512000,204800,122880)]
 for lv,e in enumerate(expected,1):
  x=DATA['building_levels']['inn'][str(lv)];assert (x['cost']['food'],x['cost']['lumber'],x['cost']['stone'],x['cost']['iron'],x['seconds'])==e;assert x['available_heroes']==lv
 assert DATA['building_levels']['inn']['1']['prerequisites']==[{'building':'cottage','level':2}]
 assert DATA['building_levels']['inn']['10']['item_cost']=={'michelangelos_script':1}

def test_feasting_hall_capacity_is_level_and_blocks_hiring():
 client,db,m=fresh_app()
 with db.SessionLocal() as s:
  c=city(s);add(s,c,'inn',20,3);add(s,c,'feasting_hall',21,1);eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id));eco.gold=100000;s.commit()
  a=seed_verified_candidate_fixture(s,c.id,1,'Rodney',2,41,65,45);b=seed_verified_candidate_fixture(s,c.id,2,'Linda',10,72,8,45);s.commit()
  out=recruit_inn_candidate(s,c.player_id,c.id,a.id,'hire1');assert out['employment_fee']==2000;assert feasting_hall_capacity(s,c.id)==1
  with pytest.raises(ValueError,match='full'):recruit_inn_candidate(s,c.player_id,c.id,b.id,'hire2')

def test_hiring_transfers_candidate_and_deducts_gold_once():
 client,db,m=fresh_app()
 with db.SessionLocal() as s:
  c=city(s);add(s,c,'inn',20,1);add(s,c,'feasting_hall',21,2);eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id));eco.gold=50000;s.commit();cand=seed_verified_candidate_fixture(s,c.id,1,'Linda',10,72,8,45);s.commit();cid=cand.id
  one=recruit_inn_candidate(s,c.player_id,c.id,cid,'same');two=recruit_inn_candidate(s,c.player_id,c.id,cid,'same');assert one==two
  s.expire_all();assert s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id)).gold==40000
  h=s.scalar(select(Hero).where(Hero.city_id==c.id,Hero.name=='Linda'));assert (h.level,h.politics,h.attack,h.intelligence)==(10,72,8,45)

def test_candidate_fixture_persists_and_does_not_change_on_render():
 client,db,m=fresh_app()
 with db.SessionLocal() as s:
  c=city(s);add(s,c,'inn',20,1);seed_verified_candidate_fixture(s,c.id,1,'Rodney',2,41,65,45);s.commit();pid=c.player_id;cid=c.id
 a=client.get(f'/api/players/{pid}/cities/{cid}/inn').json();b=client.get(f'/api/players/{pid}/cities/{cid}/inn').json();assert a['candidates']==b['candidates'];assert a['automatic_refresh_seconds']==3600

def test_candidate_rng_is_not_invented():
 client,db,m=fresh_app()
 with db.SessionLocal() as s:c=city(s);add(s,c,'inn',20,1);pid=c.player_id;cid=c.id
 r=client.post(f'/api/players/{pid}/cities/{cid}/inn/refresh',json={'idempotency_key':'r1','use_hero_hunting':False});assert r.status_code==409;assert 'HISTORICAL_VALUE_UNKNOWN' in r.text
