# QQ 群每日聊天总结机器人项目记忆

更新时间：2026-05-28 19:05 左右

> ?????? GitHub ?????????????????? SSH ???API Key?OpenViking key?NapCat token?AstrBot ??????????

## 项目目标

部署 GitHub 项目 `<USER_QQ_A>-maker/Chatbot`，实现 QQ 群每日聊天总结机器人：

- 基于 NapCat + AstrBot。
- 机器人 QQ：`<BOT_QQ>`。
- 目标 QQ 群：`<GROUP_ID_1>`。
- 每日总结时间：`08:00`。
- LLM：DeepSeek，API Key 之后由用户提供。

## NAS 与部署位置

- NAS IP：`<NAS_IP>`
- SSH 端口：`<SSH_PORT>`
- SSH 用户：`<SSH_USER>`
- SSH 密码：用户已提供过，但不要写入文件；后续需要时向用户确认或使用已有本机脚本。
- NAS 系统：Linux `Z4S-SFBM`，x86_64。
- 部署目录：`<NAS_DEPLOY_DIR>`

## 已完成

- 本机安装了 Paramiko 到 Codex Python 环境。
- 使用 Paramiko 验证 NAS SSH 登录成功。
- 在 NAS 上创建 `<NAS_DEPLOY_DIR>`。
- 下载并解压 GitHub 项目到部署目录。
- 写入 `.env`：
  - `QQ_ACCOUNT=<BOT_QQ>`
  - `ASTRBOT_UID=1007`
  - `ASTRBOT_GID=1008`
- 写入插件配置 `plugins/daily-summary/config.json`：
  - `summary_time`: `08:00`
  - `api_base`: `https://api.deepseek.com/v1`
  - `model`: `deepseek-chat`
  - `target_groups`: `["<GROUP_ID_1>", "<GROUP_ID_2>"]`
  - `api_key`: 空，等待后续配置。
- NAS 原有 `3000` 端口已被其他容器占用，所以 AstrBot 外部端口改为 `3002`。
- AstrBot 新版 WebUI 实际监听容器内 `6185`，因此 Compose 映射为 `3002:6185`。
- NapCat 原 README 镜像 `napneko/napcat-docker:latest` 拉取失败，切换为官方 NapCat-Docker 示例镜像 `mlikiowa/napcat-docker:latest`。
- Docker Hub 拉取困难，通过 `docker.m.daocloud.io/mlikiowa/napcat-docker:latest` 成功拉取后 tag 为 `mlikiowa/napcat-docker:latest`。
- NAS 上容器创建线程受限，已在 Compose 加入：
  - `security_opt: seccomp=unconfined`
  - `ulimits.nproc=65535`
  - `ulimits.nofile=65535`
- 容器已启动成功：
  - `napcat`
  - `astrbot`
  - `openviking`
- 2026-05-27 21:27 左右新增免费 A 股行情插件 `stock-market`。
- 2026-05-27 22:00 左右增强 `stock-market` 与群聊上下文身份注入，修复 `/stock` 落入默认 LLM 和相似昵称串人的问题。

## 当前服务入口

- AstrBot WebUI：`http://<NAS_IP>:3002`
- NapCat WebUI：`http://<NAS_IP>:6099/webui`，需要使用 NapCat token 登录；token 不写入记忆文件。
- OpenViking Health：`http://<NAS_IP>:1933/health`
- NapCat 端口：
  - `6099` 可访问 WebUI。
  - `3001` 在当前镜像里没有实际 Web 服务，外部探测为 refused。

## 当前 Compose 关键差异

部署目录的 `docker-compose.yml` 已改动为：

- `napcat.image = mlikiowa/napcat-docker:latest`
- `astrbot.ports = "3002:6185"`
- 两个服务都带 `seccomp=unconfined` 和高 ulimit。
- 新增 `openviking` 服务：
  - `image = soulter/astrbot:latest`
  - `ports = "1933:1933"`
  - `volumes = ./astrbot/data:/AstrBot/data` 与 `./openviking:/app/.openviking`
  - 启动命令会先启动本地 hash embedding server，再启动 `openviking-server --host 0.0.0.0 --port 1933 --config /app/.openviking/ov.conf`

## NapCat 登录状态

