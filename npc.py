"""Persistent Evony Age I NPC/barbarian city domain rules."""
from datetime import datetime,timezone,timedelta
from math import floor
NPC_LEVELS={
1:{'resources':{'food':100000,'lumber':20000,'stone':20000,'iron':20000,'gold':55000},'troops':{'warrior':50,'pikeman':40,'swordsman':35,'archer':15,'cavalry':8},'fortifications':{'trap':1000}},
2:{'resources':{'food':200000,'lumber':30000,'stone':30000,'iron':30000,'gold':65000},'troops':{'warrior':50,'pikeman':45,'swordsman':40,'archer':30,'cavalry':25},'fortifications':{'trap':1850,'abatis':550}},
3:{'resources':{'food':900000,'lumber':75000,'stone':75000,'iron':75000,'gold':75000},'troops':{'warrior':200,'pikeman':160,'swordsman':65,'archer':40,'cavalry':60},'fortifications':{'trap':2000,'abatis':1000,'archer_tower':650}},
4:{'resources':{'food':1600000,'lumber':120000,'stone':120000,'iron':120000,'gold':300000},'troops':{'warrior':400,'pikeman':400,'swordsman':100,'archer':100,'cavalry':150},'fortifications':{'trap':4500,'abatis':1875,'archer_tower':550}},
5:{'resources':{'food':3000000,'lumber':180000,'stone':180000,'iron':180000,'gold':450000},'troops':{'warrior':750,'pikeman':1000,'swordsman':350,'archer':250,'cavalry':200},'fortifications':{'trap':3750,'abatis':1875,'archer_tower':1250,'rolling_log':750}},
6:{'resources':{'food':4000000,'lumber':200000,'stone':200000,'iron':200000,'gold':600000},'troops':{'warrior':4000,'pikeman':750,'swordsman':550,'archer':500,'cavalry':450},'fortifications':{'trap':4250,'abatis':1500,'archer_tower':1500,'rolling_log':950,'defensive_trebuchet':400}},
7:{'resources':{'food':4500000,'lumber':500000,'stone':500000,'iron':500000,'gold':800000},'troops':{'warrior':12000,'pikeman':3000,'swordsman':750,'archer':800,'cavalry':750},'fortifications':{'trap':5600,'abatis':2800,'archer_tower':1850,'rolling_log':1100,'defensive_trebuchet':700}},
8:{'resources':{'food':8000000,'lumber':800000,'stone':800000,'iron':800000,'gold':1000000},'troops':{'warrior':15000,'pikeman':6750,'swordsman':4000,'archer':3000,'cavalry':2000},'fortifications':{'trap':7200,'abatis':3600,'archer_tower':2400,'rolling_log':1440,'defensive_trebuchet':900}},
9:{'resources':{'food':14000000,'lumber':550000,'stone':550000,'iron':550000,'gold':1200000},'troops':{'warrior':60000,'pikeman':18000,'swordsman':2000,'archer':6750,'cavalry':2500},'fortifications':{'trap':9000,'abatis':4500,'archer_tower':3000,'rolling_log':1800,'defensive_trebuchet':1150}},
10:{'resources':{'food':19000000,'lumber':600000,'stone':600000,'iron':600000,'gold':1500000},'troops':{'warrior':400000},'fortifications':{'trap':11000,'abatis':5500,'archer_tower':3666,'rolling_log':2200,'defensive_trebuchet':1375}},
}
RESOURCE_REGEN_SECONDS=8*3600
DEFENDER_TICK_SECONDS=360
DEFENDER_REGEN_PER_TICK=.10
LOYALTY_REGEN_PER_TICK=3

def initialize_npc(npc,now=None,force=False):
 now=now or datetime.now(timezone.utc); spec=NPC_LEVELS[int(npc.level)]
 if force or not npc.resources:npc.resources=dict(spec['resources'])
 if force or not npc.troops:npc.troops=dict(spec['troops'])
 if force or not npc.fortifications:npc.fortifications=dict(spec['fortifications'])
 if force:npc.loyalty=100
 npc.resources_updated_at=npc.resources_updated_at or now;npc.defenders_updated_at=npc.defenders_updated_at or now;npc.loyalty_updated_at=npc.loyalty_updated_at or now
 return npc

def _aware(dt):return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt

def regenerate_npc(npc,now=None):
 now=now or datetime.now(timezone.utc);initialize_npc(npc,now);spec=NPC_LEVELS[npc.level]
 # Resources regenerate continuously to their level maximum over eight hours.
 elapsed=max(0,(now-_aware(npc.resources_updated_at)).total_seconds())
 if elapsed:
  cur=dict(npc.resources)
  for k,maximum in spec['resources'].items():cur[k]=min(maximum,int(cur.get(k,0)+maximum*elapsed/RESOURCE_REGEN_SECONDS))
  npc.resources=cur;npc.resources_updated_at=now
 # Troops/fortifications restore 10% of maximum each complete six-minute tick.
 ticks=int(max(0,(now-_aware(npc.defenders_updated_at)).total_seconds())//DEFENDER_TICK_SECONDS)
 if ticks:
  for attr in ('troops','fortifications'):
   cur=dict(getattr(npc,attr)); maxima=spec[attr]
   for k,maximum in maxima.items():cur[k]=min(maximum,cur.get(k,0)+int(maximum*DEFENDER_REGEN_PER_TICK)*ticks)
   setattr(npc,attr,cur)
  npc.defenders_updated_at=_aware(npc.defenders_updated_at)+timedelta(seconds=ticks*DEFENDER_TICK_SECONDS)
 lticks=int(max(0,(now-_aware(npc.loyalty_updated_at)).total_seconds())//DEFENDER_TICK_SECONDS)
 if lticks:
  npc.loyalty=min(100,npc.loyalty+LOYALTY_REGEN_PER_TICK*lticks);npc.loyalty_updated_at=_aware(npc.loyalty_updated_at)+timedelta(seconds=lticks*DEFENDER_TICK_SECONDS)
 return npc

def npc_snapshot(npc):
 spec=NPC_LEVELS[npc.level]
 return {'id':npc.id,'level':npc.level,'resources':dict(npc.resources),'troops':dict(npc.troops),'fortifications':dict(npc.fortifications),'loyalty':npc.loyalty,'maximums':spec}
