import asyncio
from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import database
from .helpers import (
    ADMIN_STATES, log_admin_action, get_back_button
)
from .ui_files import (
    show_folder_management, show_series_browse, show_manage_series, show_filesec_actions,
    show_series_management_menu, show_series_reorder_menu,
    show_journey_detail, show_manage_series_journey, show_journey_lock_settings,
    show_journey_active_series_config, show_edit_library_message_menu
)
from .ui_config import show_auto_delete_menu
from .notifications import trigger_journey_update_notification
from .fillings import get_fillings_help_text

def to_small_text(text: str) -> str:
    superscript_map = {
        'a': 'ᵃ', 'b': 'ᵇ', 'c': 'ᶜ', 'd': 'ᵈ', 'e': 'ᵉ', 'f': 'ᶠ', 'g': 'ᵍ', 'h': 'ʰ', 
        'i': 'ⁱ', 'j': 'ʲ', 'k': 'ᵏ', 'l': 'ˡ', 'm': 'ᵐ', 'n': 'ⁿ', 'o': 'ᵒ', 'p': 'ᵖ', 
        'q': '𐞎', 'r': 'ʳ', 's': 'ˢ', 't': 'ᵗ', 'u': 'ᵘ', 'v': 'ᵛ', 'w': 'ʷ', 'x': 'ˣ', 
        'y': 'ʸ', 'z': 'ᶻ',
        'A': 'ᴬ', 'B': 'ᴮ', 'C': 'ᶜ', 'D': 'ᴰ', 'E': 'ᴱ', 'F': 'ᶠ', 'G': 'ᴳ', 'H': 'ᴴ', 
        'I': 'ᴵ', 'J': 'ᴶ', 'K': 'ᴷ', 'L': 'ᴸ', 'M': 'ᴹ', 'N': 'ᴺ', 'O': 'ᴼ', 'P': 'ᴾ', 
        'Q': '𐞎', 'R': 'ᴿ', 'S': 'ˢ', 'T': 'ᵀ', 'U': 'ᵁ', 'V': 'ⱽ', 'W': 'ᵂ', 'X': 'ˣ', 
        'Y': 'ʸ', 'Z': 'ᶻ',
        '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', 
        '8': '⁸', '9': '⁹',
        '-': '⁻', '+': '⁺', '=': '⁼', '(': '⁽', ')': '⁾'
    }
    return "".join(superscript_map.get(c, c) for c in text)

def format_sec_name_inline(name: str) -> str:
    parts = name.split('\n', 1)
    if len(parts) == 1:
        for emoji in ['📅', '🗓️', '🗓', '📆']:
            if emoji in name:
                p = name.split(emoji, 1)
                parts = [p[0].strip(), f"{emoji}{p[1]}"]
                break
    if len(parts) > 1 and parts[1]:
        return f"{parts[0]} - {to_small_text(parts[1])}"
    return name

ACTIVE_SCANS  = {}   # series_id -> True (running) / False (aborted)
PAUSED_SCANS  = {}   # series_id -> True (paused)
PENDING_BATCHES = {}

