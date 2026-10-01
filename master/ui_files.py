from pyrogram import Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import database
from .helpers import get_back_button

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

async def show_folder_management(client: Client, chat_id: int, message_id: int, series_id: int, section_id: int = 0, library_skip: int = 0):
    series = await database.get_series(series_id)
    if not series:
        try:
            if message_id:
                await client.edit_message_text(chat_id=chat_id, message_id=message_id, text="❌ Series not found.", reply_markup=InlineKeyboardMarkup([get_back_button(f"manage_series_skip_{library_skip}")]))
            else:
                await client.send_message(chat_id=chat_id, text="❌ Series not found.", reply_markup=InlineKeyboardMarkup([get_back_button(f"manage_series_skip_{library_skip}")]))
        except Exception:
            pass
        return

    is_root = (section_id == 0)
    current_sec = None
    if not is_root:
        current_sec = await database.get_section(section_id)
        if not current_sec:
            try:
                if message_id:
                    await client.edit_message_text(chat_id=chat_id, message_id=message_id, text="❌ Folder not found.", reply_markup=InlineKeyboardMarkup([InlineKeyboardButton("🔙 Back to Series", callback_data=f"browse_sec_{series_id}_0_{library_skip}")]))
                else:
                    await client.send_message(chat_id=chat_id, text="❌ Folder not found.", reply_markup=InlineKeyboardMarkup([InlineKeyboardButton("🔙 Back to Series", callback_data=f"browse_sec_{series_id}_0_{library_skip}")]))
            except Exception:
                pass
            return

    if is_root:
        name = series["title"]
        custom_msg = series.get("custom_msg")
        buttons_per_row = series.get("buttons_per_row", 2)
        custom_pic = series.get("custom_pic")
        type_str = "Series (Root)"
    else:
        name = format_sec_name_inline(current_sec["name"])
        custom_msg = current_sec.get("custom_msg")
        buttons_per_row = current_sec.get("buttons_per_row", 2)
        type_str = "Folder"

    custom_msg_status = custom_msg if custom_msg else "Default (Breadcrumbs / Description)"
    is_locked_val = series.get("is_locked", False) if is_root else current_sec.get("is_locked", False)
    locked_status_str = "Enabled 🔒 (Premium Required)" if is_locked_val else "Disabled 🔓"
    
    if is_root:
        src_chan = series.get("source_channel_id")
        src_chan_status = f"`{src_chan}`" if src_chan else "_None configured_"
        text = (
            f"⚙️ **{type_str} Settings: {name}**\n\n"
            f"💬 **Custom Message:**\n`{custom_msg_status}`\n\n"
            f"🔢 **Buttons per Row:** `{buttons_per_row}`\n\n"
            f"🔒 **Individual Lock:** `{locked_status_str}`\n\n"
            f"📢 **Source Channel:** {src_chan_status}\n\n"
            "Configure folder settings or perform administrative actions below:"
        )
    else:
        text = (
            f"⚙️ **{type_str} Settings: {name}**\n\n"
            f"💬 **Custom Message:**\n`{custom_msg_status}`\n\n"
            f"🔢 **Buttons per Row:** `{buttons_per_row}`\n\n"
            f"🔒 **Individual Lock:** `{locked_status_str}`\n\n"
            "Configure folder settings or perform administrative actions below:"
        )

    buttons_list = [
        [
            InlineKeyboardButton("💬 Edit Message", callback_data=f"edit_sec_msg_{series_id}_{section_id}_{library_skip}"),
            InlineKeyboardButton("🔢 Buttons Per Row", callback_data=f"edit_sec_cols_{series_id}_{section_id}_{library_skip}")
        ],
        [
            InlineKeyboardButton("✏️ Rename", callback_data=f"rename_series_opt_{series_id}_{library_skip}" if is_root else f"rename_sec_{series_id}_{section_id}_{library_skip}"),
            InlineKeyboardButton("🗑 Delete", callback_data=f"tree_del_series_{series_id}_{library_skip}" if is_root else f"tree_del_sec_{series_id}_{section_id}_{library_skip}")
        ],
        [
            InlineKeyboardButton("🔓 Disable Individual Lock" if is_locked_val else "🔒 Enable Individual Lock", callback_data=f"toggle_indiv_lock_{series_id}_{section_id}_{library_skip}")
        ]
    ]

    if is_root:
        buttons_list.append([
            InlineKeyboardButton("📢 Channel Config", callback_data=f"config_series_channel_{series_id}_{library_skip}"),
            InlineKeyboardButton("🔍 Scan Channel", callback_data=f"scan_mode_choose_{series_id}_{library_skip}")
        ])
        buttons_list.append([
            InlineKeyboardButton("🗑 Delete Entire Series", callback_data=f"delete_series_confirm_{series_id}_{library_skip}")
        ])

    if not is_root:
        buttons_list.append([
            InlineKeyboardButton("📂 Move Folder", callback_data=f"move_folder_select_{series_id}_{section_id}_{library_skip}_0")
        ])

    buttons_list.append([
        InlineKeyboardButton("🔙 Back to Folder", callback_data=f"browse_sec_{series_id}_{section_id}_{library_skip}")
    ])

    markup = InlineKeyboardMarkup(buttons_list)

    try:
        if message_id:
            await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
        else:
            await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    except Exception as e:
        print(f"Error editing message in show_folder_management: {e}")
        try:
            if message_id:
                await client.delete_messages(chat_id=chat_id, message_ids=[message_id])
        except Exception as del_err:
            print(f"Error deleting message in show_folder_management: {del_err}")
        try:
            await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        except Exception as send_err:
            print(f"Error sending message in show_folder_management: {send_err}")

