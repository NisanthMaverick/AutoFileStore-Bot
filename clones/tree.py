import asyncio
from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import database
from .helpers import ACTIVE_CLONES
from config import API_ID, API_HASH

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

def format_sec_name_btn(name: str) -> str:
    parts = name.split('\n', 1)
    if len(parts) == 1:
        for emoji in ['📅', '🗓️', '🗓', '📆']:
            if emoji in name:
                p = name.split(emoji, 1)
                parts = [p[0].strip(), f"{emoji}{p[1]}"]
                break
    if len(parts) > 1 and parts[1]:
        return f"{parts[0]}\n{to_small_text(parts[1])}"
    return name

# Dynamic starting of Clone Bots
async def start_clone_bot(token: str) -> bool:
    if token in ACTIVE_CLONES:
        return True

    try:
        client = Client(
            name=f"clone_{token.split(':')[0]}",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=token,
            in_memory=False
        )

        # Import dynamically to avoid circular import issues
        from clone_bot import register_clone_handlers
        register_clone_handlers(client)
        
        await client.start()
        ACTIVE_CLONES[token] = client
        return True
    except Exception as e:
        print(f"Failed to start clone bot: {e}")
        return False

# Stop Clone Bot
async def stop_clone_bot(token: str):
    if token in ACTIVE_CLONES:
        client = ACTIVE_CLONES.pop(token)
        try:
            await client.stop()
        except Exception as e:
            print(f"Failed to stop clone bot gracefully: {e}")

