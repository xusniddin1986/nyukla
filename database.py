import json
import os
from datetime import datetime
from config import OWNER_ID

DB_FILE = "data/database.json"


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
        "required_channels": [],
        "bot_active": True,
        "stats": {
            "total_downloads": 0,
            "total_music_searches": 0
        }
    }


class Database:
    def add_user(self, user_id: int, username: str = None, full_name: str = None):
        data = _load()
        uid = str(user_id)
        if uid not in data["users"]:
            data["users"][uid] = {
                "id": user_id,
                "username": username,
                "full_name": full_name,
                "joined": datetime.now().isoformat(),
                "downloads": 0,
                "searches": 0
            }
        else:
            if username:
                data["users"][uid]["username"] = username
            if full_name:
                data["users"][uid]["full_name"] = full_name
        _save(data)

    def get_all_users(self):
        data = _load()
        return list(data["users"].values())

    def get_user_count(self):
        data = _load()
        return len(data["users"])

    def get_admins(self):
        data = _load()
        admins = data.get("admins", [])
        if OWNER_ID and OWNER_ID not in admins:
            admins.append(OWNER_ID)
        return admins

    def add_admin(self, user_id: int):
        data = _load()
        if user_id not in data["admins"]:
            data["admins"].append(user_id)
            _save(data)
            return True
        return False

    def remove_admin(self, user_id: int):
        data = _load()
        if user_id in data["admins"] and user_id != OWNER_ID:
            data["admins"].remove(user_id)
            _save(data)
            return True
        return False

    def get_required_channels(self):
        data = _load()
        return data.get("required_channels", [])

    def add_channel(self, channel: str):
        data = _load()
        if channel not in data["required_channels"]:
            data["required_channels"].append(channel)
            _save(data)
            return True
        return False

    def remove_channel(self, channel: str):
        data = _load()
        if channel in data["required_channels"]:
            data["required_channels"].remove(channel)
            _save(data)
            return True
        return False

    def get_bot_status(self):
        data = _load()
        return data.get("bot_active", True)

    def set_bot_status(self, status: bool):
        data = _load()
        data["bot_active"] = status
        _save(data)

    def increment_downloads(self, user_id: int):
        data = _load()
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid]["downloads"] = data["users"][uid].get("downloads", 0) + 1
        data["stats"]["total_downloads"] = data["stats"].get("total_downloads", 0) + 1
        _save(data)

    def increment_searches(self, user_id: int):
        data = _load()
        uid = str(user_id)
        if uid in data["users"]:
            data["users"][uid]["searches"] = data["users"][uid].get("searches", 0) + 1
        data["stats"]["total_music_searches"] = data["stats"].get("total_music_searches", 0) + 1
        _save(data)

    def get_stats(self):
        data = _load()
        return {
            "users": len(data["users"]),
            "admins": len(data.get("admins", [])),
            "total_downloads": data["stats"].get("total_downloads", 0),
            "total_music_searches": data["stats"].get("total_music_searches", 0),
            "bot_active": data.get("bot_active", True)
        }


db = Database()
