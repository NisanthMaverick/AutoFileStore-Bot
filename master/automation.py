import re
import uuid
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message
import config
import database
from db.models import SessionLocal, FileRecord, SeriesSection
from .ai_parser import parse_file_metadata
from .helpers import log_admin_action, get_readable_size

def _check_file_duplicate_sync(series_id: int, file_name: str, file_size: int) -> bool:
    with SessionLocal() as session:
        from db.models import Series
        s = session.query(Series).filter(Series.id == series_id).first()
        if not s or not s.journey_id:
            record = session.query(FileRecord).filter(
                FileRecord.series_id == series_id,
                FileRecord.file_name == file_name,
                FileRecord.file_size == file_size
            ).first()
            return record is not None
            
        # Get all series belonging to the same journey
        journey_series_ids = [item.id for item in session.query(Series).filter(Series.journey_id == s.journey_id).all()]
        
        record = session.query(FileRecord).filter(
            FileRecord.series_id.in_(journey_series_ids),
            FileRecord.file_name == file_name,
            FileRecord.file_size == file_size
        ).first()
        return record is not None

async def check_file_duplicate(series_id: int, file_name: str, file_size: int) -> bool:
    return await asyncio.to_thread(_check_file_duplicate_sync, series_id, file_name, file_size)

async def find_or_create_series_by_name(title: str) -> int:
    series_list = await database.list_series()
    for s in series_list:
        if s["title"].lower().strip() == title.lower().strip():
            return s["id"]
    return await database.create_series(title, "")

def _detect_series_layout_sync(series_id: int, season_folder_id: int = None) -> str:
    with SessionLocal() as session:
        sections = session.query(SeriesSection).filter(
            SeriesSection.series_id == series_id,
            SeriesSection.parent_id == season_folder_id
        ).all()
        
    folders = [s for s in sections if s.sec_type == "folder"]
    if not folders:
        return "quality_first"
        
    for f in folders:
        name_lower = f.name.lower()
        if any(q in name_lower for q in ["480p", "720p", "1080p", "2160p", "4k"]):
            return "quality_first"
            
    for f in folders:
        name_lower = f.name.lower()
        if "ep" in name_lower or "episode" in name_lower or any(c.isdigit() for c in name_lower):
            return "episode_first"
            
    return "quality_first"

async def detect_series_layout(series_id: int, season_folder_id: int = None) -> str:
    return await asyncio.to_thread(_detect_series_layout_sync, series_id, season_folder_id)

def _guess_combined_name_style_sync(series_id: int) -> str:
    with SessionLocal() as session:
        sections = session.query(SeriesSection).filter(
            SeriesSection.series_id == series_id,
            SeriesSection.sec_type == "files"
        ).all()
    for sec in sections:
        name = sec.name
        if "—" in name:
            return "dash"
        if " - " in name:
            return "hyphen_sep"
        if "[" in name and "]" in name:
            return "brackets"
    return "brackets"

async def guess_combined_name_style(series_id: int) -> str:
    return await asyncio.to_thread(_guess_combined_name_style_sync, series_id)

def normalize_name(name: str) -> str:
    return "".join(c for c in name.lower() if c.isalnum())

def parse_season_num(name: str) -> int:
    m = re.search(r'(?:season|s)\s*(\d+)', name.lower())
    if m:
        return int(m.group(1))
    return None

def matches_quality(folder_name: str, quality: str) -> bool:
    q_norm = normalize_name(quality)
    fn_norm = normalize_name(folder_name)
    return q_norm in fn_norm

def matches_episode_range(section_name: str, start: int, end: int) -> bool:
    digits = [int(d) for d in re.findall(r'\d+', section_name)]
    if len(digits) >= 2:
        for i in range(len(digits) - 1):
            if digits[i] == start and digits[i+1] == end:
                return True
    return False

def find_matching_range_section(sections: list, ep_num: int) -> int:
    for sec in sections:
        if sec["sec_type"] == "files":
            digits = [int(d) for d in re.findall(r'\d+', sec["name"])]
            if len(digits) >= 2:
                start = digits[0]
                end = digits[1]
                if start <= ep_num <= end:
                    return sec["id"]
    return None

