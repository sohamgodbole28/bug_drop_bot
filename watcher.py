import os
import json
from datetime import datetime, timezone
import requests

H1_API_USERNAME = os.getenv("H1_API_USERNAME", "")
H1_API_TOKEN = os.getenv("H1_API_TOKEN", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

CACHE_FILE = "cache.json"
BBSCOPE_API_URL = "https://bbscope.com/api/v1/programs"

def send_discord_alert(session, program):
    if not DISCORD_WEBHOOK_URL or "discord" not in DISCORD_WEBHOOK_URL.lower():
        return

    is_bbp = "BBP" in program.get("bounty_info", "")
    embed_color = 0x00FF88 if is_bbp else 0x3B82F6

    fields = [
        {
            "name": "🌐 Platform",
            "value": f"`{program.get('platform', 'Unknown')}`",
            "inline": True
        },
        {
            "name": "💎 Bounty Type",
            "value": f"`{program.get('bounty_info', 'N/A')}`",
            "inline": True
        },
        {
            "name": "📊 Metrics",
            "value": f"`{program.get('metrics', 'N/A')}`",
            "inline": True
        }
    ]

    started_at = program.get("posted_at")
    if started_at and started_at != "N/A":
        fields.append({
            "name": "🕒 Accepting Since",
            "value": f"`{started_at}`",
            "inline": True
        })

    fields.append({
        "name": "🔗 Direct URL",
        "value": f"[Open in {program.get('platform', 'Target')}]({program.get('url', '')})",
        "inline": False
    })

    embed = {
        "title": f"🚨 New Target: {program.get('name', 'Unknown')}",
        "url": program.get("url", ""),
        "color": embed_color,
        "description": "A new target has been detected by the Bug Bounty Watcher.",
        "fields": fields,
        "footer": {
            "text": "Bug Bounty Automated Watcher • Live Tracker"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    payload = {
        "username": "Bug Bounty Watcher",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2092/2092663.png",
        "embeds": [embed]
    }

    try:
        session.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
    except Exception:
        pass

def fetch_hackerone_programs(session):
    programs = {}
    if not H1_API_USERNAME or not H1_API_TOKEN or "YOUR_" in H1_API_USERNAME:
        return programs

    page_number = 1
    while True:
        url = f"https://api.hackerone.com/v1/hackers/programs?page[size]=100&page[number]={page_number}"
        try:
            response = session.get(url, auth=(H1_API_USERNAME, H1_API_TOKEN), timeout=25)
            if response.status_code != 200:
                break

            data = response.json()
            items = data.get("data", [])
            if not items:
                break

            for item in items:
                attributes = item.get("attributes", {})
                handle = attributes.get("handle")
                name = attributes.get("name")
                started_at = attributes.get("started_accepting_at", "N/A")
                offers_bounties = attributes.get("offers_bounties", False)
                bounty_info = "💰 BBP (Paid Bounty)" if offers_bounties else "📋 VDP (Points Only)"

                if handle:
                    programs[f"h1_{handle}"] = {
                        "platform": "HackerOne",
                        "name": name or handle,
                        "url": f"https://hackerone.com/{handle}",
                        "posted_at": started_at,
                        "bounty_info": bounty_info,
                        "metrics": f"State: {attributes.get('submission_state', 'N/A')}"
                    }

            links = data.get("links", {})
            if "next" not in links or not links["next"]:
                break

            page_number += 1
        except Exception:
            break

    return programs

def fetch_bbscope_programs(session):
    programs = {}
    try:
        response = session.get(BBSCOPE_API_URL, timeout=25)
        if response.status_code == 200:
            data = response.json()
            items = data if isinstance(data, list) else data.get("programs", [])
            for item in items:
                if isinstance(item, dict):
                    raw_platform = item.get("platform", "").lower()
                    if raw_platform in ["bc", "bugcrowd"]:
                        platform_name = "Bugcrowd"
                    elif raw_platform == "it":
                        platform_name = "Intigriti"
                    elif raw_platform == "ywh":
                        platform_name = "YesWeHack"
                    elif raw_platform == "bugbase":
                        platform_name = "Bugbase"
                    else:
                        continue

                    handle = item.get("handle", "")
                    clean_name = handle.strip("/").split("/")[-1] if handle else ""
                    name = item.get("name") or clean_name or handle
                    url = item.get("url") or f"https://{platform_name.lower()}.com{handle}"
                    is_bbp = item.get("is_bbp", False)
                    in_scope_count = item.get("in_scope_count", "N/A")
                    bounty_info = "💰 BBP (Paid Bounty)" if is_bbp else "📋 VDP (Points Only)"

                    if name and url:
                        key = f"{platform_name.lower()}_{url.strip('/').lower()}"

                        programs[key] = {
                            "platform": platform_name,
                            "name": name,
                            "url": url,
                            "posted_at": "N/A",
                            "bounty_info": bounty_info,
                            "metrics": f"In-Scope Assets: {in_scope_count}"
                        }
    except Exception:
        pass
    return programs

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def main():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BugBountyWatcher/2.0"})

    current_programs = {}
    current_programs.update(fetch_bbscope_programs(session))
    current_programs.update(fetch_hackerone_programs(session))

    cached_programs = load_json(CACHE_FILE)

    if not cached_programs:
        save_json(CACHE_FILE, current_programs)
        return

    for key, info in current_programs.items():
        if key not in cached_programs:
            send_discord_alert(session, info)

    cached_programs.update(current_programs)
    save_json(CACHE_FILE, cached_programs)

if __name__ == "__main__":
    main()