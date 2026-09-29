from datetime import datetime, timezone
from sqlalchemy import String,Integer,Float,Boolean,DateTime,ForeignKey,UniqueConstraint,Text,JSON
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base

def now(): return datetime.now(timezone.utc)
class IDMixin:
 id:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
class Account(Base,IDMixin):
 __tablename__='accounts'; email:Mapped[str]=mapped_column(String,unique=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Player(Base,IDMixin):
 __tablename__='players'; account_id:Mapped[int]=mapped_column(ForeignKey('accounts.id')); name:Mapped[str]=mapped_column(String,unique=True); prestige:Mapped[int]=mapped_column(Integer,default=0); honor:Mapped[int]=mapped_column(Integer,default=0); title_rank_key:Mapped[str|None]=mapped_column(String,nullable=True)
class BeginnerProtection(Base,IDMixin):
 __tablename__='beginner_protection'
 player_id:Mapped[int]=mapped_column(ForeignKey('players.id'),unique=True,index=True)
 started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
 expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
 ended_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
 end_reason:Mapped[str|None]=mapped_column(String(64),nullable=True)
 notified_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class PlayerSetting(Base,IDMixin):
 __tablename__='player_settings'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); key:Mapped[str]=mapped_column(String); value:Mapped[dict]=mapped_column(JSON,default=dict); __table_args__=(UniqueConstraint('player_id','key'),)
class Alliance(Base,IDMixin): __tablename__='alliances'; name:Mapped[str]=mapped_column(String,unique=True); information:Mapped[str]=mapped_column(Text,default=''); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class AllianceMember(Base,IDMixin):
 __tablename__='alliance_members'; alliance_id:Mapped[int]=mapped_column(ForeignKey('alliances.id')); player_id:Mapped[int]=mapped_column(ForeignKey('players.id'),unique=True); rank:Mapped[str]=mapped_column(String)
class City(Base,IDMixin):
 __tablename__='cities'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); name:Mapped[str]=mapped_column(String); x:Mapped[int]=mapped_column(Integer); y:Mapped[int]=mapped_column(Integer); population:Mapped[int]=mapped_column(Integer,default=0); idle_population:Mapped[int]=mapped_column(Integer,default=0); gold:Mapped[int]=mapped_column(Integer,default=0); tax_rate:Mapped[int]=mapped_column(Integer,default=0); loyalty:Mapped[int]=mapped_column(Integer,default=0); grievance:Mapped[int]=mapped_column(Integer,default=0); public_sentiment:Mapped[int]=mapped_column(Integer,default=0); last_settled_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); gold_fractional:Mapped[float]=mapped_column(Float,default=0); food_upkeep_fractional:Mapped[float]=mapped_column(Float,default=0); hero_salary_fractional:Mapped[float]=mapped_column(Float,default=0); __table_args__=(UniqueConstraint('x','y'),)
class CityBuildingPlot(Base,IDMixin):
 __tablename__='city_building_plots'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); plot_index:Mapped[int]=mapped_column(Integer); __table_args__=(UniqueConstraint('city_id','plot_index'),)
class ExteriorFieldPlot(Base,IDMixin):
 __tablename__='exterior_field_plots'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); plot_index:Mapped[int]=mapped_column(Integer); __table_args__=(UniqueConstraint('city_id','plot_index'),)
class Building(Base,IDMixin):
 __tablename__='buildings'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); plot_kind:Mapped[str]=mapped_column(String); plot_index:Mapped[int]=mapped_column(Integer); definition_key:Mapped[str]=mapped_column(String); level:Mapped[int]=mapped_column(Integer,default=0); __table_args__=(UniqueConstraint('city_id','plot_kind','plot_index'),)
class ConstructionQueue(Base,IDMixin):
 __tablename__='construction_queues'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); building_id:Mapped[int]=mapped_column(ForeignKey('buildings.id')); target_level:Mapped[int]=mapped_column(Integer); started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); completes_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); status:Mapped[str]=mapped_column(String,default='ACTIVE')
class Resource(Base,IDMixin):
 __tablename__='resources'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); kind:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer,default=0); production_per_hour:Mapped[float]=mapped_column(Float,default=0); capacity:Mapped[int]=mapped_column(Integer,default=0); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); __table_args__=(UniqueConstraint('city_id','kind'),)
