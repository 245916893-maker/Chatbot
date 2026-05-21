# QQ 群每日聊天总结机器人

基于 NapCat + AstrBot，用 Docker 部署在 NAS 上，自动收集 QQ 群消息，每天定时生成昨日聊天摘要。

## 架构

```
QQ 群 ←→ NapCat (QQ 协议桥接) ←→ AstrBot (AI 处理) ←→ LLM API
```

## 前置条件

| 条件 | 说明 |
|------|------|
| NAS 已安装 Docker + Docker Compose | 部署容器 |
| 一个闲置 QQ 号 | 扫码登录机器人 |
| LLM API Key | DeepSeek / OpenAI / 兼容接口均可 |

## 快速开始

```bash
# 1. 克隆仓库
git clone <你的仓库地址>
cd qq-group-summary-bot

# 2. 配置 LLM API Key
# 方式一：通过 QQ 群里发命令
#   启动后在群里 @bot 发送: /summary_config api_key sk-xxx

# 方式二：手动编辑插件配置
#   启动后编辑 plugins/daily-summary/config.json

# 3. 启动服务
docker compose up -d

# 4. 扫码登录 QQ
# 浏览器打开 http://<NAS_IP>:3001
# 进入 NapCat WebUI，扫码登录机器人 QQ 号

# 5. 配置 AstrBot 连接 NapCat
# 浏览器打开 http://<NAS_IP>:3000
# 默认账密: astrbot / astrbot
# 左侧「消息平台」→ 添加 → OneBot v11
# 地址填: ws://napcat:6099
```

## 使用方法

| 命令 | 说明 |
|------|------|
| `/summary` | 手动生成昨日聊天总结 |
| `/zongjie` | 同上（中文别名） |
| `/summary_config` | 查看当前配置 |
| `/summary_config api_key sk-xxx` | 设置 LLM API Key |
| `/summary_config summary_time 09:00` | 设置每日推送时间 |

## 配置项

默认配置文件 `plugins/daily-summary/config.json`：

```json
{
  "summary_time": "08:00",
  "api_base": "https://api.deepseek.com/v1",
  "api_key": "",
  "model": "deepseek-chat",
  "max_tokens": 2000,
  "temperature": 0.7,
  "target_groups": []
}
```

| 配置项 | 说明 |
|--------|------|
| `summary_time` | 每日推送时间，格式 HH:MM |
| `api_base` | LLM API 地址，兼容 OpenAI 格式 |
| `api_key` | LLM API Key |
| `model` | 模型名称 |
| `max_tokens` | 最大输出 token 数 |
| `target_groups` | 指定推送的群 ID 列表，空数组=所有群 |

## 支持的 LLM

| 提供商 | api_base | model |
|--------|----------|-------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 其他兼容接口 | 按实际填写 | 按实际填写 |

## 目录结构

```
qq-group-summary-bot/
├── docker-compose.yml          # 双容器编排
├── .env.example                # 环境变量模板
├── plugins/
│   └── daily-summary/          # 每日总结插件
│       ├── metadata.yaml
│       ├── __init__.py
│       ├── main.py             # 插件主逻辑
│       ├── config.json         # 运行时配置（自动生成）
│       └── data/
│           └── messages.db     # SQLite 消息数据库
├── napcat/                     # NapCat 持久化数据（自动生成）
│   ├── data/
│   └── QQ/
└── astrbot/                    # AstrBot 持久化数据（自动生成）
    └── data/
```

## 故障排查

### 机器人收不到群消息
1. 确认 NapCat 已扫码登录且在线
2. 确认机器人 QQ 号已在目标群中
3. 检查 NapCat 容器日志：`docker logs napcat`

### 总结不生成
1. 检查 LLM API Key 是否正确：`/summary_config`
2. 手动触发测试：`/summary`
3. 查看 AstrBot 日志：`docker logs astrbot`

### 插件没加载
1. 确认 `plugins/daily-summary/main.py` 存在
2. 重启 AstrBot：`docker compose restart astrbot`
