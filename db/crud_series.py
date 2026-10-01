import asyncio
from .models import SessionLocal, Series, SeriesSection, FileRecord, Journey

def _add_file_sync(file_code: str, message_id: int, file_name: str, file_size: int, mime_type: str, caption: str, series_id=None, episode_number=None, section_id=None):
    with SessionLocal() as session:
        record = session.query(FileRecord).filter(FileRecord.file_code == file_code).first()
        if record:
            record.message_id = message_id
            record.file_name = file_name
            record.file_size = file_size
            record.mime_type = mime_type
            record.caption = caption
            record.series_id = series_id
            record.episode_number = episode_number
            record.section_id = section_id
        else:
            record = FileRecord(
                file_code=file_code,
                message_id=message_id,
                file_name=file_name,
                file_size=file_size,
                mime_type=mime_type,
                caption=caption,
                series_id=series_id,
                episode_number=episode_number,
                section_id=section_id
            )
            session.add(record)
        session.commit()

def _get_file_sync(file_code: str):
    with SessionLocal() as session:
        f = session.query(FileRecord).filter(FileRecord.file_code == file_code).first()
        if f:
            return {
                "file_code": f.file_code,
                "message_id": f.message_id,
                "file_name": f.file_name,
                "file_size": f.file_size,
                "mime_type": f.mime_type,
                "caption": f.caption,
                "series_id": f.series_id,
                "episode_number": f.episode_number,
                "section_id": f.section_id
            }
        return None

def _delete_file_sync(file_code: str) -> bool:
    with SessionLocal() as session:
        f = session.query(FileRecord).filter(FileRecord.file_code == file_code).first()
        if f:
            session.delete(f)
            session.commit()
            return True
        return False

def _list_files_sync(skip=0, limit=20, search=None, series_id=None, section_id=None, filter_root=False):
    with SessionLocal() as session:
        query = session.query(FileRecord)
        if section_id is not None:
            query = query.filter(FileRecord.section_id == section_id)
        elif series_id is not None:
            query = query.filter(FileRecord.series_id == series_id)
            if filter_root:
                query = query.filter(FileRecord.section_id == None)
        if search:
            query = query.filter(FileRecord.file_name.ilike(f"%{search}%"))
        total = query.count()
        records = query.order_by(FileRecord.message_id).offset(skip).limit(limit).all()
        files = [{
            "file_code": r.file_code,
            "message_id": r.message_id,
            "file_name": r.file_name,
            "file_size": r.file_size,
            "mime_type": r.mime_type,
            "caption": r.caption,
            "series_id": r.series_id,
            "episode_number": r.episode_number,
            "section_id": r.section_id
        } for r in records]
        return files, total

def _create_series_sync(title: str, description: str, journey_id: int = None):
    with SessionLocal() as session:
        if journey_id is None:
            first_j = session.query(Journey).first()
            if first_j:
                journey_id = first_j.id
        s = Series(title=title, description=description, journey_id=journey_id)
        session.add(s)
        session.commit()
        session.refresh(s)
        return s.id

def _get_series_sync(series_id: int):
    with SessionLocal() as session:
        s = session.query(Series).filter(Series.id == series_id).first()
        if s:
            return {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "custom_msg": s.custom_msg,
                "buttons_per_row": s.buttons_per_row,
                "display_order": s.display_order,
                "custom_pic": s.custom_pic,
                "is_active": s.is_active,
                "journey_id": s.journey_id,
                "is_locked": s.is_locked,
                "source_channel_id": s.source_channel_id,
                "created_at": s.created_at
            }
        return None

def _list_series_sync(journey_id: int = None):
    with SessionLocal() as session:
        query = session.query(Series)
        if journey_id is not None:
            query = query.filter(Series.journey_id == journey_id)
        series_list = query.order_by(Series.display_order.asc(), Series.title.asc()).all()
        return [{
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "custom_msg": s.custom_msg,
            "buttons_per_row": s.buttons_per_row,
            "display_order": s.display_order,
            "custom_pic": s.custom_pic,
            "is_active": s.is_active,
            "journey_id": s.journey_id,
            "is_locked": s.is_locked,
            "source_channel_id": s.source_channel_id,
            "created_at": s.created_at
        } for s in series_list]

def _delete_series_sync(series_id: int):
    with SessionLocal() as session:
        s = session.query(Series).filter(Series.id == series_id).first()
        if s:
            session.delete(s)
            session.commit()
            return True
        return False

