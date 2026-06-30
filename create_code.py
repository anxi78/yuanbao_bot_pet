#!/usr/bin/env python3
"""兑换码管理 - 交互式脚本 (主菜单循环运行，用户主动退出才结束)"""

import json
import random
import string
import sys
import time
from datetime import datetime, timedelta

from prompt_toolkit import prompt
from prompt_toolkit.validation import Validator, ValidationError
from prompt_toolkit.styles import Style

from pet_engine import PetEngine, REDEEM_TYPE_STAT, REDEEM_TYPE_EXP, REDEEM_UNLIMITED


STAT_OPTIONS = {
    "1": ("力量", "strength"),
    "2": ("智力", "intelligence"),
    "3": ("运气", "luck"),
    "4": ("魅力", "charisma"),
    "5": ("定力", "zen"),
}

TYPES = {
    "1": ("属性加点", REDEEM_TYPE_STAT),
    "2": ("经验值", REDEEM_TYPE_EXP),
}

# ── 样式 ──
style = Style.from_dict({
    "prompt": "ansicyan bold",
    "info": "ansigreen",
    "error": "ansired bold",
    "label": "ansiyellow",
})

# ── 随机生成中文兑换码用字 ──
CHARSET = string.ascii_uppercase + string.digits + "元宝运好气定神闲"

# ── 验证器 ──

class IntValidator(Validator):
    def __init__(self, default=None):
        self.default = default

    def validate(self, document):
        text = document.text.strip()
        if not text and self.default is not None:
            return
        if not text:
            raise ValidationError(message="请输入有效数字")
        try:
            int(text)
        except ValueError:
            raise ValidationError(message="请输入有效数字")


class CodeValidator(Validator):
    def validate(self, document):
        text = document.text.strip()
        if not text:
            raise ValidationError(message="兑换码不能为空")


# ── 辅助函数 ──

def rand_code(length=8):
    return "".join(random.choices(CHARSET, k=length))


def prompt_int(label, default=None):
    val = prompt(
        [("class:label", label)],
        style=style,
        validator=IntValidator(default),
        validate_while_typing=False,
    ).strip()
    if not val and default is not None:
        return default
    return int(val)


def prompt_optional(label):
    return prompt(
        [("class:label", label)],
        style=style,
    ).strip()


def choose(options: dict, label: str) -> str:
    print()
    for k, (label_text, _) in options.items():
        print(f"  [{k}] {label_text}")

    while True:
        raw = prompt(
            [("class:label", label + " ")],
            style=style,
        ).strip()
        if raw in options:
            return options[raw][1]
        print("  无效选择，请重新输入")


def input_expires_pt() -> float | None:
    while True:
        raw = prompt(
            [("class:label", "  过期时间 (留空=永久, 1h/1d/7d/2025-12-31): ")],
            style=style,
        ).strip()
        if not raw:
            return None

        now = datetime.now()
        if raw.endswith("h"):
            try:
                hours = int(raw[:-1])
                return (now + timedelta(hours=hours)).timestamp()
            except ValueError:
                print("  格式无效，格式如: 1h / 2d / 2025-12-31")
                continue
        if raw.endswith("d"):
            try:
                days = int(raw[:-1])
                return (now + timedelta(days=days)).timestamp()
            except ValueError:
                print("  格式无效，格式如: 1h / 2d / 2025-12-31")
                continue
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d")
            return dt.timestamp()
        except ValueError:
            print("  格式无效，格式如: 1h / 2d / 2025-12-31")
            continue


def confirm(msg: str, default_yes=True) -> bool:
    suffix = " [Y/n]: " if default_yes else " [y/N]: "
    while True:
        raw = prompt(
            [("class:label", msg + suffix)],
            style=style,
        ).strip().lower()
        if not raw:
            return default_yes
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  请输入 y 或 n")


def fmt_code(cd: dict) -> str:
    """格式化单个兑换码信息用于显示"""
    if cd["type"] == REDEEM_TYPE_STAT:
        type_cn = "属性加点"
    elif cd["type"] == REDEEM_TYPE_EXP:
        type_cn = "经验值"
    else:
        type_cn = cd["type"]

    value = cd["value"]
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            pass

    if isinstance(value, dict):
        if "stat" in value:
            value_str = f"属性={value['stat']} 点数={value['points']}"
        elif "exp" in value:
            value_str = f"经验={value['exp']}"
        else:
            value_str = str(value)
    else:
        value_str = str(value)

    uses = "无限" if cd["max_uses"] == REDEEM_UNLIMITED else f"{cd['used_count']}/{cd['max_uses']}"

    expires = "永久"
    if cd.get("expires_at"):
        try:
            dt = datetime.fromtimestamp(cd["expires_at"])
            expires = dt.strftime("%Y-%m-%d %H:%M")
            if time.time() > cd["expires_at"]:
                expires += " (已过期)"
        except Exception:
            expires = str(cd["expires_at"])

    created = cd.get("created_by", "") or "未知"
    created_at = ""
    if cd.get("created_at"):
        try:
            created_at = datetime.fromtimestamp(cd["created_at"]).strftime("%Y-%m-%d %H:%M")
        except Exception:
            created_at = str(cd["created_at"])

    return (
        f"   兑换码: {cd['code']}\n"
        f"   类型:   {type_cn}\n"
        f"   参数:   {value_str}\n"
        f"   次数:   {uses}\n"
        f"   过期:   {expires}\n"
        f"   创建者: {created}\n"
        f"   创建于: {created_at}"
    )


