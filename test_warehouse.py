import pytest
from sqlalchemy import select
from test_primary_interface import fresh_app
from app.models import City,Building,BuildingLevel,Resource,Technology,PlayerItem,WarehouseAllocation,CityEconomyState
from app.service import warehouse_base_capacity,warehouse_effective_capacity,warehouse_protected_amounts,set_warehouse_allocation,resolve_city_plunder,start_upgrade
from app.definitions import DATA

def city(s): return s.scalar(select(City).order_by(City.id))
def add_wh(s,c,plot,lv):
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key='warehouse',level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv));s.commit();return b

def test_warehouse_level_table_1_to_10_exact():
 expected=[(100,1500,1000,300,600,10000),(200,3000,2000,600,1200,30000),(400,6000,4000,1200,2400,60000),(800,12000,8000,2400,4800,100000),(1600,24000,16000,4800,9600,150000),(3200,48000,32000,9600,19200,210000),(6400,96000,64000,19200,38400,280000),(12800,182000,128000,38400,76800,360000),(25600,364000,256000,76800,153600,450000),(51200,728000,512000,153600,307200,550000)]
 for lv,e in enumerate(expected,1):
  x=DATA['building_levels']['warehouse'][str(lv)]; assert (x['cost']['food'],x['cost']['lumber'],x['cost']['stone'],x['cost']['iron'],x['seconds'],x['storage_capacity'])==e
 assert DATA['building_levels']['warehouse']['10']['item_cost']=={'michelangelos_script':1}

def test_multiple_warehouses_stack_and_stockpile_applies():
 client,db,m=fresh_app()
 with db.SessionLocal() as s:
  c=city(s); add_wh(s,c,20,10); add_wh(s,c,21,5)
  academy=Building(city_id=c.id,plot_kind='CITY',plot_index=22,definition_key='academy',level=6);s.add(academy);s.flush();s.add(BuildingLevel(building_id=academy.id,level=6));s.flush()
  assert warehouse_base_capacity(s,c.id)==700000
  s.add(Technology(player_id=c.player_id,definition_key='stockpile',level=10));s.commit()
  assert warehouse_effective_capacity(s,c.id)==1400000

def test_allocation_is_persistent_and_must_total_100():
 client,db,m=fresh_app()
 with db.SessionLocal() as s:
  c=city(s); add_wh(s,c,20,10)
  r=set_warehouse_allocation(s,c.player_id,c.id,{'food':70,'lumber':20,'stone':0,'iron':10},'alloc-1'); assert r['allocation']['food']==70
  with pytest.raises(ValueError): set_warehouse_allocation(s,c.player_id,c.id,{'food':70,'lumber':20,'stone':20,'iron':10},'bad')
 with db.SessionLocal() as s:
  a=s.scalar(select(WarehouseAllocation)); assert (a.food_percent,a.lumber_percent,a.stone_percent,a.iron_percent)==(70,20,0,10)

def test_privateering_changes_real_plunder_and_gold_never_protected():
 client,db,m=fresh_app()
 with db.SessionLocal() as s:
  c=city(s); add_wh(s,c,20,10); set_warehouse_allocation(s,c.player_id,c.id,{'food':100,'lumber':0,'stone':0,'iron':0},'alloc')
  attacker=2
  t=s.scalar(select(Technology).where(Technology.player_id==attacker,Technology.definition_key=='privateering'))
  if t:t.level=10
  else:s.add(Technology(player_id=attacker,definition_key='privateering',level=10))
  food=s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food')); food.quantity=1000000
  eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id)); eco.gold=100000;s.commit()
  protected=warehouse_protected_amounts(s,c.id,attacker); assert protected['food']==385000 and protected['gold']==0
  out=resolve_city_plunder(s,attacker,c.id,10000000,'raid-1'); assert out['plundered']['food']==615000 and out['plundered']['gold']==100000
  again=resolve_city_plunder(s,attacker,c.id,10000000,'raid-1'); assert again==out
  s.expire_all(); food=s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food')); eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id)); assert food.quantity==385000 and eco.gold==0

def test_level10_upgrade_requires_and_consumes_script():
 client,db,m=fresh_app()
 with db.SessionLocal() as s:
  c=city(s); b=add_wh(s,c,20,9)
  for r in s.scalars(select(Resource).where(Resource.city_id==c.id)).all(): r.quantity=10_000_000
  with pytest.raises(ValueError): start_upgrade(s,c.player_id,c.id,b.id,'wh10-no-script')
  s.add(PlayerItem(player_id=c.player_id,item_key='michelangelos_script',quantity=1));s.commit()
  out=start_upgrade(s,c.player_id,c.id,b.id,'wh10'); assert out['target_level']==10
  item=s.scalar(select(PlayerItem).where(PlayerItem.player_id==c.player_id,PlayerItem.item_key=='michelangelos_script')); assert item.quantity==0
