import re
import asyncio
from datetime import datetime
from pyrogram import Client
from pyrogram.errors import FloodWait
import database
from .fillings import format_fillings, to_small_text

async def trigger_journey_update_notification(client: Client, series_id: int, metadata: dict = None):
    """
    Sends an episode update notification message to the Journey's configured update_channel_id
    whenever new files or batches are added for a series.
    """
    try:
        series = await database.get_series(series_id)
        if not series or not series.get("journey_id"):
            return
            
        journey = await database.get_journey(series["journey_id"])
        if not journey or not journey.get("update_channel_id"):
            return
            
        update_channel = journey["update_channel_id"].strip()
        if not update_channel:
            return
            
        chat_id = int(update_channel) if update_channel.startswith("-100") or update_channel.isdigit() else update_channel
        
        settings = await database.get_settings()
        primary_clone = settings.get("primary_clone_username")
        bot_username = primary_clone if primary_clone else (getattr(client.me, "username", "") or "")
        
        tmpl = journey.get("update_msg_template") or "{series_name} latest episode ({date}) updated ✅\n\nBot : @{bot_username}"
        
        meta = metadata or {}
        season = meta.get("season_number") or 1
        quality = meta.get("resolution") or meta.get("quality") or "720p"
        ep_num = meta.get("episode_number")
        ep_range = meta.get("episode_range")
        
        start = meta.get("start")
        end = meta.get("end")
        if not start and ep_range:
            m = re.findall(r'\d+', str(ep_range))
            if len(m) >= 2:
                start = int(m[0])
                end = int(m[1])
        elif not start and ep_num is not None:
            start = ((ep_num - 1) // 4) * 4 + 1
            end = start + 3
            
        now = datetime.now()
        fillings_data = {
            "series_name": series["title"],
            "journey_name": journey["name"],
            "date": now.strftime("%d-%m-%Y"),
            "date_short": now.strftime("%d-%m-%y"),
            "date_small": to_small_text(now.strftime("%d-%m-%y")),
            "episodes": f"{start:02d} - {end:02d}" if (start and end) else (f"{ep_num:02d}" if ep_num else ""),
            "start": f"{start:02d}" if start else "",
            "end": f"{end:02d}" if end else "",
            "season": f"{season:02d}" if season else "01",
            "quality": quality,
            "bot_username": bot_username
        }
        
        msg_text = format_fillings(tmpl, fillings_data)
        
        try:
            await client.send_message(chat_id=chat_id, text=msg_text)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            await client.send_message(chat_id=chat_id, text=msg_text)
        except Exception as err:
            print(f"Failed to post update notification to channel {update_channel}: {err}")
    except Exception as e:
        print(f"Error in trigger_journey_update_notification: {e}")