# ── 功能模块 ──

def do_create(engine: PetEngine):
    """创建兑换码"""
    print("\n" + "=" * 40)
    print("  创建兑换码")
    print("=" * 40 + "\n")

    example = rand_code()
    raw_code = prompt(
        [("class:label", f"兑换码 (留空随机生成，如 {example}): ")],
        style=style,
        validator=CodeValidator(),
        validate_while_typing=False,
    ).strip()
    code = raw_code if raw_code else rand_code()
    print(f"  兑换码: {code}")

    code_type = choose(TYPES, "选择类型")
    type_labels = {REDEEM_TYPE_STAT: "属性加点", REDEEM_TYPE_EXP: "经验值"}
    print(f"  类型: {type_labels[code_type]}")

    if code_type == REDEEM_TYPE_STAT:
        stat = choose(STAT_OPTIONS, "选择属性")
        points = prompt_int("  加点数值 (默认5): ", 5)
        value = {"stat": stat, "points": points}
        print(f"  参数: {value}")
    else:
        exp = prompt_int("  经验值 (默认100): ", 100)
        value = {"exp": exp}
        print(f"  参数: {value}")

    uses_str = prompt(
        [("class:label", "  最大使用次数 (留空=1次, -1=无限): ")],
        style=style,
    ).strip()
    if uses_str == "-1":
        max_uses = REDEEM_UNLIMITED
    elif uses_str:
        max_uses = int(uses_str)
    else:
        max_uses = 1

    expires_at = input_expires_pt()
    created_by = prompt_optional("  创建者 (留空=未知): ")

    print("\n" + "─" * 35)
    print("  确认信息")
    print("─" * 35)
    print(f"  兑换码: {code}")
    print(f"  类型:   {type_labels[code_type]}")
    print(f"  参数:   {value}")
    print(f"  次数:   {'无限' if max_uses == REDEEM_UNLIMITED else max_uses}")
    print(f"  过期:   {'永不过期' if expires_at is None else datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M')}")
    print(f"  创建者: {created_by or '未知'}")
    print("─" * 35)

    if not confirm("\n确认创建"):
        print("已取消")
        return

    msg = engine.create_redeem_code(code, code_type, value, max_uses, created_by, expires_at)
    print(f"\n{msg}")


def do_list(engine: PetEngine):
    """列出所有兑换码"""
    codes = engine.db.list_redeem_codes()
    if not codes:
        print("\n暂无兑换码")
        return

    print(f"\n共 {len(codes)} 个兑换码：")
    print("─" * 40)
    for i, cd in enumerate(codes, 1):
        print(f"\n[{i}]")
        print(fmt_code(cd))
        print("─" * 40)


def do_delete(engine: PetEngine):
    """删除兑换码"""
    codes = engine.db.list_redeem_codes()
    if not codes:
        print("\n暂无兑换码，无需删除")
        return

    print(f"\n共 {len(codes)} 个兑换码，请选择要删除的序号：")
    print("─" * 50)
    for i, cd in enumerate(codes, 1):
        # 简略显示
        type_cn = "属性" if cd["type"] == REDEEM_TYPE_STAT else "经验"
        uses = "无限" if cd["max_uses"] == REDEEM_UNLIMITED else f"{cd['used_count']}/{cd['max_uses']}"
        print(f"  [{i:>2}] {cd['code']}  ({type_cn}  次数:{uses})")
    print("  [0] 返回主菜单")
    print("─" * 50)

    raw = prompt(
        [("class:label", "请输入序号: ")],
        style=style,
    ).strip()

    if not raw:
        return
    try:
        idx = int(raw)
    except ValueError:
        print("  无效输入")
        return

    if idx == 0:
        return
    if idx < 1 or idx > len(codes):
        print("  序号超出范围")
        return

    cd = codes[idx - 1]
    print(f"\n  选中兑换码: {cd['code']}")
    print(fmt_code(cd))

    if not confirm(f"\n确认删除兑换码「{cd['code']}」"):
        print("已取消")
        return

    msg = engine.delete_redeem_code(cd["code"])
    print(f"\n{msg}")


# ── 主菜单 ──

MENU_OPTIONS = {
    "1": ("创建兑换码", do_create),
    "2": ("删除兑换码", do_delete),
    "3": ("列出兑换码", do_list),
    "0": ("退出", None),
}


def show_menu():
    print("\n" + "╔" + "═" * 38 + "╗")
    print("║" + "  兑换码管理系统".center(34) + "║")
    print("╠" + "═" * 38 + "╣")
    for k, (label, _) in MENU_OPTIONS.items():
        print(f"║   [{k}] {label}".ljust(40) + "║")
    print("╚" + "═" * 38 + "╝")


def main():
    engine = PetEngine()
    print("\n欢迎使用兑换码管理系统！输入 Ctrl+C 或选 0 退出")

    while True:
        show_menu()
        raw = prompt(
            [("class:prompt", "\n请选择操作 (0-3): ")],
            style=style,
        ).strip()

        if raw == "0" or raw.lower() in ("exit", "quit", "q"):
            print("\n再见！")
            break

        if raw not in MENU_OPTIONS:
            print("  无效选择，请输入 0-3")
            continue

        _, func = MENU_OPTIONS[raw]
        try:
            func(engine)
        except KeyboardInterrupt:
            print("\n  已取消")
            continue

        input("\n按 Enter 继续...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n再见！")
        sys.exit(0)
