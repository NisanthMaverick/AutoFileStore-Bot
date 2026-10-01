import uuid
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
import database
from .helpers import (
    ADMIN_STATES, log_admin_action, get_readable_size, get_back_button
)
from .ui_files import show_folder_management, show_series_browse, show_manage_series

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

async def handle_files_states(client: Client, message: Message, state: str, state_data: dict, message_id: int) -> bool:
    user_id = message.from_user.id

    # Delegate bulk add and markers states
    from .states_files_bulk import handle_bulk_states
    if await handle_bulk_states(client, message, state, state_data, message_id):
        return True

    # 1. Waiting for File Upload
    if state == "waiting_for_file":
        media = message.document or message.video or message.audio or message.photo
        if not media:
            if message_id:
                try:
                    await client.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=message_id,
                        text="⚠️ Please send a valid file (document, video, audio, or photo).\n\n❌ Send /cancel to abort.",
                        reply_markup=InlineKeyboardMarkup([get_back_button("manage_files")])
                    )
                    return True
                except Exception:
                    pass
            return await message.reply_text("⚠️ Please send a valid file. Use /cancel to exit.")

        settings = await database.get_settings()
        db_channel = settings.get("db_channel_id")
        if not db_channel:
            ADMIN_STATES.pop(user_id, None)
            if message_id:
                try:
                    await client.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=message_id,
                        text="❌ Error: DB Storage Channel is not configured. Configure it in 'Database Sync & Integrity' menu first.",
                        reply_markup=InlineKeyboardMarkup([get_back_button("manage_files")])
                    )
                    return True
                except Exception:
                    pass
            return await message.reply_text("❌ Error: DB Storage Channel is not configured.")

        if message_id:
            try:
                await client.edit_message_text(chat_id=message.chat.id, message_id=message_id, text="⏳ **Processing and storing file... Please wait.**")
            except Exception:
                pass

        try:
            copied_msg = await message.copy(chat_id=int(db_channel) if db_channel.startswith("-100") or db_channel.isdigit() else db_channel)
            file_name = getattr(media, "file_name", "Photo" if message.photo else "Media File")
            file_size = getattr(media, "file_size", 0)
            mime_type = getattr(media, "mime_type", "image/jpeg" if message.photo else "unknown")
            caption = message.caption or ""
            file_code = str(uuid.uuid4())[:8]
            
            await database.add_file(
                file_code=file_code,
                message_id=copied_msg.id,
                file_name=file_name,
                file_size=file_size,
                mime_type=mime_type,
                caption=caption
            )

            primary = settings.get("primary_clone_username")
            link_str = f"https://t.me/{primary}?start=file_{file_code}" if primary else f"`file_{file_code}` (Activate a clone bot to get full link)"
            
            ADMIN_STATES.pop(user_id, None)
            text = f"✅ **File stored successfully!**\n\n" \
                   f"📂 **File Name:** `{file_name}`\n" \
                   f"📦 **Size:** {get_readable_size(file_size)}\n" \
                   f"🔗 **Shareable Link:** {link_str}"
            
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Files", callback_data="manage_files")]])
            if message_id:
                try:
                    await client.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=text, reply_markup=markup, disable_web_page_preview=True)
                    return True
                except Exception:
                    pass
            await message.reply_text(text, reply_markup=markup, disable_web_page_preview=True)
        except Exception as e:
            ADMIN_STATES.pop(user_id, None)
            error_text = f"❌ Failed to store file: {e}"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Files", callback_data="manage_files")]])
            if message_id:
                try:
                    await client.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=error_text, reply_markup=markup)
                    return True
                except Exception:
                    pass
            await message.reply_text(error_text, reply_markup=markup)
        return True

    # 2. Waiting for Series Title
    elif state == "waiting_for_series_title":
        title = message.text.strip()
        if not title:
            await message.reply_text("⚠️ Title cannot be empty. Try again or send /cancel.")
            return True
        
        series_id = await database.create_series(title, "")
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"📂 **Series Created**: {title} (ID: {series_id}) by {message.from_user.mention}")
        
        if message_id:
            try:
                await show_manage_series(client, message.chat.id, message_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ Series '{title}' created successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Series Library", callback_data="manage_series")]]))
        return True

    # 2.5 Waiting for Journey Name
    elif state == "waiting_for_journey_name":
        name = message.text.strip()
        if not name:
            await message.reply_text("⚠️ Journey name cannot be empty. Try again or send /cancel.")
            return True
        
        ADMIN_STATES[user_id] = {
            "state": "waiting_for_journey_description",
            "message_id": message_id,
            "data": {"name": name}
        }
        await message.reply_text(
            f"📝 **Category Description**\n\nPlease enter a **Description** for the category/journey '{name}':\n\nType `/skip` or `none` to create it without a description.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="manage_series")]])
        )
        return True

    # 2.55 Waiting for Journey Description (during creation)
    elif state == "waiting_for_journey_description":
        name = state_data["data"]["name"]
        description = message.text.strip()
        if description.lower() in ["/skip", "none"]:
            description = ""
            
        journey_id = await database.create_journey(name, description)
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"🗺️ **Journey Created**: {name} (ID: {journey_id}) by {message.from_user.mention}")
        
        from .ui_files import show_manage_series
        if message_id:
            try:
                await show_manage_series(client, message.chat.id, message_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ Journey '{name}' created successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Journeys", callback_data="manage_series")]]))
        return True

    # 2.6 Waiting for Rename Journey
    elif state == "waiting_for_rename_journey":
        name = message.text.strip()
        if not name:
            await message.reply_text("⚠️ Journey name cannot be empty. Try again or send /cancel.")
            return True
        
        journey_id = state_data["data"]["journey_id"]
        await database.update_journey_settings(journey_id, name=name)
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"✏️ **Journey Renamed**: {name} (ID: {journey_id}) by {message.from_user.mention}")
        
        from .ui_files import show_journey_detail
        if message_id:
            try:
                await show_journey_detail(client, message.chat.id, message_id, journey_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ Journey renamed to '{name}' successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Journey", callback_data=f"manage_journey_{journey_id}")]]))
        return True

    # 2.65 Waiting for Journey Description Edit
    elif state == "waiting_for_journey_description_edit":
        description = message.text.strip()
        journey_id = state_data["data"]["journey_id"]
        return_to = state_data["data"].get("return_to")
        if description.lower() == "none":
            description = ""
            
        await database.update_journey_settings(journey_id, description=description)
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"📝 **Journey Description Updated**: (ID: {journey_id}) by {message.from_user.mention}")
        
        if return_to == "library_msg":
            from .ui_files import show_edit_library_message_menu
            if message_id:
                try:
                    await show_edit_library_message_menu(client, message.chat.id, message_id)
                    return True
                except Exception:
                    pass
            await message.reply_text(f"✅ Journey description updated successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="edit_library_msg_opt")]]))
            return True
            
        from .ui_files import show_journey_detail
        if message_id:
            try:
                await show_journey_detail(client, message.chat.id, message_id, journey_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ Journey description updated successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Journey", callback_data=f"manage_journey_{journey_id}")]]))
        return True

    # 2.66 Waiting for Library Welcome Message
    elif state == "waiting_for_library_welcome_msg":
        welcome = message.text.strip()
        if welcome.lower() == "none":
            welcome = ""
            
        await database.update_settings({"series_library_custom_msg": welcome})
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"💬 **Library Welcome Message Updated** by {message.from_user.mention}")
        
        from .ui_files import show_manage_series
        if message_id:
            try:
                await show_manage_series(client, message.chat.id, message_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ Library welcome message updated successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Library", callback_data="manage_series")]]))
        return True

    # 2.7 Waiting for Series Title (in Journey)
    elif state == "waiting_for_series_title_j":
        title = message.text.strip()
        if not title:
            await message.reply_text("⚠️ Title cannot be empty. Try again or send /cancel.")
            return True
        
        journey_id = state_data["data"]["journey_id"]
        series_id = await database.create_series(title, "", journey_id=journey_id)
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"📂 **Series Created**: {title} (ID: {series_id}) in Journey {journey_id} by {message.from_user.mention}")
        
        from .ui_files import show_manage_series_journey
        if message_id:
            try:
                await show_manage_series_journey(client, message.chat.id, message_id, journey_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ Series '{title}' created successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Series Library", callback_data=f"list_j_series_{journey_id}_0")]]))
        return True

    # 2.85 Waiting for Series Source Channel Config
    elif state == "waiting_for_series_channel":
        text_val = message.text.strip().lower() if message.text else ""
        series_id = state_data["data"]["series_id"]
        library_skip = state_data["data"]["library_skip"]
        
        if text_val in ["none", "reset", "remove"]:
            await database.update_series_settings(series_id, source_channel_id="none")
            ADMIN_STATES.pop(user_id, None)
            
            success_text = "✅ **Source Channel configuration cleared!**"
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]])
            await message.reply_text(success_text, reply_markup=markup)
            return True
            
        channel_id = None
        channel_title = "Channel"
        
        if message.forward_from_chat:
            channel_id = message.forward_from_chat.id
            channel_title = message.forward_from_chat.title or "Channel"
        else:
            pasted = message.text.strip()
            if pasted.startswith("-100") or pasted.isdigit():
                try:
                    chat = await client.get_chat(int(pasted))
                    channel_id = chat.id
                    channel_title = chat.title or "Channel"
                except Exception:
                    channel_id = int(pasted)
            elif pasted.startswith("@") or pasted.isalnum():
                try:
                    chat = await client.get_chat(pasted)
                    channel_id = chat.id
                    channel_title = chat.title or "Channel"
                except Exception as e:
                    return await message.reply_text(f"❌ Could not find chat: {e}. Please forward a message from the channel or verify the ID/username.")
                    
        if not channel_id:
            return await message.reply_text("❌ Invalid input. Please forward a message from the channel, or paste the channel ID (e.g. `-100...`) or username (e.g. `@channel`).")
            
        try:
            member = await client.get_chat_member(channel_id, "me")
            if member.status not in ["administrator", "owner"]:
                await message.reply_text("⚠️ Warning: The bot is in the chat but does not seem to be an Administrator. Please promote the bot to Administrator in the channel!")
        except Exception as e:
            await message.reply_text(f"⚠️ Warning: Bot could not verify admin rights in the channel ({e}). Make sure the bot is an Administrator in the channel!")
            
        await database.update_series_settings(series_id, source_channel_id=str(channel_id))
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"📢 **Series Source Channel Configured**: {channel_title} (`{channel_id}`) for Series ID {series_id} by {message.from_user.mention}")
        
        success_text = f"✅ **Source Channel configured successfully!**\n\n📢 **Channel:** {channel_title}\n🆔 **ID:** `{channel_id}`"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]])
        await message.reply_text(success_text, reply_markup=markup)
        return True

    # 2.8 Waiting for Journey Unlock Duration
    elif state == "waiting_for_j_unlock_duration":
        val = message.text.strip().lower()
        journey_id = state_data["data"]["journey_id"]
        if val in ["0", "no", "disable", "none"]:
            hours = 0
        else:
            import re
            match = re.match(r"^(\d+)\s*(h|d)?$", val)
            if not match:
                return await message.reply_text(
                    "⚠️ Invalid duration format. Please enter a number followed by `h` (hours) or `d` (days).\n"
                    "Examples: `12h`, `2d`, or type `0` to disable duration lock."
                )
            num = int(match.group(1))
            unit = match.group(2) or "h"
            if unit == "d":
                hours = num * 24
            else:
                hours = num
                
        await database.update_journey_settings(journey_id, lock_time_window=hours)
        ADMIN_STATES.pop(user_id, None)
        
        if hours == 0:
            feedback_str = "Unlock duration disabled (only the latest content stays unlocked)."
        elif hours % 24 == 0:
            feedback_str = f"Unlock duration set to {hours // 24} day(s)."
        else:
            feedback_str = f"Unlock duration set to {hours} hour(s)."
            
        await log_admin_action(f"🔒 **Lock Duration Updated** for Journey {journey_id}: `{feedback_str}` by {message.from_user.mention}")
        
        from .ui_files import show_journey_lock_settings
        if message_id:
            try:
                await show_journey_lock_settings(client, message.chat.id, message_id, journey_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ {feedback_str}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Locks Settings", callback_data=f"j_lock_settings_{journey_id}")]]))
        return True

    # 2.9 Waiting for Journey DB Channel ID
    elif state == "waiting_for_j_db_channel":
        val = message.text.strip()
        journey_id = state_data["data"]["journey_id"]
        
        if val.lower() in ["none", "default"]:
            db_channel_id = ""
            feedback = "Journey DB Channel reset to Default settings."
        else:
            if not val.startswith("-100") or not val[4:].isdigit():
                if not (val.startswith("-") and val[1:].isdigit()) and not val.isdigit():
                    await message.reply_text("⚠️ Invalid Channel ID format. Numerical ID starting with `-100` expected. Try again or send /cancel.")
                    return True
            db_channel_id = val
            feedback = f"Journey DB Channel set to `{db_channel_id}`."
            
        await database.update_journey_settings(journey_id, db_channel_id=db_channel_id)
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"📁 **Journey DB Channel Updated** (ID: {journey_id}): `{feedback}` by {message.from_user.mention}")
        
        origin = state_data["data"].get("origin")
        skip = state_data["data"].get("skip", 0)
        
        if origin == "list":
            from .ui_admin import show_journey_db_channels
            if message_id:
                try:
                    await show_journey_db_channels(client, message.chat.id, message_id, skip)
                    return True
                except Exception:
                    pass
            await message.reply_text(f"✅ {feedback}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Journey DBs", callback_data=f"manage_j_db_channels_{skip}")]]))
            return True
        else:
            from .ui_files import show_journey_detail
            if message_id:
                try:
                    await show_journey_detail(client, message.chat.id, message_id, journey_id)
                    return True
                except Exception:
                    pass
            await message.reply_text(f"✅ {feedback}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Journey", callback_data=f"manage_journey_{journey_id}")]]))
            return True

    # 2.10 Waiting for Journey Update Channel ID
    elif state == "waiting_for_j_update_channel":
        val = message.text.strip()
        journey_id = state_data["data"]["journey_id"]
        
        if val.lower() in ["none", "disable", "off", "reset"]:
            update_channel_id = ""
            feedback = "Journey Episode Update Alerts disabled."
        else:
            if not val.startswith("-100") or not val[4:].isdigit():
                if not (val.startswith("-") and val[1:].isdigit()) and not val.isdigit():
                    await message.reply_text("⚠️ Invalid Channel ID format. Numerical ID starting with `-100` expected. Try again or send /cancel.")
                    return True
            update_channel_id = val
            feedback = f"Journey Episode Update Channel set to `{update_channel_id}`."
            
        await database.update_journey_settings(journey_id, update_channel_id=update_channel_id)
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"📢 **Journey Update Channel Set** (ID: {journey_id}): `{feedback}` by {message.from_user.mention}")
        
        from .ui_files import show_journey_detail
        if message_id:
            try:
                await show_journey_detail(client, message.chat.id, message_id, journey_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ {feedback}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Journey", callback_data=f"manage_journey_{journey_id}")]]))
        return True

    # 2.11 Waiting for Journey Update Message Template
    elif state == "waiting_for_j_update_template":
        val = message.text.strip()
        journey_id = state_data["data"]["journey_id"]
        
        if val.lower() == "default":
            update_msg_template = "{series_name} latest episode ({date}) updated ✅\n\nBot : @{bot_username}"
            feedback = "Update Notification Template reset to Default."
        else:
            update_msg_template = val
            feedback = f"Update Notification Template updated."
            
        await database.update_journey_settings(journey_id, update_msg_template=update_msg_template)
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"💬 **Journey Update Template Set** (ID: {journey_id}) by {message.from_user.mention}")
        
        from .ui_files import show_journey_detail
        if message_id:
            try:
                await show_journey_detail(client, message.chat.id, message_id, journey_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ {feedback}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Journey", callback_data=f"manage_journey_{journey_id}")]]))
        return True

    # 2.12 Waiting for Journey Button Name Template
    elif state == "waiting_for_j_button_template":
        val = message.text.strip()
        journey_id = state_data["data"]["journey_id"]
        
        if val.lower() == "default":
            button_name_template = "📥 Ep ({start} - {end}) {date_small}"
            feedback = "Button Format Template reset to Default (`📥 Ep ({start} - {end}) {date_small}`)."
        else:
            button_name_template = val
            feedback = f"Button Format Template updated."
            
        await database.update_journey_settings(journey_id, button_name_template=button_name_template)
        ADMIN_STATES.pop(user_id, None)
        await log_admin_action(f"🔘 **Journey Button Template Set** (ID: {journey_id}) by {message.from_user.mention}")
        
        from .ui_files import show_journey_detail
        if message_id:
            try:
                await show_journey_detail(client, message.chat.id, message_id, journey_id)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ {feedback}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Journey", callback_data=f"manage_journey_{journey_id}")]]))
        return True

    # 4. Waiting for Tree Folder Name
    elif state == "waiting_for_tree_folder_name":
        raw_text = message.text.strip()
        if not raw_text:
            await message.reply_text("⚠️ Folder name cannot be empty. Try again or send /cancel.")
            return True
        
        parts = [p.strip() for p in raw_text.split(',', 1)]
        if len(parts) > 1 and parts[1]:
            name = f"{parts[0]}\n{parts[1]}"
        else:
            name = parts[0]
        
        series_id = state_data["data"]["series_id"]
        parent_folder_id = state_data["data"]["parent_folder_id"]
        library_skip = state_data["data"].get("library_skip", 0)
        parent_id = parent_folder_id if parent_folder_id > 0 else None
        
        await database.create_section(name, series_id, parent_id=parent_id, sec_type="folder")
        ADMIN_STATES.pop(user_id, None)
        
        if message_id:
            try:
                # show browse view
                await show_series_browse(client, message.chat.id, message_id, series_id, parent_folder_id if parent_folder_id > 0 else None, library_skip=library_skip)
                return True
            except Exception:
                pass
        await message.reply_text(f"✅ Folder '{name}' created successfully!")
        return True

    # 5. Waiting for Tree File Button Name
    elif state == "waiting_for_tree_file_btn_name":
        raw_text = message.text.strip()
        if not raw_text:
            await message.reply_text("⚠️ Button/File name cannot be empty. Try again or send /cancel.")
            return True

        parts = [p.strip() for p in raw_text.split(',', 1)]
        if len(parts) > 1 and parts[1]:
            name = f"{parts[0]}\n{parts[1]}"
        else:
            name = parts[0]

        series_id = state_data["data"]["series_id"]
        parent_folder_id = state_data["data"]["parent_folder_id"]
        library_skip = state_data["data"].get("library_skip", 0)
        parent_id = parent_folder_id if parent_folder_id > 0 else None
        
        new_sec_id = await database.create_section(name, series_id, parent_id=parent_id, sec_type="files")

        ADMIN_STATES[user_id]["state"] = "waiting_for_tree_file_links"
        ADMIN_STATES[user_id]["data"]["section_id"] = new_sec_id
        ADMIN_STATES[user_id]["data"]["file_name"] = name
        ADMIN_STATES[user_id]["data"]["is_new_section"] = True
        ADMIN_STATES[user_id]["data"]["clear_before"] = True
        ADMIN_STATES[user_id]["data"]["library_skip"] = library_skip

        text = (
            f"📥 **{name}** — Import Files\n\n"
            "Please **forward a message** or send the **Telegram message link(s)** to import files.\n\n"
            "**Format Guidelines:**\n"
            "• **Single Link:** Paste a single link:\n"
            "  `https://t.me/c/12345/100` or `(https://t.me/c/12345/100)`\n"
            "• **Range of Links:** Paste first and last links with a space:\n"
            "  `https://t.me/c/12345/100 https://t.me/c/12345/110` or `(https://t.me/c/12345/100 https://t.me/c/12345/110)`\n"
            "• **Multiple Ranges:** Separate multiple links or ranges with a `+` symbol:\n"
            "  `link1 + (link2 link3) + link4`\n\n"
            "❌ Send `/cancel` to abort."
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="tree_cancel_btn")]])
        
        if message_id:
            try:
                await client.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=text, reply_markup=markup)
                return True
            except Exception:
                pass
        await message.reply_text(text, reply_markup=markup)
        return True

    # 6. Waiting for Rename Folder / Section Name
    elif state == "waiting_for_rename_sec":
        raw_text = message.text.strip()
        parts = [p.strip() for p in raw_text.split(',')]
        if len(parts) >= 3:
            new_name = f"{parts[0]} ({parts[1]})\n[{parts[2]}]"
        elif len(parts) == 2:
            new_name = f"{parts[0]}\n{parts[1]}"
        else:
            split_done = False
            for emoji in ['📅', '🗓️', '🗓', '📆']:
                if emoji in raw_text:
                    p = raw_text.split(emoji, 1)
                    new_name = f"{p[0].strip()}\n{emoji}{p[1]}"
                    split_done = True
                    break
            if not split_done:
                new_name = raw_text
        series_id = state_data["data"]["series_id"]
        section_id = state_data["data"]["section_id"]
        library_skip = state_data["data"].get("library_skip", 0)
        orig_msg_id = state_data.get("message_id")
        
        # Fetch section type before rename to know where to redirect
        sec = await database.get_section(section_id)
        is_files = sec and sec.get("sec_type") == "files"
        
        updated = await database.update_section(section_id, new_name)
        ADMIN_STATES.pop(user_id, None)
        
        if updated and sec:
            sec["name"] = new_name
        
        if updated:
            if orig_msg_id:
                if is_files:
                    from .ui_files import show_filesec_actions
                    _, total_files = await database.list_files(skip=0, limit=1, series_id=series_id, section_id=section_id)
                    await show_filesec_actions(client, message.chat.id, orig_msg_id, series_id, section_id, sec, total_files, library_skip=library_skip)
                else:
                    await show_folder_management(client, message.chat.id, orig_msg_id, series_id, section_id, library_skip=library_skip)
            else:
                back_cb = f"filesec_act_{series_id}_{section_id}_{library_skip}" if is_files else f"manage_folder_opt_{series_id}_{section_id}_{library_skip}"
                await message.reply_text(f"✅ Renamed successfully to **{format_sec_name_inline(new_name)}**!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=back_cb)]]))
        else:
            back_cb = f"filesec_act_{series_id}_{section_id}_{library_skip}" if is_files else f"manage_folder_opt_{series_id}_{section_id}_{library_skip}"
            if orig_msg_id:
                await client.edit_message_text(chat_id=message.chat.id, message_id=orig_msg_id, text="❌ Failed to rename section.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=back_cb)]]))
            else:
                await message.reply_text("❌ Failed to rename section.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=back_cb)]]))
        return True

    # 7. Waiting for Folder Custom Message
    elif state == "waiting_for_folder_msg":
        new_msg = message.text.strip()
        series_id = state_data["data"]["series_id"]
        section_id = state_data["data"]["section_id"]
        library_skip = state_data["data"].get("library_skip", 0)
        
        if section_id == 0:
            await database.update_series_settings(series_id, custom_msg=new_msg)
        else:
            await database.update_section_settings(section_id, custom_msg=new_msg)
            
        ADMIN_STATES.pop(user_id, None)
        if message_id:
            await show_folder_management(client, message.chat.id, message_id, series_id, section_id, library_skip=library_skip)
        else:
            await message.reply_text("✅ Custom message updated successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Management", callback_data=f"manage_folder_opt_{series_id}_{section_id}_{library_skip}")]]))
        return True
    # 8. Waiting for Rename Series Title
    elif state == "waiting_for_rename_series":
        new_title = message.text.strip()
        series_id = state_data["data"]["series_id"]
        library_skip = state_data["data"].get("library_skip", 0)
        
        if not new_title:
            text = "⚠️ Title cannot be empty. Please send a valid title or send /cancel."
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]])
            if message_id:
                try:
                    await client.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=text, reply_markup=markup)
                    return True
                except Exception:
                    pass
            await message.reply_text(text, reply_markup=markup)
            return True
            
        await database.update_series_settings(series_id, title=new_title)
        ADMIN_STATES.pop(user_id, None)
        
        if message_id:
            await show_folder_management(client, message.chat.id, message_id, series_id, 0, library_skip=library_skip)
        else:
            await message.reply_text("✅ Series renamed successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Management", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")]]))
        return True

    return False