class Hero(Base,IDMixin):
 __tablename__='heroes'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); city_id:Mapped[int|None]=mapped_column(ForeignKey('cities.id'),nullable=True); name:Mapped[str]=mapped_column(String); level:Mapped[int]=mapped_column(Integer,default=1); experience:Mapped[int]=mapped_column(Integer,default=0); politics:Mapped[int]=mapped_column(Integer,default=0); attack:Mapped[int]=mapped_column(Integer,default=0); intelligence:Mapped[int]=mapped_column(Integer,default=0); loyalty:Mapped[int]=mapped_column(Integer,default=70); assignment:Mapped[str|None]=mapped_column(String,nullable=True); captured:Mapped[bool]=mapped_column(Boolean,default=False); captured_from_player_id:Mapped[int|None]=mapped_column(ForeignKey('players.id'),nullable=True); salary_paid_through:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); unassigned_attribute_points:Mapped[int]=mapped_column(Integer,default=0); last_reward_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); base_politics:Mapped[int|None]=mapped_column(Integer,nullable=True); base_attack:Mapped[int|None]=mapped_column(Integer,nullable=True); base_intelligence:Mapped[int|None]=mapped_column(Integer,nullable=True); allocated_politics:Mapped[int]=mapped_column(Integer,default=0); allocated_attack:Mapped[int]=mapped_column(Integer,default=0); allocated_intelligence:Mapped[int]=mapped_column(Integer,default=0); experience_fractional:Mapped[float]=mapped_column(Float,default=0)
class TroopQuantity(Base,IDMixin):
 __tablename__='troop_quantities'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); troop_type_key:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer,default=0); __table_args__=(UniqueConstraint('city_id','troop_type_key'),)
class TrainingQueue(Base,IDMixin):
 __tablename__='training_queues'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); barracks_id:Mapped[int|None]=mapped_column(ForeignKey('buildings.id'),nullable=True); troop_type_key:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer); hero_attack_snapshot:Mapped[int]=mapped_column(Integer,default=0); military_science_snapshot:Mapped[int]=mapped_column(Integer,default=0); duration_seconds:Mapped[int]=mapped_column(Integer,default=0); queued_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); completes_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); status:Mapped[str]=mapped_column(String,default='QUEUED')
class Technology(Base,IDMixin):
 __tablename__='technologies'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); definition_key:Mapped[str]=mapped_column(String); level:Mapped[int]=mapped_column(Integer,default=0); __table_args__=(UniqueConstraint('player_id','definition_key'),)
class ResearchQueue(Base,IDMixin):
 __tablename__='research_queues'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); technology_key:Mapped[str]=mapped_column(String); target_level:Mapped[int]=mapped_column(Integer); started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); completes_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); status:Mapped[str]=mapped_column(String,default='ACTIVE')
class MapTile(Base,IDMixin):
 __tablename__='map_tiles'; x:Mapped[int]=mapped_column(Integer); y:Mapped[int]=mapped_column(Integer); tile_type:Mapped[str]=mapped_column(String); level:Mapped[int]=mapped_column(Integer,default=0); owner_player_id:Mapped[int|None]=mapped_column(ForeignKey('players.id'),nullable=True); __table_args__=(UniqueConstraint('x','y'),)
class NPCCity(Base,IDMixin): __tablename__='npc_cities'; map_tile_id:Mapped[int]=mapped_column(ForeignKey('map_tiles.id'),unique=True); level:Mapped[int]=mapped_column(Integer); resources:Mapped[dict]=mapped_column(JSON,default=dict); troops:Mapped[dict]=mapped_column(JSON,default=dict); fortifications:Mapped[dict]=mapped_column(JSON,default=dict); loyalty:Mapped[int]=mapped_column(Integer,default=100); resources_updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); defenders_updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); loyalty_updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Valley(Base,IDMixin): __tablename__='valleys'; map_tile_id:Mapped[int]=mapped_column(ForeignKey('map_tiles.id'),unique=True); valley_type:Mapped[str]=mapped_column(String); level:Mapped[int]=mapped_column(Integer); city_id:Mapped[int|None]=mapped_column(ForeignKey('cities.id'),nullable=True); defenders:Mapped[dict]=mapped_column(JSON,default=dict); defenders_updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Flat(Base,IDMixin): __tablename__='flats'; map_tile_id:Mapped[int]=mapped_column(ForeignKey('map_tiles.id'),unique=True); level:Mapped[int]=mapped_column(Integer); city_id:Mapped[int|None]=mapped_column(ForeignKey('cities.id'),nullable=True); defenders:Mapped[dict]=mapped_column(JSON,default=dict); defenders_updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Army(Base,IDMixin):
 __tablename__='armies'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); hero_id:Mapped[int|None]=mapped_column(ForeignKey('heroes.id'),nullable=True); troops:Mapped[dict]=mapped_column(JSON,default=dict); resources:Mapped[dict]=mapped_column(JSON,default=dict)
