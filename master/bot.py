import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery

# Safe monkeypatching to prevent message modification exceptions from freezing the bot
from pyrogram.errors import MessageNotModified
_original_edit_text = Message.edit_text
_original_edit_reply_markup = Message.edit_reply_markup

async def _safe_edit_text(self, *args, **kwargs):
    try:
        return await _original_edit_text(self, *args, **kwargs)
    except MessageNotModified:
        return self

async def _safe_edit_reply_markup(self, *args, **kwargs):
    try:
        return await _original_edit_reply_markup(self, *args, **kwargs)
    except MessageNotModified:
        return self

Message.edit_text = _safe_edit_text
Message.edit_reply_markup = _safe_edit_reply_markup

import database
from config import OWNER_ID
from . import helpers as main_helpers
from .helpers import ADMIN_STATES
from .handlers import start_handler, cancel_handler, id_handler, explore_handler, master_available_series_handler, user_add_bot_handler

def register_main_bot_handlers(app: Client):
    main_helpers.main_bot_client = app

    @app.on_message(filters.private, group=-1)
    async def block_testing_messages(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return
        is_admin = await database.is_admin(user_id, OWNER_ID)
        if is_admin:
            return
        settings = await database.get_settings()
        if settings.get("testing_mode", False):
            await database.add_user(user_id, message.from_user.username or "", message.from_user.first_name or "")
            await message.reply_text(
                "⚠️ **Testing Mode Active**\n\n"
                "This bot is currently in user testing mode as we are adding new features. "
                "Once it is open, you can use it. Please come back and try again after some time."
            )
            message.stop_propagation()

    @app.on_callback_query(group=-1)
    async def block_testing_callbacks(client: Client, callback: CallbackQuery):
        user_id = callback.from_user.id if callback.from_user else None
        if not user_id:
            return
        is_admin = await database.is_admin(user_id, OWNER_ID)
        if is_admin:
            return
        settings = await database.get_settings()
        if settings.get("testing_mode", False):
            await callback.answer(
                "⚠️ This bot is currently in user testing mode as we are adding new features. "
                "Once it is open, you can use it. Please come back and try again after some time.",
                show_alert=True
            )
            callback.stop_propagation()

    # --- Message Command Handlers ---
    @app.on_message(filters.command("start") & filters.private)
    async def cmd_start(client: Client, message: Message):
        await start_handler(client, message)

    @app.on_message(filters.command("cancel") & filters.private)
    async def cmd_cancel(client: Client, message: Message):
        await cancel_handler(client, message)

    @app.on_message(filters.command("id") & filters.private)
    async def cmd_id(client: Client, message: Message):
        await id_handler(client, message)

    @app.on_message(filters.command("explorefiles") & filters.private)
    async def cmd_explore(client: Client, message: Message):
        await explore_handler(client, message)

    @app.on_message(filters.command("availableseries") & filters.private)
    async def cmd_avail_series(client: Client, message: Message):
        await master_available_series_handler(client, message)

    @app.on_message(filters.command(["addbot", "add_bot"]) & filters.private)
    async def cmd_addbot(client: Client, message: Message):
        await user_add_bot_handler(client, message)

    # --- Private Messages State Input Handler ---
    @app.on_message(filters.private & ~filters.command(["start", "cancel", "id", "explorefiles", "availableseries", "addbot", "add_bot"]))
    async def msg_state(client: Client, message: Message):
        user_id = message.from_user.id
        if user_id not in ADMIN_STATES:
            return

        state_data = ADMIN_STATES[user_id]
        state = state_data["state"]
        message_id = state_data.get("message_id")

        try:
            await message.delete()
        except Exception:
            pass

        from .states_admin import handle_admin_states
        if await handle_admin_states(client, message, state, state_data, message_id):
            return

        from .states_files import handle_files_states
        await handle_files_states(client, message, state, state_data, message_id)

    # --- Weekly Web Series Automation Handler ---
    from .automation import register_automation_handlers
    register_automation_handlers(app)

    # --- Callback Query Handler ---
    @app.on_callback_query()
    async def cb_query(client: Client, callback: CallbackQuery):
        user_id = callback.from_user.id
        is_user_admin = await database.is_admin(user_id, OWNER_ID)
        if not is_user_admin:
            return await callback.answer("❌ Access Denied.", show_alert=True)

        data = callback.data

        if user_id in ADMIN_STATES:
            if not (data.startswith("tree_add_type_") or data == "tree_cancel_btn" or data.startswith("reorder_toggle_") or data.startswith("reorder_confirm_") or data == "noop" or data.startswith("stop_bulk_add_")):
                state_data = ADMIN_STATES.pop(user_id, None)
                if state_data and "data" in state_data and state_data["data"].get("is_new_section"):
                    new_sec_id = state_data["data"]["section_id"]
                    asyncio.create_task(database.delete_section(new_sec_id))

        from .callbacks_config import handle_config_callbacks
        if await handle_config_callbacks(client, callback, data):
            return

        from .callbacks_admin import handle_admin_callbacks
        if await handle_admin_callbacks(client, callback, data):
            return

        from .callbacks_files import handle_files_callbacks
        if await handle_files_callbacks(client, callback, data):
            return

        from .callbacks_series import handle_series_callbacks
        await handle_series_callbacks(client, callback, data)