- 已多次生成 QQ 登录二维码。
- 最新二维码曾保存到本地工作区：`D:\VibeCoding\群聊总结机器人\napcat-qrcode.png`
- 二维码容易过期；如需刷新，重启 `napcat` 容器后复制：
  - 容器内：`/app/napcat/cache/qrcode.png`
  - NAS：`<NAS_DEPLOY_DIR>/qrcode.png`
  - 本地：`D:\VibeCoding\群聊总结机器人\napcat-qrcode.png`

## AstrBot 状态

- AstrBot 已能启动并加载插件 `daily-summary`。
- 日志显示 `daily-summary (1.0.0)` 已加载。
- AstrBot 初始日志曾显示初始密码：
  - 已脱敏，不再写入记忆文件或 GitHub。
- 2026-05-24 14:39 左右已重置 AstrBot WebUI dashboard 密码：
  - 用户名仍为 `astrbot`。
  - 密码已写入 `cmd_config.json` 的 `password` 与 `pbkdf2_password` 字段。
  - `password_storage_upgraded=true`。
  - `password_change_required=false`。
  - 不要把新密码写入记忆文件；如需登录，查看当时对话最终回复。
  - 重置前配置备份在 NAS：`<NAS_DEPLOY_DIR>/astrbot/data/cmd_config.json.bak-20260524-143913`
- 已通过 `POST /api/auth/login` 验证 AstrBot WebUI 登录成功。
- 2026-05-24 14:50 左右用户在 AstrBot WebUI 保存 OneBot v11 平台配置后，日志显示：
  - `Loading IM platform adapter aiocqhttp(凉凉-机器人) ...`
  - `Running on http://0.0.0.0:6199`
  - `GET /ws 1.1 101`
  - `aiocqhttp(OneBot v11) 适配器已连接。`
- 说明 NapCat `ws://astrbot:6199/ws` 已成功连接 AstrBot。
- 2026-05-27 01:12 左右已启用 OpenViking 长期记忆：
  - 起因：`astrbot_plugin_openviking_memory` 的 `on_user_message` 报错 `All connection attempts failed`。
  - 原因：插件原来连接 `http://localhost:1933`，但 OpenViking 不在 AstrBot 容器内部；同时服务端此前未稳定运行。
  - 已在 NAS 部署目录新增 `openviking` 服务并启动成功，外部端口为 `1933`。
  - OpenViking Python 环境在 AstrBot 数据卷内：`/AstrBot/data/openviking-venv-test`。
  - OpenViking 持久化目录：`<NAS_DEPLOY_DIR>/openviking`。
  - 本地轻量 embedding 服务文件：`<NAS_DEPLOY_DIR>/openviking/hash_embedding_server.py`。
  - OpenViking 配置文件：`<NAS_DEPLOY_DIR>/openviking/ov.conf`；包含密钥，不能提交到 GitHub。
  - AstrBot 插件配置文件：`<NAS_DEPLOY_DIR>/astrbot/data/config/astrbot_plugin_openviking_memory_config.json`；包含密钥，不能提交到 GitHub。
  - AstrBot 插件当前关键配置：
    - `ov_base_url = http://openviking:1933`
    - `ov_account_id = astrbot`
    - `ov_agent_id = astrbot`
    - `isolation_mode = venue_user`
    - `auto_recall_enabled = true`
    - `bypass_patterns = []`
    - `backfill_max_messages = 200`
  - OpenViking 账号 `astrbot` 已创建，管理密钥已写入本地配置；不要在回复、记忆或 GitHub 中输出明文。
  - 配置备份：`<NAS_DEPLOY_DIR>/astrbot/data/config/astrbot_plugin_openviking_memory_config.json.bak-enable-openviking-20260527-011215`
  - 已验证：
    - `docker ps` 显示 `openviking`、`astrbot`、`napcat` 均为 Up。
    - AstrBot 容器内访问 `http://openviking:1933/health` 返回 `healthy=true`。
    - AstrBot 启动日志显示 `[OV] server reachable at http://openviking:1933 (account=astrbot)`。
    - 使用插件同款链路创建 OpenViking 用户成功，`add_message` 写入测试返回 `200`。
    - 修复后日志没有新的 `All connection attempts failed`。
