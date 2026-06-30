"""
宠物 ASCII 字符画 & 物种定义
"""
from typing import Optional

# ── 物种定义 ──

SPECIES = [
    # ⭐ 普通 (60%)
    {"name": "虾", "emoji": "🦐", "rarity": "common", "stars": "⭐", "key": "shrimp", "weight": 9},
    {"name": "鱼", "emoji": "🐟", "rarity": "common", "stars": "⭐", "key": "fish", "weight": 9},
    {"name": "螺", "emoji": "🐌", "rarity": "common", "stars": "⭐", "key": "snail", "weight": 7},
    {"name": "龟", "emoji": "🐢", "rarity": "common", "stars": "⭐", "key": "turtle", "weight": 7},
    {"name": "蟹", "emoji": "🦀", "rarity": "common", "stars": "⭐", "key": "crab", "weight": 7},
    {"name": "虫", "emoji": "🐛", "rarity": "common", "stars": "⭐", "key": "bug", "weight": 5},
    {"name": "猫", "emoji": "🐱", "rarity": "common", "stars": "⭐", "key": "cat", "weight": 9},
    {"name": "狗", "emoji": "🐶", "rarity": "common", "stars": "⭐", "key": "dog", "weight": 5},
    {"name": "鼠", "emoji": "🐹", "rarity": "common", "stars": "⭐", "key": "hamster", "weight": 3},
    # ⭐⭐ 稀有 (25%)
    {"name": "狐", "emoji": "🦊", "rarity": "rare", "stars": "⭐⭐", "key": "fox", "weight": 12},
    {"name": "鸮", "emoji": "🦉", "rarity": "rare", "stars": "⭐⭐", "key": "owl", "weight": 8},
    {"name": "兔", "emoji": "🐰", "rarity": "rare", "stars": "⭐⭐", "key": "rabbit", "weight": 5},
    # ⭐⭐⭐ 史诗 (10%)
    {"name": "龙", "emoji": "🐲", "rarity": "epic", "stars": "⭐⭐⭐", "key": "dragon", "weight": 4},
    {"name": "狮", "emoji": "🦁", "rarity": "epic", "stars": "⭐⭐⭐", "key": "lion", "weight": 3},
    {"name": "熊", "emoji": "🐼", "rarity": "epic", "stars": "⭐⭐⭐", "key": "bear", "weight": 3},
    # ⭐⭐⭐⭐ 传说 (4%)
    {"name": "凤", "emoji": "🔥", "rarity": "legendary", "stars": "⭐⭐⭐⭐", "key": "phoenix", "weight": 2},
    {"name": "独角兽", "emoji": "🦄", "rarity": "legendary", "stars": "⭐⭐⭐⭐", "key": "unicorn", "weight": 2},
    # ⭐⭐⭐⭐⭐ 神话 (1%)
    {"name": "鲲", "emoji": "🐾", "rarity": "mythic", "stars": "⭐⭐⭐⭐⭐", "key": "kun", "weight": 1},
]

# 特殊隐藏宠物（虾皇）
SHRIMP_KING = {"name": "虾皇", "emoji": "💎", "rarity": "mythic", "stars": "⭐⭐⭐⭐⭐", "key": "shrimp_king", "weight": 1}

RARITY_NAMES = {
    "common": "普通", "rare": "稀有", "epic": "史诗",
    "legendary": "传说", "mythic": "神话",
}

# ── ASCII 字符画 ──