async def show_series_browse(client: Client, chat_id: int, message_id: int, series_id: int, section_id: int = None, library_skip: int = 0):
    series = await database.get_series(series_id)
    if not series:
        try:
            if message_id:
                await client.edit_message_text(chat_id=chat_id, message_id=message_id, text="Series not found.", reply_markup=InlineKeyboardMarkup([get_back_button(f"manage_series_skip_{library_skip}")]))
            else:
                await client.send_message(chat_id=chat_id, text="Series not found.", reply_markup=InlineKeyboardMarkup([get_back_button(f"manage_series_skip_{library_skip}")]))
        except Exception:
            pass
        return

    current_sec = None
    if section_id:
        current_sec = await database.get_section(section_id)

    sections = await database.list_sections(series_id, parent_id=section_id)

    if section_id:
        custom_msg = current_sec.get("custom_msg") if current_sec else None
    else:
        custom_msg = series.get("custom_msg")

    if custom_msg and custom_msg.strip():
        text = custom_msg
    else:
        path_str = f"🎬 **Series:** {series['title']}"
        if section_id:
            sec_path = await database.get_section_path(section_id)
            path_str += f" › {sec_path}"

        text = f"{path_str}\n"
        desc = series.get('description', '')
        if desc and desc.strip() and desc.strip().lower() != 'none' and not section_id:
            text += f"_{desc.strip()}_\n"
        text += "\n"

    per_row = 2
    if section_id:
        if current_sec:
            per_row = current_sec.get("buttons_per_row", 2)
    else:
        per_row = series.get("buttons_per_row", 2)

    buttons = []

    if sections:
        row = []
        for s in sections:
            formatted_name = format_sec_name_btn(s['name'])
            if s.get("sec_type") == "files":
                btn = InlineKeyboardButton(f"📥 {formatted_name}", callback_data=f"filesec_act_{series_id}_{s['id']}_{library_skip}")
            else:
                btn = InlineKeyboardButton(f"📁 {formatted_name}", callback_data=f"browse_sec_{series_id}_{s['id']}_{library_skip}")
            row.append(btn)
            if len(row) == per_row:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
    else:
        if not custom_msg:
            text += "_This folder is empty._\n"

    buttons.append([
        InlineKeyboardButton("➕ Add Button", callback_data=f"tree_add_btn_{series_id}_{section_id or 0}_{library_skip}"),
        InlineKeyboardButton("📦 Bulk Add", callback_data=f"tree_bulk_add_{series_id}_{section_id or 0}_{library_skip}")
    ])
    
    if section_id:
        buttons.append([
            InlineKeyboardButton("⚙️ Folder Management", callback_data=f"manage_folder_opt_{series_id}_{section_id}_{library_skip}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("⚙️ Series Management", callback_data=f"manage_folder_opt_{series_id}_0_{library_skip}")
        ])

    if section_id:
        parent_id = current_sec["parent_id"] if current_sec else None
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"browse_sec_{series_id}_{parent_id or 0}_{library_skip}")])
    else:
        journey_id = series.get("journey_id")
        if journey_id:
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"list_j_series_{journey_id}_{library_skip}")])
        else:
            buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"manage_series_skip_{library_skip}")])

    markup = InlineKeyboardMarkup(buttons)
    try:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error editing message text in show_series_browse: {e}")
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=[message_id])
        except Exception as del_err:
            print(f"Error deleting message in show_series_browse: {del_err}")
        try:
            await client.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup
            )
        except Exception as e:
            print(f"Error sending text in show_series_browse: {e}")

