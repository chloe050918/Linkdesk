# Agent 工作区架构

## 运行组成

| 模块 | 职责 |
|---|---|
| `web-agent/` | 原生 JS 单页应用，轮询会话状态；对话、浏览器、结果、方法与过程记录 |
| `agentdesk/web.py` | FastAPI 本机 API；输入校验、Origin/Host 限制、文件上传与导出 |
| `agentdesk/runtime.py` | 有限 Agent 循环、工具分发、引文校验、独立证据验收与 Skill 提炼 |
| `agentdesk/browser.py` | Playwright 独立上下文，网页导航、操作、文本与截图快照 |
| `agentdesk/provider.py` | 方舟/OpenAI Chat Completions、工具调用、JSON 输出、超时和有限重试 |
| `agentdesk/store.py` | SQLite WAL，案例、来源、方法及追加式事件记录 |

## 一次查证

1. 服务端将任务、当前日期、已有来源索引、当前草稿与近期对话送入模型。若指定了已启用的 Skill，先验证其来源确认仍有效，再注入方法。
2. 模型返回工具调用。后端执行搜索、打开页面、点击链接、定位文字或读取已有来源。
3. 浏览器提取原文、链接、来源 URL、抓取时间、内容哈希和截图。结果回传模型，同时保存本地。
4. 模型调用 `propose_labels`。后端检查枚举、引文逐字匹配、来源归属和确定性标签的证据。
5. 对确定性标签再调用独立证据验收器。它检查时效、主体及材料是否能支持关系。失败作为工具错误返回 Agent，要求补查或保留未知。
6. 通过后保存草稿。专家确认具体草稿 ID；重新生成草稿会清除旧确认。

每轮最多 12 次主模型调用，工具按顺序执行。证据验收另计一次模型调用；过程记录中分别保留用量和耗时。网络超时与限流最多尝试三次。暂停会取消当前任务并等待其退出，再释放浏览器给专家。

验收器与主 Agent 使用同一模型服务，不具备独立数据来源，也不保证消除同源模型错误。它不是业务专家或可靠性的替代品。

## 工具

| 工具 | 输入 | 返回 |
|---|---|---|
| `search_web` | 查询词 | 真实搜索页面快照、原文、链接 |
| `open_url` | 公开 URL / 内置资料 URL | 来源 ID、原文、链接、截图 |
| `click_link` | 可见链接文字 | 导航后的页面快照 |
| `read_page` | 无 | 当前页面快照 |
| `find_text` | 要定位的文字 | 定位后的页面快照 |
| `read_source` | 当前案例来源 ID、可选关键词 | 已保存原文片段 |
| `propose_labels` | 三个关系维度、原因、逐字引文、缺口 | 经校验的草稿或具体错误 |

人工接管还支持页面截图点击、滚动、输入、按键、返回和上传。专家引用和解释独立记录；记录行为不推测隐藏意图。

## 数据与状态

- **Session**：任务、消息、来源列表、浏览器位置、草稿、确认、方法 ID、运行状态。
- **Source**：案例归属、URL、标题、文本、SHA-256、时间、截图、操作者。
- **Proposal**：各维度值、依据、来源与引文、缺口、验收结果、版本 ID。
- **Review**：确认的草稿 ID、标签、专家说明与时间。
- **Skill**：方法内容、来源案例与草稿、父版本、版本号、启用状态。
- **Event**：工具开始/结束、浏览、模型用量、证据验收、引用、确认、方法提炼/编辑。

会话状态为 idle、running、paused、error、interrupted。重启后，未结束的 running 状态转为 interrupted，既有证据与对话保留；可重新发起查证。浏览器登录态不持久化。

Skill 状态为 draft、active、disabled。修改生成新版本，旧版保留。当前实现启用前检查来源确认；还没有自动的大规模 Skill 回归闸门，需人工和独立案例验证。

## API 概览

| 路径 | 用途 |
|---|---|
| `GET /api/health`、`GET/POST /api/settings` | 服务与模型连接；响应不返回密钥 |
| `GET/POST /api/sessions` | 列表与创建案例 |
| `GET /api/sessions/{id}` | 案例、来源索引与过程事件 |
| `POST /api/sessions/{id}/chat`、`/pause` | 启动一轮查证、暂停 |
| `POST /api/sessions/{id}/browser`、`/citation`、`/upload` | 专家浏览、引用与材料补充 |
| `POST /api/sessions/{id}/review`、`/distill` | 确认结果、生成候选 Skill |
| `GET /api/skills`、`POST /api/skills/{id}/edit`、`/status` | 方法列表、修订与启停 |
| `GET /api/skills/{id}/export`、`GET /api/sessions/{id}/export` | Markdown 与 JSON 导出 |

## 安全与部署边界

密钥只在服务端使用，`.env.local` 为私有文件并被 Git 忽略。浏览器不连接用户个人 Chrome Profile，不使用其 Cookie。来源内容作为不可信数据处理，不赋予工具或权限。

只监听本机；Host 与 Origin 检查防止普通跨站访问。浏览器只允许公开 HTTP(S) 的 GET/HEAD，阻止私有地址和非标准端口，单独放行内置合成材料路径。该实现不是完整的 SSRF/DNS 重绑定防护方案或多租户隔离，生产化需受控出网代理、容器沙箱、SSO/RBAC、审计、配额和数据治理。

上传材料和网页内容会发给用户配置的模型供应商。不要将未经授权的内部或个人敏感资料用于公开模型测试。
