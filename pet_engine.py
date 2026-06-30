"""
宠物引擎 — 确定性生成/互动/对战/衰减/排行榜/SQLite持久化/兑换码
"""
import json
import os
import math
import random
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from pet_art import SPECIES, SHRIMP_KING, RARITY_NAMES, ART, get_art

DB_FILE = os.path.join(os.path.dirname(__file__), "pets.db")
JSON_FILE = os.path.join(os.path.dirname(__file__), "pets.json")
MAX_DECAY_MSGS = 30
DECAY_INTERVAL = 24 * 3600

# ── 兑换码类型 ──
REDEEM_TYPE_STAT = "stat_point"   # 属性加点
REDEEM_TYPE_EXP = "exp"           # 经验值
REDEEM_UNLIMITED = -1             # 无限次数

# ── 确定性 PRNG ──

def fnv1a_32(data: bytes) -> int:
    h = 0x811C9DC5
    for b in data:
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h

class PRNG:
    """Mulberry32 确定性伪随机"""
    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF

    def next(self) -> float:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        t = (self.state ^ (self.state >> 15)) & 0xFFFFFFFF
        t = (t * (self.state | 1)) & 0xFFFFFFFF
        t ^= (t + ((self.state ^ (self.state >> 7)) * (self.state | 61))) & 0xFFFFFFFF
        return (t ^ (t >> 14)) / 0xFFFFFFFF

    def randint(self, lo: int, hi: int) -> int:
        return lo + int(self.next() * (hi - lo + 1))

    def choice(self, items: list):
        return items[self.randint(0, len(items) - 1)]

    def weighted_choice(self, items: list, weights: list):
        total = sum(weights)
        r = self.next() * total
        acc = 0
        for i, w in enumerate(weights):
            acc += w
            if r < acc:
                return items[i]
        return items[-1]

# ── 名称池 ──

FIRST_NAMES = ["小", "大", "阿", "胖", "瘦", "白", "黑", "花", "斑", "金",
               "银", "铜", "铁", "玉", "宝", "贝", "明", "亮", "星", "月",
               "云", "雨", "风", "雪", "天", "地", "灵", "玄", "紫", "青",
               "赤", "黄", "绿", "蓝", "红", "粉", "萌", "酷", "甜", "糖",
               "可", "爱", "乖", "皮", "闹", "懒", "馋", "憨", "呆", "傲"]
LAST_NAMES = ["虾", "鱼", "螺", "龟", "蟹", "虫", "猫", "狗", "鼠",
              "狐", "鸮", "兔", "龙", "狮", "熊", "凤", "鲲", "宝",
              "球", "团", "饼", "子", "儿", "蛋", "丸", "豆", "米", "糕",
              "条", "仔", "胖", "乖", "皮", "灵", "侠", "王", "神", "仙",
              "侠", "圣", "皇", "少", "姬", "娘", "妹", "哥", "爷", "君"]

# ── 属性生成 ──

STAT_NAMES = ["intelligence", "strength", "luck", "charisma", "zen"]
STAT_LABELS = {"intelligence": "智力", "strength": "力量", "luck": "运气",
               "charisma": "魅力", "zen": "定力"}

LEVELS = [
    ("幼年", 0), ("成长期", 100), ("成熟期", 300),
    ("觉醒", 600), ("传说", 1000),
]

# ── 宠物数据结构 ──
"""
pet = {
    "user_id": str,
    "owner": str,
    "species": str (key),
    "name": str,
    "shiny": bool,
    "rarity": str,
    "exp": int,
    "level": int (0-4),
    "hp": int (max=100),
    "hunger": int (0-100),
    "mood": int (0-100),
    "intelligence": int,
    "strength": int,
    "luck": int,
    "charisma": int,
    "zen": int,
    "personality": str,
    "prompts": list[str],
    "adopt_time": float,
    "last_action_time": float,
    "msg_count": int,
    "battle_wins": int,
    "battle_losses": int,
    "interaction_count": int,
}
"""

def _generate_stats(rng: PRNG):
    """生成5项属性：1峰80-100，1谷1-25，其余基线到基线+40"""
    baseline = rng.randint(40, 60)
    stats = {}
    peak_idx = rng.randint(0, 4)
    trough_idx = rng.randint(0, 4)
    while trough_idx == peak_idx:
        trough_idx = rng.randint(0, 4)
    for i in range(5):
        if i == peak_idx:
            stats[STAT_NAMES[i]] = rng.randint(80, 100)
        elif i == trough_idx:
            stats[STAT_NAMES[i]] = rng.randint(1, 25)
        else:
            stats[STAT_NAMES[i]] = rng.randint(baseline, baseline + 40)
    return stats