class March(Base,IDMixin):
 __tablename__='marches'; army_id:Mapped[int]=mapped_column(ForeignKey('armies.id')); source_city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); target_x:Mapped[int]=mapped_column(Integer); target_y:Mapped[int]=mapped_column(Integer); mission:Mapped[str]=mapped_column(String); departed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); arrives_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); returns_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); status:Mapped[str]=mapped_column(String); camp_seconds:Mapped[int]=mapped_column(Integer,default=0); distance:Mapped[float]=mapped_column(Float,default=0); travel_seconds:Mapped[int]=mapped_column(Integer,default=0); food_cost:Mapped[int]=mapped_column(Integer,default=0); recalled_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); return_city_id:Mapped[int|None]=mapped_column(ForeignKey('cities.id'),nullable=True); return_x:Mapped[int|None]=mapped_column(Integer,nullable=True); return_y:Mapped[int|None]=mapped_column(Integer,nullable=True); arrival_processed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); resolution_key:Mapped[str|None]=mapped_column(String,nullable=True)
class Battle(Base,IDMixin): __tablename__='battles'; march_id:Mapped[int]=mapped_column(ForeignKey('marches.id')); occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); outcome:Mapped[dict]=mapped_column(JSON,default=dict)
class BattleRound(Base,IDMixin): __tablename__='battle_rounds'; battle_id:Mapped[int]=mapped_column(ForeignKey('battles.id')); round_number:Mapped[int]=mapped_column(Integer); state:Mapped[dict]=mapped_column(JSON,default=dict); __table_args__=(UniqueConstraint('battle_id','round_number'),)
class Fortification(Base,IDMixin):
 __tablename__='fortifications'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); definition_key:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer,default=0); __table_args__=(UniqueConstraint('city_id','definition_key'),)
class ChatMessage(Base,IDMixin):
 __tablename__='chat_messages'
 sender_player_id:Mapped[int]=mapped_column(ForeignKey('players.id'),index=True)
 channel:Mapped[str]=mapped_column(String(16),index=True)
 recipient_player_id:Mapped[int|None]=mapped_column(ForeignKey('players.id'),nullable=True,index=True)
 alliance_id:Mapped[int|None]=mapped_column(ForeignKey('alliances.id'),nullable=True,index=True)
 body:Mapped[str]=mapped_column(String(500))
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
 moderated:Mapped[bool]=mapped_column(Boolean,default=False)
 moderation_reason:Mapped[str|None]=mapped_column(String(200),nullable=True)
class ChatBlock(Base,IDMixin):
 __tablename__='chat_blocks'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); blocked_player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); __table_args__=(UniqueConstraint('player_id','blocked_player_id'),)
class ChatMute(Base,IDMixin):
 __tablename__='chat_mutes'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); muted_player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); __table_args__=(UniqueConstraint('player_id','muted_player_id'),)
class ChatModerationAction(Base,IDMixin):
 __tablename__='chat_moderation_actions'; moderator_label:Mapped[str]=mapped_column(String(64)); target_player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); action:Mapped[str]=mapped_column(String(32)); reason:Mapped[str]=mapped_column(String(500),default=''); expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class Mail(Base,IDMixin):
 __tablename__='mail'
 sender_player_id:Mapped[int|None]=mapped_column(ForeignKey('players.id'),nullable=True,index=True)
 recipient_player_id:Mapped[int]=mapped_column(ForeignKey('players.id'),index=True)
 subject:Mapped[str]=mapped_column(String(120));body:Mapped[str]=mapped_column(Text)
 created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
 read:Mapped[bool]=mapped_column(Boolean,default=False)
 recipient_deleted:Mapped[bool]=mapped_column(Boolean,default=False)
 sender_deleted:Mapped[bool]=mapped_column(Boolean,default=False)
 reply_to_mail_id:Mapped[int|None]=mapped_column(ForeignKey('mail.id'),nullable=True)
 system_kind:Mapped[str|None]=mapped_column(String(64),nullable=True)
 idempotency_key:Mapped[str|None]=mapped_column(String(128),nullable=True)
 __table_args__=(UniqueConstraint('sender_player_id','idempotency_key',name='uq_mail_sender_idempotency'),)