def _create_section_sync(name: str, series_id: int, parent_id: int = None, sec_type: str = "folder") -> int:
    with SessionLocal() as session:
        sec = SeriesSection(name=name, series_id=series_id, parent_id=parent_id, sec_type=sec_type)
        session.add(sec)
        session.commit()
        session.refresh(sec)
        return sec.id

def _get_section_sync(section_id: int):
    with SessionLocal() as session:
        sec = session.query(SeriesSection).filter(SeriesSection.id == section_id).first()
        if sec:
            return {
                "id": sec.id,
                "name": sec.name,
                "series_id": sec.series_id,
                "parent_id": sec.parent_id,
                "sec_type": sec.sec_type,
                "custom_msg": sec.custom_msg,
                "buttons_per_row": sec.buttons_per_row,
                "custom_pic": sec.custom_pic,
                "is_locked": sec.is_locked,
                "created_at": sec.created_at
            }
        return None

def _list_sections_sync(series_id: int, parent_id: int = None):
    with SessionLocal() as session:
        query = session.query(SeriesSection).filter(SeriesSection.series_id == series_id)
        if parent_id is None:
            query = query.filter(SeriesSection.parent_id == None)
        else:
            query = query.filter(SeriesSection.parent_id == parent_id)
        sections = query.order_by(SeriesSection.id).all()
        sec_list = [{
            "id": s.id,
            "name": s.name,
            "series_id": s.series_id,
            "parent_id": s.parent_id,
            "sec_type": s.sec_type,
            "custom_msg": s.custom_msg,
            "buttons_per_row": s.buttons_per_row,
            "custom_pic": s.custom_pic,
            "is_locked": s.is_locked,
            "created_at": s.created_at
        } for s in sections]
        
        # Sort by stored sort_order, then fall back to natural sort
        import re
        def get_natural_key(x):
            name = x["name"] or ""
            numbers = [int(n) for n in re.findall(r'\d+', name)]
            if numbers:
                return (0, numbers[0], name.lower())
            return (1, 0, name.lower())
        
        # Use sort_order if any non-zero value assigned, else natural sort
        has_sort_order = any(s.get("sort_order", 0) for s in sec_list)
        if has_sort_order:
            sec_list.sort(key=lambda x: (x.get("sort_order") or 0, get_natural_key(x)))
        else:
            sec_list.sort(key=get_natural_key)
        return sec_list

def _reorder_siblings_sync(series_id: int, parent_id):
    """Re-assigns sort_order to all siblings under parent_id using natural sort.
    Called automatically after a new section is created so old out-of-order
    buttons are repositioned without any manual admin action."""
    import re
    with SessionLocal() as session:
        query = session.query(SeriesSection).filter(SeriesSection.series_id == series_id)
        if parent_id is None:
            query = query.filter(SeriesSection.parent_id == None)
        else:
            query = query.filter(SeriesSection.parent_id == parent_id)
        siblings = query.all()

        def natural_key(sec):
            name = sec.name or ""
            numbers = [int(n) for n in re.findall(r'\d+', name)]
            if numbers:
                return (0, numbers[0], name.lower())
            return (1, 0, name.lower())

        siblings.sort(key=natural_key)
        for idx, sec in enumerate(siblings):
            sec.sort_order = idx + 1
        session.commit()

def _delete_section_sync(section_id: int) -> bool:
    with SessionLocal() as session:
        sec = session.query(SeriesSection).filter(SeriesSection.id == section_id).first()
        if sec:
            session.delete(sec)
            session.commit()
            return True
        return False

def _get_section_path_sync(section_id: int) -> str:
    path_parts = []
    curr_id = section_id
    with SessionLocal() as session:
        while curr_id:
            sec = session.query(SeriesSection).filter(SeriesSection.id == curr_id).first()
            if not sec:
                break
            path_parts.append(sec.name.split('\n')[0])
            curr_id = sec.parent_id
    return " > ".join(reversed(path_parts))

def _update_section_sync(section_id: int, name: str) -> bool:
    with SessionLocal() as session:
        sec = session.query(SeriesSection).filter(SeriesSection.id == section_id).first()
        if sec:
            sec.name = name
            session.commit()
            return True
        return False

def _clear_section_files_sync(section_id: int):
    with SessionLocal() as session:
        session.query(FileRecord).filter(FileRecord.section_id == section_id).delete()
        session.commit()

