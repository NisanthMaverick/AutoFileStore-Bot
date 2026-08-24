import json
import uuid
from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
import database
from config import API_ID, API_HASH
from .helpers import (
    ADMIN_STATES, log_admin_action
)
from .ui_config import show_btn_mgr, show_btn_details
from .ui_admin import show_manage_clones

async def handle_buttons_states(client: Client, message: Message, state: str, state_data: dict, message_id: int) -> bool:
    user_id = message.from_user.id

    # 1. Waiting for Custom Button Name
    if state == "waiting_for_btn_name":
        btn_name = message.text.strip()
        if not btn_name:
            return await message.reply_text("⚠️ Button name cannot be empty. Please enter button name:")
        
        ADMIN_STATES[user_id] = {
            "state": "waiting_for_btn_link",
            "message_id": message_id,
            "data": {"name": btn_name}
        }
        text = f"🔘 Button Name set to: **{btn_name}**\n\nNow send the **Button URL / Link** (must start with `http://` or `https://`):"
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="btn_mgr")]])
        if message_id:
            try:
                await client.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=text, reply_markup=markup)
                return True
            except Exception:
                pass
        await message.reply_text(text, reply_markup=markup)
        return True

    # 2. Waiting for Custom Button Link
    elif state == "waiting_for_btn_link":
        btn_link = message.text.strip()
        if not btn_link.startswith("http://") and not btn_link.startswith("https://"):
            return await message.reply_text("⚠️ Invalid URL! The link must start with `http://` or `https://`. Please send a valid link:")
        
        btn_name = state_data["data"]["name"]
        settings = await database.get_settings()
        buttons = json.loads(settings.get("custom_buttons", "[]"))
        buttons.append({"text": btn_name, "url": btn_link})
        await database.update_settings({"custom_buttons": json.dumps(buttons)})
        ADMIN_STATES.pop(user_id, None)
        
        if message_id:
            await show_btn_mgr(client, message.chat.id, message_id)
        else:
            await message.reply_text("✅ Button added!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Button Manager", callback_data="btn_mgr")]]))
        return True

    # 3. Waiting for Custom Button Link Edit
    elif state == "waiting_for_btn_edit_link":
        new_link = message.text.strip()
        if not new_link.startswith("http://") and not new_link.startswith("https://"):
            return await message.reply_text("⚠️ Invalid URL. The link must start with `http://` or `https://`. Please send a valid link:")
        
        idx = state_data["data"]["index"]
        settings = await database.get_settings()
        buttons_list = json.loads(settings.get("custom_buttons", "[]"))
        
        if 0 <= idx < len(buttons_list):
            buttons_list[idx]["url"] = new_link
            await database.update_settings({"custom_buttons": json.dumps(buttons_list)})
            ADMIN_STATES.pop(user_id, None)
            if message_id:
                await show_btn_details(client, message.chat.id, message_id, idx)
            else:
                await message.reply_text("✅ Button URL updated!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"btn_details_{idx}")]]))
        else:
            ADMIN_STATES.pop(user_id, None)
            if message_id:
                await show_btn_mgr(client, message.chat.id, message_id)
            else:
                await message.reply_text("❌ Invalid button index.")
        return True

    # 4. Waiting for Clone Bot Token
    elif state == "waiting_for_clone_token":
        token = message.text.strip()
        if message_id:
            try:
                await client.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=message_id,
                    text="⏳ **Validating token with Telegram API... Please wait.**"
                )
            except Exception:
                pass
        
        try:
            temp_client = Client(
                name=f"temp_validation_{uuid.uuid4().hex[:8]}",
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=token,
                in_memory=True
            )
            await temp_client.start()
            bot_me = await temp_client.get_me()
            await temp_client.stop()

            # Save clone bot in DB
            await database.add_clone_bot(token, bot_me.username, bot_me.first_name)
            
            # Start the clone bot process immediately
            from clones.tree import start_clone_bot
            started = await start_clone_bot(token)
            if started:
                await database.set_clone_bot_status(token, True)
                settings = await database.get_settings()
                if not settings.get("primary_clone_username"):
                    await database.update_settings({"primary_clone_username": bot_me.username})
                    
                ADMIN_STATES.pop(user_id, None)
                await log_admin_action(f"🛡️ **Clone Bot Added & Activated**: @{bot_me.username} ({bot_me.first_name}) by {message.from_user.mention}")
                
                is_user_admin = await database.is_admin(user_id, OWNER_ID)
                if is_user_admin:
                    if message_id:
                        await show_manage_clones(client, message.chat.id, message_id)
                    else:
                        await message.reply_text(f"✅ Clone Bot @{bot_me.username} added and started successfully!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Clones", callback_data="manage_clones")]]))
                else:
                    await message.reply_text(f"✅ Clone Bot @{bot_me.username} added, started, and deployed successfully!")
            else:
                raise ValueError("Valid token but failed to start the bot runner client.")
        except Exception as e:
            err_text = f"❌ Failed to start clone bot: {e}\n\nPlease check the token and send it again or send /cancel."
            if message_id:
                try:
                    await client.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=err_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="manage_clones")]]))
                except Exception:
                    await message.reply_text(err_text)
            else:
                await message.reply_text(err_text)
        return True

    return False
