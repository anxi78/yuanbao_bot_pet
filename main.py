#!/usr/bin/env python3
"""
元宝宠物 Bot — 独立版本
"""
import asyncio
import json
import hashlib
import hmac
import random
import string
import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta

import requests
import websockets

from pet_engine import PetEngine

# ── 配置 ──
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

APP_KEY = config["APP_KEY"]
APP_SECRET = config["APP_SECRET"]
API_DOMAIN = config.get("API_DOMAIN", "bot-openapi.yuanbao.tencent.com")
WS_URL = config["WS_URL"]
GROUP_CODE = config.get("GROUP_CODE", "")
GROUP_CODE_BLACKLIST = config.get("GROUP_CODE_BLACKLIST", [])
DEBUG = config.get("DEBUG", False)
BOT_ID = config.get("BOT_ID", "")
SALT = config.get("SALT", "xiaobai-xxp-2025")

# 协议常量
CMD_TYPE_REQUEST = 0
CMD_TYPE_RESPONSE = 1
CMD_TYPE_PUSH = 2
CMD_AUTH_BIND = "auth-bind"
CMD_PING = "ping"
MODULE_CONN_ACCESS = "conn_access"
MODULE_BIZ = "yuanbao_openclaw_proxy"

# ── Protobuf 编解码 ──

def pb_varint(value):
    if value < 0:
        value = (1 << 64) + value
    result = []
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)

def pb_tag(field, wire):
    return pb_varint((field << 3) | wire)

def pb_string(field, value):
    data = value.encode("utf-8")
    return pb_tag(field, 2) + pb_varint(len(data)) + data

def pb_bytes(field, value):
    return pb_tag(field, 2) + pb_varint(len(value)) + value

def pb_int32(field, value):
    return pb_tag(field, 0) + pb_varint(value)

def pb_uint32(field, value):
    return pb_tag(field, 0) + pb_varint(value)

def pb_msg(field, inner):
    return pb_tag(field, 2) + pb_varint(len(inner)) + inner

def pb_decode_varint(data, off=0):
    result = 0
    shift = 0
    while off < len(data):
        b = data[off]
        result |= (b & 0x7F) << shift
        off += 1
        if not (b & 0x80):
            break
        shift += 7
    return result, off

def pb_decode_delimited(data, off=0):
    length, off = pb_decode_varint(data, off)
    return data[off:off + length], off + length

def pb_decode_msg(data):
    result = {}
    off = 0
    while off < len(data):
        tag, off = pb_decode_varint(data, off)
        field = tag >> 3
        wire = tag & 7
        if wire == 0:
            val, off = pb_decode_varint(data, off)
            result[field] = (0, val)
        elif wire == 2:
            val, off = pb_decode_delimited(data, off)
            result[field] = (2, val)
        elif wire == 5:
            import struct
            val = struct.unpack_from("<I", data, off)[0]
            off += 4
            result[field] = (5, val)
        elif wire == 1:
            import struct
            val = struct.unpack_from("<Q", data, off)[0]
            off += 8
            result[field] = (1, val)
        else:
            break
    return result

# ── 连接层消息 ──

def encode_conn_msg(cmd_type, cmd, seq_no, msg_id, module, data=b""):
    head = b""
    head += pb_int32(1, cmd_type)
    head += pb_string(2, cmd)
    head += pb_int32(3, seq_no)
    head += pb_string(4, msg_id)
    head += pb_string(5, module)
    frame = pb_msg(1, head)
    if data:
        frame += pb_bytes(2, data)
    return frame

def decode_conn_msg(data):
    msg = pb_decode_msg(data)
    result = {}
    if 1 in msg:
        head = pb_decode_msg(msg[1][1])
        for fid, key in [(1, "cmdType"), (2, "cmd"), (3, "seqNo"), (4, "msgId"), (5, "module")]:
            if fid in head:
                val = head[fid][1]
                result[key] = val.decode("utf-8", errors="replace") if isinstance(val, bytes) else val
    if 2 in msg:
        result["data"] = msg[2][1]
    return result

def encode_auth_bind(biz_id, uid, source, token):
    auth_info = pb_string(1, uid) + pb_string(2, source) + pb_string(3, token)
    device_info = (
        pb_string(1, "1.0.0") +
        pb_string(2, "Linux") +
        pb_string(3, "2026.6.30") +
        pb_string(4, "1.0")
    )
    return pb_string(1, biz_id) + pb_msg(2, auth_info) + pb_msg(3, device_info)

