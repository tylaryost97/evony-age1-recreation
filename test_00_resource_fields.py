from datetime import datetime,timezone,timedelta
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *

def mk(tmp_path,population=100000):
 e=create_engine(f"sqlite:///{tmp_path/'r.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='r@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1,population=population,idle_population=population);s.add(c);s.flush();s.add(CityCoordinate(city_id=c.id,x=1,y=1));s.add(PopulationState(city_id=c.id,population=population,idle_population=population,population_limit=population));s.add(CityEconomyState(city_id=c.id,gold=10**9))
 th=Building(city_id=c.id,plot_kind='CITY',plot_index=0,definition_key='town_hall',level=1);s.add(th);s.flush();s.add(BuildingLevel(building_id=th.id,level=1))
 for k in RESOURCE_KINDS:s.add(Resource(city_id=c.id,kind=k,quantity=0,capacity=0));s.add(ResourceProduction(city_id=c.id,resource_kind=k,per_hour=0,last_calculated_at=datetime.now(timezone.utc)));s.add(ResourceCapacity(city_id=c.id,resource_kind=k,capacity=0))
 s.commit();return s,p,c

def add_field(s,c,key,level,plot):
 b=Building(city_id=c.id,plot_kind='FIELD',plot_index=plot,definition_key=key,level=level);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=level));s.flush();return b

def test_all_four_exact_level_tables():
 expected={
 'farm':[(50,300,200,150,30,10),(100,600,400,300,60,30),(200,1200,800,600,120,60),(400,2400,1600,1200,240,100),(800,4800,3200,2400,480,150),(1600,9600,6400,4800,960,210),(3200,19200,12800,9600,1920,280),(6400,38400,25600,19200,3840,360),(12800,76800,51200,38400,7680,450),(25600,153600,102400,76800,15360,550)],
 'sawmill':[(100,100,250,300,45,10),(200,200,500,600,90,30),(400,400,1000,1200,180,60),(800,800,2000,2400,360,100),(1600,1600,4000,4800,720,150),(3200,3200,8000,9600,1440,210),(6400,6400,16000,19200,2880,280),(12800,12800,32000,38400,5760,360),(25600,25600,64000,76800,11520,450),(51000,51000,128000,153600,23040,550)],
 'quarry':[(180,500,150,400,60,20),(360,1000,300,800,120,60),(720,2000,600,1600,240,120),(1440,4000,1200,3200,480,200),(2880,8000,2400,6400,960,300),(5760,16000,4800,12800,1920,420),(11520,32000,9600,25600,3840,560),(23040,64000,19200,51200,7680,720),(46080,128000,38400,102400,15360,900),(92160,256000,76800,204800,30720,1100)],
 'ironmine':[(210,600,500,200,90,25),(420,1200,1000,400,180,75),(840,2400,2000,800,360,150),(1680,4800,4000,1600,720,250),(3360,9600,8000,3200,1440,375),(6720,19200,16000,6400,2880,525),(13440,38400,32000,12800,5760,700),(26880,76800,64000,25600,11520,900),(53760,153600,128000,51200,23040,1125),(107520,307200,256000,102400,46080,1375)]}
 prod=[100,300,600,1000,1500,2100,2800,3600,4500,5500];cap=[10000,30000,60000,100000,150000,210000,280000,360000,450000,550000]
 for key,rows in expected.items():
  for lv,row in enumerate(rows,1):
   d=DATA['building_levels'][key][str(lv)];assert (d['cost']['food'],d['cost']['lumber'],d['cost']['stone'],d['cost']['iron'],d['seconds'],d['labor'])==row;assert d['production_per_hour']==prod[lv-1] and d['storage_capacity']==cap[lv-1]
  assert DATA['building_levels'][key]['10']['item_cost']=={'michelangelos_script':1}

def test_town_hall_unlocks_and_unbalanced_specialization(tmp_path):
 s,p,c=mk(tmp_path);assert sync_exterior_field_unlocks(s,c.id)==10
 for i in range(1,11):add_field(s,c,'sawmill',1,i)
 assert len(s.scalars(select(Building).where(Building.city_id==c.id,Building.plot_kind=='FIELD',Building.definition_key=='sawmill')).all())==10
 assert resource_field_totals(s,c.id)['lumber']['base_per_hour']==1000;s.close()

def test_offline_elapsed_production_and_capacity(tmp_path):
 s,p,c=mk(tmp_path);add_field(s,c,'farm',10,1);now=datetime.now(timezone.utc);rp=s.scalar(select(ResourceProduction).where(ResourceProduction.city_id==c.id,ResourceProduction.resource_kind=='food'));rp.last_calculated_at=now-timedelta(hours=2);s.flush();accrue_resources(s,c.id,now)
 food=s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food'));assert food.quantity==11000 and food.capacity==550000
 rp.last_calculated_at=now-timedelta(hours=200);food.quantity=549900;rp.fractional_remainder=0;s.flush();accrue_resources(s,c.id,now);assert food.quantity==550000;s.close()

def test_production_modifiers_and_labor(tmp_path):
 s,p,c=mk(tmp_path,population=100);add_field(s,c,'sawmill',4,1)
 ac=Building(city_id=c.id,plot_kind='CITY',plot_index=2,definition_key='academy',level=4);s.add(ac);s.flush();s.add(BuildingLevel(building_id=ac.id,level=4));s.add(Technology(player_id=p.id,definition_key='lumbering',level=2))
 h=Hero(player_id=p.id,city_id=c.id,name='Pol',level=1,politics=50);s.add(h);s.flush();s.add(HeroAssignment(hero_id=h.id,city_id=c.id,assignment_key='mayor'));s.add(HeroStats(hero_id=h.id,politics=50,attack=0,intelligence=0));
 mt=MapTile(x=2,y=2,tile_type='VALLEY',level=10,owner_player_id=p.id);s.add(mt);s.flush();s.add(Valley(map_tile_id=mt.id,valley_type='forest',level=10,city_id=c.id))
 from app.models import PlayerSetting
 s.add(PlayerSetting(player_id=p.id,key=f'city:{c.id}:production_rates',value={'food':100,'lumber':50,'stone':100,'iron':100}));now=datetime.now(timezone.utc);s.add(Buff(player_id=p.id,buff_key='arch_saw',starts_at=now-timedelta(hours=1),expires_at=now+timedelta(hours=1),metadata_json={'city_id':c.id,'resource_kind':'lumber'}));s.flush()
 r=resource_production_snapshot(s,c.id,now)['resources']['lumber'];assert r['base_per_hour']==1000 and r['assigned_labor']==50 and r['technology_bonus_percent']==20 and r['mayor_bonus_percent']==50 and r['valley_bonus_percent']==23 and r['item_bonus_percent']==25
 assert round(r['effective_per_hour'])==1090 # 1000 * 2.18 * 50%
 assert resource_production_snapshot(s,c.id,now)['idle_population']==50;s.close()

def test_buff_expiry_is_piecewise_offline(tmp_path):
 s,p,c=mk(tmp_path);add_field(s,c,'farm',1,1);now=datetime.now(timezone.utc);rp=s.scalar(select(ResourceProduction).where(ResourceProduction.city_id==c.id,ResourceProduction.resource_kind=='food'));rp.last_calculated_at=now-timedelta(hours=2);s.add(Buff(player_id=p.id,buff_key='plowshares',starts_at=now-timedelta(hours=3),expires_at=now-timedelta(hours=1),metadata_json={'city_id':c.id,'resource_kind':'food'}));s.flush();accrue_resources(s,c.id,now);food=s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='food'));assert food.quantity==225;s.close()
