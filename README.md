# 元宝宠物 Bot

基于腾讯元宝 Bot API 的群聊宠物养成机器人。在群聊中领养、互动、对战，养成专属宠物。

## 功能

- **领养宠物** — 随机生成物种/属性/性格，稀有度各异
- **宠物互动** — 喂食、散步、玩耍、训练、睡觉、抚摸
- **宠物对战** — 宠物之间 PV P对战，每日限制次数
- **宠物面板** — 查看宠物状态、属性、ASCII 艺术画
- **图鉴系统** — 收集全物种图鉴
- **排行榜** — 经验榜、对战榜
- **兑换码** — 属性加点/经验值兑换（附交互式管理脚本）
- **衰减系统** — 长期不互动宠物状态会逐步下降

## 文件说明

| 文件 | 说明 |
|------|------|
| `main.py` | 主程序，连接元宝 WebSocket 处理群消息 |
| `pet_engine.py` | 宠物引擎，核心逻辑 + SQLite 持久化 |
| `pet_art.py` | 宠物物种定义与 ASCII 艺术画 |
| `create_code.py` | 兑换码管理交互式脚本（命令行菜单） |
| `config.json` | 配置文件（需自行填写 APP_KEY/APP_SECRET） |
| `pets.db` | SQLite 数据库（自动生成，不上传仓库） |
| `requirements.txt` | Python 依赖 |

## 快速开始

```bash
pip install -r requirements.txt
# 编辑 config.json 填入 APP_KEY / APP_SECRET
python3 main.py
```

### 兑换码管理

```bash
python3 create_code.py
```

进入交互式菜单：创建/删除/列出兑换码。

## 依赖

- Python >= 3.10
- websockets
- requests
- prompt_toolkit（兑换码管理脚本使用）

## 许可证

MIT