- 2026-05-27 21:27 左右已新增 `stock-market` 免费行情插件：
  - 插件目录：`<NAS_DEPLOY_DIR>/plugins/stock-market`
  - 依赖目录：`<NAS_DEPLOY_DIR>/astrbot/data/python_libs`
  - 已安装 AkShare `1.18.64` 及其运行依赖到 `/AstrBot/data/python_libs`。
  - 实测 AkShare 部分接口在 NAS 环境中会被源站断开，因此插件实际查询优先使用腾讯财经公开行情接口。
  - 东方财富公开接口仅作为市场广度补充；如果返回不完整或失败，插件会省略涨跌家数，避免误导。
  - 支持命令：
    - `/market` 或 `/股市`：查看 A 股三大指数实时概览。
    - `/stock 600519`：按 6 位代码查个股。
    - `/stock 贵州茅台`：按股票名称查个股。
    - `/stock_help`：查看命令帮助。
  - 也支持被 @ 时识别“今天股市怎么样”等自然语言股市查询。
  - 已在容器内验证：
    - `/market` 数据函数可返回上证指数、深证成指、创业板指。
    - `/stock 600519` 与 `/stock 贵州茅台` 可返回贵州茅台实时行情。
  - 已重启 AstrBot，日志显示 `Plugin stock-market (1.0.0)` 加载成功。
  - OneBot v11 已重新连接，日志显示 `GET /ws 101` 与 `适配器已连接`。
  - 已同步到 GitHub `main`，提交：`b593c2130c029791f303544974bf4e98e1be4853 feat: add free stock market plugin`。
- 2026-05-27 22:00 左右修复群内股票查询没有走插件的问题：
  - 现象：群内发送 `/stock 贵州茅台` 后未触发 `stock-market`，而是进入默认 LLM，并尝试调用未配置 API key 的 `web_search_tavily`。
  - 修复：`stock-market/main.py` 新增高优先级群消息拦截，直接处理 `/stock`、`/股票`、`/market`、`/gushi`、`/股市`、`/行情`、`/大盘`、`/stock_help`、`/行情帮助`，并调用 `event.stop_event()` 阻止继续进入默认 LLM。
  - 修复：命令注册改为 `alias={...}`，避免多层 decorator 在当前 AstrBot 版本下行为不稳定。
  - 新增 LLM 工具：`stock_market_overview` 与 `stock_quote`；启动日志已显示两者 `Added llm tool`。
  - 新增自然语言个股识别：被 @ 时可识别“贵州茅台今天怎么样”“茅台现在多少钱”“600519 股价”等。
  - 已在容器内验证：
    - `/stock 贵州茅台` 解析为 `('stock', '贵州茅台')`。
    - `@机器人 贵州茅台今天怎么样` 可抽取查询词 `贵州茅台`。
    - `@机器人 今天股市怎么样` 不会误判为个股。
    - `StockData().stock_quote('贵州茅台')` 返回贵州茅台实时行情。
  - 已重启 AstrBot，日志显示 `Plugin stock-market (1.0.0)`、`Added llm tool: stock_market_overview`、`Added llm tool: stock_quote`，OneBot v11 已重新连接。
- 2026-05-27 22:00 左右修复群聊相似昵称导致 LLM 串人问题：
  - 现象：群里存在 `看到我请叫我少吃点2/<USER_QQ_A>` 和 `看到我请叫我少吃点/<USER_QQ_B>`，旧上下文注入只写 `[昵称/时间]`，模型容易按昵称串人。
  - 修复文件：`<NAS_DEPLOY_DIR>/plugins/astrbot_plugin_group_context_flow/main.py`。
  - `group_messages_delta` 现在把历史消息格式化为 `昵称(QQ:号码)/时间`。
  - 每次 LLM 请求前新增 `<current_group_message_sender>` 上下文，明确当前群、当前提问者昵称、当前提问者 QQ，并提示识别当前提问者时优先使用 QQ 号。
  - 已在容器内验证身份格式：`看到我请叫我少吃点2(QQ:<USER_QQ_A>)`，当前提问者 QQ 为 `<USER_QQ_A>`。
  - 已同步到 GitHub `main`，提交：`40049d778ad16e5e57269d488294c8775db04bcd fix: route stock queries and include qq identity`。
  - GitHub 上的 `PROJECT_MEMORY.md` 使用脱敏版，替换了 NAS 地址、SSH 用户、QQ 号、群号等隐私信息。
