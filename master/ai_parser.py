import re
import json
import aiohttp
import config

def clean_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text

def parse_metadata_fallback(file_name: str, caption: str) -> dict:
    """Fallback parser using regexes to extract info if Gemini API fails or is not configured."""
    metadata = {
        "series_name": None,
        "season_number": None,
        "episode_number": None,
        "episode_range": None,
        "episode_title": None,
        "resolution": None,
        "quality": None,
        "codec": None,
        "audio": None
    }
    
    # Strip extension for parsing
    base_name = file_name
    for ext in [".mkv", ".mp4", ".webm", ".avi", ".m4v"]:
        if base_name.lower().endswith(ext):
            base_name = base_name[:-len(ext)]
            break
            
    # Combine filename and caption for matching tags like quality/audio
    combined_text = f"{base_name} {caption}"
    
    # 1. Resolution
    res_match = re.search(r'\b(480p|720p|1080p|2160p|4k)\b', combined_text, re.IGNORECASE)
    if res_match:
        metadata["resolution"] = res_match.group(1).lower()
        
    # 2. Quality / Source
    quality_match = re.search(r'\b(WEB-DL|WEBRip|HDRip|BluRay|NF-WEB-DL|AMZN-WEB-DL|DSNP-WEB-DL|WEB\s*DL|WEB\s*Rip|BRRip|DVDRip)\b', combined_text, re.IGNORECASE)
    if quality_match:
        metadata["quality"] = quality_match.group(1).replace(" ", "-").upper()
        
    # 3. Codec
    codec_match = re.search(r'\b(x264|x265|HEVC|H\.?264|H\.?265)\b', combined_text, re.IGNORECASE)
    if codec_match:
        metadata["codec"] = codec_match.group(1).lower().replace(".", "")
        
    # 4. Audio / Languages
    # Look for lists of languages or dual/multi audio tags
    languages = []
    for lang in ["Tamil", "Telugu", "Hindi", "Malayalam", "Kannada", "English", "Bengali", "Marathi"]:
        if re.search(r'\b' + lang + r'\b', combined_text, re.IGNORECASE):
            languages.append(lang)
    if languages:
        metadata["audio"] = ", ".join(languages)
    else:
        audio_tag = re.search(r'\b(Dual[- ]Audio|Multi[- ]Audio|Dual|Multi)\b', combined_text, re.IGNORECASE)
        if audio_tag:
            metadata["audio"] = audio_tag.group(1)
            
    # 5. Extract Series, Season, Episode / Episode Range
    # Pattern: Series Name S01E68 or Series Name S01 E68
    season_ep_match = re.search(r'^(.*?)\s+S(\d+)\s*[eE][pP]?\s*\(?(\d+)\s*[-–]\s*(\d+)\)?', base_name)
    if season_ep_match:
        metadata["series_name"] = season_ep_match.group(1).strip()
        metadata["season_number"] = int(season_ep_match.group(2))
        metadata["episode_range"] = f"{int(season_ep_match.group(3)):02d}-{int(season_ep_match.group(4)):02d}"
    else:
        season_ep_single = re.search(r'^(.*?)\s+S(\d+)\s*[eE][pP]?\s*(\d+)', base_name)
        if season_ep_single:
            metadata["series_name"] = season_ep_single.group(1).strip()
            metadata["season_number"] = int(season_ep_single.group(2))
            metadata["episode_number"] = int(season_ep_single.group(3))
            
            # Remaining text after E68 could be the episode title
            rem = base_name[season_ep_single.end():].strip()
            # Clean symbols from title
            rem = re.sub(r'^[-_–\s]+', '', rem)
            if rem and not any(tag in rem.lower() for tag in ["720p", "1080p", "web-dl", "x264", "x265", "hevc"]):
                metadata["episode_title"] = rem
        else:
            # Maybe just episode range without Season
            ep_range_only = re.search(r'^(.*?)\s+EP\s*\(?(\d+)\s*[-–]\s*(\d+)\)?', base_name, re.IGNORECASE)
            if ep_range_only:
                metadata["series_name"] = ep_range_only.group(1).strip()
                metadata["episode_range"] = f"{int(ep_range_only.group(2)):02d}-{int(ep_range_only.group(3)):02d}"
            else:
                # Just episode number
                ep_single_only = re.search(r'^(.*?)\s+EP\s*(\d+)', base_name, re.IGNORECASE)
                if ep_single_only:
                    metadata["series_name"] = ep_single_only.group(1).strip()
                    metadata["episode_number"] = int(ep_single_only.group(2))
                else:
                    # Clean brackets and treat whatever remains as series title
                    cleaned_title = re.sub(r'\[.*?\]|\(.*?\)', '', base_name).strip()
                    metadata["series_name"] = cleaned_title
                    
    # Clean series name if it contains year at the end, e.g., Batchmates (2026) -> Batchmates
    if metadata["series_name"]:
        metadata["series_name"] = re.sub(r'\s*\(\d{4}\)$', '', metadata["series_name"]).strip()
        # Clean trailing dashes/symbols
        metadata["series_name"] = re.sub(r'[-_–\s]+$', '', metadata["series_name"]).strip()
        
    return metadata

async def parse_file_metadata(file_name: str, caption: str) -> dict:
    return parse_metadata_fallback(file_name, caption)
