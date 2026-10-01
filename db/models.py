import asyncio
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Text, Boolean, DateTime, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker
from config import DATABASE_URL

# Create database engine and session
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
Base = declarative_base()

# Models
class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, default=1)
    welcome_msg = Column(Text, default="Hey {mention}, welcome to {bot_name}!")
    fsub_channels = Column(Text, default="")
    fsub_enabled = Column(Boolean, default=False)
    custom_buttons = Column(Text, default="[]")  # JSON string of list of dicts
    primary_clone_username = Column(String, default="")
    db_channel_id = Column(String, default="")
    log_channel_id = Column(String, default="")
    auto_delete_enabled = Column(Boolean, default=False)
    auto_delete_duration = Column(Integer, default=5)
    series_buttons_per_page = Column(Integer, default=5)
    start_end_msg_enabled = Column(Boolean, default=False)
    start_msg_db_id = Column(Integer, nullable=True)
    end_msg_db_id = Column(Integer, nullable=True)
    series_library_custom_msg = Column(Text, default=None)
    user_send_delay = Column(Integer, default=3)
    db_upload_delay = Column(Integer, default=3)
    access_to_all = Column(Boolean, default=True)
    lock_buttons_enabled = Column(Boolean, default=False)
    protect_content_enabled = Column(Boolean, default=False)
    lock_time_window = Column(Integer, default=0)
    testing_mode = Column(Boolean, default=False)
    lock_active_series_enabled = Column(Boolean, default=False)
    lock_old_series_enabled = Column(Boolean, default=True)
    lock_day_based_enabled = Column(Boolean, default=False)
    subscription_db_url = Column(Text, default=None)
    more_info_msg = Column(Text, default=None)
    clone_bot_premium_only = Column(Boolean, default=False)
    info_button_enabled = Column(Boolean, default=True)




class CloneBot(Base):
    __tablename__ = "clone_bots"
    token = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)

class Journey(Base):
    __tablename__ = "journeys"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    lock_buttons_enabled = Column(Boolean, default=False)
    lock_active_series_enabled = Column(Boolean, default=False)
    lock_old_series_enabled = Column(Boolean, default=True)
    lock_day_based_enabled = Column(Boolean, default=False)
    lock_time_window = Column(Integer, default=0)
    db_channel_id = Column(String, default="")
    update_channel_id = Column(String, default="")
    update_msg_template = Column(Text, default="{series_name} latest episode ({date}) updated ✅\n\nBot : @{bot_username}")
    button_name_template = Column(String, default="📥 Ep ({start} - {end}) {date_small}")
    is_locked = Column(Boolean, default=False)

class Series(Base):
    __tablename__ = "series"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    custom_msg = Column(Text, nullable=True)
    buttons_per_row = Column(Integer, default=2)
    display_order = Column(Integer, default=0)
    custom_pic = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    journey_id = Column(Integer, ForeignKey("journeys.id", ondelete="CASCADE"), nullable=True)
    is_locked = Column(Boolean, default=False)
    source_channel_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class SeriesSection(Base):
    __tablename__ = "series_sections"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    series_id = Column(Integer, ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("series_sections.id", ondelete="CASCADE"), nullable=True)
    sec_type = Column(String, server_default="folder", default="folder")
    custom_msg = Column(Text, nullable=True)
    buttons_per_row = Column(Integer, default=2)
    custom_pic = Column(String, nullable=True)
    is_locked = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class FileRecord(Base):
    __tablename__ = "files"
    file_code = Column(String, primary_key=True)
    message_id = Column(Integer, nullable=False)
    file_name = Column(String, default="")
    file_size = Column(BigInteger, default=0)
    mime_type = Column(String, default="")
    caption = Column(Text, default="")
    series_id = Column(Integer, ForeignKey("series.id", ondelete="SET NULL"), nullable=True)
    episode_number = Column(Integer, nullable=True)
    section_id = Column(Integer, ForeignKey("series_sections.id", ondelete="CASCADE"), nullable=True)

class User(Base):
    __tablename__ = "users"
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