def _generate_soul(rng: PRNG, species_name: str):
    """生成灵魂（名字+性格+提示词）"""
    fn = rng.choice(FIRST_NAMES)
    ln = rng.choice(LAST_NAMES)
    if rng.next() < 0.3:
        name = f"{fn}{ln}"
    else:
        name = f"{species_name}{fn}{ln}" if rng.next() < 0.5 else f"{fn}{species_name}"
    PERSONALITIES = ["活泼", "憨厚", "机智", "傲娇", "温和", "冷酷", "粘人", "高冷",
                     "勇敢", "胆怯", "调皮", "文静", "霸气", "温柔"]
    PERSONALITY_SIG = {
        "活泼": "整天蹦蹦跳跳的，看着就很开心", "憨厚": "傻乎乎的，但特别招人喜欢",
        "机智": "眼珠子滴溜溜转，机灵得很", "傲娇": "嘴上不在乎，其实可喜欢你了",
        "温和": "相处起来让人特别舒服", "冷酷": "很高冷，但还是会偷偷看你",
        "粘人": "分分钟都想待在你身边", "高冷": "头仰得高高的，是个小女王/小王子",
        "勇敢": "天不怕地不怕，冲在最前面", "胆怯": "一点小事就躲到你身后",
        "调皮": "总喜欢恶作剧，让人哭笑不得", "文静": "安安静静的，是个乖宝宝",
        "霸气": "走路带风，气场全开", "温柔": "对谁都笑眯眯的，世界第一暖心",
    }
    personality = rng.choice(PERSONALITIES)
    sig = PERSONALITY_SIG.get(personality, f"性格{personality}")
    prompts = [
        rng.choice(FIRST_NAMES + ["超级", "非常", "有点"]),
        sig,
        rng.choice(["最喜欢你了", "想要变得更强大", "想和你一起去冒险",
                     "今天天气真好", "肚子有点饿了", "好想出去玩"]),
    ]
    return name, personality, prompts

def _pick_species(rng: PRNG):
    """加权随机选物种"""
    weights = [s["weight"] for s in SPECIES]
    return rng.weighted_choice(SPECIES, weights)

def _calc_level(exp: int) -> int:
    for i, (_, threshold) in reversed(list(enumerate(LEVELS))):
        if exp >= threshold:
            return i
    return 0

def _calc_max_hp(pet: dict) -> int:
    base = 50 + pet["strength"] * 5 + pet["charisma"] * 3
    level_bonus = pet["level"] * 20
    return min(base + level_bonus, 100)

# ── SQLite 数据库管理器 ──