def encode_send_group_req(group_code, text, msg_id="", from_account=""):
    if not msg_id:
        msg_id = str(random.randint(100000, 999999))
    random_val = str(random.randint(1, 999999999))
    body_content = pb_string(1, text)
    body_elem = pb_string(1, "TIMTextElem") + pb_msg(2, body_content)
    req = b""
    req += pb_string(1, msg_id)
    req += pb_string(2, group_code)
    req += pb_string(3, from_account)
    req += pb_string(4, "")
    req += pb_string(5, random_val)
    req += pb_msg(6, body_elem)
    req += pb_string(7, "")
    return req

def encode_send_c2c_req(to_account, text, msg_id="", from_account=""):
    """C2C 私聊消息编码
    字段（对照 proto）:
      1 msgId      string
      2 toAccount  string
      3 fromAccount string
      4 msgRandom  uint32
      5 msgBody    repeated MsgBodyElement
    """
    if not msg_id:
        msg_id = str(random.randint(100000, 999999))
    msg_random = random.randint(0, 2**32 - 1)
    body_content = pb_string(1, text)
    body_elem = pb_string(1, "TIMTextElem") + pb_msg(2, body_content)
    req = b""
    req += pb_string(1, msg_id)
    req += pb_string(2, to_account)
    req += pb_string(3, from_account)
    req += pb_uint32(4, msg_random)
    req += pb_msg(5, body_elem)
    return req

# ── Bot 客户端 ──

