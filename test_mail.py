
from datetime import datetime,timezone,timedelta
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Account,Player,Mail
from app.service import *
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'mail.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='a@x');b=Account(email='b@x');s.add_all([a,b]);s.flush();p=Player(account_id=a.id,name='Alice');q=Player(account_id=b.id,name='Bob');s.add_all([p,q]);s.commit();yield s,p,q;s.close()
def test_send_inbox_sent_read_and_soft_delete(ctx):
 s,a,b=ctx;r=send_player_mail(s,a.id,'Bob','Hello','Body','k1')
 assert mail_box(s,b.id,'inbox')[0]['read'] is False and mail_box(s,a.id,'sent')[0]['id']==r['mail_id']
 read_mail(s,b.id,r['mail_id']);assert mail_box(s,b.id,'inbox')[0]['read'] is True
 delete_mail(s,b.id,r['mail_id'],'inbox');assert mail_box(s,b.id,'inbox')==[] and len(mail_box(s,a.id,'sent'))==1
 delete_mail(s,a.id,r['mail_id'],'sent');assert s.get(Mail,r['mail_id']) is None
def test_reply_must_match_original_sender(ctx):
 s,a,b=ctx;r=send_player_mail(s,a.id,'Bob','Hi','x','1')
 out=send_player_mail(s,b.id,'Alice','Re: Hi','reply','2',r['mail_id']);assert s.get(Mail,out['mail_id']).reply_to_mail_id==r['mail_id']
 with pytest.raises(ValueError):send_player_mail(s,b.id,'Bob','bad','x','3',r['mail_id'])
def test_recipient_lookup_case_insensitive_exact_send(ctx):
 s,a,b=ctx;assert player_recipient_lookup(s,'bo')[0]['name']=='Bob'
 r=send_player_mail(s,a.id,'bOb','x','y','1');assert s.get(Mail,r['mail_id']).recipient_player_id==b.id
def test_validation(ctx):
 s,a,b=ctx
 for subj,body in [('', 'x'),('x',''),('x'*121,'y'),('x','y'*5001)]:
  with pytest.raises(ValueError):send_player_mail(s,a.id,'Bob',subj,body,'k'+str(len(subj)+len(body)))
 with pytest.raises(ValueError):send_player_mail(s,a.id,'Alice','x','y','self')
 with pytest.raises(ValueError):send_player_mail(s,a.id,'Nobody','x','y','none')
def test_idempotent_send(ctx):
 s,a,b=ctx;x=send_player_mail(s,a.id,'Bob','x','y','same');y=send_player_mail(s,a.id,'Bob','x','y','same');assert x['mail_id']==y['mail_id'] and y['duplicate']
def test_rate_limit_global_and_per_recipient(ctx):
 s,a,b=ctx;now=datetime.now(timezone.utc)
 for i in range(5):send_player_mail(s,a.id,'Bob',f'x{i}','y',f'k{i}',at=now+timedelta(seconds=i))
 with pytest.raises(ValueError,match='recipient mail rate'):send_player_mail(s,a.id,'Bob','overflow','y','over',at=now+timedelta(seconds=5))
def test_system_mail_cannot_be_spoofed_or_replied(ctx):
 s,a,b=ctx;m=create_system_mail(s,b.id,'System','Notice','maintenance');s.commit()
 assert mail_box(s,b.id,'inbox')[0]['sender']=='System'
 with pytest.raises(ValueError,match='system mail'):send_player_mail(s,b.id,'Alice','Re','x','r',m.id)
def test_ownership_enforced(ctx):
 s,a,b=ctx;r=send_player_mail(s,a.id,'Bob','x','y','1')
 with pytest.raises(ValueError):read_mail(s,999,r['mail_id'])
 with pytest.raises(ValueError):delete_mail(s,b.id,r['mail_id'],'sent')