- 2026-05-28 19:05 左右修复 `stock-market` 自然语言误触发问题：
  - 现象：群内 `@机器人 今天天气怎么样` 被误判为股票查询，回复“没找到「天气」对应的 A 股股票”；追问“你是不是炒股炒疯了”也会因为包含“股票/炒股”被误判。
  - 原因：`_guess_stock_query()` 把“怎么样/如何/涨/跌”等通用词作为股票触发词，清洗后把“天气”“你怎么”等非股票词当成候选股票名。
  - 修复：收紧 `STOCK_QUERY_HINT_RE`，新增 `STOCK_NAME_QUESTION_RE` 与 `NON_STOCK_CONTEXT_RE`，把天气、气温、预报、炒股吐槽等上下文排除。
  - 修复：自然语言股票候选词必须先能解析到真实 A 股代码；解析不到就放行给默认 LLM，不再由股票插件回复“没找到股票”。
  - 已验证：
    - `@机器人 今天天气怎么样` -> 股票候选为 `None`。
    - `@机器人 人家问你天气怎样，你怎么老想着股票呢，你是不是炒股炒疯了` -> 股票候选为 `None`。
    - `@机器人 贵州茅台今天怎么样` -> 候选为 `贵州茅台`。
    - `@机器人 新易盛现在多少钱` -> 候选为 `新易盛`。
    - `/stock 贵州茅台` -> 仍解析为直接股票命令。
  - 已部署到 NAS 并重启 AstrBot；日志显示 `stock_market_overview`、`stock_quote` 工具注册成功，OneBot v11 已连接。
- 2026-05-24 15:03 左右已把群 `<GROUP_ID_2>` 加入 `plugins/daily-summary/config.json` 的 `target_groups`。
  - 当前目标群：`<GROUP_ID_1>`, `<GROUP_ID_2>`
  - 备份文件：`<NAS_DEPLOY_DIR>/plugins/daily-summary/config.json.bak-20260524-150328`
  - 已重启 `astrbot`，日志显示 `daily-summary` 插件加载正常，OneBot v11 重新连接成功。
- 2026-05-24 15:08 左右已增强 `daily-summary/main.py` 的 `/summary` 命令：
  - 默认 `/summary` 仍总结昨日。
  - 新增支持 `/summary 前天`、`/summary 大前天`、`/summary 2026-05-22`、`/summary 2天前`、`/summary 3`。
  - 备份文件：`<NAS_DEPLOY_DIR>/plugins/daily-summary/main.py.bak-20260524-150800`
  - 已用容器内 Python 编译检查通过，已重启 AstrBot，OneBot v11 已重新连接成功。
- 2026-05-24 15:12 左右修复上述日期参数解析中的编码问题：
  - 现象：`/summary 前天` 等命令报错 `nothing to repeat at position 8`。
  - 原因：中文参数在远端文件里被写成问号，正则变成 `(?:??)?`。
  - 修复：日期解析函数改为 ASCII + Unicode 转义写法，并去掉中文正则。
  - 备份文件：`<NAS_DEPLOY_DIR>/plugins/daily-summary/main.py.bak-fix-date-20260524-151219`
  - 已验证容器内解析 `/summary`、`/summary 2026-05-22`、`/summary 3` 成功；AstrBot 已重启，OneBot v11 已连接。
- 2026-05-24 15:16 左右继续修复 `/summary` 回复文案中的编码问题：
  - 现象：命令能识别 `大前天`，但机器人回复 `?? ????大前天????????...`。
  - 原因：`cmd_summary` 中固定中文回复文案被远端编码写成问号。
  - 修复：回复文案改为 Unicode 转义字符串，并新增 `/summary_help`。
  - 备份文件：`<NAS_DEPLOY_DIR>/plugins/daily-summary/main.py.bak-fix-replies-20260524-151554`
  - 已编译检查通过，AstrBot 已重启，OneBot v11 已重新连接；容器内验证 `大前天` 解析为 `2026-05-21`。
- 2026-05-24 16:00 左右增强 `/summary` 支持日期 + 时间段：
  - 支持 `/summary 2026-05-24 14:00-15:30`
  - 支持 `/summary 今天 14:00 到 15:30`
  - 支持 `/summary 大前天 09:00-12:00`
  - 支持 `/summary 14:00-15:00`，默认表示今天该时段。
  - 默认 `/summary` 仍为昨日全天。
  - 插件现在按 `Asia/Shanghai` 解释输入时间；新消息用带时区的本地时间写入，老的 naive timestamp 记录按 UTC 转为北京时间过滤。
  - 备份文件：
    - `<NAS_DEPLOY_DIR>/plugins/daily-summary/main.py.bak-time-range-20260524-155435`
    - `<NAS_DEPLOY_DIR>/plugins/daily-summary/main.py.bak-time-range-fix-20260524-160008`
  - 已编译检查通过，解析测试通过，AstrBot 已重启，OneBot v11 已重新连接。
  - 已验证 `/summary 2026-05-24 14:00-15:30` 过滤现有数据库能命中 12 条消息。
