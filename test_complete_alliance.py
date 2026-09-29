
from datetime import datetime,timezone
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
from app.service import _alliance_membership,_target_info,_mission_legal
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'a.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 ps=[];cs=[]
 for i,n in enumerate(['Host','Vice','Member','Out']):
  a=Account(email=f'{i}@x');s.add(a);s.flush();p=Player(account_id=a.id,name=n);s.add(p);s.flush();c=City(player_id=p.id,name=n,x=i,y=0);s.add(c);s.flush();b=Building(city_id=c.id,plot_kind='CITY',plot_index=1,definition_key='embassy',level=10);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=10));ps.append(p);cs.append(c)
 s.commit();yield s,ps,cs;s.close()
def test_create_seeds_real_permissions(ctx):
 s,p,c=ctx;r=create_alliance(s,p[0].id,c[0].id,'A','x');assert _alliance_membership(s,p[0].id).rank=='HOST'
 assert alliance_permission(s,p[0].id,'diplomacy') and not ALLIANCE_PERMISSIONS['MEMBER']['expel']
def test_invite_accept_promote_demote_expel(ctx):
 s,p,c=ctx;create_alliance(s,p[0].id,c[0].id,'A','x');inv=invite_to_alliance(s,p[0].id,'Member');respond_alliance_invitation(s,p[2].id,inv['invitation_id'],True)
 assert _alliance_membership(s,p[2].id).rank=='MEMBER'
 change_alliance_rank(s,p[0].id,p[2].id,'promote');assert _alliance_membership(s,p[2].id).rank=='OFFICER'
 change_alliance_rank(s,p[0].id,p[2].id,'demote');expel_alliance_member(s,p[0].id,p[2].id);assert not _alliance_membership(s,p[2].id)
def test_member_cannot_cosmetically_use_host_power(ctx):
 s,p,c=ctx;create_alliance(s,p[0].id,c[0].id,'A','x');inv=invite_to_alliance(s,p[0].id,'Member');respond_alliance_invitation(s,p[2].id,inv['invitation_id'],True)
 with pytest.raises(ValueError,match='permission'):set_alliance_relation(s,p[2].id,999,'HOSTILE')
 with pytest.raises(ValueError,match='permission'):send_alliance_mail(s,p[2].id,'x','y')
def test_host_transfer_and_leave(ctx):
 s,p,c=ctx;create_alliance(s,p[0].id,c[0].id,'A','x');inv=invite_to_alliance(s,p[0].id,'Vice');respond_alliance_invitation(s,p[1].id,inv['invitation_id'],True)
 with pytest.raises(ValueError,match='transfer'):leave_alliance(s,p[0].id)
 transfer_alliance_host(s,p[0].id,p[1].id);assert _alliance_membership(s,p[1].id).rank=='HOST';leave_alliance(s,p[0].id)
def test_chat_and_alliance_mail(ctx):
 s,p,c=ctx;create_alliance(s,p[0].id,c[0].id,'A','x');inv=invite_to_alliance(s,p[0].id,'Member');respond_alliance_invitation(s,p[2].id,inv['invitation_id'],True)
 send_alliance_chat(s,p[2].id,'hello');assert alliance_chat(s,p[0].id)[0]['body']=='hello'
 send_alliance_mail(s,p[0].id,'Alliance','notice');assert mail_box(s,p[2].id,'inbox')[0]['system_kind']=='ALLIANCE_MAIL'
def test_diplomacy_changes_map_and_attack_legality(ctx):
 s,p,c=ctx;create_alliance(s,p[0].id,c[0].id,'A','x');create_alliance(s,p[3].id,c[3].id,'B','y')
 a=_alliance_membership(s,p[0].id);b=_alliance_membership(s,p[3].id)
 set_alliance_relation(s,p[0].id,b.alliance_id,'FRIENDLY');assert player_relationship(s,p[0].id,p[3].id)=='FRIENDLY'
 target=_target_info(s,c[3].x,c[3].y);assert not _mission_legal(s,p[0].id,target,'ATTACK')
 set_alliance_relation(s,p[0].id,b.alliance_id,'HOSTILE');assert _mission_legal(s,p[0].id,target,'ATTACK')
def test_application_accept_reject_permission(ctx):
 s,p,c=ctx;create_alliance(s,p[0].id,c[0].id,'A','x');aid=_alliance_membership(s,p[0].id).alliance_id
 app=apply_to_alliance(s,p[2].id,c[2].id,aid,'ap');reject_alliance_application(s,p[0].id,app['application_id']);assert s.get(AllianceApplication,app['application_id']).status=='REJECTED'