class PetBot:
    def __init__(self):
        self.token: str | None = None
        self.bot_id: str = BOT_ID
        self.ws = None
        self.connected = False
        self.seq_no = 1
        self.engine = PetEngine()
        self.instance_id = str(random.randint(1, 10000))

    # ── 签票 ──

    def _beijing_time(self) -> str:
        beijing = datetime.now(timezone(timedelta(hours=8)))
        return beijing.strftime("%Y-%m-%dT%H:%M:%S+08:00")

    def sign_token(self) -> bool:
        url = f"https://{API_DOMAIN}/api/v5/robotLogic/sign-token"
        nonce = ''.join(random.choices(string.hexdigits.lower(), k=32))
        timestamp = self._beijing_time()
        plain = f"{nonce}{timestamp}{APP_KEY}{APP_SECRET}"
        signature = hmac.new(APP_SECRET.encode(), plain.encode(), hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-AppVersion": "1.0.11",
            "X-OperationSystem": "linux",
            "X-Instance-Id": self.instance_id,
            "X-Bot-Version": "2026.3.22"
        }
        body = {"app_key": APP_KEY, "nonce": nonce, "signature": signature, "timestamp": timestamp}
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=30)
            result = resp.json()
            if result.get("code") == 0:
                data = result["data"]
                self.token = data["token"]
                self.bot_id = data.get("bot_id", self.bot_id)
                print(f"[PetBot] 签票成功! Bot ID: {self.bot_id}")
                return True
            else:
                print(f"[PetBot] 签票失败: {result}")
                return False
        except Exception as e:
            print(f"[PetBot] 签票错误: {e}")
            return False

    # ── 连接 ──

    async def connect(self) -> bool:
        if not self.token and not self.sign_token():
            return False
        try:
            self.ws = await websockets.connect(WS_URL, ping_interval=None)
            auth_data = encode_auth_bind(
                biz_id="ybBot", uid=self.bot_id or "", source="web", token=self.token or ""
            )
            msg_id = str(random.randint(100000, 999999))
            frame = encode_conn_msg(
                cmd_type=CMD_TYPE_REQUEST, cmd=CMD_AUTH_BIND,
                seq_no=self.seq_no, msg_id=msg_id,
                module=MODULE_CONN_ACCESS, data=auth_data
            )
            self.seq_no += 1
            await self.ws.send(frame)
            resp = await self.ws.recv()
            self.connected = True
            print("[PetBot] WebSocket 连接成功!")
            # 启动心跳
            asyncio.create_task(self._heartbeat())
            return True
        except Exception as e:
            print(f"[PetBot] 连接失败: {e}")
            return False

    # ── 心跳 ──

    async def _heartbeat(self):
        while self.connected and self.ws:
            await asyncio.sleep(70)
            try:
                msg_id = str(random.randint(100000, 999999))
                frame = encode_conn_msg(
                    cmd_type=CMD_TYPE_REQUEST, cmd=CMD_PING,
                    seq_no=self.seq_no, msg_id=msg_id,
                    module=MODULE_CONN_ACCESS
                )
                self.seq_no += 1
                await self.ws.send(frame)
            except Exception:
                break

    # ── 发送群消息 ──

    async def send_group_msg(self, text: str, group_code: str = None) -> bool:
        if not self.connected or not self.ws:
            return False
        try:
            target_group = group_code or GROUP_CODE
            msg_id = str(random.randint(100000, 999999))
            biz_data = encode_send_group_req(
                group_code=target_group, text=text,
                msg_id=msg_id, from_account=self.bot_id or ""
            )
            frame = encode_conn_msg(
                cmd_type=CMD_TYPE_REQUEST, cmd="send_group_message",
                seq_no=self.seq_no, msg_id=msg_id,
                module=MODULE_BIZ, data=biz_data
            )
            self.seq_no += 1
            await self.ws.send(frame)
            print(f"[PetBot] 已发送群消息({target_group}): {text[:30]}")
            return True
        except Exception as e:
            print(f"[PetBot] 发送群消息失败: {e}")
            return False

    async def send_c2c_msg(self, to_account: str, text: str) -> bool:
        """发送 C2C 私聊消息"""
        if not self.connected or not self.ws:
            return False
        try:
            msg_id = str(random.randint(100000, 999999))
            biz_data = encode_send_c2c_req(
                to_account=to_account, text=text,
                msg_id=msg_id, from_account=self.bot_id or ""
            )
            frame = encode_conn_msg(
                cmd_type=CMD_TYPE_REQUEST, cmd="send_c2c_message",
                seq_no=self.seq_no, msg_id=msg_id,
                module=MODULE_BIZ, data=biz_data
            )
            self.seq_no += 1
            await self.ws.send(frame)
            print(f"[PetBot] 已发送私聊 -> {to_account[:16]}...: {text[:30]}")
            return True
        except Exception as e:
            print(f"[PetBot] 发送私聊失败: {e}")
            return False

    # ── 接收循环 ──

    async def receive_loop(self):
        print("[PetBot] 开始监听群消息...")
        while self.connected and self.ws:
            try:
                raw = await self.ws.recv()
                if isinstance(raw, bytes):
                    conn_msg = decode_conn_msg(raw)
                    if not conn_msg:
                        continue
                    cmd_type = conn_msg.get("cmdType")
                    cmd = conn_msg.get("cmd", "")
                    if cmd_type == CMD_TYPE_PUSH and cmd == "inbound_message":
                        biz_data = conn_msg.get("data", b"")
                        if biz_data:
                            try:
                                push_json = json.loads(biz_data)
                                await self._handle_push(push_json)
                            except json.JSONDecodeError:
                                pass
            except websockets.exceptions.ConnectionClosed:
                print("[PetBot] 连接断开")
                self.connected = False
                break
            except Exception as e:
                print(f"[PetBot] 接收异常: {e}")
                break

    # ── 处理推送消息 ──

    async def _handle_push(self, push: dict):
        group_code = push.get("group_code", "")
        sender_id = push.get("from_account", "")
        if sender_id == self.bot_id:
            return  # 忽略自己的消息
        sender_name = push.get("sender_nickname", "未知用户")
        if DEBUG:
            msg_types = [e.get("msg_type") for e in push.get("msg_body", [])]
            print(f"[调试] 收到消息: group_code={group_code!r} sender={sender_id[:16] if sender_id else '?'}... msg_types={msg_types}")

        # ── 判断是否为 C2C 私聊 ──
        is_c2c = not group_code  # 私聊消息无群号
        # 黑名单过滤：在名单中的群忽略
        if not is_c2c and group_code in GROUP_CODE_BLACKLIST:
            print(f"[黑名单] 忽略来自群 {group_code} 的消息")
            return

        # 提取文本内容
        text_content = ""
        msg_body = push.get("msg_body", [])
        for elem in msg_body:
            if elem.get("msg_type") == "TIMTextElem":
                text_content += elem.get("msg_content", {}).get("text", "")

        if not text_content.strip():
            return
        text = text_content.strip()
        print(f"[{'私聊' if is_c2c else '群聊'}] {sender_name}({sender_id[:8]}...): {text[:50]}")

        # ── 检测是否艾特 bot（群聊需 @bot，私聊不检查） ──
        is_at_bot = is_c2c  # 私聊视为已 @
        if not is_c2c:
            for elem in msg_body:
                if elem.get("msg_type") == "TIMCustomElem":
                    try:
                        cd = json.loads(elem.get("msg_content", {}).get("data", "{}"))
                        if cd.get("elem_type") == 1002 and cd.get("user_id") == self.bot_id:
                            is_at_bot = True
                            break
                    except Exception:
                        pass
        if not is_at_bot:
            return  # 非艾特/私聊 忽略

        # ── 宠物指令路由 ──
        reply = None
        cmd = text.lower()

        if cmd in ["领养", "领养宠物"]:
            pet = self.engine.adopt(sender_id, sender_name)
            if pet is None:
                reply = "你已经有一只宠物了！发送「我的宠物」查看。"
            else:
                shiny_tag = "⚡" if pet.get("shiny") else ""
                rarity_cn = {"common": "普通", "rare": "稀有", "epic": "史诗",
                             "legendary": "传说", "mythic": "神话"}.get(pet["rarity"], "")
                reply = (
                    f"🎉 {sender_name} 领养了一只{rarity_cn}{pet['species_name']}{shiny_tag}！\n"
                    f"名字：{pet['name']}\n"
                    f"性格：{pet.get('personality', '未知')}\n"
                    f"发送「我的宠物」查看详情！"
                )

        elif cmd in ["我的宠物", "宠物面板", "宠物状态"]:
            panel = self.engine.render_panel(sender_id)
            if panel:
                reply = panel
            else:
                reply = "你还没有宠物！发送「领养宠物」来领养一只吧。"

        elif cmd.startswith("喂食"):
            reply = self.engine.interact(sender_id, "feed")
        elif cmd.startswith("遛遛"):
            reply = self.engine.interact(sender_id, "walk")
        elif cmd.startswith("玩耍"):
            reply = self.engine.interact(sender_id, "play")
        elif cmd.startswith("训练"):
            reply = self.engine.interact(sender_id, "train")
        elif cmd.startswith("睡觉"):
            reply = self.engine.interact(sender_id, "sleep")
        elif cmd.startswith("摸摸"):
            reply = self.engine.interact(sender_id, "pet")
        elif cmd.startswith("改名"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:
                reply = self.engine.rename(sender_id, parts[1])
                if not reply:
                    reply = "你还没有宠物！"
            else:
                reply = "格式：改名 <新名字>"

        elif cmd.startswith("对战"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:
                target_name = parts[1]
                reply = self.engine.battle_by_name(sender_id, target_name)
            else:
                reply = "格式：@bot 对战 <对方宠物名>"

        elif cmd in ["排行榜", "排行"]:
            reply = self.engine.leaderboard()

        elif cmd in ["图鉴", "宠物图鉴"]:
            reply = self.engine.handbook()

        elif cmd.startswith("/兑换"):
            parts = text.split(maxsplit=1)
            if len(parts) >= 2:
                reply = self.engine.redeem_code(parts[1], sender_id)
            else:
                reply = "格式：/兑换 <兑换码>"

        elif cmd in ["帮助", "pet帮助"]:
            reply = (
                "🐾 元宝宠物 Bot 指令\n"
                "━━━━━━━━━━━━━\n"
                "领养/领养宠物 - 领养一只随机宠物\n"
                "我的宠物 - 查看宠物状态面板\n"
                "喂食 - 喂饱你的宠物\n"
                "遛遛 - 带宠物散步\n"
                "玩耍 - 和宠物玩耍\n"
                "训练 - 训练宠物（Lv.1+）\n"
                "睡觉 - 让宠物休息\n"
                "摸摸 - 摸摸宠物\n"
                "改名 <名字> - 给宠物改名\n"
                "对战 <宠物名> - 向对方宠物发起挑战（每日10次）\n"
                "/兑换 <码> - 使用兑换码\n"
                "排行榜 - 宠物排行\n"
                "图鉴 - 查看全物种图鉴\n"
                "━━━━━━━━━━━━━"
            )

        # ── 发送回复 ──
        if reply:
            if len(reply) > 400:
                chunks = [reply[i:i+400] for i in range(0, len(reply), 400)]
                for chunk in chunks:
                    if is_c2c:
                        await self.send_c2c_msg(sender_id, chunk)
                    else:
                        await self.send_group_msg(chunk, group_code)
                    await asyncio.sleep(0.5)
            else:
                if is_c2c:
                    await self.send_c2c_msg(sender_id, reply)
                else:
                    await self.send_group_msg(reply, group_code)

# ── 主函数 ──

async def main():
    print("═══════════════════════════")
    print("  元宝宠物 Bot v1.0")
    print("═══════════════════════════")
    bot = PetBot()
    if not await bot.connect():
        print("[PetBot] 启动失败")
        return
    await bot.receive_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[PetBot] 已退出")