async def show_manage_series(client: Client, chat_id: int, message_id: int, skip: int = 0):
    journeys = await database.list_journeys()
    settings = await database.get_settings()
    library_msg = settings.get("series_library_custom_msg")
    library_msg_status = library_msg if library_msg else "Default (None)"
    
    limit = 5
    text = "🗺️ **Journeys & Categories Library**\n\n" \
           f"💬 **Library Welcome Msg:**\n`{library_msg_status}`\n\n" \
           "Select a journey/category to manage its series and access controls:\n\n"
    buttons = []
    
    sliced_list = journeys[skip:skip+limit]
    if not sliced_list:
        text += "_No journeys created yet._"
    else:
        for j in sliced_list:
            text += f"▪️ **{j['name']}**\n"
            buttons.append([
                InlineKeyboardButton(f"🗺️ {j['name']}", callback_data=f"manage_journey_{j['id']}")
            ])
            
    pag_row = []
    if skip > 0:
        pag_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"manage_series_skip_{max(0, skip - limit)}"))
    if skip + limit < len(journeys):
        pag_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"manage_series_skip_{skip + limit}"))
    if pag_row:
        buttons.append(pag_row)
        
    buttons.append([
        InlineKeyboardButton("➕ Create Journey", callback_data="create_journey_opt"),
        InlineKeyboardButton("💬 Message", callback_data="edit_library_msg_opt")
    ])
    buttons.append(get_back_button("main_panel"))
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        print(f"Error rendering show_manage_series (Journeys): {e}")

