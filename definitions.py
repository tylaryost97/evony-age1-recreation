import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
DATA=json.loads((ROOT/'game_definitions'/'core.json').read_text())
def building_def(key): return DATA['buildings'].get(key)
def building_level(key,level): return DATA['building_levels'].get(key,{}).get(str(level))
def town_hall_level(level): return DATA['town_hall_levels'].get(str(level))
def cottage_level(level): return DATA['building_levels'].get('cottage',{}).get(str(level))
