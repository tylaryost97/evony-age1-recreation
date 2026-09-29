
from app.service import DATA
def test_exact_workshop_table_and_metal_casting_gate():
 exp=[(150,1500,500,1500,540),(300,3000,1000,3000,1080),(600,6000,2000,6000,2160),(1200,12000,4000,12000,4320),(2400,24000,8000,24000,8640),(4800,48000,16000,48000,17280),(9600,96000,32000,96000,34560),(19200,192000,64000,192000,69120),(38400,384000,128000,384000,138240),(76800,768000,256000,768000,276480)]
 for lv,e in enumerate(exp,1):
  d=DATA['building_levels']['workshop'][str(lv)];assert (d['cost']['food'],d['cost']['lumber'],d['cost']['stone'],d['cost']['iron'],d['seconds'])==e
  assert DATA['technologies']['metal_casting']['levels'][str(lv)]['building_requirements']=={'workshop':'TARGET_LEVEL'}
 assert DATA['building_levels']['workshop']['1']['prerequisites']==[{'building':'forge','level':2}]
 assert DATA['building_levels']['workshop']['10']['item_cost']=={'michelangelos_script':1}