async def show_journey_detail(client: Client, chat_id: int, message_id: int, journey_id: int):
    journey = await database.get_journey(journey_id)
    if not journey:
        try:
            await client.edit_message_text(chat_id=chat_id, message_id=message_id, text="❌ Journey not found.", reply_markup=InlineKeyboardMarkup([get_back_button("manage_series")]))
        except Exception:
            pass
        return
        
    lock_status = "Enabled ✅" if journey["lock_buttons_enabled"] else "Disabled ❌"
    active_lock = "Enabled ✅" if journey["lock_active_series_enabled"] else "Disabled ❌"
    old_lock = "Enabled ✅" if journey["lock_old_series_enabled"] else "Disabled ❌"
    indiv_lock = "Enabled ✅" if journey["lock_individual_enabled"] else "Disabled ❌"
    up_chan = journey.get("update_channel_id")
    up_chan_status = f"`{up_chan}`" if up_chan else "_Disabled / Not Configured_ ❌"
    
    up_tmpl = journey.get("update_msg_template") or "{series_name} latest episode ({date}) updated ✅\n\nBot : @{bot_username}"
    btn_tmpl = journey.get("button_name_template") or "📥 Ep ({start} - {end}) {date_small}"
    
    desc = journey.get("description") or "_No description set._"
    text = (
        f"🗺️ **Journey Details: {journey['name']}**\n━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Description:**\n{desc}\n\n"
        f"🔒 **Access Control Summary:**\n"
        f"• **Master Switch:** {lock_status}\n"
        f"• **Lock Active Series:** {active_lock}\n"
        f"• **Lock Old Series:** {old_lock}\n"
        f"• **Individual Locks:** {indiv_lock}\n\n"
        f"📁 **DB Storage Channel:**\n"
        f"• **Channel ID:** {db_status}\n\n"
        f"📢 **Episode Update Alerts:**\n"
        f"• **Channel ID:** {up_chan_status}\n"
        f"• **Msg Template:** `{up_tmpl}`\n"
        f"• **Button Template:** `{btn_tmpl}`\n\n"
        f"Select an administrative option below:"
    )
    
    buttons = [
        [
            InlineKeyboardButton("🎬 View Series Library", callback_data=f"list_j_series_{journey_id}_0"),
            InlineKeyboardButton("➕ Create Series", callback_data=f"create_series_j_{journey_id}")
        ],
        [
            InlineKeyboardButton("🔒 Access Lock Settings", callback_data=f"j_lock_settings_{journey_id}"),
            InlineKeyboardButton("📁 Configure DB Channel", callback_data=f"config_j_db_{journey_id}")
        ],
        [
            InlineKeyboardButton("📢 Update Channel", callback_data=f"config_j_up_chan_{journey_id}"),
            InlineKeyboardButton("💬 Update Msg Template", callback_data=f"config_j_up_tmpl_{journey_id}")
        ],
        [
            InlineKeyboardButton("🔘 Button Format Template", callback_data=f"config_j_btn_tmpl_{journey_id}")
        ],
        [
            InlineKeyboardButton("✏️ Rename Journey", callback_data=f"rename_journey_opt_{journey_id}"),
            InlineKeyboardButton("📝 Edit Description", callback_data=f"edit_journey_desc_opt_{journey_id}")
        ],
        [
            InlineKeyboardButton("🗑 Delete Journey", callback_data=f"delete_journey_opt_{journey_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="manage_series")
        ]
    ]
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        print(f"Error rendering show_journey_detail: {e}")

async def show_manage_series_journey(client: Client, chat_id: int, message_id: int, journey_id: int, skip: int = 0):
    journey = await database.get_journey(journey_id)
    if not journey:
        return await show_manage_series(client, chat_id, message_id)
        
    settings = await database.get_settings()
    limit = settings.get("series_buttons_per_page", 5)
    
    series_list = await database.list_series(journey_id=journey_id)
    text = f"🎬 **Video Series Library — {journey['name']}**\n\nSelect a series to browse/configure:\n\n"
    buttons = []
    
    sliced_list = series_list[skip:skip+limit]
    if not sliced_list:
        text += "_No series created yet in this journey or page is empty._"
    else:
        for s in sliced_list:
            buttons.append([
                InlineKeyboardButton(f"🎬 {s['title']}", callback_data=f"browse_sec_{s['id']}_0_{skip}")
            ])
            
    pag_row = []
    if skip > 0:
        pag_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"list_j_series_{journey_id}_{max(0, skip - limit)}"))
    if skip + limit < len(series_list):
        pag_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"list_j_series_{journey_id}_{skip + limit}"))
    if pag_row:
        buttons.append(pag_row)
    
    buttons.append([
        InlineKeyboardButton("⚙️ Series Management", callback_data=f"j_series_management_menu_{journey_id}")
    ])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"manage_journey_{journey_id}")])
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        print(f"Error rendering show_manage_series_journey: {e}")
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=[message_id])
        except Exception as del_err:
            print(f"Error deleting message in show_manage_series_journey: {del_err}")
        try:
            await client.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as send_err:
            print(f"Error sending message in show_manage_series_journey: {send_err}")

