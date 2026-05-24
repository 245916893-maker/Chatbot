# QQ 群每日聊天总结机器人

基于 NapCat + AstrBot，用 Docker 部署在 NAS 上，自动收集 QQ 群消息，每天定时生成昨日聊天摘要。

## 架构

```text
QQ 群 <-> NapCat (QQ 协议桥接) <-> AstrBot (AI 处理) <-> LLM API
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
git clone https://github.com/245916893-maker/Chatbot.git
cd Chatbot

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
# 左侧「消息平台」-> 添加 -> OneBot v11
# 地址填: ws://napcat:6099
```

## 使用方法

| 命令 | 说明 |
|------|------|
| `/summary` | 手动生成昨日全天聊天总结 |
| `/summary 前天` | 手动生成前天全天聊天总结 |
| `/summary 大前天` | 手动生成大前天全天聊天总结 |
| `/summary 2026-05-24 14:00-15:30` | 手动生成指定日期、指定时间段的聊天总结 |
| `/summary 今天 14:00 到 15:30` | 手动生成今天指定时间段的聊天总结 |
| `/summary 14:00-15:00` | 手动生成今天指定时间段的聊天总结 |
| `/summary 前天 22:30 到 今天 01:15` | 手动生成跨相对日期、指定起止时间的聊天总结 |
| `/summary 2026-05-23 22:30 到 2026-05-24 01:15` | 手动生成跨自然日期、指定起止时间的聊天总结 |
| `/summary_help` | 查看手动总结命令用法 |
| `/zongjie` | 同上（中文别名） |
| `/summary_config` | 查看当前配置 |
| `/summary_config api_key sk-xxx` | 设置 LLM API Key |
| `/summary_config summary_time 09:00` | 设置每日推送时间 |

日期参数支持：`今天`、`昨天`、`昨日`、`前天`、`大前天`、`N天前`、`YYYY-MM-DD`。

时间段支持：`HH:MM-HH:MM`、`HH:MM 到 HH:MM`、`起始日期 HH:MM 到 结束日期 HH:MM`。如果需要跨午夜，请写明结束日期，例如 `/summary 昨天 23:00 到 今天 01:00`。

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
  "target_groups": [],
  "timezone": "Asia/Shanghai"
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
| `timezone` | 解析手动命令时间段和定时任务的时区，默认 `Asia/Shanghai` |

## 支持的 LLM

| 提供商 | api_base | model |
|--------|----------|-------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V3` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 其他兼容接口 | 按实际填写 | 按实际填写 |

## 目录结构

```text
qq-group-summary-bot/
├── docker-compose.yml
├── .env.example
├── plugins/
│   └── daily-summary/
│       ├── metadata.yaml
│       ├── __init__.py
│       ├── main.py
│       ├── config.json
│       └── data/
│           └── messages.db
├── napcat/
└── astrbot/
```

## 故障排查

### 机器人收不到群消息

1. 确认 NapCat 已扫码登录且在线。
2. 确认机器人 QQ 号已在目标群中。
3. 检查 NapCat 容器日志：`docker logs napcat`。

### 总结不生成

1. 检查 LLM API Key 是否正确：`/summary_config`。
2. 手动触发测试：`/summary`。
3. 查看 AstrBot 日志：`docker logs astrbot`。

### 插件没加载

1. 确认 `plugins/daily-summary/main.py` 存在。
2. 重启 AstrBot：`docker compose restart astrbot`。
