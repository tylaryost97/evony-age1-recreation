
from datetime import datetime,timezone
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
from app.service import _progression,_set_progression_keys,_item_quantity
@pytest.fixture
def ctx(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'p.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False);s=S();a=Account(email='p@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1,gold=5000000);s.add(c);s.flush()
 s.add(CityEconomyState(city_id=c.id,gold=5000000,last_settled_at=datetime.now(timezone.utc)));b=Building(city_id=c.id,plot_kind='CITY',plot_index=0,definition_key='town_hall',level=10);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=10));s.add(PlayerProgression(player_id=p.id,prestige=300000,honor=123,title_rank_key='Civilian|Civilian'))
 for k in ('cross_medal','rose_medal','lion_medal','honor_medal','courage_medal','wisdom_medal','freedom_medal','justice_medal','nation_medal'):s.add(PlayerItem(player_id=p.id,item_key=k,quantity=100))
 s.commit();yield s,p,c;s.close()
def test_rank_requirements_and_consumption(ctx):
 s,p,c=ctx;x=progression_status(s,p.id,c.id);assert x['rank']=='Civilian' and x['rank_promotion']['next']=='Lieutenant' and x['rank_promotion']['satisfied']
 before=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id)).gold;r=promote_player(s,p.id,c.id,'RANK','Lieutenant','r1');assert r['rank']=='Lieutenant' and r['prestige']==300100
 assert s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id)).gold==before-10000
def test_medals_consumed_but_prestige_requirement_not(ctx):
 s,p,c=ctx;promote_player(s,p.id,c.id,'RANK','Lieutenant','r1');pre=_progression(s,p.id)[0].prestige
 cross=_item_quantity(s,p.id,'cross_medal');rose=_item_quantity(s,p.id,'rose_medal');promote_player(s,p.id,c.id,'TITLE','Knight','t1')
 assert _progression(s,p.id)[2]=='Knight' and _progression(s,p.id)[0].prestige==pre+100
 assert _item_quantity(s,p.id,'cross_medal')==cross-10 and _item_quantity(s,p.id,'rose_medal')==rose-5
def test_city_limits_exact(ctx):
 s,p,c=ctx
 for title,cap in [('Civilian',1),('Knight',2),('Baronet',3),('Baron',4),('Viscount',5),('Earl',6),('Marquis',7),('Duke',8),('Furstin',9),('Prinzessin',10)]:
  pr,rank,_=_progression(s,p.id);_set_progression_keys(pr,rank,title);s.flush();assert player_city_cap(s,p.id)==cap
def test_missing_requirement_displayed_and_server_rejects(ctx):
 s,p,c=ctx;eco=s.scalar(select(CityEconomyState).where(CityEconomyState.city_id==c.id));eco.gold=0;s.flush();q=promotion_preview(s,p.id,'RANK','Lieutenant',c.id);gold=next(x for x in q['requirements'] if x['type']=='gold');assert not gold['satisfied']
 with pytest.raises(ValueError,match='requirements'):promote_player(s,p.id,c.id,'RANK','Lieutenant','x')
def test_rank_sequence(ctx):
 s,p,c=ctx
 for rank in ['Lieutenant','Captain','Major','Colonel','General']:promote_player(s,p.id,c.id,'RANK',rank,'r'+rank)
 assert _progression(s,p.id)[1]=='General'
def test_title_sequence_and_cap(ctx):
 s,p,c=ctx
 for rank in ['Lieutenant','Captain','Major','Colonel','General']:promote_player(s,p.id,c.id,'RANK',rank,'r'+rank)
 for title in ['Knight','Baronet','Baron','Viscount','Earl','Marquis','Duke','Furstin','Prinzessin']:promote_player(s,p.id,c.id,'TITLE',title,'t'+title)
 assert player_city_cap(s,p.id)==10
def test_honor_persists_not_xp_level(ctx):
 s,p,c=ctx;x=progression_status(s,p.id,c.id);assert x['honor']==123 and 'level' not in x
def test_idempotent_promotion(ctx):
 s,p,c=ctx;a=promote_player(s,p.id,c.id,'RANK','Lieutenant','same');b=promote_player(s,p.id,c.id,'RANK','Lieutenant','same');assert a==b