async def show_journey_lock_settings(client: Client, chat_id: int, message_id: int, journey_id: int):
    journey = await database.get_journey(journey_id)
    if not journey:
        return await show_manage_series(client, chat_id, message_id)
        
    lock_status = "Enabled ✅" if journey["lock_buttons_enabled"] else "Disabled ❌"
    active_enabled = journey["lock_active_series_enabled"]
    active_status = "Enabled ✅" if active_enabled else "Disabled ❌"
    old_status = "Enabled ✅" if journey["lock_old_series_enabled"] else "Disabled ❌"
    indiv_status = "Enabled ✅" if journey["lock_individual_enabled"] else "Disabled ❌"
    
    is_locked_val = journey.get("is_locked", False)
    j_lock_status_str = "Enabled 🔒 (Premium Required)" if is_locked_val else "Disabled 🔓"
    
    if active_enabled:
        day_based_status = "Enabled ✅" if journey["lock_day_based_enabled"] else "Disabled ❌"
        window = journey["lock_time_window"]
        if window == 0:
            duration_str = "Disabled (Latest only) ❌"
        elif window % 24 == 0:
            days = window // 24
            duration_str = f"{days} day(s) ✅"
        else:
            duration_str = f"{window} hour(s) ✅"
    else:
        day_based_status = "Inactive (Requires Lock Active Series ON) ⚠️"
        duration_str = "Inactive (Requires Lock Active Series ON) ⚠️"
        
    text = (
        f"🔒 **Lock Settings — {journey['name']}**\n\n"
        f"🔒 **Entire Journey Lock:** {j_lock_status_str}\n"
        f"⚡ **Lock Buttons Master Switch:** {lock_status}\n"
        f"🎬 **Lock Active Series:** {active_status}\n"
        f"⏳ **Lock Old/Non-Active Series:** {old_status}\n"
        f"⏱ **Day-Based Lock for Active Series:** {day_based_status}\n"
        f"📅 **Active Series Unlock Duration:** `{duration_str}`\n"
        f"🔓 **Individual Lock Switch:** {indiv_status}\n\n"
        f"**Access Control Logic:**\n"
        f"• If **Entire Journey Lock** is enabled, all contents under this Journey are completely restricted to premium users.\n"
        f"• Master Switch must be enabled for other locks (Active, Old, Individual) to apply.\n"
        f"• If Lock Active Series is enabled, files in active series are locked. If Day-Based Lock is ON, they unlock within the duration window; otherwise, only the latest section is unlocked.\n"
        f"• If Lock Old Series is enabled, all non-active series folders are restricted to premium.\n"
        f"• If Individual Lock Switch is enabled, any series/folder with individual lock enabled is restricted."
    )
    
    toggle_btn_text = "🔴 Disable Master Switch" if journey["lock_buttons_enabled"] else "🟢 Enable Master Switch"
    active_btn_text = "🎬 Lock Active: ON" if journey["lock_active_series_enabled"] else "🎬 Lock Active: OFF"
    old_btn_text = "⏳ Lock Old: ON" if journey["lock_old_series_enabled"] else "⏳ Lock Old: OFF"
    day_based_btn_text = "⏱ Day-Based: ON" if journey["lock_day_based_enabled"] else "⏱ Day-Based: OFF"
    indiv_btn_text = "🔓 Individual Lock: ON" if journey["lock_individual_enabled"] else "🔓 Individual Lock: OFF"
    journey_lock_btn_text = "🔓 Unlock Entire Journey" if is_locked_val else "🔒 Lock Entire Journey"
    
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(journey_lock_btn_text, callback_data=f"tog_j_is_locked_{journey_id}")
        ],
        [
            InlineKeyboardButton(toggle_btn_text, callback_data=f"tog_j_lock_b_{journey_id}"),
            InlineKeyboardButton(old_btn_text, callback_data=f"tog_j_lock_o_{journey_id}")
        ],
        [
            InlineKeyboardButton(active_btn_text, callback_data=f"tog_j_lock_a_{journey_id}"),
            InlineKeyboardButton(day_based_btn_text, callback_data=f"tog_j_lock_d_{journey_id}")
        ],
        [
            InlineKeyboardButton(indiv_btn_text, callback_data=f"tog_j_lock_i_{journey_id}"),
            InlineKeyboardButton("🔄 Reset All Locks", callback_data=f"reset_j_locks_btn_{journey_id}")
        ],
        [
            InlineKeyboardButton("📅 Edit Duration", callback_data=f"edit_j_unlock_dur_{journey_id}"),
            InlineKeyboardButton("📁 Config Active List", callback_data=f"config_j_active_{journey_id}_0")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=f"manage_journey_{journey_id}")
        ]
    ])
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
    except Exception as e:
        print(f"Error rendering show_journey_lock_settings: {e}")

