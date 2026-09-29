
from app.service import DATA
def test_exact_relief_station_table_and_speed_steps():
 exp=[(1500,5000,4500,500,3600),(3000,10000,9000,1000,7200),(6000,20000,18000,2000,14400),(12000,40000,36000,4000,28800),(24000,80000,72000,8000,57600),(48000,160000,144000,16000,115200),(96000,320000,288000,32000,230400),(192000,640000,576000,64000,460800),(384000,1280000,1152000,128000,921600),(768000,2560000,2304000,256000,1843200)]
 mult=[2,2,2,3,4,4,4,5,5,6]
 for lv,e in enumerate(exp,1):
  d=DATA['building_levels']['relief_station'][str(lv)];assert (d['cost']['food'],d['cost']['lumber'],d['cost']['stone'],d['cost']['iron'],d['seconds'])==e
  assert d['city_support_speed_multiplier']==mult[lv-1]
  assert {'technology':'horseback_riding','level':lv} in d['prerequisites']
 assert {'building':'stable','level':1} in DATA['building_levels']['relief_station']['1']['prerequisites']
 assert DATA['building_levels']['relief_station']['10']['item_cost']=={'michelangelos_script':1}
