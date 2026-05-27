# QQ 群每日聊天总结机器人项目记忆

更新时间：2026-05-27 01:20 左右

> 这是可同步到 GitHub 的脱敏版项目记忆。不要在本文件中记录 SSH 密码、API Key、OpenViking key、NapCat token、AstrBot 密码或其他敏感凭据。

## 项目目标

部署 GitHub 项目 `245916893-maker/Chatbot`，实现基于 NapCat + AstrBot 的 QQ 群每日聊天总结机器人。

核心能力：

- 自动收集目标 QQ 群消息。
- 每日定时生成昨日群聊总结。
- 支持手动 `/summary` 命令按相对日期、绝对日期、时间段和跨天范围生成总结。
- 已接入 OpenViking 长期记忆，用于后续自动捕获对话与语义召回。
- 已新增免费 A 股行情插件，可在 QQ 群内查询今日股市和个股行情。

## 当前服务

服务部署在 NAS 的 Docker Compose 环境中，运行容器包括：

- `napcat`
- `astrbot`
- `openviking`

公开入口按实际部署环境替换 `<NAS_IP>`：

- AstrBot WebUI：`http://<NAS_IP>:3002`
- NapCat WebUI：`http://<NAS_IP>:6099/webui`，需要使用本地保存的 NapCat token 登录。
- OpenViking Health：`http://<NAS_IP>:1933/health`

## Daily Summary 插件状态

`daily-summary` 插件已支持：

- `/summary`
- `/summary 前天`
- `/summary 大前天`
- `/summary 2026-05-24`
- `/summary 2026-05-24 14:00-15:30`
- `/summary 今天 14:00 到 15:30`
- `/summary 前天 22:30 到 今天 01:15`
- `/summary 2026-05-23 22:30 到 2026-05-24 01:15`
- `/summary_help`

时间解析按 `Asia/Shanghai` 处理。跨天范围已统一走起止时间比较逻辑，避免同日分钟范围过滤的限制。

## OpenViking 长期记忆状态

2026-05-27 01:12 左右已启用 OpenViking 长期记忆。

故障起因：

- AstrBot 插件 `astrbot_plugin_openviking_memory` 的 `on_user_message` 报错：`All connection attempts failed`。
- 根因是插件原来连接 `http://localhost:1933`，但 OpenViking 不在 AstrBot 容器内部；同时服务端此前未稳定运行。

修复结果：

- 新增 `openviking` Docker 服务，映射端口 `1933:1933`。
- AstrBot 插件改为连接 `http://openviking:1933`。
- OpenViking 账号使用 `astrbot`。
- 插件使用 `venue_user` 隔离模式。
- `auto_recall_enabled=true`。
- `bypass_patterns=[]`。
- `backfill_max_messages=200`。

验证结果：

- `openviking`、`astrbot`、`napcat` 容器均为 Up。
- AstrBot 容器内访问 `http://openviking:1933/health` 返回 healthy。
- AstrBot 启动日志显示 `[OV] server reachable at http://openviking:1933 (account=astrbot)`。
- 使用插件同款链路创建 OpenViking 用户成功。
- 使用插件同款链路 `add_message` 写入测试返回 HTTP 200。
- 修复后未再出现新的 `All connection attempts failed`。

## OpenViking 实现注意

当前 OpenViking 使用一个本地轻量 hash embedding 服务作为 OpenAI-compatible embeddings fallback。它可以跑通写入与检索链路，但语义召回质量不如真实 embedding provider。后续如果需要更好的长期记忆质量，应替换为真实语义 embedding 服务。

本地部署中的 OpenViking 配置文件、AstrBot 插件配置文件和各类 key 只能留在 NAS 本地，不能提交到 GitHub。

## Stock Market 免费行情插件状态

2026-05-27 已新增 `plugins/stock-market` 插件，用于免费查询 A 股行情。

命令：

- `/market` 或 `/股市`：查询今日 A 股三大指数概览。
- `/stock 600519`：按股票代码查询个股。
- `/stock 贵州茅台`：按股票名称查询个股。
- `/stock_help`：查看行情命令用法。

实现状态：

- AstrBot 容器内已安装 AkShare 到持久路径 `/AstrBot/data/python_libs`。
- 实测 AkShare 所调用的部分源站接口在 NAS 环境中会被远端断开连接，因此插件实际查询优先使用腾讯财经公开行情接口。
- 东方财富公开接口仅作为市场广度的可选补充；如果返回不完整或连接失败，插件会省略涨跌家数，避免误导。
- 已验证插件数据函数可返回 `/market`、`/stock 600519`、`/stock 贵州茅台` 的结果。
- 已重启 AstrBot，日志显示 `Plugin stock-market (1.0.0)` 加载成功，OneBot v11 已重新连接。
- 免费公开行情可能存在延迟，仅供群聊参考，不构成投资建议。

## 常用验证命令

在 QQ 群内可验证：

- `/summary`
- `/summary_help`
- `/ov_status`
- `/market`
- `/stock 600519`

在 NAS 上可验证：

```bash
docker ps
curl http://127.0.0.1:1933/health
docker logs --tail=200 astrbot
```

## 重要注意

- 不要提交 `.env`、运行时数据库、NapCat 登录态、AstrBot 数据目录、OpenViking key、API Key、token、密码。
- 不要把本地 NAS 的完整运行配置当作通用开源配置直接提交。
- GitHub 上只保留可公开的运行状态、命令说明、问题根因和脱敏后的修复记录。