class ReportBase: player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); payload:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); read:Mapped[bool]=mapped_column(Boolean,default=False); deleted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class BattleReport(Base,IDMixin,ReportBase): __tablename__='battle_reports'
class ScoutReport(Base,IDMixin,ReportBase): __tablename__='scout_reports'
class TransportReport(Base,IDMixin,ReportBase): __tablename__='transport_reports'
class ReinforcementReport(Base,IDMixin,ReportBase): __tablename__='reinforcement_reports'
class SystemReport(Base,IDMixin,ReportBase): __tablename__='system_reports'
class QuestProgress(Base,IDMixin): __tablename__='quest_progress'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); quest_key:Mapped[str]=mapped_column(String); state:Mapped[dict]=mapped_column(JSON,default=dict); completed:Mapped[bool]=mapped_column(Boolean,default=False); claimed:Mapped[bool]=mapped_column(Boolean,default=False); __table_args__=(UniqueConstraint('player_id','quest_key'),)
class ItemApplication(Base,IDMixin):
 __tablename__='item_applications'
 player_id:Mapped[int]=mapped_column(ForeignKey('players.id'))
 item_key:Mapped[str]=mapped_column(String,index=True)
 target_type:Mapped[str]=mapped_column(String)
 target_id:Mapped[int]=mapped_column(Integer)
 applied_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
 __table_args__=(UniqueConstraint('item_key','target_type','target_id'),)
class PlayerItem(Base,IDMixin): __tablename__='player_items'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); item_key:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer,default=0); __table_args__=(UniqueConstraint('player_id','item_key'),)
class Buff(Base,IDMixin): __tablename__='buffs'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); buff_key:Mapped[str]=mapped_column(String); starts_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); metadata_json:Mapped[dict]=mapped_column(JSON,default=dict)
class Bookmark(Base,IDMixin): __tablename__='bookmarks'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); x:Mapped[int]=mapped_column(Integer); y:Mapped[int]=mapped_column(Integer); label:Mapped[str]=mapped_column(String); __table_args__=(UniqueConstraint('player_id','x','y'),)
class OperationRequest(Base,IDMixin):
 __tablename__='operation_requests'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); idempotency_key:Mapped[str]=mapped_column(String); operation:Mapped[str]=mapped_column(String); response:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); __table_args__=(UniqueConstraint('player_id','idempotency_key'),)

# First-class normalized state records required by the authoritative domain contract.
class CityCoordinate(Base,IDMixin):
 __tablename__='city_coordinates'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id'),unique=True); x:Mapped[int]=mapped_column(Integer); y:Mapped[int]=mapped_column(Integer); __table_args__=(UniqueConstraint('x','y'),)
class BuildingLevel(Base,IDMixin):
 __tablename__='building_levels'; building_id:Mapped[int]=mapped_column(ForeignKey('buildings.id'),unique=True); level:Mapped[int]=mapped_column(Integer,default=0)
class ResourceProduction(Base,IDMixin):
 __tablename__='resource_production'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); resource_kind:Mapped[str]=mapped_column(String); per_hour:Mapped[float]=mapped_column(Float,default=0); fractional_remainder:Mapped[float]=mapped_column(Float,default=0); last_calculated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); __table_args__=(UniqueConstraint('city_id','resource_kind'),)
class ResourceCapacity(Base,IDMixin):
 __tablename__='resource_capacity'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); resource_kind:Mapped[str]=mapped_column(String); capacity:Mapped[int]=mapped_column(Integer,default=0); __table_args__=(UniqueConstraint('city_id','resource_kind'),)