async def show_journey_active_series_config(client: Client, chat_id: int, message_id: int, journey_id: int, skip: int = 0):
    journey = await database.get_journey(journey_id)
    if not journey:
        return await show_manage_series(client, chat_id, message_id)
        
    series_list = await database.list_series(journey_id=journey_id)
    limit = 5
    
    text = (
        f"🎬 **Configure Active Series — {journey['name']}**\n\n"
        "Select active/inactive series. Non-active series are locked for non-premium users.\n\n"
        "• ✅ = Active (open to everyone)\n"
        "• ❌ = Inactive (restricted to premium/subscribers)\n\n"
        "Click on any series below to toggle active status:"
    )
    
    buttons = []
    sliced_list = series_list[skip:skip+limit]
    
    for s in sliced_list:
        status_emoji = "✅" if s.get("is_active", True) else "❌"
        buttons.append([
            InlineKeyboardButton(f"{status_emoji} {s['title']}", callback_data=f"tog_j_ser_active_{journey_id}_{s['id']}_{skip}")
        ])
        
    pag_row = []
    if skip > 0:
        pag_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"config_j_active_{journey_id}_{max(0, skip - limit)}"))
    if skip + limit < len(series_list):
        pag_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"config_j_active_{journey_id}_{skip + limit}"))
    if pag_row:
        buttons.append(pag_row)
        
    buttons.append([InlineKeyboardButton("🔙 Back to Locks Settings", callback_data=f"j_lock_settings_{journey_id}")])
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        print(f"Error rendering show_journey_active_series_config: {e}")

async def show_series_management_menu(client: Client, chat_id: int, message_id: int, journey_id: int):
    settings = await database.get_settings()
    limit = settings.get("series_buttons_per_page", 5)
    custom_msg = settings.get("series_library_custom_msg")
    msg_status = "Set ✅" if custom_msg else "Not Set ❌"
    
    text = (
        "⚙️ **Series Library Management**\n\n"
        f"🔢 **User Series Pagination Limit:** `{limit}` buttons per page\n"
        f"💬 **Library Custom Message:** {msg_status}\n\n"
        "Choose a configuration option below:"
    )
    
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔢 Edit Buttons per Page", callback_data=f"edit_series_pag_limit_{journey_id}"),
            InlineKeyboardButton("💬 Edit Library Message", callback_data=f"edit_series_library_msg_{journey_id}")
        ],
        [
            InlineKeyboardButton("↕️ Reorder Series List", callback_data=f"series_reorder_menu_{journey_id}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=f"list_j_series_{journey_id}_0")
        ]
    ])
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
    except Exception as e:
        print(f"Error rendering series_management_menu: {e}")