class Admin(Base):
    __tablename__ = "admins"
    user_id = Column(BigInteger, primary_key=True)

class Subscriber(Base):
    __tablename__ = "subscribers"
    user_id = Column(BigInteger, primary_key=True)
    first_name = Column(String, nullable=True)
    username = Column(String, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

class RemotePremiumCache(Base):
    __tablename__ = "remote_premium_cache"
    user_id = Column(BigInteger, primary_key=True)
    plan_id = Column(Integer, nullable=True)
    plan_name = Column(String, nullable=True)
    expiry_date = Column(String, nullable=True)
    last_checked = Column(DateTime, default=datetime.utcnow)


# Helper to initialize DB
def db_init():
    Base.metadata.create_all(engine)
    from sqlalchemy import inspect
    inspector = inspect(engine)
    
    # files columns check
    columns = [c["name"] for c in inspector.get_columns("files")]
    if "section_id" not in columns:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE files ADD COLUMN section_id INTEGER REFERENCES series_sections(id) ON DELETE CASCADE"))
            conn.commit()
            
    # series_sections columns check
    columns_sec = [c["name"] for c in inspector.get_columns("series_sections")]
    if "sec_type" not in columns_sec:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series_sections ADD COLUMN sec_type VARCHAR DEFAULT 'folder'"))
            conn.commit()
    if "custom_msg" not in columns_sec:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series_sections ADD COLUMN custom_msg TEXT DEFAULT NULL"))
            conn.commit()
    if "buttons_per_row" not in columns_sec:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series_sections ADD COLUMN buttons_per_row INTEGER DEFAULT 2"))
            conn.commit()
    if "custom_pic" not in columns_sec:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series_sections ADD COLUMN custom_pic VARCHAR DEFAULT NULL"))
            conn.commit()
    if "created_at" not in columns_sec:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series_sections ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.commit()
    if "sort_order" not in columns_sec:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series_sections ADD COLUMN sort_order INTEGER DEFAULT 0"))
            conn.commit()

    # settings columns check
    columns_sett = [c["name"] for c in inspector.get_columns("settings")]
    if "auto_delete_enabled" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN auto_delete_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "auto_delete_duration" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN auto_delete_duration INTEGER DEFAULT 5"))
            conn.commit()
    if "series_buttons_per_page" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN series_buttons_per_page INTEGER DEFAULT 5"))
            conn.commit()
    if "start_end_msg_enabled" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN start_end_msg_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "start_msg_db_id" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN start_msg_db_id INTEGER DEFAULT NULL"))
            conn.commit()
    if "end_msg_db_id" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN end_msg_db_id INTEGER DEFAULT NULL"))
            conn.commit()
    if "series_library_custom_msg" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN series_library_custom_msg TEXT DEFAULT NULL"))
            conn.commit()
    if "user_send_delay" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN user_send_delay INTEGER DEFAULT 3"))
            conn.commit()
    if "db_upload_delay" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN db_upload_delay INTEGER DEFAULT 3"))
            conn.commit()
    if "access_to_all" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN access_to_all BOOLEAN DEFAULT TRUE"))
            conn.commit()
    if "lock_buttons_enabled" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN lock_buttons_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "protect_content_enabled" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN protect_content_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "lock_time_window" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN lock_time_window INTEGER DEFAULT 0"))
            conn.commit()
    if "testing_mode" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN testing_mode BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "lock_active_series_enabled" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN lock_active_series_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "lock_old_series_enabled" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN lock_old_series_enabled BOOLEAN DEFAULT TRUE"))
            conn.commit()
    if "lock_day_based_enabled" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN lock_day_based_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "subscription_db_url" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN subscription_db_url TEXT DEFAULT NULL"))
            conn.commit()
    if "more_info_msg" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN more_info_msg TEXT DEFAULT NULL"))
            conn.commit()
    if "clone_bot_premium_only" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN clone_bot_premium_only BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "info_button_enabled" not in columns_sett:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE settings ADD COLUMN info_button_enabled BOOLEAN DEFAULT TRUE"))
            conn.commit()

    # journeys columns check
    columns_journeys = [c["name"] for c in inspector.get_columns("journeys")]
    if "db_channel_id" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN db_channel_id VARCHAR DEFAULT ''"))
            conn.commit()
    if "is_locked" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN is_locked BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "description" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN description TEXT DEFAULT ''"))
            conn.commit()
    if "lock_buttons_enabled" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN lock_buttons_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "lock_active_series_enabled" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN lock_active_series_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "lock_old_series_enabled" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN lock_old_series_enabled BOOLEAN DEFAULT TRUE"))
            conn.commit()
    if "lock_day_based_enabled" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN lock_day_based_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "lock_time_window" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN lock_time_window INTEGER DEFAULT 0"))
            conn.commit()
    if "lock_individual_enabled" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN lock_individual_enabled BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "update_channel_id" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN update_channel_id VARCHAR DEFAULT ''"))
            conn.commit()
    if "update_msg_template" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN update_msg_template TEXT DEFAULT '{series_name} latest episode ({date}) updated ✅\n\nBot : @{bot_username}'"))
            conn.commit()
    if "button_name_template" not in columns_journeys:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE journeys ADD COLUMN button_name_template VARCHAR DEFAULT '📥 Ep ({start} - {end}) {date_small}'"))
            conn.commit()



    # series columns check
    columns_ser = [c["name"] for c in inspector.get_columns("series")]
    if "custom_msg" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN custom_msg TEXT DEFAULT NULL"))
            conn.commit()
    if "buttons_per_row" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN buttons_per_row INTEGER DEFAULT 2"))
            conn.commit()
    if "display_order" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN display_order INTEGER DEFAULT 0"))
            conn.commit()
    if "custom_pic" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN custom_pic VARCHAR DEFAULT NULL"))
            conn.commit()
    if "is_active" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN is_active BOOLEAN DEFAULT TRUE"))
            conn.commit()
    if "journey_id" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN journey_id INTEGER REFERENCES journeys(id) ON DELETE CASCADE"))
            conn.commit()
    if "is_locked" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN is_locked BOOLEAN DEFAULT FALSE"))
            conn.commit()
    if "created_at" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.commit()
    if "source_channel_id" not in columns_ser:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series ADD COLUMN source_channel_id VARCHAR DEFAULT NULL"))
            conn.commit()

    # series_sections is_locked column check
    columns_sec = [c["name"] for c in inspector.get_columns("series_sections")]
    if "is_locked" not in columns_sec:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE series_sections ADD COLUMN is_locked BOOLEAN DEFAULT FALSE"))
            conn.commit()

    # Auto-migrate: any section that owns file records must be sec_type='files'
    with engine.connect() as conn:
        conn.execute(text(
            "UPDATE series_sections SET sec_type = 'files' "
            "WHERE id IN (SELECT DISTINCT section_id FROM files WHERE section_id IS NOT NULL) "
            "AND (sec_type IS NULL OR sec_type != 'files')"
        ))
        conn.commit()

    # Ensure settings row exists
    with SessionLocal() as session:
        settings = session.query(Settings).first()
        if not settings:
            settings = Settings(id=1)
            session.add(settings)
            session.commit()

    # Ensure a default Journey exists and update NULL journey_id
    with SessionLocal() as session:
        journey_count = session.query(Journey).count()
        if journey_count == 0:
            default_journey = Journey(
                name="Weekly Webseries",
                lock_buttons_enabled=False,
                lock_active_series_enabled=False,
                lock_old_series_enabled=True,
                lock_day_based_enabled=False,
                lock_time_window=0,
                lock_individual_enabled=False
            )
            session.add(default_journey)
            session.commit()
            session.refresh(default_journey)
            session.query(Series).filter(Series.journey_id == None).update({Series.journey_id: default_journey.id})
            session.commit()
        else:
            first_journey = session.query(Journey).first()
            if first_journey:
                session.query(Series).filter(Series.journey_id == None).update({Series.journey_id: first_journey.id})
                session.commit()