def _update_series_settings_sync(series_id: int, custom_msg=None, buttons_per_row=None, title=None, description=None, display_order=None, custom_pic=None, is_active=None, journey_id=None, is_locked=None, source_channel_id=None) -> bool:
    with SessionLocal() as session:
        s = session.query(Series).filter(Series.id == series_id).first()
        if s:
            if custom_msg is not None:
                s.custom_msg = None if custom_msg == "none" else custom_msg
            if buttons_per_row is not None:
                s.buttons_per_row = buttons_per_row
            if title is not None:
                s.title = title
            if description is not None:
                s.description = description
            if display_order is not None:
                s.display_order = display_order
            if custom_pic is not None:
                s.custom_pic = None if custom_pic == "none" else custom_pic
            if is_active is not None:
                s.is_active = is_active
            if journey_id is not None:
                s.journey_id = journey_id
            if is_locked is not None:
                s.is_locked = is_locked
            if source_channel_id is not None:
                s.source_channel_id = None if source_channel_id == "none" else source_channel_id
            session.commit()
            return True
        return False

def _update_section_settings_sync(section_id: int, custom_msg=None, buttons_per_row=None, custom_pic=None, is_locked=None) -> bool:
    with SessionLocal() as session:
        sec = session.query(SeriesSection).filter(SeriesSection.id == section_id).first()
        if sec:
            if custom_msg is not None:
                sec.custom_msg = None if custom_msg == "none" else custom_msg
            if buttons_per_row is not None:
                sec.buttons_per_row = buttons_per_row
            if custom_pic is not None:
                sec.custom_pic = None if custom_pic == "none" else custom_pic
            if is_locked is not None:
                sec.is_locked = is_locked
            session.commit()
            return True
        return False

# --- Journey CRUD ---
def _create_journey_sync(name: str, description: str = "") -> int:
    with SessionLocal() as session:
        j = Journey(name=name, description=description)
        session.add(j)
        session.commit()
        session.refresh(j)
        return j.id

def _get_journey_sync(journey_id: int):
    with SessionLocal() as session:
        j = session.query(Journey).filter(Journey.id == journey_id).first()
        if j:
            return {
                "id": j.id,
                "name": j.name,
                "description": getattr(j, "description", "") or "",
                "lock_buttons_enabled": getattr(j, "lock_buttons_enabled", False),
                "lock_active_series_enabled": getattr(j, "lock_active_series_enabled", False),
                "lock_old_series_enabled": getattr(j, "lock_old_series_enabled", True),
                "lock_day_based_enabled": getattr(j, "lock_day_based_enabled", False),
                "lock_time_window": getattr(j, "lock_time_window", 0) or 0,
                "lock_individual_enabled": getattr(j, "lock_individual_enabled", False),
                "db_channel_id": getattr(j, "db_channel_id", "") or "",
                "update_channel_id": getattr(j, "update_channel_id", "") or "",
                "update_msg_template": getattr(j, "update_msg_template", "") or "{series_name} latest episode ({date}) updated ✅\n\nBot : @{bot_username}",
                "button_name_template": getattr(j, "button_name_template", "") or "📥 Ep ({start} - {end}) {date_small}",
                "is_locked": getattr(j, "is_locked", False)
            }
        return None

def _list_journeys_sync():
    with SessionLocal() as session:
        journeys = session.query(Journey).order_by(Journey.id.asc()).all()
        return [{
            "id": j.id,
            "name": j.name,
            "description": getattr(j, "description", "") or "",
            "lock_buttons_enabled": getattr(j, "lock_buttons_enabled", False),
            "lock_active_series_enabled": getattr(j, "lock_active_series_enabled", False),
            "lock_old_series_enabled": getattr(j, "lock_old_series_enabled", True),
            "lock_day_based_enabled": getattr(j, "lock_day_based_enabled", False),
            "lock_time_window": getattr(j, "lock_time_window", 0) or 0,
            "lock_individual_enabled": getattr(j, "lock_individual_enabled", False),
            "db_channel_id": getattr(j, "db_channel_id", "") or "",
            "update_channel_id": getattr(j, "update_channel_id", "") or "",
            "update_msg_template": getattr(j, "update_msg_template", "") or "{series_name} latest episode ({date}) updated ✅\n\nBot : @{bot_username}",
            "button_name_template": getattr(j, "button_name_template", "") or "📥 Ep ({start} - {end}) {date_small}",
            "is_locked": getattr(j, "is_locked", False)
        } for j in journeys]

