# Database for slug-to-IMDB mapping and persistent provider telemetry
from sqlalchemy import create_engine, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime, timedelta
from config import Config

Base = declarative_base()

class Mapping(Base):
    __tablename__ = 'mappings'
    slug = Column(String, primary_key=True)
    tmdb_id = Column(String)
    imdb_id = Column(String, index=True)
    provider = Column(String, default='')

class FailedMapping(Base):
    __tablename__ = 'failed_mappings'
    imdb_id = Column(String, primary_key=True)
    checked_at = Column(DateTime, default=datetime.utcnow)

class HealthLog(Base):
    __tablename__ = 'health_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String, index=True)
    status = Column(String)  # 'up', 'degraded', 'down'
    response_ms = Column(Integer, default=0)
    stream_count = Column(Integer, default=0)
    error = Column(String, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow)

class Database:
    def __init__(self):
        if Config.DB_TYPE == 'postgresql':
            engine = create_engine(Config.DATABASE_URL, pool_size=3, max_overflow=5, pool_pre_ping=True, pool_recycle=1800, connect_args={'sslmode': 'require'})
        else:
            engine = create_engine(f'sqlite:///{Config.DB_PATH}', pool_size=3, max_overflow=5)
        Base.metadata.create_all(engine)
        self.Session = scoped_session(sessionmaker(bind=engine))

    def get_mapping(self, slug: str) -> tuple:
        session = self.Session()
        try:
            m = session.query(Mapping).filter_by(slug=slug).first()
            return (m.tmdb_id, m.imdb_id, m.provider) if m else None
        finally: session.close()

    def get_slug_by_imdb(self, imdb_id: str) -> tuple:
        session = self.Session()
        try:
            m = session.query(Mapping).filter_by(imdb_id=imdb_id).first()
            return (m.slug, m.provider) if m else None
        finally: session.close()

    def set_mapping(self, slug: str, tmdb_id: str, imdb_id: str, provider: str = ''):
        session = self.Session()
        try:
            m = session.query(Mapping).filter_by(slug=slug).first()
            if m:
                m.tmdb_id, m.imdb_id, m.provider = tmdb_id, imdb_id, provider
            else:
                session.add(Mapping(slug=slug, tmdb_id=tmdb_id, imdb_id=imdb_id, provider=provider))
            session.commit()
        finally: session.close()

    def is_failed(self, imdb_id: str, ttl_days: int = 30) -> bool:
        session = self.Session()
        try:
            f = session.query(FailedMapping).filter_by(imdb_id=imdb_id).first()
            if not f: return False
            if datetime.utcnow() - f.checked_at > timedelta(days=ttl_days):
                session.delete(f); session.commit()
                return False
            return True
        finally: session.close()

    def add_failed(self, imdb_id: str):
        session = self.Session()
        try:
            f = session.query(FailedMapping).filter_by(imdb_id=imdb_id).first()
            if f: f.checked_at = datetime.utcnow()
            else: session.add(FailedMapping(imdb_id=imdb_id))
            session.commit()
        finally: session.close()

    def record_health(self, provider: str, status: str, response_ms: int = 0, stream_count: int = 0, error: str = None):
        session = self.Session()
        try:
            session.add(HealthLog(
                provider=provider,
                status=status,
                response_ms=response_ms,
                stream_count=stream_count,
                error=error,
                checked_at=datetime.utcnow()
            ))
            session.commit()
        finally:
            session.close()

    def get_health_history(self, provider: str, limit: int = 60) -> list:
        session = self.Session()
        try:
            logs = session.query(HealthLog).filter_by(provider=provider).order_by(HealthLog.id.desc()).limit(limit).all()
            return [l.status for l in reversed(logs)]
        finally:
            session.close()

    def get_health_history_info(self, provider: str, limit: int = 60) -> dict:
        """Return ONLY real recorded checks, with the window start and uptime.

        Callers must not pad this with invented 'up' samples: a fresh VM has only
        a handful of checks, and fabricating a full 90-day history is misleading.
        """
        session = self.Session()
        try:
            logs = session.query(HealthLog).filter_by(provider=provider).order_by(HealthLog.id.desc()).limit(limit).all()
            logs = list(reversed(logs))
            history = [l.status for l in logs]
            uptime = None
            healthy = sum(1 for s in history if s in ('up', 'degraded'))
            if history:
                uptime = round(100.0 * healthy / len(history), 1)
            return {
                'history': history,
                'samples': len(history),
                'since': logs[0].checked_at.isoformat() if logs else None,
                'uptimePct': uptime,
            }
        finally:
            session.close()

db = Database()