ART = {
    # ⭐ 普通
    "shrimp": [
        "  )))))))",
        " /  ___  \\",
        "(  (   )  )",
        " \\  \\_/  /",
        "  )))))))",
    ],
    "fish": [
        "   ><((°>",
        "  / \\__/ \\",
        " |  o  o  |",
        "  \\  \\__/  /",
        "   \\______/",
    ],
    "snail": [
        "  .-\"\"-.",
        " | o  o |",
        " |  __  |",
        "  '-..-'",
        "    ~~",
    ],
    "turtle": [
        "  .-\"\"-.",
        " / o  o \\",
        "|   __   |",
        " \\ '  ' /",
        "  '-..-'",
    ],
    "crab": [
        "   /\\  /\\",
        "   \\ \\/ /",
        "     )  (",
        "    /_/\\_\\",
    ],
    "bug": [
        "   __",
        "  (())",
        "   ||",
        "  (())",
        "   ~~",
    ],
    "cat": [
        "  /\\_/\\",
        " ( · · )",
        "  > ^ <",
        " /|   |\\",
        "_|   |_",
    ],
    "dog": [
        "   __",
        "  /  \\_",
        " |  o o|",
        "  \\   _/",
        "   \\__/",
    ],
    "hamster": [
        "   (\\",
        "   /  \\",
        " (\\__/)",
        " (o  o)",
        "  `--'",
    ],
    # ⭐⭐ 稀有
    "fox": [
        "     /\\",
        "    /  \\___",
        "   |  o   o |",
        "    \\  >v<  /",
        "     |    |",
        "     |____|",
    ],
    "owl": [
        "    ,_,",
        "   ( -.-)",
        "  /     \\",
        " |  o   o |",
        " |   > <  |",
        " \\_______/",
    ],
    "rabbit": [
        "   (\\",
        "   /  \\_",
        " |  o o|",
        " |  ^  |",
        " /|    |\\",
        "_|    |_",
    ],
    # ⭐⭐⭐ 史诗
    "dragon": [
        "     /\\",
        "    /  \\___",
        "   |  o   o |~~~|",
        "    \\   ^   /  /|",
        "     |   |  /  |",
        "     |___| /__ |",
    ],
    "lion": [
        "   _____",
        "  /     \\",
        " | o   o |",
        " |   >   |",
        " |  ___  |",
        " \\_/   \\_/",
    ],
    "bear": [
        "   _____",
        "  /     \\",
        " | o   o |",
        " |   v   |",
        " |  ___  |",
        " \\_/   \\_/",
    ],
    # ⭐⭐⭐⭐ 传说
    "phoenix": [
        "     \\   /",
        "      \\ /",
        "   /\\_/\\_/\\",
        "  | o   o  |",
        "  |   ^    |",
        "   \\  |  /",
        "    | | |",
        "  ~~| | |~~",
    ],
    "unicorn": [
        "     \\   /",
        "      \\ /",
        "   /\\_/\\_/\\",
        "  | o   o  |",
        "  |  \\|/   |",
        "   \\  |  /",
        "    | | |",
        "  ~~| | |~~",
    ],
    # ⭐⭐⭐⭐⭐ 神话
    "kun": [
        "        .-\"\"-.",
        "      .'  _  `.",
        "    /   _/ \\_   \\",
        "   |  _/     \\_  |",
        "   |_/  .-.   \\_|",
        "      _/   \\_",
        "    .'       `.",
        "  .'___________`.",
    ],
    "shrimp_king": [
        "  ))))))))))))))))",
        " /  _____  \\",
        "|  (👑)   |",
        "|  \\___/  |",
        "|   \\ /   |",
        "|    |    |",
        "|   / \\   |",
        "|  /   \\  |",
        ")))))))))))))))",
    ],
}


def get_art(species_key: str) -> str:
    """获取某个物种的 ASCII 字符画（多行字符串）"""
    lines = ART.get(species_key)
    if not lines:
        return "(无画像)"
    return "\n".join(lines)


def wrap_shiny(art: str, name: str) -> str:
    """闪光宠物包装：加 ✨ 标记"""
    return f"✨ ⚡{name} ⚡ ✨\n{art}"


def species_by_key(key: str) -> Optional[dict]:
    """通过 key 查找物种定义"""
    for s in SPECIES:
        if s["key"] == key:
            return s
    if key == "shrimp_king":
        return SHRIMP_KING
    return None