async def scan_channel_task(client: Client, admin_chat_id: int, admin_message_id: int, series_id: int, library_skip: int, auto_mode: bool = False):
    from .automation import check_file_duplicate, get_or_create_section_for_file
    from .ai_parser import parse_file_metadata
    from .helpers import log_admin_action, get_readable_size
    import database
    import asyncio
    import re
    
    ACTIVE_SCANS[series_id] = True
    
    series = await database.get_series(series_id)
    if not series or not series.get("source_channel_id"):
        return
        
    channel_id = series["source_channel_id"]
    chat_id = int(channel_id) if channel_id.startswith("-100") or channel_id.isdigit() else channel_id

    def _scan_markup(is_paused: bool) -> InlineKeyboardMarkup:
        pause_btn = (
            InlineKeyboardButton("▶️ Resume", callback_data=f"resume_scan_{series_id}_{library_skip}")
            if is_paused else
            InlineKeyboardButton("⏸ Pause", callback_data=f"pause_scan_{series_id}_{library_skip}")
        )
        return InlineKeyboardMarkup([[
            pause_btn,
            InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_scan_confirm_{series_id}_{library_skip}")
        ]])

    await client.edit_message_text(
        chat_id=admin_chat_id,
        message_id=admin_message_id,
        text=(
            f"🔍 **Scanning Channel...**\n\n"
            f"🎬 **Series:** {series['title']}\n"
            f"📢 **Channel:** `{channel_id}`\n\n"
            f"⏳ Iterating history, please wait..."
        ),
        reply_markup=_scan_markup(False)
    )
    
    missing_count = 0
    scanned_count = 0
    
    try:
        series_ids = [series_id]
        if series.get("journey_id"):
            journey_series = await database.list_series(journey_id=series["journey_id"])
            series_ids = [s["id"] for s in journey_series]
            
        existing_index = set()
        for sid in series_ids:
            files_list, _ = await database.list_files(series_id=sid, limit=10000)
            for f in files_list:
                existing_index.add((f["file_name"], f["file_size"]))
        
        max_id = 1000
        try:
            temp_msg = await client.send_message(chat_id, "🔍 **Starting Channel Scan...**")
            max_id = temp_msg.id
            await temp_msg.delete()
        except Exception:
            try:
                chat_info = await client.get_chat(chat_id)
                if chat_info.pinned_message:
                    max_id = max(max_id, chat_info.pinned_message.id)
            except Exception:
                pass
                
        batch_size = 100
        current_id = max_id
        min_id = 1
        
        # Group files: key is (season, start, end, quality), value is list of message objects
        groups = {}
        
        while current_id > min_id:
            # ── Pause wait loop during scanning ──
            if PAUSED_SCANS.get(series_id, False):
                try:
                    await client.edit_message_text(
                        chat_id=admin_chat_id,
                        message_id=admin_message_id,
                        text=(
                            f"⏸ **Scan Paused**\n\n"
                            f"🎬 **Series:** {series['title']}\n"
                            f"📢 **Channel:** `{channel_id}`\n\n"
                            f"🔢 **Checked so far:** `{scanned_count}` messages\n"
                            f"❓ **Missing found:** `{missing_count}`\n\n"
                            f"Click **Resume** to continue scanning."
                        ),
                        reply_markup=_scan_markup(True)
                    )
                except Exception:
                    pass
                while PAUSED_SCANS.get(series_id, False) and ACTIVE_SCANS.get(series_id, False):
                    await asyncio.sleep(1)
                if not ACTIVE_SCANS.get(series_id, False):
                    break

            if not ACTIVE_SCANS.get(series_id, False):
                await client.edit_message_text(
                    chat_id=admin_chat_id,
                    message_id=admin_message_id,
                    text=f"🔴 **Scan Cancelled.**\n\n🎬 **Series:** {series['title']}\n🔢 **Processed:** `{scanned_count}` messages.\n❓ **Missing Found:** `{missing_count}`",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]])
                )
                return
                
            batch_ids = list(range(max(min_id, current_id - batch_size + 1), current_id + 1))
            current_id -= batch_size
            
            messages = []
            while True:
                try:
                    messages = await client.get_messages(chat_id, message_ids=batch_ids)
                    if not isinstance(messages, list):
                        messages = [messages]
                    break
                except FloodWait as e:
                    print(f"FloodWait in scan_channel_task get_messages: sleeping for {e.value + 1}s...")
                    await asyncio.sleep(e.value + 1)
                except Exception as e:
                    print(f"Error fetching channel messages: {e}")
                    await asyncio.sleep(1)
                    break
                
            for msg in reversed(messages):
                if not msg or msg.empty:
                    continue
                    
                scanned_count += 1
                if scanned_count % 15 == 0:
                    try:
                        await client.edit_message_text(
                            chat_id=admin_chat_id,
                            message_id=admin_message_id,
                            text=(
                                f"🔍 **Scanning Channel...**\n\n"
                                f"🎬 **Series:** {series['title']}\n"
                                f"📢 **Channel:** `{channel_id}`\n\n"
                                f"🔢 **Messages Checked:** `{scanned_count}`\n"
                                f"❓ **Missing Files Found:** `{missing_count}`\n\n"
                                f"⏳ Please wait..."
                            ),
                            reply_markup=_scan_markup(False)
                        )
                    except Exception:
                        pass
                        
                media = msg.document or msg.video or msg.audio
                if not media:
                    continue
                    
                file_name = getattr(media, "file_name", "Media File")
                file_size = getattr(media, "file_size", 0)
                
                if (file_name, file_size) not in existing_index:
                    missing_count += 1
                    caption = msg.caption or ""
                    metadata = await parse_file_metadata(file_name, caption)
                    quality = metadata.get("resolution") or metadata.get("quality") or "720p"
                    season = metadata.get("season_number") or 1
                    ep_num = metadata.get("episode_number")
                    ep_range = metadata.get("episode_range")
                    
                    start = 1
                    end = 4
                    if ep_range:
                        m_digits = re.findall(r'\d+', ep_range)
                        if len(m_digits) >= 2:
                            start = int(m_digits[0])
                            end = int(m_digits[1])
                    elif ep_num is not None:
                        start = ((ep_num - 1) // 4) * 4 + 1
                        end = start + 3
                        
                    key = (season, start, end, quality)
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(msg)
                    
            await asyncio.sleep(0.5)
            
        # Sort groups ascending by season then episode-start so EP01 forwards before EP90
        sorted_groups = sorted(groups.items(), key=lambda x: (x[0][0], x[0][1]))
        
        import uuid, time
        auto_imported = 0
        skipped_dup   = 0
        
        settings = await database.get_settings()
        db_channel = settings.get("db_channel_id")
        if series.get("journey_id"):
            journey = await database.get_journey(series["journey_id"])
            if journey and journey.get("db_channel_id"):
                db_channel = journey["db_channel_id"]
        dest_chat = int(db_channel) if db_channel and (db_channel.startswith("-100") or db_channel.isdigit()) else db_channel
        
        # Pre-compute total file count across all groups for ETA
        total_files_all = sum(len(gf) for gf in groups.values())
        import_start_time = time.time()
        last_edit_time = 0.0
        EDIT_COOLDOWN = 3.0  # min seconds between Telegram edits to avoid flood

        def _build_progress_bar(done: int, total: int, width: int = 12) -> str:
            if total == 0:
                return "░" * width
            filled = int(width * done / total)
            return "█" * filled + "░" * (width - filled)

        def _eta_str(done: int, total: int, elapsed: float) -> str:
            if done == 0 or elapsed == 0:
                return "Calculating..."
            rate = done / elapsed          # files per second
            remaining = (total - done) / rate
            mins, secs = divmod(int(remaining), 60)
            if mins > 0:
                return f"{mins}m {secs:02d}s"
            return f"{secs}s"

        async def _live_update(current_fname: str, batch_label: str, done: int, total: int, force: bool = False):
            nonlocal last_edit_time
            now = time.time()
            if not force and now - last_edit_time < EDIT_COOLDOWN:
                return
            last_edit_time = now
            elapsed = now - import_start_time
            bar  = _build_progress_bar(done, total)
            eta  = _eta_str(done, total, elapsed)
            pct  = int(100 * done / total) if total else 0
            is_paused = PAUSED_SCANS.get(series_id, False)
            status_line = "⏸ **PAUSED** — click Resume to continue" if is_paused else "⚠️ Import in progress — do not close this panel"
            text = (
                f"📡 **Live Import Panel**\n"
                f"{'━' * 28}\n"
                f"🎬 **Series:** {series['title']}\n"
                f"📢 **Source:** `{channel_id}`\n"
                f"💾 **DB Channel:** `{db_channel}`\n"
                f"{'━' * 28}\n"
                f"📁 **Current Batch:** {batch_label}\n"
                f"📤 **Forwarding:** `{current_fname}`\n"
                f"{'━' * 28}\n"
                f"[{bar}] {pct}%\n"
                f"✅ **Done:** `{done}` / `{total}` files\n"
                f"⏭ **Remaining:** `{total - done}` files\n"
                f"⏱ **ETA:** ~{eta}\n"
                f"⚡ **Speed:** 1 file / 2 sec\n"
                f"{'━' * 28}\n"
                f"{status_line}"
            )
            pause_btn = (
                InlineKeyboardButton("▶️ Resume", callback_data=f"resume_scan_{series_id}_{library_skip}")
                if is_paused else
                InlineKeyboardButton("⏸ Pause", callback_data=f"pause_scan_{series_id}_{library_skip}")
            )
            try:
                await client.edit_message_text(
                    chat_id=admin_chat_id,
                    message_id=admin_message_id,
                    text=text,
                    reply_markup=InlineKeyboardMarkup([[
                        pause_btn,
                        InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_scan_confirm_{series_id}_{library_skip}")
                    ]])
                )
            except Exception:
                pass

        for (season, start, end, quality), group_files in sorted_groups:
            group_files.sort(key=lambda m: m.id)   # ascending within batch
            batch_key = str(uuid.uuid4())[:8]
            batch_label = f"S{season:02d} EP ({start:02d}–{end:02d}) | {quality}"
            PENDING_BATCHES[batch_key] = {
                "series_id": series_id,
                "season": season,
                "start": start,
                "end": end,
                "quality": quality,
                "msg_ids": [m.id for m in group_files]
            }
            
            if auto_mode:
                dummy_meta = {"season_number": season, "resolution": quality, "episode_range": f"{start:02d}-{end:02d}"}
                section_id_auto = await get_or_create_section_for_file(series_id, dummy_meta)
                
                for msg in group_files:
                    # ── Abort check ──
                    if not ACTIVE_SCANS.get(series_id, False):
                        break
                    
                    # ── Pause wait loop ──
                    if PAUSED_SCANS.get(series_id, False):
                        media_tmp = msg.document or msg.video or msg.audio
                        fname_tmp = getattr(media_tmp, "file_name", "...") if media_tmp else "..."
                        await _live_update(fname_tmp, batch_label, auto_imported, total_files_all, force=True)
                        while PAUSED_SCANS.get(series_id, False) and ACTIVE_SCANS.get(series_id, False):
                            await asyncio.sleep(1)
                        if not ACTIVE_SCANS.get(series_id, False):
                            break
                        # Refresh panel to show resumed state
                        last_edit_time = 0.0

                    media_auto = msg.document or msg.video or msg.audio
                    if not media_auto:
                        continue
                    fname = getattr(media_auto, "file_name", "Media File")
                    fsize = getattr(media_auto, "file_size", 0)
                    fmime = getattr(media_auto, "mime_type", "unknown")
                    fcap  = msg.caption or ""
                    
                    # Live update: show which file is being forwarded NOW
                    await _live_update(fname, batch_label, auto_imported, total_files_all)
                    
                    if not dest_chat:
                        continue
                    copied = None
                    while True:
                        try:
                            copied = await client.copy_message(
                                chat_id=dest_chat, from_chat_id=chat_id, message_id=msg.id
                            )
                            break
                        except FloodWait as e:
                            print(f"FloodWait in auto-scan copy_message: sleeping for {e.value + 1}s...")
                            await asyncio.sleep(e.value + 1)
                        except Exception as copy_err:
                            print(f"Auto-scan copy failed: {copy_err}")
                            await asyncio.sleep(3)
                            break
                    if not copied:
                        continue
                    
                    fc = str(uuid.uuid4())[:8]
                    await database.add_file(
                        file_code=fc, message_id=copied.id, file_name=fname,
                        file_size=fsize, mime_type=fmime, caption=fcap,
                        series_id=series_id, episode_number=None, section_id=section_id_auto
                    )
                    auto_imported += 1
                    # Force a live update after each successful import
                    last_edit_time = 0.0
                    await _live_update(fname, batch_label, auto_imported, total_files_all)
                    
                    await asyncio.sleep(2)   # 2s gap — Telegram rate limit
                    
                PENDING_BATCHES.pop(batch_key, None)
            else:
                # Manual mode: send approval prompt to admin
                file_lines = []
                for i, m in enumerate(group_files, 1):
                    media_obj = m.document or m.video or m.audio
                    fname = getattr(media_obj, "file_name", "File")
                    fsize = get_readable_size(getattr(media_obj, "file_size", 0))
                    file_lines.append(f"{i}. `{fname}` ({fsize})")
                files_text = "\n".join(file_lines)
                
                prompt_text = (
                    f"📦 **Missing Episode Batch Detected**\n\n"
                    f"🎬 **Series:** {series['title']}\n"
                    f"💡 **Season:** {season:02d} | 📁 **Quality:** {quality}\n"
                    f"🗳 **Episode Range:** EP ({start:02d} - {end:02d})\n\n"
                    f"📂 **Files in Batch:**\n{files_text}\n\n"
                    f"Would you like to import this batch and create the buttons/folders?"
                )
                markup = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Import Batch", callback_data=f"scan_batch_{batch_key}"),
                        InlineKeyboardButton("❌ Ignore", callback_data="scan_ignore")
                    ]
                ])
                await client.send_message(chat_id=admin_chat_id, text=prompt_text, reply_markup=markup)
                await asyncio.sleep(0.3)
            
        # ── Final summary ──
        total_elapsed   = time.time() - import_start_time
        elapsed_mins, elapsed_secs = divmod(int(total_elapsed), 60)
        elapsed_str = f"{elapsed_mins}m {elapsed_secs:02d}s" if elapsed_mins else f"{elapsed_secs}s"
        
        if auto_mode:
            bar_done = _build_progress_bar(auto_imported, total_files_all)
            summary_text = (
                f"✅ **Auto-Import Completed!**\n"
                f"{'━' * 28}\n"
                f"🎬 **Series:** {series['title']}\n"
                f"📢 **Source Channel:** `{channel_id}`\n"
                f"💾 **DB Channel:** `{db_channel}`\n"
                f"{'━' * 28}\n"
                f"[{bar_done}] 100%\n"
                f"📨 **Messages Scanned:** `{scanned_count}`\n"
                f"📦 **Batches Processed:** `{len(groups)}`\n"
                f"✅ **Files Imported:** `{auto_imported}`\n"
                f"⏭ **Duplicates Skipped:** `{skipped_dup}`\n"
                f"⏱ **Total Time:** `{elapsed_str}`\n"
                f"{'━' * 28}\n"
                f"All buttons and folders have been created! 🎉"
            )
        else:
            summary_text = (
                f"✅ **Scan Completed!**\n\n"
                f"🎬 **Series:** {series['title']}\n"
                f"📢 **Channel:** `{channel_id}`\n\n"
                f"🔢 **Total Messages Scanned:** `{scanned_count}`\n"
                f"❓ **Missing Batch Groups Found:** `{len(groups)}`\n\n"
                f"Prompt messages have been sent to your chat for importing."
            )
            
        await client.edit_message_text(
            chat_id=admin_chat_id,
            message_id=admin_message_id,
            text=summary_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")
            ]])
        )
    except Exception as e:
        print(f"Error during scan: {e}")
        await client.edit_message_text(
            chat_id=admin_chat_id,
            message_id=admin_message_id,
            text=f"❌ **Scan Failed:** `{e}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]])
        )
    finally:
        ACTIVE_SCANS.pop(series_id, None)

