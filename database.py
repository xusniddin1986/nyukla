import json
import os
from datetime import datetime
from config import OWNER_ID

DB_FILE = "data/db.json"

def _load():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DB_FILE):
        _save(_default())
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data):
    os.makedirs("data", exist_ok=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _default():
    return {
        "users": {},
        "admins": [OWNER_ID] if OWNER_ID else [],
        "channels": [],
        "bot_on": True,
        "stats": {"downloads": 0, "searches": 0}
    }

class DB:
    def add_user(self, uid, username=None, full_name=None):
        d = _load()
        key = str(uid)
        if key not in d["users"]:
            d["users"][key] = {"id": uid, "username": username, "full_name": full_name,
                                "joined": datetime.now().isoformat(), "downloads": 0, "searches": 0}
        else:
            if username: d["users"][key]["username"] = username
            if full_name: d["users"][key]["full_name"] = full_name
        _save(d)

    def get_users(self):
        return list(_load()["users"].values())

    def get_user_count(self):
        return len(_load()["users"])

    def get_admins(self):
        d = _load()
        admins = d.get("admins", [])
        if OWNER_ID and OWNER_ID not in admins:
            admins.append(OWNER_ID)
        return admins

    def add_admin(self, uid):
        d = _load()
        if uid not in d["admins"]:
            d["admins"].append(uid)
            _save(d)
            return True
        return False

    def remove_admin(self, uid):
        d = _load()
        if uid in d["admins"] and uid != OWNER_ID:
            d["admins"].remove(uid)
            _save(d)
            return True
        return False

    def get_channels(self):
        return _load().get("channels", [])

    def add_channel(self, ch):
        d = _load()
        if ch not in d["channels"]:
            d["channels"].append(ch)
            _save(d)
            return True
        return False

    def remove_channel(self, ch):
        d = _load()
        if ch in d["channels"]:
            d["channels"].remove(ch)
            _save(d)
            return True
        return False

    def is_active(self):
        return _load().get("bot_on", True)

    def set_active(self, val):
        d = _load()
        d["bot_on"] = val
        _save(d)

    def inc_download(self, uid):
        d = _load()
        key = str(uid)
        if key in d["users"]:
            d["users"][key]["downloads"] = d["users"][key].get("downloads", 0) + 1
        d["stats"]["downloads"] = d["stats"].get("downloads", 0) + 1
        _save(d)

    def inc_search(self, uid):
        d = _load()
        key = str(uid)
        if key in d["users"]:
            d["users"][key]["searches"] = d["users"][key].get("searches", 0) + 1
        d["stats"]["searches"] = d["stats"].get("searches", 0) + 1
        _save(d)

    def get_stats(self):
        d = _load()
        return {
            "users": len(d["users"]),
            "admins": len(d.get("admins", [])),
            "downloads": d["stats"].get("downloads", 0),
            "searches": d["stats"].get("searches", 0),
            "bot_on": d.get("bot_on", True),
            "channels": len(d.get("channels", []))
        }

db = DB()
