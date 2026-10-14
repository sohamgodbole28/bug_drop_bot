import os
import json
import requests
import difflib

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

H1_API_USERNAME = os.getenv("H1_API_USERNAME", "YOUR_H1_USERNAME")
H1_API_TOKEN = os.getenv("H1_API_TOKEN", "YOUR_H1_TOKEN")

CACHE_FILE = "cache.json"
TRACKED_FILE = "tracked.json"
OFFSET_FILE = "offset.json"
BBSCOPE_API_URL = "https://bbscope.com/api/v1/programs"

def send_telegram_alert(message, chat_id=None):
    target_chat = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not target_chat or "YOUR_" in TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception:
        pass

def fetch_hackerone_programs():
    programs = {}
    if not H1_API_USERNAME or not H1_API_TOKEN or "YOUR_" in H1_API_USERNAME:
        return programs

    url = "https://api.hackerone.com/v1/hackers/programs?page[size]=100"
    try:
        response = requests.get(url, auth=(H1_API_USERNAME, H1_API_TOKEN), timeout=20)
        if response.status_code == 200:
            data = response.json()
            for item in data.get("data", []):
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
    except Exception:
        pass
    return programs

def fetch_bbscope_programs():
    programs = {}
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(BBSCOPE_API_URL, headers=headers, timeout=25)
        if response.status_code == 200:
            data = response.json()
            items = data if isinstance(data, list) else data.get("programs", [])
            
            for item in items:
                if isinstance(item, dict):
                    platform = item.get("platform", "").lower()
                    if platform in ["bc", "bugcrowd", "bugbase"]:
                        platform_name = "Bugcrowd" if platform in ["bc", "bugcrowd"] else "Bugbase"
                        handle = item.get("handle", "")
                        name = item.get("name") or handle
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

def process_commands(current_programs):
    if not TELEGRAM_BOT_TOKEN or "YOUR_" in TELEGRAM_BOT_TOKEN:
        return

    offset_data = load_json(OFFSET_FILE)
    offset = offset_data.get("offset", 0)
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=1"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return
        
        updates = response.json().get("result", [])
        tracked = load_json(TRACKED_FILE)
        
        for update in updates:
            update_id = update.get("update_id")
            offset_data["offset"] = update_id + 1
            
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "").strip()
            
            if not text or not chat_id:
                continue
                
            parts = text.split(" ", 1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""
            
            if cmd == "/track":
                if not arg:
                    if not tracked:
                        send_telegram_alert("📂 You are not tracking any programs currently.", chat_id)
                    else:
                        msg = "📂 *Your Tracked Programs:*\n\n"
                        for k, info in tracked.items():
                            msg += f"• *{info['name']}* ({info['platform']})\n  🔗 {info['url']}\n\n"
                        send_telegram_alert(msg, chat_id)
                else:
                    keys = list(current_programs.keys())
                    matches = difflib.get_close_matches(arg.lower(), keys, n=1, cutoff=0.3)
                    if matches:
                        match_key = matches[0]
                        prog = current_programs[match_key]
                        tracked[match_key] = prog
                        save_json(TRACKED_FILE, tracked)
                        send_telegram_alert(f"✅ Successfully tracking: *{prog['name']}* ({prog['platform']})", chat_id)
                    else:
                        send_telegram_alert(f"❌ Could not find any program matching '{arg}'.", chat_id)
                        
            elif cmd == "/untrack":
                if not arg:
                    send_telegram_alert("Usage: `/untrack <program name>`", chat_id)
                else:
                    tracked_keys = list(tracked.keys())
                    matches = difflib.get_close_matches(arg.lower(), tracked_keys, n=1, cutoff=0.3)
                    if matches:
                        match_key = matches[0]
                        prog_name = tracked[match_key]["name"]
                        del tracked[match_key]
                        save_json(TRACKED_FILE, tracked)
                        send_telegram_alert(f"🗑️ Stopped tracking: *{prog_name}*", chat_id)
                    else:
                        send_telegram_alert(f"❌ No tracked program found matching '{arg}'.", chat_id)

            elif cmd == "/check":
                send_telegram_alert("🔄 Running manual program check...", chat_id)
                cached = load_json(CACHE_FILE)
                new_found = 0
                
                for k, info in current_programs.items():
                    if k not in cached:
                        new_found += 1
                        msg = (
                            f"🚨 *New Program Dropped on {info['platform']}!*\n\n"
                            f"🎯 *Target:* {info['name']}\n"
                            f"💎 *Type:* {info['bounty_info']}\n"
                            f"📊 *Metrics:* {info['metrics']}\n"
                            f"🕒 *Started At:* {info['posted_at']}\n"
                            f"🔗 *Link:* {info['url']}"
                        )
                        send_telegram_alert(msg)
                
                save_json(CACHE_FILE, current_programs)
                send_telegram_alert(f"✅ Manual check complete! Found {new_found} new programs.", chat_id)

            elif cmd.startswith("/latest"):
                try:
                    count = int(arg) if arg else 5
                except ValueError:
                    count = 5
                
                if not current_programs:
                    send_telegram_alert("⚠️ No programs currently loaded in memory.", chat_id)
                else:
                    h1_progs = [p for p in current_programs.values() if p.get('platform') == 'HackerOne' and p.get('posted_at') != 'N/A']
                    sorted_progs = sorted(h1_progs, key=lambda x: x.get('posted_at'), reverse=True)
                    limited_progs = sorted_progs[:count]
                    
                    if not limited_progs:
                        send_telegram_alert("⚠️ No timestamped HackerOne programs available to sort.", chat_id)
                    else:
                        msg = f"🔥 *Latest {len(limited_progs)} HackerOne Programs:*\n\n"
                        for info in limited_progs:
                            msg += (
                                f"• *{info['name']}* ({info['platform']})\n"
                                f"  💎 {info['bounty_info']}\n"
                                f"  🕒 {info['posted_at']}\n"
                                f"  🔗 {info['url']}\n\n"
                            )
                        send_telegram_alert(msg, chat_id)
                        
        save_json(OFFSET_FILE, offset_data)
    except Exception:
        pass

def main():
    current_programs = {}
    current_programs.update(fetch_hackerone_programs())
    current_programs.update(fetch_bbscope_programs())
    
    process_commands(current_programs)
    
    cached_programs = load_json(CACHE_FILE)
    
    if not cached_programs:
        save_json(CACHE_FILE, current_programs)
        return

    for key, info in current_programs.items():
        if key not in cached_programs:
            msg = (
                f"🚨 *New Program Dropped on {info['platform']}!*\n\n"
                f"🎯 *Target:* {info['name']}\n"
                f"💎 *Type:* {info['bounty_info']}\n"
                f"📊 *Metrics:* {info['metrics']}\n"
                f"🕒 *Started At:* {info['posted_at']}\n"
                f"🔗 *Link:* {info['url']}"
            )
            send_telegram_alert(msg)

    save_json(CACHE_FILE, current_programs)

if __name__ == "__main__":
    main()