def _delete_journey_sync(journey_id: int) -> bool:
    with SessionLocal() as session:
        j = session.query(Journey).filter(Journey.id == journey_id).first()
        if j:
            session.delete(j)
            session.commit()
            return True
        return False

def _update_journey_settings_sync(journey_id: int, name=None, description=None, lock_buttons_enabled=None, lock_active_series_enabled=None, lock_old_series_enabled=None, lock_day_based_enabled=None, lock_time_window=None, lock_individual_enabled=None, db_channel_id=None, update_channel_id=None, update_msg_template=None, button_name_template=None, is_locked=None) -> bool:
    with SessionLocal() as session:
        j = session.query(Journey).filter(Journey.id == journey_id).first()
        if j:
            if name is not None:
                j.name = name
            if description is not None:
                j.description = description
            if lock_buttons_enabled is not None:
                j.lock_buttons_enabled = lock_buttons_enabled
            if lock_active_series_enabled is not None:
                j.lock_active_series_enabled = lock_active_series_enabled
            if lock_old_series_enabled is not None:
                j.lock_old_series_enabled = lock_old_series_enabled
            if lock_day_based_enabled is not None:
                j.lock_day_based_enabled = lock_day_based_enabled
            if lock_time_window is not None:
                j.lock_time_window = lock_time_window
            if lock_individual_enabled is not None:
                j.lock_individual_enabled = lock_individual_enabled
            if db_channel_id is not None:
                j.db_channel_id = db_channel_id
            if update_channel_id is not None:
                j.update_channel_id = update_channel_id
            if update_msg_template is not None:
                j.update_msg_template = update_msg_template
            if button_name_template is not None:
                j.button_name_template = button_name_template
            if is_locked is not None:
                j.is_locked = is_locked
            session.commit()
            return True
        return False

def _reset_journey_locks_sync(journey_id: int) -> bool:
    with SessionLocal() as session:
        series_ids = [s.id for s in session.query(Series).filter(Series.journey_id == journey_id).all()]
        if series_ids:
            session.query(Series).filter(Series.id.in_(series_ids)).update({Series.is_locked: False}, synchronize_session=False)
            session.query(SeriesSection).filter(SeriesSection.series_id.in_(series_ids)).update({SeriesSection.is_locked: False}, synchronize_session=False)
        session.commit()
        return True

# --- Async wrappers ---
async def create_series(title: str, description: str, journey_id: int = None):
    return await asyncio.to_thread(_create_series_sync, title, description, journey_id)

async def get_series(series_id: int):
    return await asyncio.to_thread(_get_series_sync, series_id)

async def list_series(journey_id: int = None):
    return await asyncio.to_thread(_list_series_sync, journey_id)

async def delete_series(series_id: int):
    return await asyncio.to_thread(_delete_series_sync, series_id)

async def create_section(name: str, series_id: int, parent_id: int = None, sec_type: str = "folder") -> int:
    section_id = await asyncio.to_thread(_create_section_sync, name, series_id, parent_id, sec_type)
    # Auto-reorder all siblings so old out-of-order buttons get fixed immediately
    await asyncio.to_thread(_reorder_siblings_sync, series_id, parent_id)
    return section_id

async def reorder_siblings(series_id: int, parent_id=None):
    """Explicitly reorder all siblings under parent_id. Call this to fix
    existing buttons that were created in the wrong order."""
    return await asyncio.to_thread(_reorder_siblings_sync, series_id, parent_id)

async def get_section(section_id: int):
    return await asyncio.to_thread(_get_section_sync, section_id)

async def list_sections(series_id: int, parent_id: int = None):
    return await asyncio.to_thread(_list_sections_sync, series_id, parent_id)

async def delete_section(section_id: int):
    return await asyncio.to_thread(_delete_section_sync, section_id)

async def get_section_path(section_id: int) -> str:
    return await asyncio.to_thread(_get_section_path_sync, section_id)

async def update_section(section_id: int, name: str) -> bool:
    return await asyncio.to_thread(_update_section_sync, section_id, name)

async def clear_section_files(section_id: int):
    await asyncio.to_thread(_clear_section_files_sync, section_id)

