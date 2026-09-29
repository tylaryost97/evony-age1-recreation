
import json
from pathlib import Path
from app.combat import *
ROOT=Path(__file__).resolve().parents[1]
DEFS=json.loads((ROOT/'game_definitions/core.json').read_text())['troop_types']
def inp(a,d,at=None,dt=None,fort=None,wall=0):
 return {'unit_definitions':DEFS,'attacker':{'troops':a,'technologies':at or {},'hero_attack':0},'defender':{'troops':d,'technologies':dt or {},'hero_attack':0,'fortifications':fort or {},'wall_level':wall}}
def test_deterministic_same_input_same_result():
 x=inp({'archer':1000,'warrior':1},{'archer':1000,'warrior':1},{'archery':10},{'archery':9})
 assert simulateBattle(x)==simulateBattle(x)
def test_opening_distance_is_200_plus_modified_longest_range():
 r=simulateBattle(inp({'archer':10},{'warrior':10},{'archery':10}))
 assert r.opening_distance==200+1800
def test_higher_range_archers_get_first_fire():
 r=simulateBattle(inp({'archer':1000},{'archer':1000},{'archery':10},{'archery':0}))
 first=[e for e in r.round_log[0]['events'] if e['phase']=='attack']
 assert any(e['attacker_side']=='attacker' for e in first)
 assert not any(e['attacker_side']=='defender' for e in first)
def test_military_tradition_iron_working_medicine_change_resolution():
 base=simulateBattle(inp({'warrior':1000},{'warrior':1000}))
 tech=simulateBattle(inp({'warrior':1000},{'warrior':1000},{'military_tradition':10},{'iron_working':10,'medicine':10}))
 assert base.attacker_losses!=tech.attacker_losses or base.defender_losses!=tech.defender_losses
def test_layers_are_distinct_targets_not_pooled_hp():
 r=simulateBattle(inp({'archer':1000},{'warrior':1,'archer':1000}))
 attacked=[e['target'] for e in r.round_log[0]['events'] if e['phase']=='attack' and e['attacker_side']=='attacker']
 assert attacked and len(set(attacked))==1
def test_round_cap_defaults_to_defender():
 rules=Age1CombatRules(max_rounds=1)
 x=inp({'battering_ram':100},{'battering_ram':100}); x['unit_definitions']['battering_ram']=dict(x['unit_definitions']['battering_ram'],life=10**9); r=simulateBattle(x,rules)
 assert r.winner=='defender' and r.reason=='ROUND_CAP_DEFENDER_WINS'
def test_abatis_only_targets_mounted():
 r=simulateBattle(inp({'warrior':100},{},fort={'abatis':100}))
 # No eligible target for abatis, so it never attacks warrior.
 assert not any(e['attacker']=='abatis' for q in r.round_log for e in q['events'] if e['phase']=='attack')
def test_trap_behavior_is_documented_but_disputed_curve_is_configurable():
 r=simulateBattle(inp({'warrior':100},{},fort={'trap':100}))
 assert 'fortifications' in r.uncertainties
 assert r.attacker_losses['warrior']==100
 disabled=simulateBattle(inp({'warrior':100},{},fort={'trap':100}),Age1CombatRules(obstacle_casualty_rule='DISABLED_UNTIL_VERIFIED'))
 assert disabled.attacker_losses['warrior']==0
def test_archer_tower_range_uses_wall_and_archery():
 r=simulateBattle(inp({'archer':10},{},dt={'archery':3},fort={'archer_tower':10},wall=5))
 expected=1300*(1+.05*(5+3))
 # opening longest should include tower formula.
 assert r.opening_distance==200+expected
def test_hero_attack_uncertainty_is_not_invented():
 a=inp({'warrior':100},{'warrior':100});a['attacker']['hero_attack']=200
 r=simulateBattle(a)
 assert 'hero_attack' in r.uncertainties
def test_result_contains_report_grade_round_detail():
 r=simulateBattle(inp({'cavalry':100},{'archer':100}))
 assert r.round_log and {'winner','reason','rounds','attacker_survivors','defender_survivors'} <= r.__dict__.keys()
