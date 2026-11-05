# 架构与实现

## 运行方式

单个 Python HTTP 服务监听 `127.0.0.1:8850`，提供静态页面和 JSON API。没有构建步骤，没有第三方运行时依赖。SQLite 保存案例与运营记录；浏览器保存当前选中案例，不保存模型密钥。

## 模块

| 模块 | 责任 |
|---|---|
| `engine.py` | 本地/在线提取、原文逐字校验、材料类型与日期检查、三维关系判断 |
| `operations.py` | 分流理由、影响范围、代表去重、随机抽检、模板适用性与固定回归 |
| `server.py` | API、持久化、并发锁、复核状态、版本校验、批量草稿事务 |
| `static/app.js` | 单案调查、材料、补证、人工复核、档案 |
| `static/operations-ui.js` | 运营首页、模式对比、模板验证与复用界面 |

## 数据对象

- **Case**：两家主体、调查问题、核验时点、材料、分析、补证任务、复核记录、历史。批次案例额外有结构化行为信号和模拟上游候选。
- **Analysis**：正文指纹、提取版本、每个关系维度的候选值与引用、被排除的陈述、缺口。
- **Review**：确认的维度、提交人、复核人、分析快照、材料指纹、意见与状态。
- **Policy**：来源案例与复核 ID、来源指纹、规则类型版本、说明、回归结果、启停状态、操作历史。
- **Prepared draft**：规则与来源版本、本案指纹、本案引用、预填复核说明。不是标签，也不是复核通过记录。
- **Review plan**：名额、随机种子、选中的案例及当时选择理由。保存的是计划快照；不会自动通知或分配到真实人员账户。

SQLite 两张表：`cases(id, payload)` 与 `operations(id, kind, payload)`。后一张保存检查模板及复核安排。批量生成草稿时，所有案例与规则操作历史在同一事务中提交。

## 状态变化

案例：调查中 → 待复核 → 已归档。退回后进入调查中；待补证是可保存状态。材料变化会使待复核/已通过记录失效，旧记录保留。复核依据与当前正文不一致时，不能确认。

模板：草稿 → 回归通过 → 启用 → 停用。启用时再次校验来源和回归数据摘要；来源记录失效或撤回，即便存储状态仍为 active，运行时有效状态也会变为“需重新核验”，禁止生成新草稿。

草稿：生成 → 人工检查 → 提交 → 复核。草稿不自动入档。模板停用会阻止生成新草稿；已有草稿保留来源，由人按当前证据判断。

## 关键保障

1. **逐案证据。** 模板只能使用目标案例自己的材料。代表案例的引用不会复制到其他主体。
2. **预览与执行一致。** 预览返回政策与候选指纹摘要。应用前重新计算；期间材料或状态变更则要求重新预览。
3. **边界验证绑定版本。** 结果绑定规则字段摘要、规则代码版本与评测文件 SHA-256。改动后不能继续使用旧的通过状态启用。
4. **不把未知当否定。** 有代理授权、无控制证明时只保留集团未知；不能推出无集团关系。
5. **最小本机服务。** 写请求要求本机 Host、同源 Origin（如存在）与 JSON Content-Type。仍没有生产身份鉴别，不应直接暴露公网。

## API 摘要

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 服务健康 |
| GET | `/api/bootstrap` | 案例与模型可用配置状态 |
| GET | `/api/operations?budget=4&seed=review-01` | 实时队列、安排预览、模板与历史计划 |
| POST | `/api/review-plans` | 保存计划快照；字段 budget、seed |
| POST | `/api/cases` | 新建调查 |
| POST | `/api/cases/{id}/material` | 添加材料 |
| POST | `/api/cases/{id}/analyze` | 异步提取；mode 为 local 或 online |
| GET | `/api/jobs/{id}` | 查询分析状态 |
| POST | `/api/cases/{id}/submit` | 提交 selected、rationale、name |
| POST | `/api/cases/{id}/approve` | 业务复核，name、note |
| POST | `/api/cases/{id}/return`、`revoke` | 退回或撤回 |
| POST | `/api/cases/{id}/task`、`task-response` | 建立补证、保存回复 |
| GET | `/api/cases/{id}/export?format=md` | 完整档案；也支持 json |
| POST | `/api/policies` | 从有效复核来源创建模板；source_id、rationale |
| POST | `/api/policies/{id}/evaluate` | 固定边界回归 |
| POST | `/api/policies/{id}/activate`、`disable` | 启用、停用 |
| POST | `/api/policies/{id}/preview` | 返回逐案适用性与预览 token |
| POST | `/api/policies/{id}/apply` | 指定 ids 与 token，原子生成草稿 |
| GET | `/api/policies/{id}/export` | 导出规则、来源、回归与历史 |

API 修改已有案例时可带 revision；不一致时拒绝覆盖。前端正常修改会携带此字段。

## 评测与运行数据隔离

`evaluation/boundary_cases.json` 含独立样例输入与 expected eligibility。运行候选来自 `batch_fixtures.py`，不携带参考标签。排序、适用性函数不读取预期结果。

当前回归检验的是受约束规则：满足条件时允许生成草稿，其余拒绝。它不是模型效果对比或主动学习算法。外部未知数据还需要新测试覆盖。