- 2026-05-24 21:30 左右已将本次插件功能同步到 GitHub 仓库 `<USER_QQ_A>-maker/Chatbot`：
  - 安装了 Git for Windows 与 GitHub CLI。
  - GitHub App 无法写入，报 `403 Resource not accessible by integration`；后改用本机 Git 凭据推送。
  - 已推送分支：`codex/summary-date-time-range`
  - 已快进合并并推送到 `main`。
  - 提交：`24f5fd4 feat: support date and time range summaries`
  - 已确认远端 `README.md` 和 `plugins/daily-summary/main.py` 包含日期/时间段总结与 `timezone` 配置。
  - 未把 DeepSeek API Key、SSH 密码、NAS 运行配置写入 GitHub。
- 2026-05-24 22:35 左右继续增强 `daily-summary/main.py` 的 `/summary` 命令，支持跨天指定起止日期与时间：
  - 支持 `/summary 前天 22:30 到 今天 01:15`
  - 支持 `/summary 2026-05-23 22:30 到 2026-05-24 01:15`
  - 支持 `/summary 2026-05-23 22:30-2026-05-24 01:15`
  - 保留原有 `/summary`、`/summary 前天`、`/summary 大前天`、`/summary 2026-05-24 14:00-15:30`、`/summary 今天 14:00 到 15:30`、`/summary 14:00-15:00`。
  - 实现方式：解析命令为北京时间 `start_dt/end_dt`，用消息本地时间直接比较过滤；跨天不再受同日分钟范围限制。
  - 同时修复定时任务里 aware/naive datetime 比较风险，并让自动昨日总结也走统一的全天起止时间范围。
  - NAS 备份文件：`<NAS_DEPLOY_DIR>/plugins/daily-summary/main.py.bak-cross-day-20260524-222733`
  - 已在本机和 AstrBot 容器内通过 Python 编译与解析测试。
  - 容器内验证 `<GROUP_ID_2>` 的 `2026-05-24 14:50` 到 `15:30` 过滤能命中消息。
  - AstrBot 已重启，日志显示 `daily-summary` 插件加载正常，OneBot v11 重新连接成功。
  - 本机到 GitHub 443 不通；最终通过临时 SSH SOCKS 代理经 NAS 出口完成 Git 同步。
  - 已推送到 GitHub `main`。
  - 提交：`511e1376978df7db1e7e095ce6232f1fdb37e5f2 feat: support cross-day summary ranges`
  - 已确认远端 `README.md` 和 `plugins/daily-summary/main.py` 包含跨天起止时间范围功能。
  - 未把 DeepSeek API Key、SSH 密码、NAS 运行配置写入 GitHub。

## Chrome 插件状态

- 用户要求使用 `@chrome` 操作浏览器。
- 初始未安装 Codex Chrome Extension。
- 后来用户安装/启用后，检测结果为：
  - installed: true
  - enabled: true
  - profile: Default
  - version: `1.1.5_0`
- 重置 Node REPL 后 Chrome 扩展连接成功。
- Chrome 当前可被接管。
- 但 AstrBot 登录失败，停在 `http://<NAS_IP>:3002/#/auth/login`。

## 待完成

1. QQ 群内可继续验证：
   - `/summary`
   - `/summary_help`
   - `/ov_status`
   - `/market`
   - `/stock 600519`
   - `/stock 贵州茅台`
2. OpenViking 当前使用本地轻量 hash embedding 服务，能跑通记忆写入与检索链路；如后续追求更强语义召回质量，可替换为真实 embedding provider。

## 重要注意

- 不要覆盖用户 NAS 上已有容器；`3000` 已被 `19970688_nastools-bt` 占用。
- Docker 操作需要 sudo。
- 不要把 SSH 密码、API Key、OpenViking key、NapCat token、AstrBot 密码写入提交、记忆文件或最终回复。
- 如果需要改 AstrBot 密码或直接写配置文件，先说明影响并取得用户确认。
