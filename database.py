from db.models import (
    engine, SessionLocal, Base, Settings, CloneBot, Series,
    SeriesSection, FileRecord, User, Admin, db_init
)
from db.backup import export_db_backup, import_db_backup, restart_database
from db.crud_settings import (
    get_settings, update_settings, add_clone_bot, get_clone_bots,
    set_clone_bot_status, delete_clone_bot, add_user, get_user_count,
    list_users, is_admin, add_admin, remove_admin,
    add_subscriber, remove_subscriber, is_subscriber, get_subscriber_count, list_subscribers,
    is_premium_user, sync_premium_users, sync_single_premium_user, get_premium_cache_count,
    get_remote_channels, get_db_stats, format_bytes
)
from db.crud_series import (
    create_series, get_series, list_series, delete_series,
    create_section, get_section, list_sections, delete_section,
    get_section_path, update_section, clear_section_files,
    update_series_settings, update_section_settings, add_file,
    get_file, delete_file, list_files,
    update_section_parent, list_all_folders,
    create_journey, get_journey, list_journeys, delete_journey,
    update_journey_settings, reset_journey_locks, get_series_by_channel
)

async def get_formatted_more_info_msg(settings: dict) -> str:
    from db.models import SessionLocal, Series
    active_titles = []
    old_titles = []
    with SessionLocal() as session:
        series_rows = session.query(Series).order_by(Series.display_order.asc(), Series.id.asc()).all()
        for s in series_rows:
            if s.is_active:
                active_titles.append(s.title)
            else:
                old_titles.append(s.title)

    active_list_str = "\n".join(f"• {t}" for t in active_titles) if active_titles else "_No active series._"
    old_list_str = "\n".join(f"• {t}" for t in old_titles) if old_titles else "_No old series._"

    # Settings variables
    active_premium_lock = "ON 🟢 (Premium Required)" if settings.get("lock_active_series_enabled", False) else "OFF 🔴 (Open to Everyone)"
    
    # Day-based status
    if settings.get("lock_active_series_enabled", False):
        day_based_lock = "ON 🟢" if settings.get("lock_day_based_enabled", False) else "OFF 🔴"
        # Duration
        window = settings.get("lock_time_window", 0)
        if window == 0:
            duration_str = "Latest episode only"
        elif window % 24 == 0:
            duration_str = f"{window // 24} day(s)"
        else:
            duration_str = f"{window} hour(s)"
    else:
        day_based_lock = "Inactive ⚠️"
        duration_str = "Inactive ⚠️"

    old_series_lock = "ON 🟢 (Premium Required)" if settings.get("lock_old_series_enabled", True) else "OFF 🔴 (Open to Everyone)"

    default_template = (
        "ℹ️ **BOT INFORMATION & SYSTEM STATUS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📢 **Access Rules & Lock Settings:**\n"
        "• 🎬 **Lock Active Series:** {active_premium_series_status}\n"
        "• ⏳ **Lock Old Series:** {old_series_lock}\n"
        "• ⏱ **Day-Based Lock:** {day_based_lock}\n"
        "• 📅 **Active Unlock Duration:** `{unlock_duration}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📂 **Active Categories (Unrestricted):**\n"
        "{active_series_list}\n\n"
        "🔒 **Old/Archived Series (Premium Only):**\n"
        "{old_series_list}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 _Tip: Non-premium users can only download files from the active series._"
    )

    template = settings.get("more_info_msg") or default_template
    
    formatted = template.format(
        active_premium_series_status=active_premium_lock,
        old_series_lock=old_series_lock,
        day_based_lock=day_based_lock,
        day_based_lock_status=day_based_lock,
        unlock_duration=duration_str,
        active_series_list=active_list_str,
        old_series_list=old_list_str
    )
    return formatted

