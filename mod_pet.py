#!/usr/bin/env python3
"""宠物修改器 — 交互式向导"""

import os
import sys
import sqlite3
import shutil

DB_FILE = os.path.join(os.path.dirname(__file__), "pets.db")

STAT_LABELS = {
    "intelligence": "智力", "strength": "力量", "luck": "运气",
    "charisma": "魅力", "zen": "定力"
}
RARITY_NAMES = {"common": "普通", "rare": "稀有", "epic": "史诗",
                "legendary": "传说", "mythic": "神话"}
LEVEL_NAMES = ["幼年", "成长期", "成熟期", "觉醒期", "传说"]


def get_cols(cursor):
    """获取表所有列名"""
    cursor.execute("PRAGMA table_info(pets)")
    return [row[1] for row in cursor.fetchall()]


def list_pets(cursor):
    cursor.execute("SELECT rowid, * FROM pets ORDER BY owner")
    rows = cursor.fetchall()
    if not rows:
        print("  (数据库中没有宠物)")
        return []
    cols = get_cols(cursor)
    # 插入 rowid 后列数 +1
    all_cols = ["rowid"] + cols
    return rows, all_cols


def show_pet_info(pet_dict: dict):
    """显示宠物完整信息"""
    width = 40
    print()
    print("╔" + "═" * width + "╗")
    title = f"   {pet_dict['name']}  ({pet_dict['owner']})"
    print("║" + title.ljust(width) + "║")
    print("╠" + "═" * width + "╣")
    info = [
        ("物种", f"{pet_dict.get('emoji', '')} {pet_dict['species_name']}"),
        ("稀有度", f"{pet_dict['rarity']} {RARITY_NAMES.get(pet_dict['rarity'], pet_dict['rarity'])}"),
        ("等级", f"Lv.{pet_dict['level']} ({LEVEL_NAMES[pet_dict['level']]})"),
        ("经验", str(pet_dict['exp'])),
        ("HP", f"{pet_dict['hp']} / {pet_dict['max_hp']}"),
        ("饱食度", str(pet_dict['hunger'])),
        ("心情", str(pet_dict['mood'])),
        ("", ""),
        ("─ 属性", "─" * 20),
    ]
    for sn in ["intelligence", "strength", "luck", "charisma", "zen"]:
        info.append((f"  {STAT_LABELS[sn]}", str(pet_dict.get(sn, 0))))
    info += [
        ("", ""),
        ("─ 对战", "─" * 20),
        ("  胜场", str(pet_dict.get("battle_wins", 0))),
        ("  负场", str(pet_dict.get("battle_losses", 0))),
        ("  互动次数", str(pet_dict.get("interaction_count", 0))),
    ]
    for label, value in info:
        if not label:
            continue
        line = f"  {label}: {value}"
        print("║" + line.ljust(width) + "║")
    print("╚" + "═" * width + "╝")


def pick_pet(rows, cols):
    """让用户选择宠物"""
    print("\n" + "=" * 50)
    print("  选择要修改的宠物")
    print("=" * 50)
    for i, row in enumerate(rows, 1):
        name = row[cols.index("name")]
        owner = row[cols.index("owner")]
        species = row[cols.index("species_name")]
        level = row[cols.index("level")]
        emoji = row[cols.index("emoji")]
        rarity = row[cols.index("rarity")]
        exp = row[cols.index("exp")]
        print(f"  [{i:>2}] {emoji} {name}  (主人:{owner}  {species}  Lv.{level}  {RARITY_NAMES.get(rarity,'')}  exp:{exp})")
    print("  [0]  退出")
    print("─" * 50)
    while True:
        raw = input("\n  选择序号: ").strip()
        if raw == "0":
            return None
        try:
            idx = int(raw)
            if 1 <= idx <= len(rows):
                return rows[idx - 1], cols
        except ValueError:
            pass
        print("  无效选择，请重新输入")


