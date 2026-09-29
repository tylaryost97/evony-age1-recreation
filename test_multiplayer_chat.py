
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'c.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();ps=[]
 for i,n in enumerate(['A','B','C']):
  a=Account(email=f'{i}@x');s.add(a);s.flush();p=Player(account_id=a.id,name=n);s.add(p);s.flush();ps.append(p)
 al=Alliance(name='X');s.add(al);s.flush();s.add_all([AllianceMember(alliance_id=al.id,player_id=ps[0].id,rank='HOST'),AllianceMember(alliance_id=al.id,player_id=ps[1].id,rank='MEMBER')]);s.commit();yield s,ps;s.close()
def test_world_persistent_and_incremental(ctx):
 s,p=ctx;a=send_chat_message(s,p[0].id,'WORLD','one');b=send_chat_message(s,p[1].id,'WORLD','two')
 assert [x['body'] for x in chat_messages(s,p[2].id,'WORLD')]==['one','two']
 assert [x['body'] for x in chat_messages(s,p[2].id,'WORLD',a['id'])]==['two']
def test_alliance_requires_membership_and_is_private(ctx):
 s,p=ctx;send_chat_message(s,p[0].id,'ALLIANCE','ally');assert chat_messages(s,p[1].id,'ALLIANCE')[0]['body']=='ally'
 with pytest.raises(ValueError):send_chat_message(s,p[2].id,'ALLIANCE','no')
 with pytest.raises(ValueError):chat_messages(s,p[2].id,'ALLIANCE')
def test_whisper_only_participants(ctx):
 s,p=ctx;send_chat_message(s,p[0].id,'WHISPER','secret','B')
 assert chat_messages(s,p[1].id,'WHISPER')[0]['body']=='secret' and chat_messages(s,p[2].id,'WHISPER')==[]
def test_block_prevents_whisper_and_filters_world(ctx):
 s,p=ctx;send_chat_message(s,p[0].id,'WORLD','visible');set_chat_block(s,p[1].id,'A',True)
 assert chat_messages(s,p[1].id,'WORLD')==[]
 with pytest.raises(ValueError,match='not accepting'):send_chat_message(s,p[0].id,'WHISPER','x','B')
def test_mute_filters_without_preventing_sender(ctx):
 s,p=ctx;set_chat_mute(s,p[1].id,'A',True);send_chat_message(s,p[0].id,'WORLD','x')
 assert chat_messages(s,p[1].id,'WORLD')==[] and chat_messages(s,p[2].id,'WORLD')[0]['body']=='x'
def test_rate_limit_server_side(ctx):
 s,p=ctx;now=datetime.now(timezone.utc)
 for i in range(5):send_chat_message(s,p[0].id,'WORLD',str(i),at=now+timedelta(seconds=i))
 with pytest.raises(ValueError,match='rate limit'):send_chat_message(s,p[0].id,'WORLD','6',at=now+timedelta(seconds=5))
def test_moderation_remove_and_restrict(ctx):
 s,p=ctx;r=send_chat_message(s,p[0].id,'WORLD','bad');moderate_chat_message(s,r['id'],'admin','rule')
 assert chat_messages(s,p[1].id,'WORLD')==[]
 restrict_chat_player(s,p[0].id,'admin','timeout',10)
 with pytest.raises(ValueError,match='moderation'):send_chat_message(s,p[0].id,'WORLD','again')
def test_metadata(ctx):
 s,p=ctx;r=send_chat_message(s,p[0].id,'WHISPER','hi','B');x=chat_messages(s,p[1].id,'WHISPER')[0]
 assert x['sender']=='A' and x['recipient']=='B' and x['channel']=='WHISPER' and x['timestamp']
