
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import *
from app.service import *
def test_exact_forge_table():
 exp=[(125,1000,600,1200,180),(250,2000,1200,2400,360),(500,4000,2400,4800,720),(1000,8000,4800,9600,1440),(2000,16000,9600,19200,2880),(4000,32000,19200,38400,5760),(8000,64000,38400,76800,11520),(16000,128000,76800,153600,23040),(32000,256000,153600,307200,46080),(64000,512000,307200,614400,92160)]
 for lv,e in enumerate(exp,1):
  d=DATA['building_levels']['forge'][str(lv)];assert (d['cost']['food'],d['cost']['lumber'],d['cost']['stone'],d['cost']['iron'],d['seconds'])==e
 assert DATA['building_levels']['forge']['1']['prerequisites']==[{'building':'ironmine','level':3}]
 assert DATA['building_levels']['forge']['10']['item_cost']=={'michelangelos_script':1}
def test_military_science_requires_matching_forge(tmp_path):
 e=create_engine(f"sqlite:///{tmp_path/'x.db'}");Base.metadata.create_all(e);S=sessionmaker(e,expire_on_commit=False)
 with S() as s:
  a=Account(email='x@x');s.add(a);s.flush();p=Player(account_id=a.id,name='P');s.add(p);s.flush();c=City(player_id=p.id,name='C',x=1,y=1,gold=99999999);s.add(c);s.flush();s.add(CityEconomyState(city_id=c.id,gold=99999999))
  for k in ('food','lumber','stone','iron'):s.add(Resource(city_id=c.id,kind=k,quantity=99999999))
  for key,lv,plot in [('academy',10,2),('forge',1,3)]:
   b=Building(city_id=c.id,plot_kind='CITY',plot_index=plot,definition_key=key,level=lv);s.add(b);s.flush();s.add(BuildingLevel(building_id=b.id,level=lv))
  s.add(Technology(player_id=p.id,definition_key='military_science',level=1));s.flush()
  try:start_research(s,p.id,c.id,'military_science','ms2');assert False
  except ValueError as x:assert 'forge level 2 required' in str(x)