def input_int(prompt_text: str, current=None, min_v=None, max_v=None):
    """输入整数，回车保留当前值"""
    suffix = f" (当前: {current})" if current is not None else ""
    range_hint = ""
    if min_v is not None and max_v is not None:
        range_hint = f" [{min_v}-{max_v}]"
    while True:
        raw = input(f"  {prompt_text}{range_hint}{suffix}: ").strip()
        if not raw and current is not None:
            return current
        try:
            val = int(raw)
            if min_v is not None and val < min_v:
                print(f"  最小值为 {min_v}")
                continue
            if max_v is not None and val > max_v:
                print(f"  最大值为 {max_v}")
                continue
            return val
        except ValueError:
            print("  请输入有效数字")


def input_text(prompt_text: str, current=None):
    """输入文本，回车保留当前值"""
    suffix = f" (当前: {current})" if current is not None else ""
    raw = input(f"  {prompt_text}{suffix}: ").strip()
    if not raw and current is not None:
        return current
    return raw


def confirm(prompt_text: str) -> bool:
    while True:
        raw = input(f"  {prompt_text} [Y/n]: ").strip().lower()
        if not raw:
            return True
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False


def edit_menu(pet_dict: dict) -> tuple:
    """交互式修改，返回 (字段名列表, 新值列表) 或 None"""
    changes = {}

    print("\n" + "=" * 50)
    print("  选择要修改的项目")
    print("=" * 50)
    print("  [1]  基础信息 (名字/物种/稀有度/等级)")
    print("  [2]  五维属性 (智力/力量/运气/魅力/定力)")
    print("  [3]  状态数值 (HP/饱食/心情/经验)")
    print("  [4]  对战数据 (胜场/负场/互动次数)")
    print("  [5]  一键拉满 (全属性100 + 传说Lv.5 + 满HP)")
    print("  [0]  返回上级")

    while True:
        raw = input("\n  选择 (0-5): ").strip()
        if raw == "0":
            return None
        if raw == "1":
            # 基础信息
            name = input_text("名字", pet_dict.get("name", ""))
            if name != pet_dict.get("name"):
                changes["name"] = name

            species = input_text("物种名 (如 鲲/神虾/灵猫)", pet_dict.get("species_name", ""))
            if species != pet_dict.get("species_name"):
                changes["species_name"] = species

            emoji = input_text("Emoji (如 🐉/🦐/🐱)", pet_dict.get("emoji", ""))
            if emoji != pet_dict.get("emoji"):
                changes["emoji"] = emoji

            print("\n  稀有度:")
            rarity_keys = list(RARITY_NAMES.keys())
            for i, k in enumerate(rarity_keys, 1):
                print(f"    [{i}] {RARITY_NAMES[k]}")
            while True:
                r = input(f"  选择稀有度 (当前: {pet_dict.get('rarity','')}): ").strip()
                if not r:
                    break
                try:
                    idx = int(r)
                    if 1 <= idx <= len(rarity_keys):
                        changes["rarity"] = rarity_keys[idx - 1]
                        break
                except ValueError:
                    pass
                print("  无效选择")

            # 星星自动匹配稀有度
            rarity_stars = {"common": "⭐", "rare": "⭐⭐", "epic": "⭐⭐⭐",
                           "legendary": "⭐⭐⭐⭐", "mythic": "⭐⭐⭐⭐⭐"}
            new_rarity = changes.get("rarity", pet_dict.get("rarity", "common"))
            changes["stars"] = rarity_stars.get(new_rarity, "⭐")

            level = input_int("等级 (0-4)", pet_dict.get("level", 0), 0, 4)
            if level != pet_dict.get("level"):
                changes["level"] = level
                changes["level_name"] = LEVEL_NAMES[level]

            exp = input_int("经验值", pet_dict.get("exp", 0), 0)
            if exp != pet_dict.get("exp"):
                changes["exp"] = exp
            break

        elif raw == "2":
            # 五维属性
            for sn, label in STAT_LABELS.items():
                val = input_int(f"{label} (0-100)", pet_dict.get(sn, 50), 0, 100)
                if val != pet_dict.get(sn):
                    changes[sn] = val
            break

        elif raw == "3":
            # 状态数值
            hp = input_int("当前 HP", pet_dict.get("hp", 100), 1)
            if hp != pet_dict.get("hp"):
                changes["hp"] = hp

            max_hp = input_int("最大 HP", pet_dict.get("max_hp", 100), 1)
            if max_hp != pet_dict.get("max_hp"):
                changes["max_hp"] = max_hp

            hunger = input_int("饱食度 (0-100)", pet_dict.get("hunger", 100), 0, 100)
            if hunger != pet_dict.get("hunger"):
                changes["hunger"] = hunger

            mood = input_int("心情 (0-100)", pet_dict.get("mood", 100), 0, 100)
            if mood != pet_dict.get("mood"):
                changes["mood"] = mood

            exp = input_int("经验值", pet_dict.get("exp", 0), 0)
            if exp != pet_dict.get("exp"):
                changes["exp"] = exp
                # 自动重算等级
                level_table = [("幼年", 0), ("成长期", 100), ("成熟期", 300),
                              ("觉醒期", 600), ("传说", 1000)]
                new_lv = 0
                for i, (_, thr) in reversed(list(enumerate(level_table))):
                    if exp >= thr:
                        new_lv = i
                        break
                changes["level"] = new_lv
                changes["level_name"] = LEVEL_NAMES[new_lv]
            break

        elif raw == "4":
            # 对战数据
            wins = input_int("胜场", pet_dict.get("battle_wins", 0), 0)
            if wins != pet_dict.get("battle_wins"):
                changes["battle_wins"] = wins

            losses = input_int("负场", pet_dict.get("battle_losses", 0), 0)
            if losses != pet_dict.get("battle_losses"):
                changes["battle_losses"] = losses

            interact = input_int("互动次数", pet_dict.get("interaction_count", 0), 0)
            if interact != pet_dict.get("interaction_count"):
                changes["interaction_count"] = interact
            break

        elif raw == "5":
            # 一键拉满
            if not confirm("确定将宠物拉到最强？"):
                return None
            changes = {
                "strength": 100, "intelligence": 100, "luck": 100,
                "charisma": 100, "zen": 100,
                "level": 4, "level_name": "传说",
                "exp": 5000,
                "hp": 100, "max_hp": 100,
                "hunger": 100, "mood": 100,
            }
            break
        else:
            print("  无效选择")

    if not changes:
        print("\n  没有做任何修改")
        return None

    # 自动计算 max_hp（如果改了 strength/charisma 但没有显式设 max_hp）
    if ("strength" in changes or "charisma" in changes) and "max_hp" not in changes:
        s = changes.get("strength", pet_dict.get("strength", 50))
        c = changes.get("charisma", pet_dict.get("charisma", 50))
        lv = changes.get("level", pet_dict.get("level", 0))
        new_max = min(50 + s * 5 + c * 3 + lv * 20, 100)
        changes["max_hp"] = new_max

    # 显示变更内容
    print("\n" + "─" * 40)
    print("  即将修改：")
    for k, v in changes.items():
        old = pet_dict.get(k, "—")
        label = STAT_LABELS.get(k, k)
        print(f"    {label}: {old} → {v}")
    print("─" * 40)

    if not confirm("确认修改"):
        return None

    return list(changes.keys()), list(changes.values())