async def show_series_reorder_menu(client: Client, chat_id: int, message_id: int, journey_id: int, selected_ids: list = None):
    if selected_ids is None:
        selected_ids = []
        
    def get_number_emoji(num: int) -> str:
        emojis = {
            1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣",
            6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣", 10: "🔟"
        }
        return emojis.get(num, f"[{num}]")
        
    series_list = await database.list_series(journey_id=journey_id)
    text = (
        "↕️ **Reorder Video Series**\n\n"
        "Select the series in the order you want them to display. "
        "Selected ones will show first (in selection sequence), and remaining unselected series will follow in their current relative order:\n\n"
    )
    
    if selected_ids:
        text += "📝 **Current Selection Order:**\n"
        for idx, sid in enumerate(selected_ids):
            for s in series_list:
                if s["id"] == sid:
                    text += f"{get_number_emoji(idx + 1)} {s['title']}\n"
                    break
        text += "\n"
        
    buttons = []
    
    for s in series_list:
        sid = s["id"]
        is_selected = sid in selected_ids
        
        display_title = s["title"]
        if is_selected:
            idx = selected_ids.index(sid)
            checkbox_text = get_number_emoji(idx + 1)
        else:
            checkbox_text = "⬜"
            
        row = [
            InlineKeyboardButton(f"🎬 {display_title}", callback_data="noop"),
            InlineKeyboardButton(checkbox_text, callback_data=f"reorder_toggle_{journey_id}_{sid}")
        ]
        buttons.append(row)
        
    if len(selected_ids) >= 2:
        buttons.append([
            InlineKeyboardButton(f"✅ Confirm Reorder ({len(selected_ids)} selected)", callback_data=f"reorder_confirm_{journey_id}")
        ])
        
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"j_series_management_menu_{journey_id}")])
    
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        print(f"Error rendering show_series_reorder_menu: {e}")

async def show_manage_files(client: Client, chat_id: int, message_id: int):
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 Store New File", callback_data="add_file"),
            InlineKeyboardButton("🗺️ Journey & Series Library", callback_data="manage_series")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="main_panel")
        ]
    ])
    try:
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📂 **File and Series Management**\n\nHere you can add new media files, view stored files, and create/manage video/episodes series.",
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error rendering manage_files: {e}")

async def show_filesec_actions(client: Client, chat_id: int, message_id: int, series_id: int, section_id: int, sec: dict, total_files: int, library_skip: int = 0):
    parent_id = sec["parent_id"]
    text = f"📥 **{format_sec_name_inline(sec['name'])}**\n\n📂 Contains **{total_files} file(s)**\n\nChoose an action:"
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add More Files", callback_data=f"filesec_add_{series_id}_{section_id}_{library_skip}"),
            InlineKeyboardButton("🔄 Replace All Files", callback_data=f"filesec_replace_{series_id}_{section_id}_{library_skip}")
        ],
        [
            InlineKeyboardButton("✏️ Rename Button", callback_data=f"rename_sec_{series_id}_{section_id}_{library_skip}"),
            InlineKeyboardButton("🗑 Delete Button", callback_data=f"tree_del_sec_{series_id}_{section_id}_{library_skip}")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data=f"browse_sec_{series_id}_{parent_id or 0}_{library_skip}")
        ]
    ])
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
    except Exception as e:
        print(f"Error rendering filesec_actions: {e}")
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=[message_id])
        except Exception as del_err:
            print(f"Error deleting message in show_filesec_actions: {del_err}")
        try:
            await client.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        except Exception as send_err:
            print(f"Error sending message in show_filesec_actions: {send_err}")