async def show_user_tree(client: Client, chat_id: int, message_id: int, series_id: int, section_id: int = None, is_new_message: bool = False, library_skip: int = 0):
    from config import OWNER_ID

    async def _none():
        return None

    # --- Parallel fetch: series + sections + premium status + section info ---
    series, sections, is_user_premium, current_sec = await asyncio.gather(
        database.get_series(series_id),
        database.list_sections(series_id, parent_id=section_id),
        database.is_premium_user(chat_id, OWNER_ID),
        database.get_section(section_id) if section_id else _none()
    )

    if not series:
        text = "❌ Series not found."
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Categories", callback_data="cl_browse_series_0")]])
        if is_new_message:
            await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        else:
            try:
                await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
            except Exception:
                await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        return

    # Load Journey settings
    journey = None
    if series.get("journey_id"):
        journey = await database.get_journey(series["journey_id"])
    if not journey:
        journey = {
            "lock_buttons_enabled": False,
            "lock_active_series_enabled": False,
            "lock_old_series_enabled": True,
            "lock_day_based_enabled": False,
            "lock_time_window": 0,
            "lock_individual_enabled": False
        }

    # Check if series is locked (premium lock) and user is not premium
    is_locked_series = False
    if journey.get("is_locked", False):
        is_locked_series = True
    elif journey.get("lock_buttons_enabled", False):
        if not series.get("is_active", True) and journey.get("lock_old_series_enabled", True):
            is_locked_series = True
        elif journey.get("lock_individual_enabled", False) and series.get("is_locked", False):
            is_locked_series = True

    if is_locked_series and not is_user_premium:
        owner_username = None
        try:
            owner_user = await client.get_users(OWNER_ID)
            if owner_user and owner_user.username:
                owner_username = owner_user.username
        except Exception:
            pass
        contact_url = f"https://t.me/{owner_username}" if owner_username else f"tg://user?id={OWNER_ID}"
        
        text = (
            "🔒 **Premium Access Required**\n\n"
            "You are not a premium user to see old series/content.\n"
            "Please buy a subscription or contact the administrator if you have any issues."
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💳 Buy Subscription", url="https://t.me/SubscriptionTamilan_bot?start=plans"),
                InlineKeyboardButton("👨‍💻 Contact Admin", url=contact_url)
            ],
            [
                InlineKeyboardButton("🔄 Check Subscription", callback_data=f"cl_chk_sub_{series_id}_0")
            ],
            [
                InlineKeyboardButton("🔙 Back to Categories", callback_data=f"cl_journey_{series['journey_id'] or 0}_0")
            ]
        ])
        if is_new_message:
            await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        else:
            try:
                await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
            except Exception:
                await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        return

    custom_msg = None
    per_row = 2

    if section_id:
        if current_sec:
            custom_msg = current_sec.get("custom_msg")
            per_row = current_sec.get("buttons_per_row", 2)
    else:
        custom_msg = series.get("custom_msg")
        per_row = series.get("buttons_per_row", 2)

    if custom_msg and custom_msg.strip():
        text = custom_msg
    else:
        journey_name = journey.get("name", "Main Library") if journey else "Main Library"
        path_str = f"🗺️ **Home › {journey_name} › {series['title']}**"
        if section_id:
            sec_path = await database.get_section_path(section_id)
            path_str = f"🗺️ **Home › {journey_name} › {series['title']} › {sec_path}**"

        current_name = current_sec["name"].split('\n')[0] if (section_id and current_sec) else series["title"]
        text = f"{path_str}\n━━━━━━━━━━━━━━━━━━━━\n\n📁 Go inside to browse {current_name}:\n\n"
        if series.get('description') and not section_id:
            text += f"_{series['description']}_\n\n"

    buttons = []

    if sections:
        is_premium = is_user_premium
        lock_enabled = journey.get("lock_buttons_enabled", False)
        window = journey.get("lock_time_window", 0)
        latest_file_sec_id = None
        
        file_sections = [sec for sec in sections if sec.get("sec_type") == "files"]
        if file_sections:
            latest_file_sec_id = max(sec["id"] for sec in file_sections)

        row = []
        for s in sections:
            if s.get("sec_type") == "files":
                is_unlocked = True
                if lock_enabled and not is_premium:
                    if journey.get("lock_individual_enabled", False) and s.get("is_locked", False):
                        is_unlocked = False
                    else:
                        parent_series_active = series.get("is_active", True)
                        if journey.get("lock_individual_enabled", False) and series.get("is_locked", False):
                            is_unlocked = False
                        elif not parent_series_active:
                            if journey.get("lock_old_series_enabled", True):
                                is_unlocked = False
                        else:
                            if journey.get("lock_active_series_enabled", False):
                                if journey.get("lock_day_based_enabled", False):
                                    created_at = s.get("created_at")
                                    is_within_window = False
                                    if created_at and window > 0:
                                        from datetime import datetime
                                        age_hours = (datetime.utcnow() - created_at).total_seconds() / 3600.0
                                        if age_hours < window:
                                            is_within_window = True
                                    if not is_within_window:
                                        is_unlocked = False
                                else:
                                    if s["id"] != latest_file_sec_id:
                                        is_unlocked = False

                formatted_name = format_sec_name_btn(s['name'])
                if is_unlocked:
                    btn = InlineKeyboardButton(f"📥 {formatted_name}", callback_data=f"cl_send_sec_{series_id}_{s['id']}_{library_skip}")
                else:
                    btn = InlineKeyboardButton(f"🔒 {formatted_name}", callback_data=f"cl_locked_sec_{series_id}_{s['id']}_{library_skip}")
            else:
                # Folder section
                is_unlocked = True
                if lock_enabled and not is_premium:
                    if journey.get("lock_individual_enabled", False) and s.get("is_locked", False):
                        is_unlocked = False
                    elif journey.get("lock_individual_enabled", False) and series.get("is_locked", False):
                        is_unlocked = False
                        
                formatted_name = format_sec_name_btn(s['name'])
                if is_unlocked:
                    btn = InlineKeyboardButton(f"📁 {formatted_name}", callback_data=f"cl_tree_{series_id}_{s['id']}_{library_skip}")
                else:
                    btn = InlineKeyboardButton(f"🔒 {formatted_name}", callback_data=f"cl_locked_sec_{series_id}_{s['id']}_{library_skip}")
            
            row.append(btn)
            if len(row) == per_row:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
    else:
        if not custom_msg:
            text += "_Nothing here yet._\n"

    if section_id:
        parent_id = current_sec["parent_id"] if current_sec else None
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"cl_tree_{series_id}_{parent_id or 0}_{library_skip}")])
    else:
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"cl_journey_{series['journey_id'] or 0}_{library_skip}")])

    markup = InlineKeyboardMarkup(buttons)
    if is_new_message:
        try:
            await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        except Exception as e:
            print(f"Error sending text in show_user_tree: {e}")
    else:
        try:
            await client.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=markup
            )
        except Exception as e:
            print(f"Error editing message text in show_user_tree: {e}")
            try:
                await client.delete_messages(chat_id=chat_id, message_ids=[message_id])
            except Exception as del_err:
                print(f"Error deleting message in show_user_tree: {del_err}")
            try:
                await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
            except Exception as e:
                print(f"Error sending text in show_user_tree: {e}")
