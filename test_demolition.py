
from datetime import datetime,timezone,timedelta
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
def fixture(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'d.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S()
 a=Account(email='d@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1);s.add(c);s.flush()
 for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=0))
 b=Building(city_id=c.id,plot_kind='CITY',plot_index=5,definition_key='cottage',level=2);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=2));s.add(PlayerItem(player_id=p.id,item_key='dynamite',quantity=1));s.commit();return s,p,c,b
def test_labor_downgrade_is_timed_refunds_30_percent_and_persists(tmp_path):
 s,p,c,b=fixture(tmp_path);r=start_demolish_one_level(s,p.id,c.id,b.id,'one');assert r['to_level']==1 and r['refund']=={'food':60,'lumber':300,'stone':60,'iron':30}
 q=s.get(DemolitionQueue,r['demolition_id']);assert q.status=='ACTIVE' and b.level==2
 q.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1);s.flush();done=complete_demolition(s,c.id);assert done and done[0].status=='COMPLETE'
 assert s.scalar(select(Resource).where(Resource.city_id==c.id,Resource.kind=='lumber')).quantity==300;s.close()
def test_dynamite_immediate_no_refund_and_consumes_item(tmp_path):
 s,p,c,b=fixture(tmp_path);out=dynamite_building(s,p.id,c.id,b.id,'boom');assert out['refund']=={} and out['status']=='DEMOLISHED' and out['dynamite_consumed']==1;s.close()
def test_duplicate_demolition_request_is_idempotent(tmp_path):
 s,p,c,b=fixture(tmp_path);a=start_demolish_one_level(s,p.id,c.id,b.id,'same');z=start_demolish_one_level(s,p.id,c.id,b.id,'same');assert a==z and len(s.scalars(select(DemolitionQueue)).all())==1;s.close()