def main():
    if not os.path.exists(DB_FILE):
        print(f"错误：找不到数据库文件 {DB_FILE}")
        sys.exit(1)

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    rows_result = list_pets(cursor)
    if not rows_result:
        print("数据库中没有宠物，无法修改")
        conn.close()
        return

    rows, cols = rows_result

    result = pick_pet(rows, cols)
    if result is None:
        print("退出")
        conn.close()
        return

    row, cols = result
    pet_dict = dict(row)

    show_pet_info(pet_dict)

    edits = edit_menu(pet_dict)
    if edits is None:
        print("\n未做修改，退出")
        conn.close()
        return

    fields, values = edits
    if not fields:
        conn.close()
        return

    # 执行 UPDATE
    set_clause = ", ".join(f"{f} = ?" for f in fields)
    sql = f"UPDATE pets SET {set_clause} WHERE user_id = ?"
    cursor.execute(sql, values + [pet_dict["user_id"]])
    conn.commit()

    print(f"\n✅ 修改成功！共更新 {len(fields)} 个字段")
    print()

    # 显示修改后的状态
    cursor.execute("SELECT * FROM pets WHERE user_id = ?", (pet_dict["user_id"],))
    updated = dict(cursor.fetchone())
    show_pet_info(updated)

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已退出")
        sys.exit(0)