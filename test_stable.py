
from app.service import DATA
def test_exact_stable_table_and_effects():
 exp=[(1200,2000,800,1000,270),(2400,4000,1600,2000,540),(4800,8000,3200,4000,1080),(9600,16000,6400,8000,2160),(19200,32000,12800,16000,4320),(38400,64000,25600,32000,8640),(76800,128000,51200,64000,17280),(153600,256000,102400,128000,34560),(307200,512000,204800,256000,69120),(614400,1028000,409600,512000,138240)]
 for lv,e in enumerate(exp,1):
  d=DATA['building_levels']['stable'][str(lv)];assert (d['cost']['food'],d['cost']['lumber'],d['cost']['stone'],d['cost']['iron'],d['seconds'])==e
  assert DATA['technologies']['horseback_riding']['levels'][str(lv)]['building_requirements']=={'stable':'TARGET_LEVEL'}
 assert DATA['building_levels']['stable']['1']['prerequisites']==[{'building':'farm','level':5}]
 assert DATA['building_levels']['stable']['10']['item_cost']=={'michelangelos_script':1}
