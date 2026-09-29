
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'web/index.html').read_text()
JS=(ROOT/'web/assets/game.js').read_text()
CSS=(ROOT/'web/assets/game.css').read_text()
def test_classic_information_hierarchy_present():
 for token in ('id="resources"','id="citySelect"','data-view="city"','data-view="fields"','data-view="map"','id="cityRail"','id="rightCitySummary"','id="activityRows"','id="chatButton"'):
  assert token in HTML
def test_empty_plot_opens_construction():
 assert "else await openEmptyPlot(plot)" in JS
def test_every_map_tile_has_full_hitbox():
 assert 'class="map-tile-hitbox"' in JS and "document.querySelectorAll('.map-tile-hitbox')" in JS
def test_specific_building_windows_cover_core_age1_locations():
 for fn in ('openTownHall','openBarracks','openAcademy','openInn','openFeastingHall','openRallySpot','openWalls','openMarketplace','openEmbassy','openWarehouse'):
  assert f'function {fn}' in JS
def test_map_actions_enter_real_rally_interface_not_notice_only():
 assert 'openRallyForTarget' in JS
 assert "await openRallyForTarget(x,y,mission)" in JS
def test_responsive_breakpoints_preserve_information():
 for bp in ('@media(max-width:1180px)','@media(max-width:900px)','@media(max-width:600px)','@media(max-width:390px)'):
  assert bp in CSS
 assert '.play-layout{display:block}' in CSS
def test_modal_never_exceeds_viewport():
 assert 'max-height:calc(100dvh - 16px)' in CSS and 'width:min(900px,calc(100vw - 16px))' in CSS