class DatabaseManager:
    """SQLite 持久化层，替代 JSON 文件"""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._migrate_schema()
        self._migrate_from_json()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS pets (
                user_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL DEFAULT '',
                species TEXT NOT NULL DEFAULT '',
                species_name TEXT NOT NULL DEFAULT '',
                rarity TEXT NOT NULL DEFAULT 'common',
                stars TEXT NOT NULL DEFAULT '⭐',
                name TEXT NOT NULL DEFAULT '无名',
                shiny INTEGER NOT NULL DEFAULT 0,
                emoji TEXT NOT NULL DEFAULT '🐾',
                exp INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 0,
                level_name TEXT NOT NULL DEFAULT '幼年',
                hp INTEGER NOT NULL DEFAULT 100,
                max_hp INTEGER NOT NULL DEFAULT 100,
                hunger INTEGER NOT NULL DEFAULT 100,
                mood INTEGER NOT NULL DEFAULT 100,
                intelligence INTEGER NOT NULL DEFAULT 50,
                strength INTEGER NOT NULL DEFAULT 50,
                luck INTEGER NOT NULL DEFAULT 50,
                charisma INTEGER NOT NULL DEFAULT 50,
                zen INTEGER NOT NULL DEFAULT 50,
                personality TEXT NOT NULL DEFAULT '温和',
                personality_sig TEXT NOT NULL DEFAULT '性格温和',
                prompts TEXT NOT NULL DEFAULT '[]',
                adopt_time REAL NOT NULL DEFAULT 0,
                last_action_time REAL NOT NULL DEFAULT 0,
                msg_count INTEGER NOT NULL DEFAULT 0,
                battle_wins INTEGER NOT NULL DEFAULT 0,
                battle_losses INTEGER NOT NULL DEFAULT 0,
                interaction_count INTEGER NOT NULL DEFAULT 0,
                decay_count INTEGER NOT NULL DEFAULT 0,
                daily_battle_count INTEGER NOT NULL DEFAULT 0,
                daily_battle_date TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                value TEXT NOT NULL,
                max_uses INTEGER NOT NULL DEFAULT 1,
                used_count INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL DEFAULT 0,
                expires_at REAL
            );

            CREATE TABLE IF NOT EXISTS redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                user_id TEXT NOT NULL,
                redeemed_at REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (code) REFERENCES redeem_codes(code)
            );

            CREATE INDEX IF NOT EXISTS idx_redemptions_code ON redemptions(code);
            CREATE INDEX IF NOT EXISTS idx_redemptions_user ON redemptions(user_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_redemptions_code_user ON redemptions(code, user_id);
        """)
        self.conn.commit()

    def _migrate_schema(self):
        """迁移已有数据库，添加新列"""
        cur = self.conn.cursor()
        for col in [
            ("daily_battle_count", "INTEGER NOT NULL DEFAULT 0"),
            ("daily_battle_date", "TEXT NOT NULL DEFAULT ''"),
        ]:
            try:
                cur.execute(f"ALTER TABLE pets ADD COLUMN {col[0]} {col[1]}")
            except sqlite3.OperationalError:
                pass
        self.conn.commit()

    def _migrate_from_json(self):
        """从 pets.json 导入已有数据"""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pets")
        if cur.fetchone()[0] > 0:
            return  # 已有数据不重复导入
        if not os.path.exists(JSON_FILE):
            return
        try:
            with open(JSON_FILE, "r") as f:
                pets = json.load(f)
        except Exception:
            return
        for uid, pet in pets.items():
            self.save_pet(pet)

    def pet_to_row(self, pet: dict) -> dict:
        row = dict(pet)
        row["shiny"] = 1 if pet.get("shiny") else 0
        row["prompts"] = json.dumps(pet.get("prompts", []), ensure_ascii=False)
        return row

    def row_to_pet(self, row: sqlite3.Row) -> dict:
        pet = dict(row)
        pet["shiny"] = bool(pet["shiny"])
        pet["prompts"] = json.loads(pet.get("prompts", "[]"))
        return pet

    def get_pet(self, user_id: str) -> Optional[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM pets WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return self.row_to_pet(row) if row else None

    def save_pet(self, pet: dict):
        row = self.pet_to_row(pet)
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(f"{k}=excluded.{k}" for k in row.keys())
        sql = f"INSERT INTO pets ({cols}) VALUES ({placeholders}) ON CONFLICT(user_id) DO UPDATE SET {updates}"
        cur = self.conn.cursor()
        cur.execute(sql, list(row.values()))
        self.conn.commit()

    def delete_pet(self, user_id: str):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM pets WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def all_pets(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM pets")
        return [self.row_to_pet(row) for row in cur.fetchall()]

    def find_pet_by_name(self, name: str) -> list[dict]:
        """按宠物名查找宠物，返回匹配列表（可能有重名）"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM pets WHERE name = ?", (name,))
        return [self.row_to_pet(row) for row in cur.fetchall()]

    def get_leaderboard(self, by: str = "exp", top: int = 10) -> list[dict]:
        cur = self.conn.cursor()
        if by == "level":
            sql = "SELECT * FROM pets ORDER BY level DESC, exp DESC LIMIT ?"
        elif by == "battle":
            sql = "SELECT * FROM pets ORDER BY (battle_wins - battle_losses) DESC LIMIT ?"
        else:
            sql = "SELECT * FROM pets ORDER BY exp DESC LIMIT ?"
        cur.execute(sql, (top,))
        return [self.row_to_pet(row) for row in cur.fetchall()]

    # ── 兑换码 ──

    def create_redeem_code(self, code: str, code_type: str, value: dict,
                          max_uses: int = 1, created_by: str = "",
                          expires_at: Optional[float] = None) -> bool:
        """创建兑换码。返回值：是否创建成功（False=已存在）"""
        cur = self.conn.cursor()
        cur.execute("SELECT code FROM redeem_codes WHERE code = ?", (code,))
        if cur.fetchone():
            return False
        cur.execute(
            "INSERT INTO redeem_codes (code, type, value, max_uses, created_by, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (code, code_type, json.dumps(value, ensure_ascii=False),
             max_uses, created_by, time.time(), expires_at)
        )
        self.conn.commit()
        return True

    def use_redeem_code(self, code: str, user_id: str) -> Optional[dict]:
        """使用兑换码。成功返回 effect dict，失败返回 None"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM redeem_codes WHERE code = ?", (code,))
        row = cur.fetchone()
        if not row:
            return None  # 码不存在
        cd = dict(row)
        value = json.loads(cd["value"])
        # 检查过期
        if cd["expires_at"] and time.time() > cd["expires_at"]:
            return None  # 已过期
        # 检查次数
        if cd["max_uses"] != REDEEM_UNLIMITED and cd["used_count"] >= cd["max_uses"]:
            return None  # 次数用完
        # 检查用户是否已使用
        cur.execute("SELECT id FROM redemptions WHERE code = ? AND user_id = ?", (code, user_id))
        if cur.fetchone():
            return None  # 已使用过
        # 执行兑换
        effect = {"type": cd["type"], "value": value}
        cur.execute(
            "INSERT INTO redemptions (code, user_id, redeemed_at) VALUES (?, ?, ?)",
            (code, user_id, time.time())
        )
        cur.execute(
            "UPDATE redeem_codes SET used_count = used_count + 1 WHERE code = ?",
            (code,)
        )
        # 次数用完了自动删除
        if cd["max_uses"] != REDEEM_UNLIMITED and cd["used_count"] + 1 >= cd["max_uses"]:
            cur.execute("DELETE FROM redemptions WHERE code = ?", (code,))
            cur.execute("DELETE FROM redeem_codes WHERE code = ?", (code,))
        self.conn.commit()
        return effect

    def list_redeem_codes(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM redeem_codes ORDER BY created_at DESC")
        return [dict(row) for row in cur.fetchall()]

    def delete_redeem_code(self, code: str) -> bool:
        """删除兑换码及其所有兑换记录。返回值：是否删除成功"""
        cur = self.conn.cursor()
        cur.execute("SELECT code FROM redeem_codes WHERE code = ?", (code,))
        if not cur.fetchone():
            return False
        cur.execute("DELETE FROM redemptions WHERE code = ?", (code,))
        cur.execute("DELETE FROM redeem_codes WHERE code = ?", (code,))
        self.conn.commit()
        return True

    def close(self):
        self.conn.close()


# ── 引擎 API ──

class PetEngine:
    def __init__(self):
        self.db = DatabaseManager(DB_FILE)
        self.battle_mgr = BattleManager(self)

    # ── 领养 ──

    def adopt(self, user_id: str, owner: str) -> dict:
        if self.db.get_pet(user_id):
            return None
        seed = fnv1a_32(f"{user_id}:xiaobai-xxp-2025".encode("utf-8"))
        rng = PRNG(seed)
        species = _pick_species(rng)
        shiny = rng.next() < 0.01
        stats = _generate_stats(rng)
        name, personality, prompts = _generate_soul(rng, species["name"])
        # 特殊：神话隐藏——极小概率出虾皇
        if species["key"] == "kun" and rng.next() < 0.3:
            species = SHRIMP_KING
            name = "虾皇·至尊"
            personality = "霸者"
            prompts = ["万虾之王", "统领四海虾兵蟹将", "天上天下，唯虾独尊"]
        hp = _calc_max_hp({"strength": stats["strength"], "charisma": stats["charisma"], "level": 0})
        now = time.time()
        pet = {
            "user_id": user_id,
            "owner": owner,
            "species": species["key"],
            "species_name": species["name"],
            "rarity": species["rarity"],
            "stars": species["stars"],
            "name": name,
            "shiny": shiny,
            "emoji": species["emoji"],
            "exp": 0,
            "level": 0,
            "level_name": "幼年",
            "hp": hp,
            "max_hp": hp,
            "hunger": 100,
            "mood": 100,
            "intelligence": stats["intelligence"],
            "strength": stats["strength"],
            "luck": stats["luck"],
            "charisma": stats["charisma"],
            "zen": stats["zen"],
            "personality": personality,
            "personality_sig": f"性格{personality}",
            "prompts": prompts,
            "adopt_time": now,
            "last_action_time": now,
            "msg_count": 0,
            "battle_wins": 0,
            "battle_losses": 0,
            "interaction_count": 0,
        }
        self.db.save_pet(pet)
        return pet

    # ── 获取宠物 ──

    def get_pet(self, user_id: str) -> Optional[dict]:
        pet = self.db.get_pet(user_id)
        if pet:
            self._apply_decay(pet)
            self.db.save_pet(pet)  # 衰减后持久化
        return pet

    def get_pet_no_decay(self, user_id: str) -> Optional[dict]:
        return self.db.get_pet(user_id)

    # ── 互动 ──

    INTERACT_RESULTS = {
        "feed": {
            "ok": ["{owner}喂{name}吃了好吃的，{name}开心地摇着尾巴", "一顿美味的饱餐！{name}的肚子圆滚滚的"],
            "full": ["{name}已经吃饱了，再也吃不下了", "{name}打了个饱嗝，表示拒绝"],
        },
        "walk": {
            "ok": ["{owner}带{name}出去散步，{name}一路上蹦蹦跳跳", "风和日丽，{name}在外面玩得很开心"],
            "sad": ["{name}心情不太好，不想出去", "{name}趴在地上不肯动"],
        },
        "play": {
            "ok": ["{owner}和{name}一起玩耍，{name}高兴得转圈圈", "玩得太开心了！{name}用头蹭了蹭你"],
            "sad": ["{name}现在没心情玩", "{name}懒洋洋地看了你一眼，继续睡觉"],
        },
        "train": {
            "ok": ["{owner}对{name}进行了特训！{name}变得更强了", "魔鬼训练！{name}累趴了，但实力提升了"],
            "sad": ["{name}还太小，不能训练", "训练太苦了，{name}眼泪汪汪地看着你"],
        },
        "sleep": {
            "ok": ["{name}乖乖睡觉了，睡得很香", "{name}进入了甜美的梦乡，嘴角还挂着微笑"],
            "done": ["{name}已经睡饱了，精神抖擞"],
        },
        "pet": {
            "ok": ["{owner}摸了摸{name}的头，{name}舒服地眯起了眼睛", "摸一摸！{name}发出了舒服的咕噜声"],
            "sad": ["{name}害羞地躲开了", "{name}今天不想被摸"],
        },
    }

    def interact(self, user_id: str, action: str) -> str:
        pet = self.get_pet(user_id)
        if not pet:
            return "你还没有领养宠物，发送「领养宠物」来领养一只吧！"
        self._apply_decay(pet)
        owner = pet["owner"]
        name = pet["name"]
        emoji = pet.get("emoji", "")
        rng = PRNG(int(time.time() * 1000) & 0xFFFFFFFF)
        replies = self.INTERACT_RESULTS.get(action, {})

        def _fmt(text: str) -> str:
            return text.format(name=name, owner=owner)

        if action == "feed":
            if pet["hunger"] >= 100:
                msg = _fmt(rng.choice(replies.get("full", ["已经饱了"])))
            else:
                pet["hunger"] = min(100, pet["hunger"] + 20)
                pet["mood"] = min(100, pet["mood"] + 5)
                pet["exp"] += 10
                gain_exp = 10
                msg = _fmt(rng.choice(replies.get("ok", ["吃得好"]))) + f"\n饱食+20 心情+5 经验+{gain_exp}"
        elif action == "walk":
            if pet["mood"] < 20:
                msg = _fmt(rng.choice(replies.get("sad", ["不想出去"])))
            else:
                pet["mood"] = min(100, pet["mood"] + 10)
                pet["hunger"] = max(0, pet["hunger"] - 10)
                pet["exp"] += 15
                gain_exp = 15
                msg = _fmt(rng.choice(replies.get("ok", ["出去玩了"]))) + f"\n心情+10 饱食-10 经验+{gain_exp}"
        elif action == "play":
            if pet["mood"] < 15:
                msg = _fmt(rng.choice(replies.get("sad", ["不想玩"])))
            else:
                pet["mood"] = min(100, pet["mood"] + 15)
                pet["exp"] += 15
                gain_exp = 15
                msg = _fmt(rng.choice(replies.get("ok", ["玩得开心"]))) + f"\n心情+15 经验+{gain_exp}"
        elif action == "train":
            if pet["level"] < 1:
                msg = _fmt(replies.get("sad", ["太小不能训练"])[0])
            else:
                pet["strength"] = min(100, pet["strength"] + 3)
                pet["exp"] += 20
                gain_exp = 20
                msg = _fmt(rng.choice(replies.get("ok", ["训练成功"]))) + f"\n力量+3 经验+{gain_exp}"
        elif action == "sleep":
            pet["mood"] = min(100, pet["mood"] + 20)
            pet["hp"] = min(pet.get("max_hp", 100), pet["hp"] + 20)
            msg = _fmt(rng.choice(replies.get("ok", ["睡得好"]))) + "\n心情+20 HP+20"
        elif action == "pet":
            if pet["mood"] < 10:
                msg = _fmt(rng.choice(replies.get("sad", ["躲开了"])))
            else:
                pet["mood"] = min(100, pet["mood"] + 8)
                pet["exp"] += 5
                gain_exp = 5
                msg = _fmt(rng.choice(replies.get("ok", ["开心"]))) + f"\n心情+8 经验+{gain_exp}"
        else:
            return f"未知动作：{action}"
        # 经验升级检查
        old_level = pet["level"]
        new_level = _calc_level(pet["exp"])
        pet["level"] = new_level
        pet["level_name"] = LEVELS[new_level][0]
        if new_level > old_level:
            max_hp = _calc_max_hp(pet)
            pet["max_hp"] = max_hp
            pet["hp"] = min(pet["hp"] + 30, max_hp)
            msg += f"\n🎉 恭喜进化！{name} 已进入「{LEVELS[new_level][0]}」阶段！"
        pet["interaction_count"] = pet.get("interaction_count", 0) + 1
        pet["last_action_time"] = time.time()
        self.db.save_pet(pet)
        # 被动事件检查
        event_msg = self._check_passive_event(pet, rng)
        if event_msg:
            msg += "\n" + event_msg
        return f"{emoji} {msg}"

    # ── 改名 ──

    def rename(self, user_id: str, new_name: str) -> Optional[str]:
        pet = self.db.get_pet(user_id)
        if not pet:
            return None
        old = pet["name"]
        pet["name"] = new_name[:8]
        self.db.save_pet(pet)
        return f"{pet.get('emoji', '')} {old} 改名为 {new_name[:8]} 啦！"

    # ── 兑换码 ──

    def create_redeem_code(self, code: str, code_type: str, value: dict,
                          max_uses: int = 1, created_by: str = "",
                          expires_at: Optional[float] = None) -> str:
        """创建兑换码，返回提示消息"""
        ok = self.db.create_redeem_code(code, code_type, value, max_uses, created_by, expires_at)
        if not ok:
            return f"兑换码 {code} 已存在"
        type_cn = "属性点" if code_type == "stat_point" else code_type
        uses_cn = "无限次" if max_uses == REDEEM_UNLIMITED else f"{max_uses}次"
        return f"✅ 兑换码 {code} 创建成功\n类型:{type_cn} 次数:{uses_cn}"

    def redeem_code(self, code: str, user_id: str) -> str:
        """使用兑换码，对宠物生效后返回提示"""
        pet = self.db.get_pet(user_id)
        if not pet:
            return "你还没有领养宠物，发送「领养宠物」来领养一只吧！"
        effect = self.db.use_redeem_code(code, user_id)
        if not effect:
            return "兑换码无效或已过期/用完/已使用过"
        kind = effect["type"]
        val = effect["value"]
        if kind == "stat_point":
            stat = val.get("stat", "strength")
            points = val.get("points", 1)
            if stat in pet and isinstance(pet[stat], (int, float)):
                pet[stat] = min(100, pet[stat] + points)
                stat_cn = {"strength": "力量", "intelligence": "智力", "luck": "运气",
                           "charisma": "魅力", "zen": "定力"}.get(stat, stat)
                msg = f"✨ 兑换成功！{stat_cn}+{points}"
            else:
                msg = f"✨ 兑换成功（属性 {stat} 无法识别，未生效）"
        elif kind == "exp":
            exp_gain = val.get("exp", 0)
            pet["exp"] += exp_gain
            # 升级检查
            old_level = pet["level"]
            new_level = _calc_level(pet["exp"])
            pet["level"] = new_level
            if new_level > old_level:
                pet["level_name"] = LEVELS[new_level][0]
                max_hp = _calc_max_hp(pet)
                pet["max_hp"] = max_hp
                pet["hp"] = min(pet["hp"] + 30, max_hp)
                msg = f"✨ 兑换成功！经验+{exp_gain} 🎉 进化至「{LEVELS[new_level][0]}」阶段！"
            else:
                msg = f"✨ 兑换成功！经验+{exp_gain}"
        else:
            msg = f"✨ 兑换成功（未知类型）"
        self.db.save_pet(pet)
        return msg

    def delete_redeem_code(self, code: str) -> str:
        """删除兑换码，返回提示消息"""
        ok = self.db.delete_redeem_code(code)
        if not ok:
            return f"兑换码 {code} 不存在"
        return f"✅ 兑换码 {code} 已删除（包含其兑换记录）"

    # ── 衰减 ──

    def _apply_decay(self, pet: dict):
        now = time.time()
        dt = now - pet.get("last_action_time", now)
        msgs = pet.get("msg_count", 0)
        decayed = False
        if dt >= DECAY_INTERVAL or msgs >= MAX_DECAY_MSGS:
            if msgs >= MAX_DECAY_MSGS or dt >= DECAY_INTERVAL:
                zen = pet.get("zen", 0)
                factor = 0.5 if zen >= 60 else 1.0
                h_decay = int(5 * factor)
                m_decay = int(3 * factor)
                pet["hunger"] = max(0, pet["hunger"] - h_decay)
                pet["mood"] = max(0, pet["mood"] - m_decay)
                pet["msg_count"] = 0
                pet["last_action_time"] = now
                if "decay_count" not in pet:
                    pet["decay_count"] = 0
                pet["decay_count"] += 1
                decayed = True
            if pet["hunger"] < 10:
                pet["hp"] = max(1, pet["hp"] - 5)
        if not decayed:
            pet["msg_count"] = msgs + 1

    # ── 被动事件 ──

    PASSIVE_EVENTS = [
        ("捡到宝", "{name}在路边捡到一枚金币！经验+30"),
        ("学到招", "{name}突然领悟新技能！力量+2"),
        ("交好友", "{name}交到了一个好朋友！心情+15"),
        ("遇贵人", "{name}遇到了一位神秘老人，获得指点！智力+3"),
        ("撞大运", "{name}运气爆棚！捡到了一颗幸运石！运气+3"),
        ("躲一劫", "{name}差点遇到危险，但机智地躲过了！定力+3"),
    ]

    def _check_passive_event(self, pet: dict, rng: PRNG) -> Optional[str]:
        if rng.next() >= 0.05:
            return None
        event_name, template = rng.choice(self.PASSIVE_EVENTS)
        name = pet["name"]
        msg = template.format(name=name)
        if "经验" in msg:
            pet["exp"] += 30
        if "力量" in msg:
            pet["strength"] = min(100, pet["strength"] + 2)
        if "心情" in msg:
            pet["mood"] = min(100, pet["mood"] + 15)
        if "智力" in msg:
            pet["intelligence"] = min(100, pet["intelligence"] + 3)
        if "运气" in msg:
            pet["luck"] = min(100, pet["luck"] + 3)
        if "定力" in msg:
            pet["zen"] = min(100, pet["zen"] + 3)
        return f"✨ {event_name}：{msg}"

    # ── 社交事件 ──

    SOCIAL_EVENTS = [
        ("贴贴", "{a}和{b}贴在一起，感情变得更好了！{a}心情+10, {b}心情+10"),
        ("打架", "{a}和{b}打了一架！{a}HP-5, {b}HP-5"),
        ("送礼", "{a}送了{b}一份小礼物！{b}心情+15"),
        ("午睡", "{a}和{b}一起午睡，醒来精神抖擞！HP+10"),
        ("合唱", "{a}和{b}一起唱歌跳舞，开心极了！心情+20"),
    ]

    def get_social_event(self, pet_a: dict, pet_b: dict, rng: PRNG) -> Optional[str]:
        if rng.next() >= 0.30:
            return None
        ev_name, template = rng.choice(self.SOCIAL_EVENTS)
        a, b = pet_a["name"], pet_b["name"]
        msg = template.format(a=a, b=b)
        if "心情+10" in msg:
            pet_a["mood"] = min(100, pet_a["mood"] + 10)
            pet_b["mood"] = min(100, pet_b["mood"] + 10)
        if "HP-5" in msg:
            pet_a["hp"] = max(1, pet_a["hp"] - 5)
            pet_b["hp"] = max(1, pet_b["hp"] - 5)
        if "心情+15" in msg:
            pet_b["mood"] = min(100, pet_b["mood"] + 15)
        if "HP+10" in msg:
            mhp_a = pet_a.get("max_hp", 100)
            mhp_b = pet_b.get("max_hp", 100)
            pet_a["hp"] = min(mhp_a, pet_a["hp"] + 10)
            pet_b["hp"] = min(mhp_b, pet_b["hp"] + 10)
        if "心情+20" in msg:
            pet_a["mood"] = min(100, pet_a["mood"] + 20)
            pet_b["mood"] = min(100, pet_b["mood"] + 20)
        self.db.save_pet(pet_a)
        self.db.save_pet(pet_b)
        return f"🎉 {ev_name}：{msg}"

    # ── 对战 ──

    def battle(self, user_a: str, user_b: str) -> str:
        return self.battle_mgr.battle(user_a, user_b)

    def battle_by_name(self, attacker_id: str, target_name: str) -> str:
        """通过宠物名发起对战，每日限10次"""
        my_pet = self.db.get_pet(attacker_id)
        if not my_pet:
            return "你还没有宠物！发送「领养宠物」来领养一只吧。"

        matches = self.db.find_pet_by_name(target_name)
        if not matches:
            return f"没有找到叫「{target_name}」的宠物"

        # 排除自己的宠物
        matches = [p for p in matches if p["user_id"] != attacker_id]
        if not matches:
            return "不能和自己的宠物对战！"

        target_pet = matches[0]
        target_id = target_pet["user_id"]

        # 每日次数检查（北京时间）
        beijing = datetime.now(timezone(timedelta(hours=8)))
        today = beijing.strftime("%Y-%m-%d")
        daily_date = my_pet.get("daily_battle_date", "")
        daily_count = my_pet.get("daily_battle_count", 0)
        if daily_date == today and daily_count >= 10:
            return "你今天已经对战10次了，明天再来吧！"

        # 执行对战
        result = self.battle_mgr.battle(attacker_id, target_id)

        # 更新对战次数
        updated_pet = self.db.get_pet(attacker_id)
        if updated_pet:
            d = updated_pet.get("daily_battle_date", "")
            c = updated_pet.get("daily_battle_count", 0)
            if d != today:
                updated_pet["daily_battle_date"] = today
                updated_pet["daily_battle_count"] = 1
            else:
                updated_pet["daily_battle_count"] = c + 1
            self.db.save_pet(updated_pet)

        # 多只同名提示
        if len(matches) > 1:
            remaining = len(matches) - 1
            result = (
                f"（有 {len(matches) + 1} 只叫「{target_name}」的宠物，匹配到{target_pet['name']}）\n\n"
                + result
            )
        return result

    # ── 排行榜 ──

    def leaderboard(self, by: str = "exp", top: int = 10) -> str:
        all_pets = [p for p in self.db.all_pets() if p.get("species")]
        if not all_pets:
            return "还没有宠物上榜～"
        if by == "level":
            key = lambda p: (p.get("level", 0), p.get("exp", 0))
        elif by == "battle":
            key = lambda p: p.get("battle_wins", 0) - p.get("battle_losses", 0)
        else:
            key = lambda p: p.get("exp", 0)
        sorted_pets = sorted(all_pets, key=key, reverse=True)[:top]
        lines = ["🏆 宠物排行榜\n"]
        medal = ["🥇", "🥈", "🥉"]
        for i, pet in enumerate(sorted_pets):
            icon = medal[i] if i < 3 else f"{i+1}."
            exp = pet.get("exp", 0)
            w = pet.get("battle_wins", 0)
            l = pet.get("battle_losses", 0)
            shiny = "⚡" if pet.get("shiny") else ""
            name = pet.get("name", "??")
            lvl = pet.get("level_name", "幼年")
            species_n = pet.get("species_name", "??")
            lines.append(f"{icon} {shiny}{name} Lv.{pet.get('level', 0)}({lvl}) {species_n}")
            lines.append(f"   经验:{exp} 战绩:{w}胜{l}负")
        return "\n".join(lines)

    # ── 属性面板 ──

    def render_panel(self, user_id: str) -> str:
        pet = self.get_pet(user_id)
        if not pet:
            return None
        self._apply_decay(pet)
        species_key = pet["species"]
        art = get_art(species_key)
        art_lines = art.split("\n")
        # 构建面板
        shiny_tag = "⚡" if pet.get("shiny") else ""
        name = pet["name"]
        emoji = pet.get("emoji", "")
        rarity_cn = RARITY_NAMES.get(pet.get("rarity", "common"), "普通")
        hp_bar = "█" * int(pet["hp"] / 10) + "░" * (10 - int(pet["hp"] / 10))
        hun_bar = "█" * int(pet["hunger"] / 10) + "░" * (10 - int(pet["hunger"] / 10))
        mod_bar = "█" * int(pet["mood"] / 10) + "░" * (10 - int(pet["mood"] / 10))
        lines = [
            f"╔══════════════════════════╗",
            f"║  {shiny_tag}{emoji} {name} {pet.get('stars', '')}  ║",
            f"║  {rarity_cn} · {pet.get('level_name', '幼年')} Lv.{pet.get('level', 0)}  ║",
            f"╠══════════════════════════╣",
            f"║ HP: {hp_bar} {pet['hp']}/{pet.get('max_hp', 100)}  ║",
            f"║ 饱: {hun_bar} {pet['hunger']}/100  ║",
            f"║ 心: {mod_bar} {pet['mood']}/100  ║",
            f"╠══════════════════════════╣",
            f"║ 智:{pet['intelligence']:>3} 力:{pet['strength']:>3} 运:{pet['luck']:>3}  ║",
            f"║ 魅:{pet['charisma']:>3} 定:{pet['zen']:>3}  经验:{pet['exp']:>4} ║",
            f"╠══════════════════════════╣",
            f"║ {pet.get('personality_sig', '')}",
        ]
        # 计算面板高度
        panel_h = len(lines)
        # 拼接ASCII画（居中对齐宽度）
        art_block = "\n".join(f"  {l}" for l in art_lines)
        lines.append(f"╚══════════════════════════╝")
        full = "\n".join(lines)
        return f"{full}\n{art_block}\n{pet['owner']}的{pet['species_name']}「{shiny_tag}{name}」"

    # ── 全图鉴 ──

    def handbook(self) -> str:
        from collections import Counter
        all_pets = self.db.all_pets()
        # 已有物种
        owned = Counter(p.get("species") for p in all_pets if p.get("species"))
        total = len(all_pets)
        lines = ["📖 宠物图鉴\n"]
        for s in SPECIES:
            key = s["key"]
            cnt = owned.get(key, 0)
            check = "🐾" if cnt > 0 else "❌"
            lines.append(f"{check} {s['emoji']} {s['name']} {s['stars']} {RARITY_NAMES[s['rarity']]} ×{cnt}")
        # 特殊
        cnt_sk = owned.get("shrimp_king", 0)
        check_sk = "🐾" if cnt_sk > 0 else "❌"
        lines.append(f"\n{check_sk} 💎 虾皇 ⭐⭐⭐⭐⭐ 神话 ×{cnt_sk}")
        lines.append(f"\n共 {total} 只宠物")
        return "\n".join(lines)

# ── 对战管理器 ──

class BattleManager:
    def __init__(self, engine: PetEngine):
        self.engine = engine

    def battle(self, user_a: str, user_b: str) -> str:
        p1 = self.engine.get_pet(user_a)
        p2 = self.engine.get_pet(user_b)
        if not p1 or not p2:
            return "其中一方还没有宠物！"
        if p1["level"] < 1 or p2["level"] < 1:
            return "对战需要双方宠物达到成长期（Lv.1）以上！"
        rng = PRNG(int(time.time() * 10000) & 0xFFFFFFFF)
        score1 = p1["strength"] * 0.6 + p1["luck"] * 0.4
        score2 = p2["strength"] * 0.6 + p2["luck"] * 0.4
        upset = rng.next() < 0.1  # 10%冷门
        p1_wins = (score1 > score2) != upset
        winner, loser = (p1, p2) if p1_wins else (p2, p1)
        w_user, l_user = (user_a, user_b) if p1_wins else (user_b, user_a)
        # 胜负结果
        winner["battle_wins"] = winner.get("battle_wins", 0) + 1
        loser["battle_losses"] = loser.get("battle_losses", 0) + 1
        winner["exp"] += 30
        loser["exp"] += 10
        winner["hp"] = max(1, winner["hp"] - rng.randint(5, 15))
        loser["hp"] = max(1, loser["hp"] - rng.randint(10, 25))
        self.engine.db.save_pet(p1)
        self.engine.db.save_pet(p2)
        # 报道消息
        a, b = p1["name"], p2["name"]
        if upset:
            upset_msg = f"\n🔥 爆冷！{'%s' % (w_user if p1_wins else l_user)}的{winner['name']}展现了惊人的意志！"
        else:
            upset_msg = ""
        battle_lines = [
            f"⚔️ {a} VS {b} ⚔️",
            f"",
            f"【{a}】力:{p1['strength']} 运:{p1['luck']}",
            f"【{b}】力:{p2['strength']} 运:{p2['luck']}",
            f"",
            f"经过激烈的战斗……",
            f"🎉 {winner['name']} 获得了胜利！{upset_msg}",
            f"",
            f"📊 战后：",
            f"  {winner['name']}: 经验+30 HP-{rng.randint(5, 15)}",
            f"  {loser['name']}: 经验+10 HP-{rng.randint(10, 25)}",
        ]
        return "\n".join(battle_lines)
