from datetime import datetime,timezone,timedelta,timedelta
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.npc import *
from app.service import *

def setup(tmp_path,level=1):
 e=create_engine(f"sqlite:///{tmp_path/'n.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();a=Account(email='n@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();s.add(BeginnerProtection(player_id=p.id,started_at=datetime.now(timezone.utc)-timedelta(days=10),expires_at=datetime.now(timezone.utc)-timedelta(days=3),ended_at=datetime.now(timezone.utc)-timedelta(days=3),end_reason='SEVEN_DAYS_EXPIRED'));c=City(player_id=p.id,name='C',x=100,y=100,population=10000,idle_population=10000);s.add(c);s.flush();s.add(CityEconomyState(city_id=c.id,gold=100000,last_settled_at=datetime.now(timezone.utc)));s.add(PopulationState(city_id=c.id,population=10000,idle_population=10000,population_limit=10000,last_population_tick_at=datetime.now(timezone.utc)))
 for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=10000000,capacity=20000000,updated_at=datetime.now(timezone.utc)))
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=1,definition_key='rally_spot',level=10);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=10));ac=Building(city_id=c.id,plot_kind='CITY',plot_index=2,definition_key='academy',level=10);s.add(ac);s.flush();s.add(BuildingLevel(building_id=ac.id,level=10))
 for k in ('informatics','military_tradition','iron_working','medicine','archery','compass','horseback_riding','logistics'):s.add(Technology(player_id=p.id,definition_key=k,level=10))
 for k,n in [('warrior',100000),('scout',1000),('ballista',5000),('transporter',5000)]:s.add(TroopQuantity(city_id=c.id,troop_type_key=k,quantity=n))
 h=Hero(player_id=p.id,city_id=c.id,name='H',level=10,attack=100);s.add(h);s.flush();s.add(HeroAssignment(hero_id=h.id,city_id=c.id,assignment_key='idle'))
 t=MapTile(x=101,y=100,tile_type='NPC_CITY',level=level);s.add(t);s.flush();n=NPCCity(map_tile_id=t.id,level=level);s.add(n);s.flush();initialize_npc(n,force=True);s.commit();return s,p,c,h,n

def test_all_ten_documented_levels():
 assert set(NPC_LEVELS)==set(range(1,11));assert NPC_LEVELS[5]['resources']['food']==3000000;assert NPC_LEVELS[10]['troops']['warrior']==400000;assert NPC_LEVELS[10]['fortifications']['archer_tower']==3666

def test_regeneration_cadence(tmp_path):
 s,p,c,h,n=setup(tmp_path,5);now=datetime.now(timezone.utc);n.resources={k:0 for k in n.resources};n.troops={k:0 for k in n.troops};n.fortifications={k:0 for k in n.fortifications};n.resources_updated_at=now;n.defenders_updated_at=now
 regenerate_npc(n,now+timedelta(minutes=6));assert n.troops['warrior']==75 and n.fortifications['trap']==375;assert n.resources['food']==37500
 regenerate_npc(n,now+timedelta(hours=8));assert n.resources==NPC_LEVELS[5]['resources'];assert n.troops==NPC_LEVELS[5]['troops'];assert n.fortifications==NPC_LEVELS[5]['fortifications']

def test_real_scout_march_report(tmp_path):
 s,p,c,h,n=setup(tmp_path,1);r=create_march(s,p.id,c.id,'SCOUT',101,100,{'scout':10},{},None,0,False,'s');m=s.get(March,r['march_id']);o=resolve_march_arrival(s,m.id,m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1));rep=s.get(ScoutReport,o['report_id']);assert rep.payload['target']=='NPC_CITY' and rep.payload['troops']['warrior']=='Lots' and o['status']=='RETURNING'

def test_real_attack_runs_combat_and_mutates_npc(tmp_path):
 s,p,c,h,n=setup(tmp_path,1);r=create_march(s,p.id,c.id,'ATTACK',101,100,{'warrior':10000},{},h.id,0,False,'a');m=s.get(March,r['march_id']);o=resolve_march_arrival(s,m.id,m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1));assert s.get(Battle,o['battle_id']).outcome['status']=='RESOLVED';assert s.scalar(select(func.count(BattleRound.id)).join(Battle).where(Battle.march_id==m.id))>0;assert o['status']=='RETURNING';s.refresh(n);assert n.troops!=NPC_LEVELS[1]['troops'] or n.fortifications!=NPC_LEVELS[1]['fortifications']

def test_attack_arrival_exactly_once(tmp_path):
 s,p,c,h,n=setup(tmp_path,1);r=create_march(s,p.id,c.id,'ATTACK',101,100,{'warrior':10000},{},h.id,0,False,'a');m=s.get(March,r['march_id']);when=m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1);resolve_march_arrival(s,m.id,when);before=s.scalar(select(func.count(Battle.id)));two=resolve_march_arrival(s,m.id,when);assert two['already_processed'] and s.scalar(select(func.count(Battle.id)))==before

def test_density_does_not_scale_strength():
 assert NPC_LEVELS[5]['troops']['warrior']==750 and NPC_LEVELS[5]['fortifications']['trap']==3750

def test_zero_loyalty_successful_attack_can_capture_with_city_slot(tmp_path):
 s,p,c,h,n=setup(tmp_path,1);s.add(PlayerProgression(player_id=p.id,title_rank_key='Knight'));n.loyalty=2;s.commit();r=create_march(s,p.id,c.id,'ATTACK',101,100,{'warrior':10000},{},h.id,0,False,'cap');m=s.get(March,r['march_id']);o=resolve_march_arrival(s,m.id,m.arrives_at.replace(tzinfo=timezone.utc)+timedelta(seconds=1));tile=s.scalar(select(MapTile).where(MapTile.x==101,MapTile.y==100));assert tile.tile_type=='PLAYER_CITY' and tile.owner_player_id==p.id;assert s.scalar(select(func.count(City.id)).where(City.player_id==p.id))==2
