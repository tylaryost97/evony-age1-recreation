import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
DB_URL=os.getenv('GAME_DATABASE_URL','sqlite:///./data/game.db')
engine=create_engine(DB_URL,connect_args={'check_same_thread':False,'timeout':30} if DB_URL.startswith('sqlite') else {},future=True)
if DB_URL.startswith('sqlite'):
 @event.listens_for(engine,'connect')
 def pragmas(conn,_):
  cur=conn.cursor(); cur.execute('PRAGMA foreign_keys=ON'); cur.execute('PRAGMA journal_mode=WAL'); cur.close()
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False,future=True)
class Base(DeclarativeBase): pass