class PopulationState(Base,IDMixin):
 __tablename__='population_state'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id'),unique=True); population:Mapped[int]=mapped_column(Integer,default=0); idle_population:Mapped[int]=mapped_column(Integer,default=0); population_limit:Mapped[int]=mapped_column(Integer,default=0); last_population_tick_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class CityEconomyState(Base,IDMixin):
 __tablename__='city_economy_state'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id'),unique=True); gold:Mapped[int]=mapped_column(Integer,default=0); tax_rate:Mapped[int]=mapped_column(Integer,default=0); loyalty:Mapped[int]=mapped_column(Integer,default=0); grievance:Mapped[int]=mapped_column(Integer,default=0); public_sentiment:Mapped[int]=mapped_column(Integer,default=0); last_settled_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); gold_fractional:Mapped[float]=mapped_column(Float,default=0); food_upkeep_fractional:Mapped[float]=mapped_column(Float,default=0); hero_salary_fractional:Mapped[float]=mapped_column(Float,default=0)
class HeroStats(Base,IDMixin):
 __tablename__='hero_stats'; hero_id:Mapped[int]=mapped_column(ForeignKey('heroes.id'),unique=True); politics:Mapped[int]=mapped_column(Integer,default=0); attack:Mapped[int]=mapped_column(Integer,default=0); intelligence:Mapped[int]=mapped_column(Integer,default=0)
class HeroExperience(Base,IDMixin):
 __tablename__='hero_experience'; hero_id:Mapped[int]=mapped_column(ForeignKey('heroes.id'),unique=True); level:Mapped[int]=mapped_column(Integer,default=1); experience:Mapped[int]=mapped_column(Integer,default=0)
class HeroAssignment(Base,IDMixin):
 __tablename__='hero_assignments'; hero_id:Mapped[int]=mapped_column(ForeignKey('heroes.id'),unique=True); city_id:Mapped[int|None]=mapped_column(ForeignKey('cities.id'),nullable=True); assignment_key:Mapped[str|None]=mapped_column(String,nullable=True); starts_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); ends_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
class PlayerProgression(Base,IDMixin):
 __tablename__='player_progression'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id'),unique=True); prestige:Mapped[int]=mapped_column(Integer,default=0); honor:Mapped[int]=mapped_column(Integer,default=0); title_rank_key:Mapped[str|None]=mapped_column(String,nullable=True)
class AllianceRank(Base,IDMixin):
 __tablename__='alliance_ranks'; alliance_id:Mapped[int]=mapped_column(ForeignKey('alliances.id')); rank_key:Mapped[str]=mapped_column(String); permissions:Mapped[dict]=mapped_column(JSON,default=dict); __table_args__=(UniqueConstraint('alliance_id','rank_key'),)
class MarchMission(Base,IDMixin):
 __tablename__='march_missions'; march_id:Mapped[int]=mapped_column(ForeignKey('marches.id'),unique=True); mission_key:Mapped[str]=mapped_column(String); mission_state:Mapped[dict]=mapped_column(JSON,default=dict)

class WarehouseAllocation(Base,IDMixin):
 __tablename__='warehouse_allocations'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id'),unique=True); food_percent:Mapped[int]=mapped_column(Integer,default=100); lumber_percent:Mapped[int]=mapped_column(Integer,default=0); stone_percent:Mapped[int]=mapped_column(Integer,default=0); iron_percent:Mapped[int]=mapped_column(Integer,default=0)

class InnCandidate(Base,IDMixin):
 __tablename__='inn_candidates'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); slot_index:Mapped[int]=mapped_column(Integer); name:Mapped[str]=mapped_column(String); level:Mapped[int]=mapped_column(Integer); politics:Mapped[int]=mapped_column(Integer); attack:Mapped[int]=mapped_column(Integer); intelligence:Mapped[int]=mapped_column(Integer); loyalty:Mapped[int]=mapped_column(Integer,default=70); generated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); refreshes_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); generation_source:Mapped[str]=mapped_column(String,default='HISTORICAL_VALUE_UNKNOWN'); __table_args__=(UniqueConstraint('city_id','slot_index'),)

class AllianceInvitation(Base,IDMixin):
 __tablename__='alliance_invitations'; alliance_id:Mapped[int]=mapped_column(ForeignKey('alliances.id')); inviter_player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); status:Mapped[str]=mapped_column(String,default='PENDING'); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); __table_args__=(UniqueConstraint('alliance_id','player_id'),)