async def update_series_settings(series_id: int, custom_msg=None, buttons_per_row=None, title=None, description=None, display_order=None, custom_pic=None, is_active=None, journey_id=None, is_locked=None, source_channel_id=None):
    return await asyncio.to_thread(_update_series_settings_sync, series_id, custom_msg, buttons_per_row, title, description, display_order, custom_pic, is_active, journey_id, is_locked, source_channel_id)

async def update_section_settings(section_id: int, custom_msg=None, buttons_per_row=None, custom_pic=None, is_locked=None):
    return await asyncio.to_thread(_update_section_settings_sync, section_id, custom_msg, buttons_per_row, custom_pic, is_locked)

async def create_journey(name: str, description: str = ""):
    return await asyncio.to_thread(_create_journey_sync, name, description)

async def get_journey(journey_id: int):
    return await asyncio.to_thread(_get_journey_sync, journey_id)

async def list_journeys():
    return await asyncio.to_thread(_list_journeys_sync)

async def delete_journey(journey_id: int):
    return await asyncio.to_thread(_delete_journey_sync, journey_id)

async def update_journey_settings(journey_id: int, name=None, description=None, lock_buttons_enabled=None, lock_active_series_enabled=None, lock_old_series_enabled=None, lock_day_based_enabled=None, lock_time_window=None, lock_individual_enabled=None, db_channel_id=None, update_channel_id=None, update_msg_template=None, button_name_template=None, is_locked=None):
    return await asyncio.to_thread(_update_journey_settings_sync, journey_id, name, description, lock_buttons_enabled, lock_active_series_enabled, lock_old_series_enabled, lock_day_based_enabled, lock_time_window, lock_individual_enabled, db_channel_id, update_channel_id, update_msg_template, button_name_template, is_locked)

async def reset_journey_locks(journey_id: int):
    return await asyncio.to_thread(_reset_journey_locks_sync, journey_id)

async def add_file(file_code: str, message_id: int, file_name: str, file_size: int, mime_type: str, caption: str, series_id=None, episode_number=None, section_id=None):
    await asyncio.to_thread(_add_file_sync, file_code, message_id, file_name, file_size, mime_type, caption, series_id, episode_number, section_id)

async def get_file(file_code: str):
    return await asyncio.to_thread(_get_file_sync, file_code)

async def delete_file(file_code: str):
    return await asyncio.to_thread(_delete_file_sync, file_code)

async def list_files(skip=0, limit=20, search=None, series_id=None, section_id=None, filter_root=False):
    return await asyncio.to_thread(_list_files_sync, skip, limit, search, series_id, section_id, filter_root)

# --- Move Folder Sync Helpers ---
def _update_section_parent_sync(section_id: int, parent_id: int = None) -> bool:
    with SessionLocal() as session:
        sec = session.query(SeriesSection).filter(SeriesSection.id == section_id).first()
        if sec:
            sec.parent_id = parent_id
            session.commit()
            return True
        return False

def _list_all_folders_sync(series_id: int):
    with SessionLocal() as session:
        folders = session.query(SeriesSection).filter(
            SeriesSection.series_id == series_id,
            SeriesSection.sec_type == "folder"
        ).order_by(SeriesSection.id).all()
        return [{
            "id": f.id,
            "name": f.name,
            "series_id": f.series_id,
            "parent_id": f.parent_id,
            "sec_type": f.sec_type,
            "custom_msg": f.custom_msg,
            "buttons_per_row": f.buttons_per_row,
            "custom_pic": f.custom_pic
        } for f in folders]

# --- Move Folder Async Helpers ---
async def update_section_parent(section_id: int, parent_id: int = None) -> bool:
    return await asyncio.to_thread(_update_section_parent_sync, section_id, parent_id)

async def list_all_folders(series_id: int):
    return await asyncio.to_thread(_list_all_folders_sync, series_id)

def _get_series_by_channel_sync(channel_id: str):
    with SessionLocal() as session:
        s = session.query(Series).filter(Series.source_channel_id == channel_id).first()
        if s:
            return {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "custom_msg": s.custom_msg,
                "buttons_per_row": s.buttons_per_row,
                "display_order": s.display_order,
                "custom_pic": s.custom_pic,
                "is_active": s.is_active,
                "journey_id": s.journey_id,
                "is_locked": s.is_locked,
                "source_channel_id": s.source_channel_id,
                "created_at": s.created_at
            }
        return None

async def get_series_by_channel(channel_id: str):
    return await asyncio.to_thread(_get_series_by_channel_sync, channel_id)

