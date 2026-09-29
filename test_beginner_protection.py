
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
from app.service import _enforce_beginner_protection_march
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'bp.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();now=datetime.now(timezone.utc);a=Account(email='bp@x',created_at=now);s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1);s.add(c);s.flush();th=Building(city_id=c.id,plot_kind='CITY',plot_index=0,definition_key='town_hall',level=1);s.add(th);s.flush();s.add(BuildingLevel(building_id=th.id,level=1));s.add(BeginnerProtection(player_id=p.id,started_at=now,expires_at=now+timedelta(days=7)));s.commit();yield s,p,c,now;s.close()
def test_new_player_active_seven_days(ctx):
 s,p,c,now=ctx;x=beginner_protection_status(s,p.id,now+timedelta(days=1));assert x['active'] and x['seconds_remaining']==6*86400
def test_expires_after_seven_days_authoritatively(ctx):
 s,p,c,now=ctx;x=beginner_protection_status(s,p.id,now+timedelta(days=7,seconds=1));assert not x['active'] and x['end_reason']=='SEVEN_DAYS_EXPIRED'
 assert s.scalar(select(BeginnerProtection).where(BeginnerProtection.player_id==p.id)).ended_at is not None
def test_any_city_th5_ends_bp(ctx):
 s,p,c,now=ctx;b=town_hall_building(s,c.id);b.level=5;s.scalar(select(BuildingLevel).where(BuildingLevel.building_id==b.id)).level=5;s.flush();x=beginner_protection_status(s,p.id,now+timedelta(hours=1));assert not x['active'] and x['end_reason']=='TOWN_HALL_LEVEL_5'
def test_protected_player_cannot_attack_or_scout_any_city(ctx):
 s,p,c,now=ctx
 for kind in ('CITY','NPC_CITY'):
  for mission in ('ATTACK','SCOUT'):
   with pytest.raises(ValueError,match='Beginner Protection'):_enforce_beginner_protection_march(s,p.id,mission,{'kind':kind,'owner_player_id':999 if kind=='CITY' else None},now)
def test_wilderness_attack_and_scout_allowed(ctx):
 s,p,c,now=ctx
 for mission in ('ATTACK','OCCUPY','SCOUT'):_enforce_beginner_protection_march(s,p.id,mission,{'kind':'VALLEY','owner_player_id':None},now)
def test_other_player_cannot_attack_or_scout_protected_city(ctx):
 s,p,c,now=ctx;a=Account(email='e@x',created_at=now-timedelta(days=30));s.add(a);s.flush();e=Player(account_id=a.id,name='E');s.add(e);s.flush();s.add(BeginnerProtection(player_id=e.id,started_at=a.created_at,expires_at=a.created_at+timedelta(days=7),ended_at=now-timedelta(days=20),end_reason='SEVEN_DAYS_EXPIRED'));s.commit()
 for mission in ('ATTACK','SCOUT'):
  with pytest.raises(ValueError,match='target player'):_enforce_beginner_protection_march(s,e.id,mission,{'kind':'CITY','owner_player_id':p.id},now)
def test_player_tiles_remain_attackable(ctx):
 s,p,c,now=ctx;a=Account(email='e@x',created_at=now-timedelta(days=30));s.add(a);s.flush();e=Player(account_id=a.id,name='E');s.add(e);s.flush();s.add(BeginnerProtection(player_id=e.id,started_at=a.created_at,expires_at=a.created_at+timedelta(days=7),ended_at=now-timedelta(days=20),end_reason='SEVEN_DAYS_EXPIRED'));s.commit()
 _enforce_beginner_protection_march(s,e.id,'ATTACK',{'kind':'VALLEY','owner_player_id':p.id},now)
def test_expiry_creates_system_mail_once(ctx):
 s,p,c,now=ctx;beginner_protection_status(s,p.id,now+timedelta(days=8));beginner_protection_status(s,p.id,now+timedelta(days=9));rows=s.scalars(select(Mail).where(Mail.recipient_player_id==p.id,Mail.system_kind=='BEGINNER_PROTECTION_ENDED')).all();assert len(rows)==1
def test_second_city_does_not_restart_bp(ctx):
 s,p,c,now=ctx;c2=City(player_id=p.id,name='C2',x=2,y=2);s.add(c2);s.commit();bp=beginner_protection_status(s,p.id,now+timedelta(days=2));assert bp['started_at']==s.scalar(select(BeginnerProtection).where(BeginnerProtection.player_id==p.id)).started_at