async def delete_series_task(client: Client, admin_chat_id: int, admin_message_id: int, series_id: int, library_skip: int, admin_mention: str, delete_channel_files: bool = True):
    import time
    from .helpers import log_admin_action
    
    series = await database.get_series(series_id)
    if not series:
        return
        
    title = series["title"]
    
    # 1. Fetch DB channel ID for storage message deletion
    settings = await database.get_settings()
    db_channel = settings.get("db_channel_id")
    if series.get("journey_id"):
        journey = await database.get_journey(series["journey_id"])
        if journey and journey.get("db_channel_id"):
            db_channel = journey["db_channel_id"]
    dest_chat = int(db_channel) if db_channel and (db_channel.startswith("-100") or db_channel.isdigit()) else db_channel

    # Fetch files & sections
    files_list, _ = await database.list_files(series_id=series_id, limit=100000)
    sections = await database.list_sections(series_id, parent_id=None)
    
    total_files = len(files_list)
    total_secs = len(sections)
    
    start_time = time.time()
    last_edit_time = 0.0
    EDIT_COOLDOWN = 3.0
    
    def _build_progress_bar(done: int, total: int, width: int = 12) -> str:
        if total == 0:
            return "█" * width
        filled = int(width * done / total)
        return "█" * filled + "░" * (width - filled)

    def _eta_str(done: int, total: int, elapsed: float) -> str:
        if done == 0 or elapsed == 0:
            return "Calculating..."
        rate = done / elapsed
        remaining = (total - done) / rate
        mins, secs = divmod(int(remaining), 60)
        if mins > 0:
            return f"{mins}m {secs:02d}s"
        return f"{secs}s"
        
    async def _live_del_update(current_item: str, done: int, total: int, force: bool = False):
        nonlocal last_edit_time
        now = time.time()
        if not force and now - last_edit_time < EDIT_COOLDOWN:
            return
        last_edit_time = now
        elapsed = now - start_time
        bar = _build_progress_bar(done, total)
        eta = _eta_str(done, total, elapsed)
        pct = int(100 * done / total) if total else 100
        
        mode_str = "Deleting DB records & Channel storage messages..." if delete_channel_files else "Deleting DB records (Preserving Channel storage files)..."
        text = (
            f"🗑 **Live Series Deletion Panel**\n"
            f"{'━' * 28}\n"
            f"🎬 **Series:** {title}\n"
            f"💾 **DB Channel:** `{db_channel or 'N/A'}`\n"
            f"{'━' * 28}\n"
            f"🗑 **Deleting:** `{current_item}`\n"
            f"{'━' * 28}\n"
            f"[{bar}] {pct}%\n"
            f"✅ **Files Deleted:** `{done}` / `{total}`\n"
            f"⏱ **ETA:** ~{eta}\n"
            f"{'━' * 28}\n"
            f"⚠️ {mode_str}"
        )
        try:
            await client.edit_message_text(
                chat_id=admin_chat_id,
                message_id=admin_message_id,
                text=text
            )
        except Exception:
            pass

    deleted_files_count = 0
    deleted_msg_count = 0

    # Delete each file + its DB channel storage message
    for f in files_list:
        fname = f.get("file_name", "Media File")
        await _live_del_update(fname, deleted_files_count, total_files)
        
        # Delete message from DB storage channel if delete_channel_files is True
        if delete_channel_files and dest_chat and f.get("message_id"):
            while True:
                try:
                    await client.delete_messages(chat_id=dest_chat, message_ids=[f["message_id"]])
                    deleted_msg_count += 1
                    break
                except FloodWait as e:
                    print(f"FloodWait in delete_series_task delete_messages: sleeping for {e.value + 1}s...")
                    await asyncio.sleep(e.value + 1)
                except Exception as e:
                    print(f"Failed to delete channel msg {f['message_id']}: {e}")
                    break
                
        # Delete file record from database
        try:
            await database.delete_file(f["file_code"])
            deleted_files_count += 1
        except Exception as e:
            print(f"Failed to delete file record {f['file_code']}: {e}")
            
        await asyncio.sleep(0.1 if not delete_channel_files else 0.3)
        
    # Delete sections
    await _live_del_update("Folder Structure & Categories...", total_files, total_files, force=True)
    for sec in sections:
        try:
            await database.delete_section(sec["id"])
        except Exception:
            pass
            
    # Delete series itself
    await database.delete_series(series_id)
    
    total_elapsed = time.time() - start_time
    elapsed_mins, elapsed_secs = divmod(int(total_elapsed), 60)
    elapsed_str = f"{elapsed_mins}m {elapsed_secs:02d}s" if elapsed_mins else f"{elapsed_secs}s"
    
    chan_msg_summary = f"`{deleted_msg_count}` messages deleted" if delete_channel_files else "Preserved in DB Channel 🛡️"
    await log_admin_action(
        f"🗑 **Series Permanently Deleted**\n"
        f"🎬 **Series:** {title}\n"
        f"📄 **Files Deleted:** `{deleted_files_count}`\n"
        f"💬 **Channel Storage Files:** `{chan_msg_summary}`\n"
        f"👤 **By:** {admin_mention}"
    )
    
    final_text = (
        f"✅ **Series Deleted Successfully!**\n"
        f"{'━' * 28}\n"
        f"🎬 **Series:** {title}\n"
        f"📄 **Files Removed:** `{deleted_files_count}`\n"
        f"💬 **Channel Storage Files:** {chan_msg_summary}\n"
        f"📂 **Folders Cleared:** `{total_secs}`\n"
        f"⏱ **Total Time Spent:** `{elapsed_str}`\n"
        f"{'━' * 28}\n"
        f"Series database records have been successfully cleaned up."
    )
    
    try:
        await client.edit_message_text(
            chat_id=admin_chat_id,
            message_id=admin_message_id,
            text=final_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Series List", callback_data=f"manage_series_skip_{library_skip}")
            ]])
        )
    except Exception:
        pass

