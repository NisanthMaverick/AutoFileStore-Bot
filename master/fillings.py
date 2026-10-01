from datetime import datetime

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

def to_small_text(text: str) -> str:
    """Converts numbers and characters to small superscript text."""
    return "".join(superscript_map.get(c, c) for c in text)

def format_fillings(template: str, data: dict) -> str:
    """
    Replaces placeholders ("fillings") in templates.
    Supported placeholders:
      {series_name} / {series}  : Series Title
      {journey_name} / {journey}: Journey Name
      {date}                   : Full Date DD-MM-YYYY (e.g. 01-10-2026)
      {date_short}             : Short Date DD-MM-YY (e.g. 01-10-26)
      {date_small}             : Small Superscript Date (e.g. ⁰¹⁻¹⁰⁻²⁶)
      {episodes} / {ep_range}  : Episode number or range (e.g. 57 - 60)
      {start}                  : Episode start number (e.g. 57)
      {end}                    : Episode end number (e.g. 60)
      {season}                 : Season number (e.g. 01)
      {quality}                : Quality (e.g. 480p, 720p, 1080p)
      {bot_username}           : Clone/Main Bot Username
      {bot_link}               : Bot username with @
    """
    if not template:
        return ""
        
    now = datetime.now()
    date_full = data.get("date") or now.strftime("%d-%m-%Y")
    date_short = data.get("date_short") or now.strftime("%d-%m-%y")
    date_small = data.get("date_small") or to_small_text(date_short)
    
    series_name = data.get("series_name") or data.get("series") or ""
    journey_name = data.get("journey_name") or data.get("journey") or ""
    
    episodes = data.get("episodes") or data.get("ep_range") or ""
    start = data.get("start", "")
    end = data.get("end", "")
    if not episodes and start and end:
        episodes = f"{start} - {end}"
        
    season = data.get("season", "")
    quality = data.get("quality") or data.get("resolution") or ""
    
    bot_username = data.get("bot_username") or ""
    if bot_username.startswith("@"):
        bot_username = bot_username[1:]
    bot_link = f"@{bot_username}" if bot_username else ""
    
    replacements = {
        "{series_name}": series_name,
        "{series}": series_name,
        "{journey_name}": journey_name,
        "{journey}": journey_name,
        "{date}": date_full,
        "{date_short}": date_short,
        "{date_small}": date_small,
        "{episodes}": episodes,
        "{ep_range}": episodes,
        "{episode}": episodes,
        "{start}": str(start),
        "{end}": str(end),
        "{season}": str(season),
        "{quality}": quality,
        "{bot_username}": bot_username,
        "{bot_link}": bot_link,
        "{bot_mention}": bot_link
    }
    
    res = template
    for key, val in replacements.items():
        res = res.replace(key, str(val))
        
    return res

def get_fillings_help_text() -> str:
    return (
        "✨ **Available Template Placeholders (Fillings):**\n\n"
        "• `{series_name}` — Series Title (e.g. `Vikram On Duty`)\n"
        "• `{journey_name}` — Journey Title\n"
        "• `{date}` — Full Date (e.g. `01-10-2026`)\n"
        "• `{date_short}` — Short Date (e.g. `01-10-26`)\n"
        "• `{date_small}` — Superscript Small Date (e.g. `⁰¹⁻¹⁰⁻²⁶`)\n"
        "• `{episodes}` — Episode / Range (e.g. `57 - 60`)\n"
        "• `{start}` / `{end}` — Episode start / end number\n"
        "• `{season}` — Season Number (e.g. `01`)\n"
        "• `{quality}` — Quality resolution (e.g. `720p`)\n"
        "• `{bot_username}` — Bot username (e.g. `FileStoreClone_bot`)\n"
        "• `{bot_link}` — Bot username with `@` (e.g. `@FileStoreClone_bot`)\n"
    )