def guess_episode_button_style(existing_sections: list) -> str:
    for sec in existing_sections:
        if sec["sec_type"] == "files":
            name = sec["name"]
            if re.search(r'ep\s*\(\d+\s*-\s*\d+\)', name, re.IGNORECASE):
                return "brackets_spaces"
            if re.search(r'ep\s*\(\d+\s*–\s*\d+\)', name, re.IGNORECASE):
                return "brackets_spaces_dash"
            if re.search(r'ep\s*\d+\s*-\s*\d+', name, re.IGNORECASE):
                return "spaces"
            if re.search(r'ep\s*\d+\s*–\s*\d+', name, re.IGNORECASE):
                return "spaces_dash"
    return "brackets_spaces"

section_lock = asyncio.Lock()

async def get_or_create_section_for_file(series_id: int, metadata: dict) -> int:
    async with section_lock:
        return await _get_or_create_section_for_file(series_id, metadata)

async def _get_or_create_section_for_file(series_id: int, metadata: dict) -> int:
    season_num = metadata.get("season_number") or 1
    ep_num = metadata.get("episode_number")
    ep_range = metadata.get("episode_range")
    
    # Standardize quality representation
    quality = metadata.get("resolution") or metadata.get("quality") or "720p"
    
    # 1. Season folder resolution (Level 1)
    season_folder_id = None
    level_1_sections = await database.list_sections(series_id, parent_id=None)
    
    # Look for Season folder
    for sec in level_1_sections:
        if sec["sec_type"] == "folder" and parse_season_num(sec["name"]) == season_num:
            season_folder_id = sec["id"]
            break
            
    if season_folder_id is None:
        has_seasons = False
        for sec in level_1_sections:
            if sec["sec_type"] == "folder" and parse_season_num(sec["name"]) is not None:
                has_seasons = True
                break
                
        if has_seasons or not level_1_sections:
            # Create Season folder: Season 01
            season_name = f"Season {season_num:02d}"
            season_folder_id = await database.create_section(
                name=season_name,
                series_id=series_id,
                parent_id=None,
                sec_type="folder"
            )
            
    # Calculate Episode Range digits
    start = 1
    end = 4
    if ep_range:
        m = re.findall(r'\d+', ep_range)
        if len(m) >= 2:
            start = int(m[0])
            end = int(m[1])
    elif ep_num is not None:
        start = ((ep_num - 1) // 4) * 4 + 1
        end = start + 3
        
    # 2. Detect series layout
    layout = await detect_series_layout(series_id, season_folder_id)
    
    # List sub-sections under season_folder_id (or root if None)
    parent_id = season_folder_id
    sub_sections = await database.list_sections(series_id, parent_id=parent_id)
    
    if layout == "quality_first":
        # Under Season ➔ Find/Create Quality Folder (e.g. 480p)
        quality_folder_id = None
        for sec in sub_sections:
            if sec["sec_type"] == "folder" and matches_quality(sec["name"], quality):
                quality_folder_id = sec["id"]
                break
                
        if quality_folder_id is None:
            # Create Quality folder
            quality_folder_name = f"{quality} 🔰" if "480p" in quality or "720p" in quality else quality
            quality_folder_id = await database.create_section(
                name=quality_folder_name,
                series_id=series_id,
                parent_id=parent_id,
                sec_type="folder"
            )
            
        # Inside Quality Folder ➔ Find/Create Episode Range Files Section (e.g. EP (05 - 08))
        range_sections = await database.list_sections(series_id, parent_id=quality_folder_id)
        
        # A. Check if the episode falls into any existing files sections first
        if ep_num is not None:
            matched_id = find_matching_range_section(range_sections, ep_num)
            if matched_id:
                return matched_id
                
        # B. Check for exact range matching
        for sec in range_sections:
            if sec["sec_type"] == "files" and matches_episode_range(sec["name"], start, end):
                return sec["id"]
                
        # Guess style and create Episode Range Files Section
        style = guess_episode_button_style(range_sections)
        if style == "brackets_spaces":
            name = f"EP ({start:02d} - {end:02d})"
        elif style == "brackets_spaces_dash":
            name = f"EP ({start:02d} – {end:02d})"
        elif style == "spaces":
            name = f"EP {start:02d} - {end:02d}"
        else:
            name = f"EP {start:02d} – {end:02d}"
            
        return await database.create_section(
            name=name,
            series_id=series_id,
            parent_id=quality_folder_id,
            sec_type="files"
        )
        
    elif layout == "episode_first":
        ep_folder_id = None
        for sec in sub_sections:
            if sec["sec_type"] == "folder" and matches_episode_range(sec["name"], start, end):
                ep_folder_id = sec["id"]
                break
                
        if ep_folder_id is None:
            style = guess_episode_button_style(sub_sections)
            if style == "brackets_spaces":
                name = f"🎬 EP ({start:02d} - {end:02d})"
            elif style == "brackets_spaces_dash":
                name = f"🎬 EP ({start:02d} – {end:02d})"
            elif style == "spaces":
                name = f"🎬 EP {start:02d} - {end:02d}"
            else:
                name = f"🎬 EP {start:02d} – {end:02d}"
                
            ep_folder_id = await database.create_section(
                name=name,
                series_id=series_id,
                parent_id=parent_id,
                sec_type="folder"
            )
            
        quality_sections = await database.list_sections(series_id, parent_id=ep_folder_id)
        quality_norm = normalize_name(quality)
        for sec in quality_sections:
            if sec["sec_type"] == "files" and normalize_name(sec["name"]) == quality_norm:
                return sec["id"]
                
        return await database.create_section(
            name=quality,
            series_id=series_id,
            parent_id=ep_folder_id,
            sec_type="files"
        )
        
    else:
        # Combined structure
        quality_norm = normalize_name(quality)
        range_norm = f"{start:02d}{end:02d}"
        for sec in sub_sections:
            if sec["sec_type"] == "files":
                sec_norm = normalize_name(sec["name"])
                if range_norm in sec_norm and quality_norm in sec_norm:
                    return sec["id"]
                    
        style = await guess_combined_name_style(series_id)
        if style == "dash":
            name = f"🎬 EP ({start:02d} - {end:02d}) — {quality}"
        elif style == "hyphen_sep":
            name = f"🎬 EP ({start:02d} - {end:02d}) - {quality}"
        else:
            name = f"🎬 EP ({start:02d} - {end:02d}) [{quality}]"
            
        return await database.create_section(
            name=name,
            series_id=series_id,
            parent_id=parent_id,
            sec_type="files"
        )

async def handle_text_message_automation(client: Client, message: Message):
    async with section_lock:
        return await _handle_text_message_automation(client, message)

async def _handle_text_message_automation(client: Client, message: Message):
    if not message.text:
        return
        
    text = message.text.strip()
    
    # 1. Identify the target Series based on the channel ID/username config
    chat_id_str = str(message.chat.id)
    chat_username = f"@{message.chat.username}" if message.chat.username else None
    
    series_obj = await database.get_series_by_channel(chat_id_str)
    if not series_obj and chat_username:
        series_obj = await database.get_series_by_channel(chat_username)
        
    if not series_obj:
        return
        
    series_id = series_obj["id"]
    series_name = series_obj["title"]
    
    # 2. Parse details from text message
    season_num = 1
    m_season = re.search(r'(?:season|s)\s*(\d+)', text, re.IGNORECASE)
    if m_season:
        season_num = int(m_season.group(1))
        
    start = None
    end = None
    m_range = re.search(r'ep\s*\(\s*(\d+)\s*[-–]\s*(\d+)\s*\)', text, re.IGNORECASE)
    if not m_range:
        m_range = re.search(r'ep\s*(\d+)\s*[-–]\s*(\d+)', text, re.IGNORECASE)
        
    if m_range:
        start = int(m_range.group(1))
        end = int(m_range.group(2))
    else:
        m_single = re.search(r'ep\s*(\d+)', text, re.IGNORECASE)
        if m_single:
            start = int(m_single.group(1))
            end = start
            
    if start is None:
        return
        
    quality = "720p"
    for q in ["480p", "720p", "1080p", "2160p", "4k"]:
        if q in text.lower():
            quality = q
            break
            
    print(f"Text configuration matched: Series: {series_name}, Season: {season_num}, Range: EP ({start}-{end}), Quality: {quality}")
    
    # 3. Create Season, Quality, and Episode buttons/folders in DB
    
    # Season Folder
    season_folder_id = None
    level_1_sections = await database.list_sections(series_id, parent_id=None)
    for sec in level_1_sections:
        if sec["sec_type"] == "folder" and parse_season_num(sec["name"]) == season_num:
            season_folder_id = sec["id"]
            break
            
    if season_folder_id is None:
        season_name = f"Season {season_num:02d}"
        season_folder_id = await database.create_section(
            name=season_name,
            series_id=series_id,
            parent_id=None,
            sec_type="folder"
        )
        
    # Quality Folder
    parent_id = season_folder_id
    sub_sections = await database.list_sections(series_id, parent_id=parent_id)
    
    quality_folder_id = None
    for sec in sub_sections:
        if sec["sec_type"] == "folder" and matches_quality(sec["name"], quality):
            quality_folder_id = sec["id"]
            break
            
    if quality_folder_id is None:
        quality_folder_name = f"{quality} 🔰" if "480p" in quality or "720p" in quality else quality
        quality_folder_id = await database.create_section(
            name=quality_folder_name,
            series_id=series_id,
            parent_id=parent_id,
            sec_type="folder"
        )
        
    # Episode Range Button (files section) inside Quality Folder
    range_sections = await database.list_sections(series_id, parent_id=quality_folder_id)
    range_exists = False
    for sec in range_sections:
        if sec["sec_type"] == "files" and matches_episode_range(sec["name"], start, end):
            range_exists = True
            break
            
    if not range_exists:
        style = guess_episode_button_style(range_sections)
        if style == "brackets_spaces":
            name = f"EP ({start:02d} - {end:02d})"
        elif style == "brackets_spaces_dash":
            name = f"EP ({start:02d} – {end:02d})"
        elif style == "spaces":
            name = f"EP {start:02d} - {end:02d}"
        else:
            name = f"EP {start:02d} – {end:02d}"
            
        await database.create_section(
            name=name,
            series_id=series_id,
            parent_id=quality_folder_id,
            sec_type="files"
        )
        
        await log_admin_action(
            f"🤖 **Auto-Created Episode Button**\n"
            f"🎬 **Series:** {series_name}\n"
            f"📁 **Quality Folder:** {quality}\n"
            f"🗳 **Button:** `{name}`"
        )
        print(f"Created button: '{name}' in folder '{quality}' for series '{series_name}'")

IMPORT_QUEUES = {}
QUEUE_LOCKS = {}

async def handle_new_file_automation(client: Client, message: Message):
    media = message.document or message.video or message.audio
    if not media:
        return
        
    chat_id_str = str(message.chat.id)
    chat_username = f"@{message.chat.username}" if message.chat.username else None
    
    series_obj = await database.get_series_by_channel(chat_id_str)
    if not series_obj and chat_username:
        series_obj = await database.get_series_by_channel(chat_username)
        
    series_id = None
    series_name = None
    
    if series_obj:
        series_id = series_obj["id"]
        series_name = series_obj["title"]
    else:
        is_global_source = False
        if config.WEEKELY_SOURCE_CHANNELS:  # Check both spelling variations if any
            source_list = config.WEEKELY_SOURCE_CHANNELS
        else:
            source_list = getattr(config, "WEEKLY_SOURCE_CHANNELS", [])
            
        if source_list:
            for item in source_list:
                if str(item) == chat_id_str or (chat_username and str(item).lower() == chat_username.lower()):
                    is_global_source = True
                    break
        
        if is_global_source:
            file_name = getattr(media, "file_name", "Media File")
            caption = message.caption or ""
            metadata = await parse_file_metadata(file_name, caption)
            if metadata and metadata.get("series_name"):
                series_name = metadata["series_name"]
                series_id = await find_or_create_series_by_name(series_name)
                
    if not series_id:
        return
        
    if series_id not in IMPORT_QUEUES:
        IMPORT_QUEUES[series_id] = []
    IMPORT_QUEUES[series_id].append((client, message, series_id, series_name))
    
    if series_id not in QUEUE_LOCKS:
        QUEUE_LOCKS[series_id] = asyncio.create_task(process_import_queue(series_id))

async def process_import_queue(series_id: int):
    await asyncio.sleep(1.5)
    
    if series_id not in IMPORT_QUEUES or not IMPORT_QUEUES[series_id]:
        QUEUE_LOCKS.pop(series_id, None)
        return
        
    pending_items = sorted(IMPORT_QUEUES[series_id], key=lambda x: x[1].id)
    IMPORT_QUEUES[series_id] = []
    
    for client, message, s_id, s_name in pending_items:
        try:
            await _import_single_file_sequentially(client, message, s_id, s_name)
        except Exception as e:
            print(f"Error importing file sequentially: {e}")
            
    QUEUE_LOCKS.pop(series_id, None)

async def _import_single_file_sequentially(client: Client, message: Message, series_id: int, series_name: str):
    media = message.document or message.video or message.audio
    if not media:
        return
        
    file_name = getattr(media, "file_name", "Media File")
    file_size = getattr(media, "file_size", 0)
    mime_type = getattr(media, "mime_type", "unknown")
    caption = message.caption or ""
    
    metadata = await parse_file_metadata(file_name, caption)
    if not metadata:
        metadata = {}
        
    is_duplicate = await check_file_duplicate(series_id, file_name, file_size)
    if is_duplicate:
        print(f"Duplicate file found: {file_name} in series {series_name}. Skipping store.")
        return
        
    section_id = await get_or_create_section_for_file(series_id, metadata)
    
    settings = await database.get_settings()
    db_channel = settings.get("db_channel_id")
    
    series_ref = await database.get_series(series_id)
    if series_ref and series_ref.get("journey_id"):
        journey = await database.get_journey(series_ref["journey_id"])
        if journey and journey.get("db_channel_id"):
            db_channel = journey["db_channel_id"]
            
    if not db_channel:
        print("Error in Automation: Storage DB Channel is not configured.")
        return
        
    dest_chat = int(db_channel) if db_channel.startswith("-100") or db_channel.isdigit() else db_channel
    copied_msg = None
    while True:
        try:
            copied_msg = await client.copy_message(
                chat_id=dest_chat,
                from_chat_id=message.chat.id,
                message_id=message.id
            )
            break
        except FloodWait as e:
            print(f"Telegram FloodWait in automated import: sleeping for {e.value + 1}s...")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            print(f"Failed to copy file message {message.id} from {message.chat.id}: {e}")
            return

    if not copied_msg:
        return
        
    file_code = str(uuid.uuid4())[:8]
    episode_num = metadata.get("episode_number")
    
    await database.add_file(
        file_code=file_code,
        message_id=copied_msg.id,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        caption=caption,
        series_id=series_id,
        episode_number=episode_num,
        section_id=section_id
    )
    
    primary = settings.get("primary_clone_username")
    link_str = f"https://t.me/{primary}?start=file_{file_code}" if primary else f"file_{file_code}"
    
    await log_admin_action(
        f"🤖 **AI Auto-Stored File**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 **Series:** {series_name}\n"
        f"📂 **File:** `{file_name}`\n"
        f"📦 **Size:** {get_readable_size(file_size)}\n"
        f"🎚 **Target Section ID:** `{section_id}`\n"
        f"🔗 **Link:** {link_str}"
    )
    print(f"Successfully auto-stored: {file_name} in Section {section_id}")

def register_automation_handlers(app: Client):
    # Register the automation handler to listen to all channels
    print("Registering Weekly Web Series Automation on channel posts...")
    
    @app.on_message(filters.channel)
    async def channel_post_listener(client: Client, message: Message):
        try:
            media = message.document or message.video or message.audio
            if media:
                await handle_new_file_automation(client, message)
            elif message.text:
                await handle_text_message_automation(client, message)
        except Exception as e:
            print(f"Error in Weekly Web Series Automation: {e}")