async def handle_series_callbacks(client: Client, callback: CallbackQuery, data: str) -> bool:
    user_id = callback.from_user.id

    if data.startswith("import_files_"):
        parts = data.split("_")
        series_id = int(parts[2])
        section_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        await callback.answer()
        sec = await database.get_section(section_id)
        parent_id = sec["parent_id"] if sec else None
        ADMIN_STATES[user_id] = {"state": "waiting_for_tree_file_links", "message_id": callback.message.id, "data": {"series_id": series_id, "section_id": section_id, "parent_folder_id": parent_id, "clear_before": True, "library_skip": library_skip}}
        await callback.message.edit_text(
            f"📥 **{format_sec_name_inline(sec['name']) if sec else 'Files'}** — Import Files\n\n"
            "Please **forward a message** or send the **Telegram message link(s)** to import files.\n\n"
            "**Format Guidelines:**\n"
            "• **Single Link:** Paste a single link:\n"
            "  `https://t.me/c/12345/100` or `(https://t.me/c/12345/100)`\n"
            "• **Range of Links:** Paste first and last links with a space:\n"
            "  `https://t.me/c/12345/100 https://t.me/c/12345/110` or `(https://t.me/c/12345/100 https://t.me/c/12345/110)`\n"
            "• **Multiple Ranges:** Separate multiple links or ranges with a `+` symbol:\n"
            "  `link1 + (link2 link3) + link4`\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="tree_cancel_btn")]])
        )
        return True

    elif data.startswith("rename_sec_"):
        parts = data.split("_")
        series_id = int(parts[2])
        section_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        await callback.answer()
        sec = await database.get_section(section_id)
        if not sec:
            return await callback.message.edit_text("Folder not found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"browse_sec_{series_id}_0_{library_skip}")]]))
        ADMIN_STATES[user_id] = {"state": "waiting_for_rename_sec", "message_id": callback.message.id, "data": {"series_id": series_id, "section_id": section_id, "library_skip": library_skip}}
        await callback.message.edit_text(
            f"✏️ **Rename Folder: {format_sec_name_inline(sec['name'])}**\n\nPlease enter the **New Folder Name / Heading** and optional **Description** (separated by a comma `,`):\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"browse_sec_{series_id}_{section_id}_{library_skip}")]])
        )
        return True

    elif data.startswith("browse_sec_"):
        parts = data.split("_")
        series_id = int(parts[2])
        section_id = int(parts[3])
        await callback.answer()
        await show_series_browse(client, callback.message.chat.id, callback.message.id, series_id, section_id if section_id > 0 else None)
        return True

    elif data.startswith("manage_folder_opt_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        await callback.answer()
        await show_folder_management(client, callback.message.chat.id, callback.message.id, series_id, section_id)
        return True

    elif data.startswith("move_folder_select_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        skip = int(parts[5])
        await callback.answer()
        from .ui_files import show_move_folder_menu
        await show_move_folder_menu(client, callback.message.chat.id, callback.message.id, series_id, section_id, skip)
        return True

    elif data.startswith("move_folder_execute_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        target_val = parts[5]
        
        target_id = None if target_val == "root" else int(target_val)
        
        await callback.answer("📂 Moving folder...")
        success = await database.update_section_parent(section_id, target_id)
        if success:
            await callback.answer("✅ Folder moved successfully!", show_alert=True)
        else:
            await callback.answer("❌ Failed to move folder.", show_alert=True)
            
        await show_folder_management(client, callback.message.chat.id, callback.message.id, series_id, section_id)
        return True

    elif data.startswith("edit_sec_msg_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        library_skip = int(parts[5]) if len(parts) > 5 else 0
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_folder_msg", "message_id": callback.message.id, "data": {"series_id": series_id, "section_id": section_id, "library_skip": library_skip}}
        await callback.message.edit_text(
            "💬 **Edit Section Custom Message**\n\nSend the custom display message for this folder/section. Send `none` to reset to default.\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="tree_cancel_btn")]])
        )
        return True

    elif data.startswith("edit_sec_cols_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        library_skip = int(parts[5]) if len(parts) > 5 else 0
        await callback.answer()
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("1 Column", callback_data=f"set_sec_cols_{series_id}_{section_id}_1_{library_skip}"), InlineKeyboardButton("2 Columns", callback_data=f"set_sec_cols_{series_id}_{section_id}_2_{library_skip}")],
            [InlineKeyboardButton("3 Columns", callback_data=f"set_sec_cols_{series_id}_{section_id}_3_{library_skip}"), InlineKeyboardButton("4 Columns", callback_data=f"set_sec_cols_{series_id}_{section_id}_4_{library_skip}")],
            [InlineKeyboardButton("🔙 Cancel", callback_data=f"manage_folder_opt_{series_id}_{section_id}_{library_skip}")]
        ])
        await callback.message.edit_text("🔢 **Set Buttons Per Row**\n\nSelect columns layout per row:", reply_markup=markup)
        return True

    elif data.startswith("set_sec_cols_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        num = int(parts[5])
        library_skip = int(parts[6]) if len(parts) > 6 else 0
        await callback.answer(f"Buttons per row set to {num}")
        if section_id == 0:
            await database.update_series_settings(series_id, buttons_per_row=num)
        else:
            await database.update_section_settings(section_id, buttons_per_row=num)
        await show_folder_management(client, callback.message.chat.id, callback.message.id, series_id, section_id, library_skip=library_skip)
        return True

    elif data.startswith("rename_series_opt_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_rename_series", "message_id": callback.message.id, "data": {"series_id": series_id, "library_skip": library_skip}}
        await callback.message.edit_text("✏️ **Rename Series**\n\nSend the new title for this series:\n\n❌ Send `/cancel` to abort.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="tree_cancel_btn")]]))
        return True

    elif data.startswith("tree_del_series_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        await callback.answer()
        series = await database.get_series(series_id)
        if not series:
            return await callback.answer("Series not found.")
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⚠️ Yes, Delete Series", callback_data=f"confirm_del_series_{series_id}_{library_skip}"), InlineKeyboardButton("❌ Cancel", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]])
        await callback.message.edit_text(f"⚠️ **Confirm Delete Series**\n\nAre you sure you want to delete **{series['title']}**? This action is permanent!", reply_markup=markup)
        return True

    elif data.startswith("confirm_del_series_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        
        await callback.answer("Starting live series deletion...")
        asyncio.create_task(
            delete_series_task(
                client=client,
                admin_chat_id=callback.message.chat.id,
                admin_message_id=callback.message.id,
                series_id=series_id,
                library_skip=library_skip,
                admin_mention=callback.from_user.mention
            )
        )
        return True

    elif data.startswith("tree_del_sec_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        library_skip = int(parts[5]) if len(parts) > 5 else 0
        await callback.answer()
        sec = await database.get_section(section_id)
        if not sec:
            return await callback.answer("Folder not found.")
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("⚠️ Yes, Delete Folder", callback_data=f"confirm_del_sec_{series_id}_{section_id}_{library_skip}"), InlineKeyboardButton("❌ Cancel", callback_data=f"manage_folder_opt_{series_id}_{section_id}_{library_skip}")]])
        await callback.message.edit_text(f"⚠️ **Confirm Delete Folder**\n\nAre you sure you want to delete **{format_sec_name_inline(sec['name'])}**? This action is permanent!", reply_markup=markup)
        return True

    elif data.startswith("confirm_del_sec_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        library_skip = int(parts[5]) if len(parts) > 5 else 0
        sec = await database.get_section(section_id)
        parent_id = None
        if sec:
            parent_id = sec["parent_id"]
            await database.delete_section(section_id)
            await callback.answer("Folder deleted successfully.", show_alert=True)
        else:
            await callback.answer("Folder not found.")
        await show_series_browse(client, callback.message.chat.id, callback.message.id, series_id, parent_id, library_skip=library_skip)
        return True

    elif data.startswith("config_series_channel_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        await callback.answer()
        ADMIN_STATES[user_id] = {
            "state": "waiting_for_series_channel",
            "message_id": callback.message.id,
            "data": {"series_id": series_id, "library_skip": library_skip}
        }
        await callback.message.edit_text(
            "📢 **Configure Series Source Channel**\n\n"
            "Please **forward any message** from the target Telegram channel here.\n"
            "The bot will extract the channel ID and name to configure it as the automatic source for this series.\n\n"
            "Make sure the Main Bot is added as an **Administrator** in that channel!\n\n"
            "Type `none` or `reset` to remove the source channel.\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]])
        )
        return True

    elif data.startswith("scan_mode_choose_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        
        series = await database.get_series(series_id)
        if not series or not series.get("source_channel_id"):
            return await callback.answer("❌ Please configure a Source Channel first!", show_alert=True)
        
        await callback.answer()
        await callback.message.edit_text(
            f"🔍 **Channel Scan Mode**\n\n"
            f"🎬 **Series:** {series['title']}\n\n"
            f"Choose how the scan should handle missing files:\n\n"
            f"🤖 **Auto** — Bot scans and imports all missing files **automatically** without asking you for each batch.\n\n"
            f"📋 **Manual** — Bot asks you to approve each missing batch before importing.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🤖 Auto Import", callback_data=f"scan_start_auto_{series_id}_{library_skip}"),
                    InlineKeyboardButton("📋 Ask Me Each", callback_data=f"scan_series_channel_{series_id}_{library_skip}")
                ],
                [InlineKeyboardButton("🔙 Cancel", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]
            ])
        )
        return True
    
    elif data.startswith("scan_start_auto_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        
        series = await database.get_series(series_id)
        if not series or not series.get("source_channel_id"):
            return await callback.answer("❌ Source Channel not configured.", show_alert=True)
        
        await callback.answer("Starting auto scan...")
        asyncio.create_task(
            scan_channel_task(
                client=client,
                admin_chat_id=callback.message.chat.id,
                admin_message_id=callback.message.id,
                series_id=series_id,
                library_skip=library_skip,
                auto_mode=True
            )
        )
        return True

    elif data.startswith("scan_series_channel_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        
        series = await database.get_series(series_id)
        if not series or not series.get("source_channel_id"):
            return await callback.answer("❌ Please configure a Source Channel first!", show_alert=True)
            
        await callback.answer("Starting channel scan...")
        asyncio.create_task(
            scan_channel_task(
                client=client,
                admin_chat_id=callback.message.chat.id,
                admin_message_id=callback.message.id,
                series_id=series_id,
                library_skip=library_skip,
                auto_mode=False
            )
        )
        return True

    elif data.startswith("delete_series_confirm_") or data.startswith("tree_del_series_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        
        series = await database.get_series(series_id)
        title = series["title"] if series else f"Series #{series_id}"
        await callback.answer()
        await callback.message.edit_text(
            f"⚠️ **Delete Series Options**\n\n"
            f"🎬 **Series:** {title}\n\n"
            f"Choose how you want to delete this series:\n\n"
            f"🗑 **DB Records Only**\n"
            f"Deletes series details, folders, buttons, and file links from DB, but **keeps** the raw files inside your Telegram Storage DB Channel.\n\n"
            f"🔥 **Delete Entirely (With Channel Files)**\n"
            f"Deletes series details, folders, buttons, file links **AND** deletes the file posts from your Telegram Storage DB Channel.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🗑 DB Only (Keep Channel Files)", callback_data=f"delete_series_db_only_{series_id}_{library_skip}")
                ],
                [
                    InlineKeyboardButton("🔥 Delete Entirely (With Channel Files)", callback_data=f"delete_series_full_{series_id}_{library_skip}")
                ],
                [
                    InlineKeyboardButton("❌ Cancel", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")
                ]
            ])
        )
        return True

    elif data.startswith("delete_series_db_only_"):
        parts = data.split("_")
        series_id = int(parts[4])
        library_skip = int(parts[5]) if len(parts) > 5 else 0
        
        await callback.answer("Starting DB-only series deletion...")
        asyncio.create_task(
            delete_series_task(
                client=client,
                admin_chat_id=callback.message.chat.id,
                admin_message_id=callback.message.id,
                series_id=series_id,
                library_skip=library_skip,
                admin_mention=callback.from_user.mention,
                delete_channel_files=False
            )
        )
        return True

    elif data.startswith("delete_series_full_") or data.startswith("delete_series_execute_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        
        await callback.answer("Starting full series deletion...")
        asyncio.create_task(
            delete_series_task(
                client=client,
                admin_chat_id=callback.message.chat.id,
                admin_message_id=callback.message.id,
                series_id=series_id,
                library_skip=library_skip,
                admin_mention=callback.from_user.mention,
                delete_channel_files=True
            )
        )
        return True

    elif data.startswith("pause_scan_"):
        parts = data.split("_")
        series_id = int(parts[2])
        library_skip = int(parts[3]) if len(parts) > 3 else 0
        PAUSED_SCANS[series_id] = True
        await callback.answer("⏸ Import paused. Click Resume when ready.", show_alert=False)
        return True

    elif data.startswith("resume_scan_"):
        parts = data.split("_")
        series_id = int(parts[2])
        PAUSED_SCANS.pop(series_id, None)
        await callback.answer("▶️ Import resumed!", show_alert=False)
        return True

    elif data.startswith("cancel_scan_confirm_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        # Pause while waiting for confirmation so no more files forward
        PAUSED_SCANS[series_id] = True
        await callback.answer()
        await callback.message.edit_text(
            f"⚠️ **Cancel Import?**\n\n"
            f"The import has been **paused**.\n\n"
            f"Are you sure you want to cancel? Files already imported will remain in the DB.\n"
            f"Remaining files in the queue **will not** be imported.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🗑 Yes, Cancel Import", callback_data=f"cancel_scan_execute_{series_id}_{library_skip}"),
                    InlineKeyboardButton("▶️ No, Resume", callback_data=f"resume_scan_{series_id}_{library_skip}")
                ]
            ])
        )
        return True

    elif data.startswith("cancel_scan_execute_"):
        parts = data.split("_")
        series_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        # Signal the import task to stop
        ACTIVE_SCANS[series_id] = False
        PAUSED_SCANS.pop(series_id, None)
        await callback.answer("❌ Import cancelled.")
        await callback.message.edit_text(
            f"🔴 **Import Cancelled**\n\n"
            f"The channel import has been stopped.\n"
            f"Files that were already imported remain in the database.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Back to Settings", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")
            ]])
        )
        return True

    elif data.startswith("abort_scan_"):
        parts = data.split("_")
        series_id = int(parts[2])
        ACTIVE_SCANS[series_id] = False
        PAUSED_SCANS.pop(series_id, None)
        await callback.answer("Aborting scan process...")
        return True
        
    elif data.startswith("scan_add_"):
        parts = data.split("_")
        series_id = int(parts[2])
        msg_id = int(parts[3])
        
        await callback.answer("Importing file...")
        
        series = await database.get_series(series_id)
        if not series or not series.get("source_channel_id"):
            return await callback.message.edit_text("❌ Series or source channel not configured.")
            
        channel_id = series["source_channel_id"]
        chat_id = int(channel_id) if channel_id.startswith("-100") or channel_id.isdigit() else channel_id
        
        try:
            msg = await client.get_messages(chat_id, message_ids=msg_id)
        except Exception as e:
            return await callback.message.edit_text(f"❌ Failed to fetch message: {e}")
            
        if not msg or msg.empty:
            return await callback.message.edit_text("❌ Message not found in channel.")
            
        media = msg.document or msg.video or msg.audio
        if not media:
            return await callback.message.edit_text("❌ No media found in this message.")
            
        file_name = getattr(media, "file_name", "Media File")
        file_size = getattr(media, "file_size", 0)
        mime_type = getattr(media, "mime_type", "unknown")
        caption = msg.caption or ""
        
        from .automation import check_file_duplicate, get_or_create_section_for_file
        from .ai_parser import parse_file_metadata
        from .helpers import get_readable_size
        
        is_duplicate = await check_file_duplicate(series_id, file_name, file_size)
        if is_duplicate:
            return await callback.message.edit_text(f"⚠️ Duplicate found: `{file_name}` is already imported.")
            
        metadata = await parse_file_metadata(file_name, caption)
        if not metadata:
            metadata = {}
            
        section_id = await get_or_create_section_for_file(series_id, metadata)
        
        settings = await database.get_settings()
        db_channel = settings.get("db_channel_id")
        if series.get("journey_id"):
            journey = await database.get_journey(series["journey_id"])
            if journey and journey.get("db_channel_id"):
                db_channel = journey["db_channel_id"]
                
        if not db_channel:
            return await callback.message.edit_text("❌ DB Channel storage is not configured.")
            
        dest_chat = int(db_channel) if db_channel.startswith("-100") or db_channel.isdigit() else db_channel
        
        try:
            copied_msg = await client.copy_message(
                chat_id=dest_chat,
                from_chat_id=chat_id,
                message_id=msg_id
            )
        except Exception as e:
            return await callback.message.edit_text(f"❌ Copy failed: {e}")
            
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
            f"📥 **Manual Scan Import**\n"
            f"🎬 **Series:** {series['title']}\n"
            f"📂 **File:** `{file_name}`\n"
            f"👤 **By:** {callback.from_user.mention}\n"
            f"🔗 **Link:** {link_str}"
        )
        
        sec_info = await database.get_section(section_id)
        sec_name = sec_info["name"] if sec_info else "Target Folder"
        await callback.message.edit_text(
            f"✅ **Imported successfully!**\n\n"
            f"📄 **File:** `{file_name}`\n"
            f"📂 **Added under:** `{sec_name}`\n"
            f"🔗 **Link:** {link_str}"
        )
        return True

    elif data.startswith("scan_batch_"):
        parts = data.split("_")
        batch_key = parts[2]
        
        batch = PENDING_BATCHES.get(batch_key)
        if not batch:
            return await callback.message.edit_text("❌ Batch configuration expired or already processed.")
            
        await callback.answer("Importing batch...")
        
        series_id = batch["series_id"]
        season = batch["season"]
        start = batch["start"]
        end = batch["end"]
        quality = batch["quality"]
        msg_ids = batch["msg_ids"]
        
        series = await database.get_series(series_id)
        if not series or not series.get("source_channel_id"):
            return await callback.message.edit_text("❌ Series or source channel not configured.")
            
        channel_id = series["source_channel_id"]
        chat_id = int(channel_id) if channel_id.startswith("-100") or channel_id.isdigit() else channel_id
        
        settings = await database.get_settings()
        db_channel = settings.get("db_channel_id")
        if series.get("journey_id"):
            journey = await database.get_journey(series["journey_id"])
            if journey and journey.get("db_channel_id"):
                db_channel = journey["db_channel_id"]
                
        if not db_channel:
            return await callback.message.edit_text("❌ DB Channel storage is not configured.")
            
        dest_chat = int(db_channel) if db_channel.startswith("-100") or db_channel.isdigit() else db_channel
        
        from .automation import get_or_create_section_for_file, check_file_duplicate
        from .helpers import get_readable_size
        import uuid
        
        imported_count = 0
        duplicate_count = 0
        section_id = None
        
        dummy_metadata = {
            "season_number": season,
            "resolution": quality,
            "episode_range": f"{start:02d}-{end:02d}"
        }
        section_id = await get_or_create_section_for_file(series_id, dummy_metadata)
        
        # Ensure msg_ids are in ascending order (EP01 → EP90)
        msg_ids = sorted(msg_ids)
        
        for msg_id in msg_ids:
            try:
                msg = await client.get_messages(chat_id, message_ids=msg_id)
            except Exception:
                continue
                
            if not msg or msg.empty:
                continue
                
            media = msg.document or msg.video or msg.audio
            if not media:
                continue
                
            file_name = getattr(media, "file_name", "Media File")
            file_size = getattr(media, "file_size", 0)
            mime_type = getattr(media, "mime_type", "unknown")
            caption = msg.caption or ""
            
            is_dup = await check_file_duplicate(series_id, file_name, file_size)
            if is_dup:
                duplicate_count += 1
                continue
                
            copied_msg = None
            while True:
                try:
                    copied_msg = await client.copy_message(
                        chat_id=dest_chat,
                        from_chat_id=chat_id,
                        message_id=msg_id
                    )
                    break
                except FloodWait as e:
                    print(f"FloodWait in scan_batch_ copy_message: sleeping for {e.value + 1}s...")
                    await asyncio.sleep(e.value + 1)
                except Exception as e:
                    print(f"Failed to copy file {msg_id}: {e}")
                    await asyncio.sleep(3)
                    break
            if not copied_msg:
                continue
                
            from .ai_parser import parse_file_metadata
            meta = await parse_file_metadata(file_name, caption)
            ep_num = meta.get("episode_number") if meta else None
            
            file_code = str(uuid.uuid4())[:8]
            await database.add_file(
                file_code=file_code,
                message_id=copied_msg.id,
                file_name=file_name,
                file_size=file_size,
                mime_type=mime_type,
                caption=caption,
                series_id=series_id,
                episode_number=ep_num,
                section_id=section_id
            )
            imported_count += 1
            
            # 2-second gap between each file to respect Telegram rate limits
            await asyncio.sleep(2)
            
        PENDING_BATCHES.pop(batch_key, None)
        
        sec_info = await database.get_section(section_id)
        sec_name = sec_info["name"] if sec_info else f"EP ({start:02d} - {end:02d})"
        
        primary = settings.get("primary_clone_username")
        await log_admin_action(
            f"📥 **Manual Batch Scan Import**\n"
            f"🎬 **Series:** {series['title']}\n"
            f"📂 **Section:** `{sec_name}`\n"
            f"📥 **Imported:** `{imported_count}` files\n"
            f"⚠️ **Duplicates Skipped:** `{duplicate_count}`\n"
            f"👤 **By:** {callback.from_user.mention}"
        )
        
        await callback.message.edit_text(
            f"✅ **Batch Imported successfully!**\n\n"
            f"🎬 **Series:** {series['title']}\n"
            f"📂 **Added under:** `{sec_name}`\n"
            f"📥 **Files Imported:** `{imported_count}`\n"
            f"⚠️ **Duplicates Skipped:** `{duplicate_count}`"
        )
        return True

    elif data == "scan_ignore":
        await callback.answer("Ignored.")
        await callback.message.delete()
        return True

    elif data.startswith("del_tree_file_"):
        parts = data.split("_")
        file_code = parts[3]
        series_id = int(parts[4])
        section_id = int(parts[5])
        file_info = await database.get_file(file_code)
        if file_info:
            await database.delete_file(file_code)
            await callback.answer("File deleted successfully!", show_alert=True)
        else:
            await callback.answer("File not found.")
        await show_series_browse(client, callback.message.chat.id, callback.message.id, series_id, section_id if section_id > 0 else None)
        return True

    elif data.startswith("tree_add_btn_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        library_skip = int(parts[5]) if len(parts) > 5 else 0
        await callback.answer()
        
        text = (
            "➕ **Add Button**\n\n"
            "Select the button type:\n\n"
            "📁 **Folder**: Opens a subfolder section for nested buttons.\n"
            "📄 **File**: Directly delivers content/files to the user."
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📁 Folder", callback_data=f"tree_add_type_folder_{series_id}_{section_id}_{library_skip}"),
                InlineKeyboardButton("📄 File", callback_data=f"tree_add_type_file_{series_id}_{section_id}_{library_skip}")
            ],
            [
                InlineKeyboardButton("🔙 Cancel", callback_data=f"browse_sec_{series_id}_{section_id}_{library_skip}")
            ]
        ])
        await callback.message.edit_text(text, reply_markup=markup)
        return True

    elif data.startswith("tree_bulk_add_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        library_skip = int(parts[5]) if len(parts) > 5 else 0
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_bulk_add", "message_id": callback.message.id, "data": {"series_id": series_id, "section_id": section_id, "library_skip": library_skip}}
        
        bulk_note = (
            "📥 **Bulk Add Guide**\n\n"
            "Bulk Add lets you create folders, buttons, and message ranges with a single copy & paste. The bot automatically understands the format and creates everything for you.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📄 **Add Files / Buttons**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Enter the button name first, followed by the Telegram link(s).\n\n"
            "• The first Telegram link is treated as the Start Link.\n"
            "• If another link is provided after it (without `+`), it is treated as the End Link, and the bot will copy all messages between them.\n"
            "• Use a comma (`,`) to start the next button.\n\n"
            "✅ **Single File**\n"
            "`Episode 01 https://t.me/c/12345/100`\n\n"
            "✅ **Message Range**\n"
            "`EP (01 - 10) https://t.me/c/12345/100 https://t.me/c/12345/109`\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "➕ **Multiple Files / Ranges**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Use `+` to combine multiple files or ranges into a single button.\n\n"
            "• A single link copies one message.\n"
            "• A pair of links inside `( )` is treated as a message range.\n"
            "• Everything before the comma belongs to the same button.\n\n"
            "**Example:**\n"
            "`Episode Pack https://t.me/c/12345/100 + https://t.me/c/12345/120 + (https://t.me/c/12345/200 https://t.me/c/12345/205)`\n\n"
            "This creates **ONE** button containing:\n"
            "• Message 100\n"
            "• Message 120\n"
            "• Messages 200–205\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📁 **Create Folders**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Wrap folders using the following format:\n\n"
            "```\n"
            "[\"Folder Name\"{\n"
            "    Folder Contents\n"
            "}]\n"
            "```\n"
            "• Folder names must be inside double quotes (`\" \"`).\n"
            "• Everything inside `{ }` belongs to that folder.\n"
            "• You can create folders inside folders.\n"
            "• Separate multiple folders using a comma (`,`).\n\n"
            "**Example:**\n"
            "```\n"
            "[\"Season 01\"{\n"
            "    Episode 01 https://t.me/c/12345/100,\n"
            "    Episode 02 https://t.me/c/12345/101\n"
            "}]\n"
            "```\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📂 **Nested Folder Example**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "```\n"
            "[\"Season 01\"{\n"
            "    EP (01 - 04) https://t.me/c/12345/100 https://t.me/c/12345/103,\n"
            "    EP (05 - 08) https://t.me/c/12345/104 https://t.me/c/12345/107,\n\n"
            "    [\"Special Episodes\"{\n"
            "        Special 01 https://t.me/c/12345/200,\n"
            "        Special Pack https://t.me/c/12345/201 + (https://t.me/c/12345/210 https://t.me/c/12345/215)\n"
            "    }]\n"
            "}]\n"
            "```\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📋 **Full Copy & Paste Example**\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "```\n"
            "[\"Season 01\"{\n"
            "    EP (01 - 04) https://t.me/c/12345/100 https://t.me/c/12345/103,\n"
            "    EP (05 - 08) https://t.me/c/12345/104 https://t.me/c/12345/107,\n"
            "    Special Pack https://t.me/c/12345/108 + https://t.me/c/12345/109 + (https://t.me/c/12345/110 https://t.me/c/12345/115),\n\n"
            "    [\"Extras\"{\n"
            "        Trailer https://t.me/c/12345/300,\n"
            "        Behind The Scenes https://t.me/c/12345/301\n"
            "    }]\n"
            "}],\n"
            "[\"Season 02\"{\n"
            "    EP (01 - 04) https://t.me/c/12345/400 https://t.me/c/12345/403\n"
            "}]\n"
            "```\n\n"
            "❌ Send `/cancel` to abort."
        )
        await callback.message.edit_text(
            bulk_note,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="tree_cancel_btn")]])
        )
        return True

    elif data.startswith("stop_bulk_add_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        await callback.answer("🛑 Stopping bulk creation...", show_alert=True)
        if user_id in ADMIN_STATES and ADMIN_STATES[user_id].get("state") == "bulk_adding":
            ADMIN_STATES[user_id]["cancel_requested"] = True
        return True

    elif data.startswith("filesec_act_"):
        parts = data.split("_")
        series_id = int(parts[2])
        section_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        await callback.answer()
        sec = await database.get_section(section_id)
        if not sec:
            return await callback.answer("❌ Section not found.", show_alert=True)
        _, total_files = await database.list_files(skip=0, limit=1, series_id=series_id, section_id=section_id)
        await show_filesec_actions(client, callback.message.chat.id, callback.message.id, series_id, section_id, sec, total_files, library_skip=library_skip)
        return True

    elif data.startswith("filesec_add_"):
        parts = data.split("_")
        series_id = int(parts[2])
        section_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        await callback.answer()
        sec = await database.get_section(section_id)
        parent_id = sec["parent_id"] if sec else None
        ADMIN_STATES[user_id] = {"state": "waiting_for_tree_file_links", "message_id": callback.message.id, "data": {"series_id": series_id, "section_id": section_id, "parent_folder_id": parent_id, "clear_before": False, "library_skip": library_skip}}
        await callback.message.edit_text(
            f"➕ **Add More Files to: {format_sec_name_inline(sec['name']) if sec else 'Button'}**\n\n"
            "Please **forward a message** or send the **Telegram message link(s)** to append files.\n\n"
            "**Format Guidelines:**\n"
            "• **Single Link:** Paste a single link:\n"
            "  `https://t.me/c/12345/100` or `(https://t.me/c/12345/100)`\n"
            "• **Range of Links:** Paste first and last links with a space:\n"
            "  `https://t.me/c/12345/100 https://t.me/c/12345/110` or `(https://t.me/c/12345/100 https://t.me/c/12345/110)`\n"
            "• **Multiple Ranges:** Separate multiple links or ranges with a `+` symbol:\n"
            "  `link1 + (link2 link3) + link4`\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"filesec_act_{series_id}_{section_id}_{library_skip}")]]))
        return True

    elif data.startswith("filesec_replace_"):
        parts = data.split("_")
        series_id = int(parts[2])
        section_id = int(parts[3])
        library_skip = int(parts[4]) if len(parts) > 4 else 0
        await callback.answer()
        sec = await database.get_section(section_id)
        parent_id = sec["parent_id"] if sec else None
        ADMIN_STATES[user_id] = {"state": "waiting_for_tree_file_links", "message_id": callback.message.id, "data": {"series_id": series_id, "section_id": section_id, "parent_folder_id": parent_id, "clear_before": True, "library_skip": library_skip}}
        await callback.message.edit_text(
            f"🔄 **Replace All Files in: {format_sec_name_inline(sec['name']) if sec else 'Button'}**\n\n"
            "⚠️ **WARNING:** This will delete existing files in this button!\n\n"
            "Please **forward a message** or send the new **Telegram message link(s)**:\n\n"
            "**Format Guidelines:**\n"
            "• **Single Link:** Paste a single link:\n"
            "  `https://t.me/c/12345/100` or `(https://t.me/c/12345/100)`\n"
            "• **Range of Links:** Paste first and last links with a space:\n"
            "  `https://t.me/c/12345/100 https://t.me/c/12345/110` or `(https://t.me/c/12345/100 https://t.me/c/12345/110)`\n"
            "• **Multiple Ranges:** Separate multiple links or ranges with a `+` symbol:\n"
            "  `link1 + (link2 link3) + link4`\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"filesec_act_{series_id}_{section_id}_{library_skip}")]]))
        return True

    elif data.startswith("tree_add_type_folder_"):
        parts = data.split("_")
        series_id = int(parts[4])
        section_id = int(parts[5])
        library_skip = int(parts[6]) if len(parts) > 6 else 0
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_tree_folder_name", "message_id": callback.message.id, "data": {"series_id": series_id, "parent_folder_id": section_id, "library_skip": library_skip}}
        await callback.message.edit_text(
            "📁 **Create Folder**\n\nPlease enter the **Folder Name** and optional **Description** (separated by a comma `,`):\n\nExample: `Season 1, 📅 Released in 2024`\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="tree_cancel_btn")]])
        )
        return True

    elif data.startswith("tree_add_type_file_"):
        parts = data.split("_")
        series_id = int(parts[4])
        section_id = int(parts[5])
        library_skip = int(parts[6]) if len(parts) > 6 else 0
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_tree_file_btn_name", "message_id": callback.message.id, "data": {"series_id": series_id, "parent_folder_id": section_id, "library_skip": library_skip}}
        await callback.message.edit_text(
            "📄 **Add File Button**\n\nPlease enter the **Button / File Name** and optional **Description** (separated by a comma `,`):\n\nExample: `Ep (01 - 10), 📅 Added on 07 Jul 2025`\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="tree_cancel_btn")]])
        )
        return True

    elif data == "tree_cancel_btn":
        await callback.answer()
        state_data = ADMIN_STATES.pop(user_id, None)
        if state_data:
            state_name = state_data.get("state")
            if state_name == "waiting_for_auto_delete_duration":
                await show_auto_delete_menu(client, callback.message.chat.id, callback.message.id)
                return True
            
            series_id = state_data["data"].get("series_id")
            parent_folder_id = state_data["data"].get("parent_folder_id")
            section_id = state_data["data"].get("section_id")
            library_skip = state_data["data"].get("library_skip", 0)
            
            if state_name in ["waiting_for_folder_msg", "waiting_for_rename_series", "waiting_for_folder_pic"]:
                target_sec = section_id if section_id is not None else 0
                await show_folder_management(client, callback.message.chat.id, callback.message.id, series_id, target_sec, library_skip=library_skip)
                return True
            
            if state_data["data"].get("is_new_section"):
                new_sec_id = state_data["data"]["section_id"]
                await database.delete_section(new_sec_id)
                await show_series_browse(client, callback.message.chat.id, callback.message.id, series_id, parent_folder_id if parent_folder_id and parent_folder_id > 0 else None, library_skip=library_skip)
            else:
                sec = await database.get_section(section_id)
                if sec:
                    _, total_files = await database.list_files(skip=0, limit=1, series_id=series_id, section_id=section_id)
                    await show_filesec_actions(client, callback.message.chat.id, callback.message.id, series_id, section_id, sec, total_files, library_skip=library_skip)
                else:
                    await show_series_browse(client, callback.message.chat.id, callback.message.id, series_id, parent_folder_id if parent_folder_id and parent_folder_id > 0 else None, library_skip=library_skip)
        return True

    elif data.startswith("manage_journey_"):
        journey_id = int(data.split("_")[2])
        await callback.answer()
        await show_journey_detail(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data == "create_journey_opt":
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_journey_name", "message_id": callback.message.id}
        await callback.message.edit_text(
            "🗺️ **Create New Journey / Category**\n\nPlease enter the **Journey Name** (e.g., `Movies`, `Weekly Webseries`):\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="manage_series")]])
        )
        return True

    elif data == "edit_library_msg_opt":
        await callback.answer()
        await show_edit_library_message_menu(client, callback.message.chat.id, callback.message.id)
        return True

    elif data == "edit_global_library_welcome_msg":
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_library_welcome_msg", "message_id": callback.message.id}
        await callback.message.edit_text(
            "💬 **Edit Global Welcome Message**\n\n"
            "Send the custom welcome message to display at the top of the categories/journey list page in Clone Bots.\n\n"
            "Send `none` to disable/reset to default.\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="edit_library_msg_opt")]])
        )
        return True

    elif data.startswith("edit_journey_desc_lib_"):
        journey_id = int(data.split("_")[4])
        await callback.answer()
        j = await database.get_journey(journey_id)
        ADMIN_STATES[user_id] = {
            "state": "waiting_for_journey_description_edit",
            "message_id": callback.message.id,
            "data": {"journey_id": journey_id, "return_to": "library_msg"}
        }
        await callback.message.edit_text(
            f"📝 **Edit Description: {j['name']}**\n\n"
            "Please send the new description for this category/journey.\n"
            "This description will display below the heading in the series list/category screen.\n\n"
            "Send `none` to clear the description.\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="edit_library_msg_opt")]])
        )
        return True

    elif data.startswith("rename_journey_opt_"):
        journey_id = int(data.split("_")[3])
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_rename_journey", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            "✏️ **Rename Journey**\n\nPlease enter the new name for this journey:\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"manage_journey_{journey_id}")]])
        )
        return True

    elif data.startswith("edit_journey_desc_opt_"):
        journey_id = int(data.split("_")[4])
        await callback.answer()
        ADMIN_STATES[user_id] = {
            "state": "waiting_for_journey_description_edit",
            "message_id": callback.message.id,
            "data": {"journey_id": journey_id}
        }
        await callback.message.edit_text(
            "📝 **Edit Journey Description**\n\nPlease enter the new description for this category/journey.\nSend `none` to clear the description.\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"manage_journey_{journey_id}")]])
        )
        return True

    elif data.startswith("delete_journey_opt_"):
        journey_id = int(data.split("_")[3])
        await callback.answer()
        j = await database.get_journey(journey_id)
        if not j:
            return await callback.answer("Journey not found.", show_alert=True)
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Yes, Delete Journey", callback_data=f"confirm_delete_j_{journey_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"manage_journey_{journey_id}")
            ]
        ])
        await callback.message.edit_text(
            f"⚠️ **Confirm Delete Journey**\n\nAre you sure you want to delete **{j['name']}**?\n"
            "This will delete ALL series, folders, and links associated with this journey! This action is permanent!",
            reply_markup=markup
        )
        return True

    elif data.startswith("confirm_delete_j_"):
        journey_id = int(data.split("_")[3])
        j = await database.get_journey(journey_id)
        if j:
            name = j["name"]
            await database.delete_journey(journey_id)
            await log_admin_action(f"🗑 **Journey Deleted**: `{name}` (ID: {journey_id}) by {callback.from_user.mention}")
            await callback.answer("Journey deleted successfully.", show_alert=True)
        else:
            await callback.answer("Journey not found.")
        await show_manage_series(client, callback.message.chat.id, callback.message.id)
        return True

    elif data.startswith("list_j_series_"):
        parts = data.split("_")
        journey_id = int(parts[3])
        skip = int(parts[4])
        await callback.answer()
        await show_manage_series_journey(client, callback.message.chat.id, callback.message.id, journey_id, skip)
        return True

    elif data.startswith("create_series_j_"):
        journey_id = int(data.split("_")[3])
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_series_title_j", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            "🎬 **Create New Series**\n\nPlease enter the **Series Title**:\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"list_j_series_{journey_id}_0")]])
        )
    elif data.startswith("config_j_db_"):
        journey_id = int(data.split("_")[3])
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_j_db_channel", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            "📁 **Configure Journey DB Channel**\n\n"
            "Please send the numerical channel ID (e.g., `-100123456789`) where files for this journey are stored.\n"
            "Normal users on clone bots will download files directly from this channel.\n\n"
            "To reset and use the default global DB channel, send `none` or `default`.\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"manage_journey_{journey_id}")]])
        )
        return True

    elif data.startswith("config_j_up_chan_"):
        journey_id = int(data.split("_")[4])
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_j_update_channel", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            "📢 **Configure Episode Update Channel**\n\n"
            "Please send the numerical Telegram Channel ID (e.g. `-1001234567890`) where episode update alert messages will be automatically posted when new files are added.\n\n"
            "Make sure the Bot is added as an **Administrator** in that channel!\n\n"
            "To disable notification posts for this Journey, send `none` or `disable`.\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"manage_journey_{journey_id}")]])
        )
        return True

    elif data.startswith("config_j_up_tmpl_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        current_tmpl = (j and j.get("update_msg_template")) or "{series_name} latest episode ({date}) updated ✅\n\nBot : @{bot_username}"
        help_text = get_fillings_help_text()
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_j_update_template", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            f"💬 **Configure Episode Update Notification Template**\n\n"
            f"Current Template:\n`{current_tmpl}`\n\n"
            f"{help_text}\n"
            f"Send your new message template below.\n"
            f"To reset to default template, send `default`.\n\n"
            f"❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"manage_journey_{journey_id}")]])
        )
        return True

    elif data.startswith("config_j_btn_tmpl_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        current_tmpl = (j and j.get("button_name_template")) or "📥 Ep ({start} - {end}) {date_small}"
        help_text = get_fillings_help_text()
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_j_button_template", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            f"🔘 **Configure Button Name Format Template**\n\n"
            f"Current Button Template:\n`{current_tmpl}`\n\n"
            f"{help_text}\n"
            f"Example format:\n`📥 Ep ({start} - {end}) {date_small}` ➔ Renders as: `📥 Ep (57 - 60) ⁰⁶⁻⁰⁸⁻²⁶`\n\n"
            f"Send your new button template below.\n"
            f"To reset to default template, send `default`.\n\n"
            f"❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"manage_journey_{journey_id}")]])
        )
        return True

    elif data.startswith("j_lock_settings_"):
        journey_id = int(data.split("_")[3])
        await callback.answer()
        await show_journey_lock_settings(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("tog_j_is_locked_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        if j:
            new_val = not j.get("is_locked", False)
            await database.update_journey_settings(journey_id, is_locked=new_val)
            await callback.answer(f"Entire Journey Lock toggled to: {'ON' if new_val else 'OFF'}")
        await show_journey_lock_settings(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("tog_j_lock_b_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        if j:
            new_val = not j["lock_buttons_enabled"]
            await database.update_journey_settings(journey_id, lock_buttons_enabled=new_val)
            await callback.answer(f"Master Switch toggled to: {'ON' if new_val else 'OFF'}")
        await show_journey_lock_settings(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("tog_j_lock_o_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        if j:
            new_val = not j["lock_old_series_enabled"]
            await database.update_journey_settings(journey_id, lock_old_series_enabled=new_val)
            await callback.answer(f"Lock Old Series toggled to: {'ON' if new_val else 'OFF'}")
        await show_journey_lock_settings(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("tog_j_lock_a_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        if j:
            new_val = not j["lock_active_series_enabled"]
            await database.update_journey_settings(journey_id, lock_active_series_enabled=new_val)
            await callback.answer(f"Lock Active Series toggled to: {'ON' if new_val else 'OFF'}")
        await show_journey_lock_settings(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("tog_j_lock_d_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        if j:
            if not j["lock_active_series_enabled"]:
                await callback.answer("⚠️ Please enable 'Lock Active Series' first!", show_alert=True)
                return True
            new_val = not j["lock_day_based_enabled"]
            await database.update_journey_settings(journey_id, lock_day_based_enabled=new_val)
            await callback.answer(f"Day-Based Lock toggled to: {'ON' if new_val else 'OFF'}")
        await show_journey_lock_settings(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("tog_j_lock_i_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        if j:
            new_val = not j["lock_individual_enabled"]
            await database.update_journey_settings(journey_id, lock_individual_enabled=new_val)
            await callback.answer(f"Individual Lock Switch toggled to: {'ON' if new_val else 'OFF'}")
        await show_journey_lock_settings(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("reset_j_locks_btn_"):
        journey_id = int(data.split("_")[4])
        await callback.answer()
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Yes, Reset All Locks", callback_data=f"confirm_reset_locks_{journey_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"j_lock_settings_{journey_id}")
            ]
        ])
        await callback.message.edit_text(
            "⚠️ **Confirm Reset All Individual Locks**\n\n"
            "This will remove the individual lock status from ALL series and sections in this journey. "
            "They will all be unlocked by default.",
            reply_markup=markup
        )
        return True

    elif data.startswith("confirm_reset_locks_"):
        journey_id = int(data.split("_")[3])
        await database.reset_journey_locks(journey_id)
        await callback.answer("✅ All individual locks reset successfully!", show_alert=True)
        await show_journey_lock_settings(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("edit_j_unlock_dur_"):
        journey_id = int(data.split("_")[4])
        j = await database.get_journey(journey_id)
        if j and not j["lock_active_series_enabled"]:
            await callback.answer("⚠️ Please enable 'Lock Active Series' first!", show_alert=True)
            return True
        await callback.answer()
        current_window = j["lock_time_window"] if j else 0
        ADMIN_STATES[user_id] = {"state": "waiting_for_j_unlock_duration", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            "⏱ **Edit Unlock Duration**\n\n"
            "Specify the period during which new content remains unlocked for non-premium users.\n"
            "Format: number followed by `h` (hours) or `d` (days).\n"
            "Examples: `12h` (12 hours), `1d` (24 hours), `3d` (72 hours).\n\n"
            f"Current Unlock Duration: `{current_window} hour(s)`\n"
            "Type `0`, `no`, or `disable` to only keep the latest item unlocked.\n\n"
            "❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data=f"j_lock_settings_{journey_id}")]])
        )
        return True

    elif data.startswith("config_j_active_"):
        parts = data.split("_")
        journey_id = int(parts[3])
        skip = int(parts[4])
        await callback.answer()
        await show_journey_active_series_config(client, callback.message.chat.id, callback.message.id, journey_id, skip)
        return True

    elif data.startswith("tog_j_ser_active_"):
        parts = data.split("_")
        journey_id = int(parts[4])
        series_id = int(parts[5])
        skip = int(parts[6])
        
        series = await database.get_series(series_id)
        if series:
            new_status = not series.get("is_active", True)
            await database.update_series_settings(series_id, is_active=new_status)
            await callback.answer(f"Toggled {series['title']} active status to: {'Active' if new_status else 'Inactive'}")
        else:
            await callback.answer("Series not found.", show_alert=True)
            
        await show_journey_active_series_config(client, callback.message.chat.id, callback.message.id, journey_id, skip)
        return True

    elif data.startswith("toggle_indiv_lock_"):
        parts = data.split("_")
        series_id = int(parts[3])
        section_id = int(parts[4])
        library_skip = int(parts[5]) if len(parts) > 5 else 0
        await callback.answer()
        if section_id == 0:
            s = await database.get_series(series_id)
            if s:
                new_lock = not s.get("is_locked", False)
                await database.update_series_settings(series_id, is_locked=new_lock)
                await callback.answer(f"Individual Lock: {'ON' if new_lock else 'OFF'}")
        else:
            sec = await database.get_section(section_id)
            if sec:
                new_lock = not sec.get("is_locked", False)
                await database.update_section_settings(section_id, is_locked=new_lock)
                await callback.answer(f"Individual Lock: {'ON' if new_lock else 'OFF'}")
        await show_folder_management(client, callback.message.chat.id, callback.message.id, series_id, section_id, library_skip=library_skip)
        return True

    elif data.startswith("j_series_management_menu_"):
        journey_id = int(data.split("_")[4])
        await callback.answer()
        ADMIN_STATES.pop(user_id, None)
        await show_series_management_menu(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("series_reorder_menu_"):
        journey_id = int(data.split("_")[3])
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_reorder", "message_id": callback.message.id, "data": {"selected_ids": [], "journey_id": journey_id}}
        await show_series_reorder_menu(client, callback.message.chat.id, callback.message.id, journey_id, selected_ids=[])
        return True

    elif data.startswith("reorder_toggle_"):
        parts = data.split("_")
        journey_id = int(parts[2])
        series_id = int(parts[3])
        await callback.answer()
        if user_id not in ADMIN_STATES or ADMIN_STATES[user_id].get("state") != "waiting_for_reorder":
            ADMIN_STATES[user_id] = {"state": "waiting_for_reorder", "message_id": callback.message.id, "data": {"selected_ids": [], "journey_id": journey_id}}
        
        selected_ids = ADMIN_STATES[user_id]["data"]["selected_ids"]
        if series_id in selected_ids:
            selected_ids.remove(series_id)
        else:
            selected_ids.append(series_id)
            
        await show_series_reorder_menu(client, callback.message.chat.id, callback.message.id, journey_id, selected_ids=selected_ids)
        return True

    elif data.startswith("reorder_confirm_"):
        journey_id = int(data.split("_")[2])
        if user_id not in ADMIN_STATES or ADMIN_STATES[user_id].get("state") != "waiting_for_reorder":
            await callback.answer("❌ Error: Reordering session expired. Please start over.", show_alert=True)
            await show_series_management_menu(client, callback.message.chat.id, callback.message.id, journey_id)
            return True
            
        selected_ids = ADMIN_STATES[user_id]["data"]["selected_ids"]
        if len(selected_ids) < 2:
            await callback.answer("Please select at least 2 series to reorder.", show_alert=True)
            return True
            
        series_list = await database.list_series(journey_id=journey_id)
        ordered_ids = []
        ordered_ids.extend(selected_ids)
        for s in series_list:
            sid = s["id"]
            if sid not in selected_ids:
                ordered_ids.append(sid)
                
        for index, sid in enumerate(ordered_ids):
            await database.update_series_settings(sid, display_order=index)
            
        ADMIN_STATES.pop(user_id, None)
        await callback.answer("✅ Series list reordered successfully!", show_alert=True)
        await show_series_management_menu(client, callback.message.chat.id, callback.message.id, journey_id)
        return True

    elif data.startswith("edit_series_pag_limit_"):
        journey_id = int(data.split("_")[4])
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_series_pag_limit", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            "🔢 **Edit Series Buttons per Page**\n\nEnter the number of series buttons to display on a single page for users (e.g., `5`):\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"j_series_management_menu_{journey_id}")]])
        )
        return True

    elif data.startswith("manage_series_skip_"):
        skip = int(data.split("_")[3])
        await callback.answer()
        await show_manage_series(client, callback.message.chat.id, callback.message.id, skip=skip)
        return True

    elif data.startswith("edit_series_library_msg_"):
        journey_id = int(data.split("_")[4])
        await callback.answer()
        ADMIN_STATES[user_id] = {"state": "waiting_for_series_library_msg", "message_id": callback.message.id, "data": {"journey_id": journey_id}}
        await callback.message.edit_text(
            "💬 **Edit Series Library Custom Message**\n\nEnter the custom display message to show above the series categories page. Send `none` to reset:\n\n❌ Send `/cancel` to abort.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"j_series_management_menu_{journey_id}")]])
        )
        return True

    elif data == "noop":
        await callback.answer()
        return True

    return False
