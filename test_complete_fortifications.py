
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
from app.combat import simulateBattle,Age1CombatRules
from app.definitions import DATA

def setup(tmp_path,wall=10):
 e=create_engine(f"sqlite:///{tmp_path/'f.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='f@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1,population=1000,idle_population=1000);s.add(c);s.flush()
 s.add(CityEconomyState(city_id=c.id,gold=100000,last_settled_at=datetime.now(timezone.utc)));s.add(PopulationState(city_id=c.id,population=1000,idle_population=1000,population_limit=1000,last_population_tick_at=datetime.now(timezone.utc)))
 for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=10_000_000,capacity=20_000_000,updated_at=datetime.now(timezone.utc)))
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=33,definition_key='walls',level=wall);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=wall)); academy=Building(city_id=c.id,plot_kind='CITY',plot_index=3,definition_key='academy',level=10);s.add(academy);s.flush();s.add(BuildingLevel(building_id=academy.id,level=10))
 for key,lv in [('metal_casting',10),('archery',10),('construction',0),('machinery',0),('engineering',0)]:s.add(Technology(player_id=p.id,definition_key=key,level=lv))
 s.commit();return s,p,c

def test_all_age1_fortification_definitions_exact():
 f=DATA['fortifications']
 assert f['trap']['space']==1 and f['trap']['cost']=={'food':50,'lumber':500,'stone':100,'iron':50} and f['trap']['base_seconds']==60 and f['trap']['wall_level']==1 and f['trap']['range']==5000
 assert f['abatis']['space']==2 and f['abatis']['cost']=={'food':100,'lumber':1200,'stone':0,'iron':150} and f['abatis']['base_seconds']==120 and f['abatis']['technology_requirements']=={'metal_casting':1}
 assert f['archer_tower']['space']==3 and f['archer_tower']['cost']=={'food':200,'lumber':2000,'stone':1000,'iron':500} and f['archer_tower']['base_seconds']==180 and (f['archer_tower']['life'],f['archer_tower']['attack'],f['archer_tower']['defense'])==(2000,300,360)
 assert f['rolling_log']['space']==4 and f['rolling_log']['base_seconds']==360 and f['rolling_log']['attack']==500 and f['rolling_log']['technology_requirements']=={'metal_casting':5}
 assert f['defensive_trebuchet']['space']==5 and f['defensive_trebuchet']['base_seconds']==600 and f['defensive_trebuchet']['attack']==800 and f['defensive_trebuchet']['range']==5000 and f['defensive_trebuchet']['technology_requirements']=={'metal_casting':6}

def test_wall_capacity_all_levels():
 expected={1:(10000,1000),2:(30000,3000),3:(60000,6000),4:(100000,10000),5:(150000,15000),6:(210000,21000),7:(280000,28000),8:(360000,36000),9:(450000,45000),10:(550000,55000)}
 for lv,(dur,spaces) in expected.items():
  d=DATA['building_levels']['walls'][str(lv)];assert (d['durability'],d['fortified_spaces'])==(dur,spaces)

def test_construction_is_walls_authoritative_and_reserves_space(tmp_path):
 s,p,c=setup(tmp_path)
 r=build_fortification(s,p.id,c.id,'archer_tower',100,'x');assert r['duration_seconds']==18000
 cap=wall_capacity(s,c.id);assert cap['used']==300 and cap['vacant']==54700
 q=s.get(FortificationQueue,r['queue_id']);q.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1);complete_fortifications(s,c.id)
 f=s.scalar(select(Fortification).where(Fortification.city_id==c.id,Fortification.definition_key=='archer_tower'));assert f.quantity==100
 s.close()

def test_prerequisites_are_real(tmp_path):
 s,p,c=setup(tmp_path,wall=1)
 assert fortification_prerequisites(s,c.id,'abatis')[0]['type']=='walls'
 with pytest.raises(ValueError,match='missing prerequisites'):build_fortification(s,p.id,c.id,'abatis',1,'a')
 s.close()

def test_archer_tower_range_uses_wall_and_archery(tmp_path):
 s,p,c=setup(tmp_path,wall=10);assert archer_tower_range(s,c.id)==2600
 s.close()

DEFS={
 'warrior':{'life':200,'attack':50,'defense':50,'range':20,'speed_miles_per_1000_minutes':200},
 'cavalry':{'life':500,'attack':250,'defense':180,'range':100,'speed_miles_per_1000_minutes':1000},
 'ballista':{'life':320,'attack':450,'defense':160,'range':1400,'speed_miles_per_1000_minutes':100},
}
def battle(att,fort):
 return simulateBattle({'unit_definitions':DEFS,'attacker':{'troops':att,'technologies':{},'hero_attack':0},'defender':{'troops':{},'technologies':{},'hero_attack':0,'fortifications':fort,'wall_level':10}})

def test_traps_hit_infantry_and_not_mounted():
 a=battle({'warrior':100},{'trap':100});assert a.attacker_losses['warrior']==100 and a.fortification_survivors.get('trap',0)==0
 b=battle({'cavalry':100},{'trap':100});assert b.attacker_losses['cavalry']==0

def test_abatis_hit_mounted_and_not_infantry():
 a=battle({'cavalry':100},{'abatis':100});assert a.attacker_losses['cavalry']==100
 b=battle({'warrior':100},{'abatis':100});assert b.attacker_losses['warrior']==0

def test_rolling_log_is_one_shot_attack():
 r=battle({'warrior':1000},{'rolling_log':10});assert r.defender_initial=={} and r.fortification_survivors.get('rolling_log',0)==0
 assert any(e.get('attacker')=='rolling_log' for rd in r.round_log for e in rd['events'] if e['phase']=='attack')

def test_defensive_trebuchet_targets_siege_only():
 r=battle({'ballista':100},{'defensive_trebuchet':10});assert r.attacker_losses['ballista']>0
 r2=battle({'warrior':100},{'defensive_trebuchet':10});assert r2.attacker_losses['warrior']==0

def test_towers_are_persistent_combat_stacks_not_one_shot():
 r=battle({'warrior':10000},{'archer_tower':10});shots=[e for rd in r.round_log for e in rd['events'] if e.get('attacker')=='archer_tower']
 assert len(shots)>=1
