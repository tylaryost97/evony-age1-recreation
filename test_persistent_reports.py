from datetime import datetime,timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
from app.service import _create_report

def setup(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'r.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();a=Account(email='r@x');s.add(a);s.flush();p=Player(account_id=a.id,name='Reporter');s.add(p);s.flush();c=City(player_id=p.id,name='Home',x=10,y=10);s.add(c);s.flush();
 for key,lv,plot in [('academy',10,1),('beacon_tower',8,2)]:
  b=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv))
 s.add(Technology(player_id=p.id,definition_key='informatics',level=10));s.commit();return s,p,c

def test_reports_persist_read_and_soft_delete(tmp_path):
 s,p,c=setup(tmp_path);r=create_system_report(s,p.id,'REFUGE',{'losses':{'warrior':10}});s.commit();rows=list_reports(s,p.id);assert rows[0]['payload']['event_type']=='REFUGE' and not rows[0]['read'];get_report(s,p.id,'system',r.id);s.commit();assert list_reports(s,p.id)[0]['read'];delete_report(s,p.id,'system',r.id);s.commit();assert list_reports(s,p.id)==[] and s.get(SystemReport,r.id).deleted_at is not None

def test_report_kinds_are_separate(tmp_path):
 s,p,c=setup(tmp_path)
 for cls in (BattleReport,ScoutReport,TransportReport,ReinforcementReport,SystemReport):_create_report(s,cls,p.id,{'authoritative':True})
 s.commit();assert {r['kind'] for r in list_reports(s,p.id)}=={'battle','scout','transport','reinforcement','system'}

def test_scout_detail_is_limited_by_beacon_and_scout_count(tmp_path):
 s,p,c=setup(tmp_path);d=scout_detail_level(s,c.id,9,None,90,True);assert d['informatics']==10 and d['beacon_tower']==8 and d['effective_detail_level']==8 and not d['exact_numbers']
 b=s.query(Building).filter_by(city_id=c.id,definition_key='beacon_tower').one();b.level=10;s.flush();assert scout_detail_level(s,c.id,9,None,89,True)['exact_numbers'] is False;assert scout_detail_level(s,c.id,9,None,90,True)['exact_numbers'] is True

def test_scout_bands_match_age1_ranges(tmp_path):
 s,p,c=setup(tmp_path);tile=MapTile(x=20,y=20,tile_type='NPC_CITY',level=10);s.add(tile);s.flush();n=NPCCity(map_tile_id=tile.id,level=10,resources={},troops={'warrior':10000,'archer':24,'scout':25},fortifications={'trap':999},resources_updated_at=datetime.now(timezone.utc),defenders_updated_at=datetime.now(timezone.utc));s.add(n);b=s.query(Building).filter_by(city_id=c.id,definition_key='beacon_tower').one();b.level=1;s.commit();r=npc_scout_payload(s,p.id,c.id,20,20,datetime.now(timezone.utc),None,100);assert not r['exact'];assert r['troops']['warrior']=='Giga' and r['troops']['archer']=='Few' and r['troops']['scout']=='Pack'

def test_battle_report_snapshot_does_not_follow_later_state(tmp_path):
 s,p,c=setup(tmp_path);payload={'attacker':{'troops':{'warrior':100}},'losses':{'warrior':25},'survivors':{'warrior':75},'location':{'x':2,'y':3},'outcome':'attacker'};r=_create_report(s,BattleReport,p.id,payload);s.commit();payload['survivors']['warrior']=0;stored=get_report(s,p.id,'battle',r.id,False);assert stored['payload']['survivors']['warrior']==75