class AllianceRelation(Base,IDMixin):
 __tablename__='alliance_relations'; alliance_id:Mapped[int]=mapped_column(ForeignKey('alliances.id')); other_alliance_id:Mapped[int]=mapped_column(ForeignKey('alliances.id')); state:Mapped[str]=mapped_column(String); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); __table_args__=(UniqueConstraint('alliance_id','other_alliance_id'),)
class AllianceChatMessage(Base,IDMixin):
 __tablename__='alliance_chat_messages'; alliance_id:Mapped[int]=mapped_column(ForeignKey('alliances.id')); player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); body:Mapped[str]=mapped_column(String(500)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now,index=True)
class AllianceApplication(Base,IDMixin):
 __tablename__='alliance_applications'; alliance_id:Mapped[int]=mapped_column(ForeignKey('alliances.id')); player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); status:Mapped[str]=mapped_column(String,default='PENDING'); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); __table_args__=(UniqueConstraint('alliance_id','player_id'),)
class EmbassyState(Base,IDMixin):
 __tablename__='embassy_states'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id'),unique=True); allow_allied_garrison:Mapped[bool]=mapped_column(Boolean,default=False)
class ForeignGarrison(Base,IDMixin):
 __tablename__='foreign_garrisons'; host_city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); owner_player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); source_city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); army_id:Mapped[int]=mapped_column(ForeignKey('armies.id'),unique=True); hero_id:Mapped[int|None]=mapped_column(ForeignKey('heroes.id'),nullable=True); troops:Mapped[dict]=mapped_column(JSON,default=dict); resources:Mapped[dict]=mapped_column(JSON,default=dict); arrived_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); status:Mapped[str]=mapped_column(String,default='GARRISONED')

class MarketOrder(Base,IDMixin):
 __tablename__='market_orders'; player_id:Mapped[int]=mapped_column(ForeignKey('players.id')); city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); side:Mapped[str]=mapped_column(String); resource_kind:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer); remaining_quantity:Mapped[int]=mapped_column(Integer); price:Mapped[float]=mapped_column(Float); status:Mapped[str]=mapped_column(String,default='OPEN'); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
class MarketTrade(Base,IDMixin):
 __tablename__='market_trades'; resource_kind:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer); price:Mapped[float]=mapped_column(Float); buy_order_id:Mapped[int]=mapped_column(ForeignKey('market_orders.id')); sell_order_id:Mapped[int]=mapped_column(ForeignKey('market_orders.id')); buyer_city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); seller_city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); gold_value:Mapped[int]=mapped_column(Integer); buyer_fee:Mapped[int]=mapped_column(Integer); seller_fee:Mapped[int]=mapped_column(Integer); matched_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); delivers_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True); status:Mapped[str]=mapped_column(String,default='MATCHED')

class RallySpotState(Base,IDMixin):
 __tablename__='rally_spot_states'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id'),unique=True); open_gates:Mapped[bool]=mapped_column(Boolean,default=False)
class WoundedTroop(Base,IDMixin):
 __tablename__='wounded_troops'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); troop_type_key:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer,default=0); __table_args__=(UniqueConstraint('city_id','troop_type_key'),)

class FortificationQueue(Base,IDMixin):
 __tablename__='fortification_queues'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); definition_key:Mapped[str]=mapped_column(String); quantity:Mapped[int]=mapped_column(Integer); started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); completes_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); status:Mapped[str]=mapped_column(String,default='QUEUED'); position:Mapped[int]=mapped_column(Integer); duration_seconds:Mapped[int]=mapped_column(Integer,default=0)

class DemolitionQueue(Base,IDMixin):
 __tablename__='demolition_queues'; city_id:Mapped[int]=mapped_column(ForeignKey('cities.id')); building_id:Mapped[int]=mapped_column(ForeignKey('buildings.id')); from_level:Mapped[int]=mapped_column(Integer); to_level:Mapped[int]=mapped_column(Integer); started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); completes_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); refund:Mapped[dict]=mapped_column(JSON,default=dict); status:Mapped[str]=mapped_column(String,default='ACTIVE')

class HeroBuff(Base,IDMixin):
 __tablename__='hero_buffs'; hero_id:Mapped[int]=mapped_column(ForeignKey('heroes.id')); buff_key:Mapped[str]=mapped_column(String); attribute_key:Mapped[str]=mapped_column(String); multiplier:Mapped[float]=mapped_column(Float,default=1.25); starts_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now); expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True)); __table_args__=(UniqueConstraint('hero_id','buff_key'),)