async def show_move_folder_menu(client: Client, chat_id: int, message_id: int, series_id: int, section_id: int, skip: int = 0, library_skip: int = 0):
    series = await database.get_series(series_id)
    folder_to_move = await database.get_section(section_id)
    if not series or not folder_to_move:
        try:
            await client.edit_message_text(chat_id=chat_id, message_id=message_id, text="❌ Folder or Series not found.")
        except Exception:
            pass
        return

    # Fetch all folders in this series
    all_folders = await database.list_all_folders(series_id)
    
    # Exclude itself and any descendants to prevent loops
    descendants = set()
    
    def add_descendants(parent_id):
        for f in all_folders:
            if f["parent_id"] == parent_id:
                if f["id"] not in descendants:
                    descendants.add(f["id"])
                    add_descendants(f["id"])
                    
    descendants.add(section_id)
    add_descendants(section_id)
    
    # Filter valid target folders
    valid_folders = [f for f in all_folders if f["id"] not in descendants]
    
    text = (
        f"📂 **Move Folder: {format_sec_name_inline(folder_to_move['name'])}**\n\n"
        f"Choose a new parent folder for **{format_sec_name_inline(folder_to_move['name'])}** from the list below.\n"
        "Select **Root (Top-Level)** to move it to the series root."
    )
    
    buttons = []
    
    # Always allow moving to Root (Top-Level) if currently not at root
    if folder_to_move["parent_id"] is not None:
        buttons.append([
            InlineKeyboardButton("📁 Root (Top-Level)", callback_data=f"move_folder_execute_{series_id}_{section_id}_root_{library_skip}")
        ])
        
    # Page valid folders
    limit = 5
    page_folders = valid_folders[skip:skip+limit]
    
    for f in page_folders:
        prefix = "👉 " if f["id"] == folder_to_move["parent_id"] else "📁 "
        buttons.append([
            InlineKeyboardButton(f"{prefix}{format_sec_name_btn(f['name'])}", callback_data=f"move_folder_execute_{series_id}_{section_id}_{f['id']}_{library_skip}")
        ])
        
    # Pagination
    pag_row = []
    if skip > 0:
        pag_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"move_folder_select_{series_id}_{section_id}_{library_skip}_{max(0, skip - limit)}"))
    if skip + limit < len(valid_folders):
        pag_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"move_folder_select_{series_id}_{section_id}_{library_skip}_{skip + limit}"))
    if pag_row:
        buttons.append(pag_row)
        
    buttons.append([
        InlineKeyboardButton("🔙 Cancel / Back", callback_data=f"manage_folder_opt_{series_id}_{section_id}_{library_skip}")
    ])
    
    try:
        await client.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        print(f"Error rendering show_move_folder_menu: {e}")


async def show_edit_library_message_menu(client: Client, chat_id: int, message_id: int):
    """Show the menu allowing choice between editing global welcome message or journey descriptions."""
    journeys = await database.list_journeys()
    settings = await database.get_settings()
    library_msg = settings.get("series_library_custom_msg")
    library_msg_status = f"`{library_msg[:60]}...`" if library_msg else "_Default (None)_ ⚠️"
    
    text = (
        "💬 **Library Message & Descriptions Manager**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📝 **Global Welcome Message:**\n{library_msg_status}\n\n"
        "Choose what you want to edit below. Selecting a journey/category allows you to edit its description directly, which will show under its heading in Clone Bots:\n\n"
    )
    
    buttons = [
        [
            InlineKeyboardButton("💬 Edit Global Welcome Message", callback_data="edit_global_library_welcome_msg")
        ]
    ]
    
    for j in journeys:
        desc_preview = f" ({j.get('description', '')[:25]}...)" if j.get('description') else " (No Description)"
        buttons.append([
            InlineKeyboardButton(f"🗺️ {j['name']}{desc_preview}", callback_data=f"edit_journey_desc_lib_{j['id']}")
        ])
        
    buttons.append([
        InlineKeyboardButton("🔙 Back", callback_data="manage_series")
    ])
    
    try:
        await client.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=text, reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        print(f"Error rendering show_edit_library_message_menu: {e}")


