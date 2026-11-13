# 2989 · 数据范围过滤器（S2-IAM data_scope）

## 运行

```bash
pip install fastapi httpx pytest sqlalchemy
pytest -v
```

测试跑在 SQLite（磁盘文件，自动清理）；`probe_records` 仅测试库使用（DDL 见 `migrations/0001_probe_records.sql`），生产表归各业务工单所有。

## 核心 API（app/data_scope.py）

| 函数 | 语义 |
|------|------|
| `scoped_select(model, ctx)` | **真 SELECT**（`select(model).where(*conds)`）— 列表/导出/聚合共用同一过滤器 |
| `scoped_conditions(model, ctx)` | WHERE 条件组装：租户过滤恒在 + 范围过滤 |
| `check_object_scope(obj, ctx)` | 单条记录范围判断；不满足 → **404**（不是 403，防存在性泄露） |
| `apply_create_defaults(obj, ctx)` | CREATE 时 site_id 缺省取当前会所 |
| `apply_write_rules(obj, ctx, payload)` | UPDATE 规则（见下表） |
| `validate_models(registry)` | **启动期**校验（`create_app` 调用）：缺 org_id/site_id/归属字段 → ConfigError |

## 范围语义（模型声明方式）

```python
class ProbeRecord(Base):
    __tablename__ = "probe_records"
    id = ...
    org_id = ...     # 租户过滤（恒在）
    site_id = ...    # site 范围过滤
    owner_id = ...   # self 范围归属字段（可用 __owner_field__ 覆盖，默认 owner_id）
    __collaborator_table__ = {record_id: user_id}  # 可选：协作人可见（桩，对接 S2-CRM）
    __scope_exempt__ = True  # 仅参考表（orgs/sites/users）豁免启动校验
```

- **self** → `owner_id == ctx.user_id`（+协作人映射可见，列表与单条一致）
- **site** → `site_id == ctx.site_id`
- **org** → 仅租户过滤（集团全部会所）
- 模型缺列 → **create_app 启动即抛** ConfigError（不在首次查询才炸）

## 写入规则（UPDATE 语义 — 本单关键修正）

| 场景 | 行为 |
|------|------|
| PATCH 无 site_id | **记录保持原会所**（PATCH 永不搬移记录——org 管理员改标题不会把会所 B 记录搬到会所 A） |
| PATCH 显式改 site_id（改到别会所） | self/site 范围 → 403；org 范围 → 允许（显式搬移） |
| self 员工改 owner_id | 403 |
| org/site 改 owner_id | 允许（角色矩阵允许管理员改派） |
| payload 白名单外字段 | **400 invalid_payload**（绝不静默丢弃） |
| CREATE 无 site_id | 缺省取当前会所（`apply_create_defaults`） |

## 测试覆盖（25 个用例）

| 验收 | 用例 |
|------|------|
| 1 三档范围 | self=3 / site=6 / org=12（种子：1 集团、2 会所、每会所 2 员工、每人 3 条）+ 租户不越界 + 会所不重叠 |
| 2 404 语义 | 范围外 PATCH → 404；缺失与范围外响应体完全一致；范围内 200；site 范围跨会所 PATCH → 404 |
| 3 写入规则 | PATCH 不搬移会所（持久化复核）、显式改会所 self/site 403 / org 200、self 改 owner 403、org 改 owner 200、未知字段 400、CREATE 缺省会所 |
| 4 total+导出 | 列表 total 3/6/12（按权限点矩阵）；**export 端点复用 scoped_select**，导出条数一致 |
| 5 启动校验 | validate_models 直接抛 ConfigError ×2；**create_app 端到端**抛 ConfigError |
| 6 协作人 | 单条可见/不可见 + **列表可见（own 3 + collab 1 = 4）**、非协作人恒 3 |

## 探针接口（仅 APP_ENV=test 挂载）

- `GET /__probe__/{code}/records` — 按权限点范围过滤返回
- `GET /__probe__/{code}/export` — 导出，同一 scoped_select
- `PATCH /__probe__/{code}/records/{id}` — 范围校验后改 title/owner_id/site_id；范围外一律 404

权限矩阵桩：`app/permissions.py::SCOPE_MATRIX`（真实矩阵 = S2-IAM-001/2981，对接点已标注）。

## 对接点（依赖桩）

- 协作人映射：`__collaborator_table__`（dict 桩；真实协作表 = S2-CRM 工单）。
- 角色矩阵：`SCOPE_MATRIX`（桩；真实 = S2-IAM-001）。
- require_permission：`get_ctx`（桩；真实 = S2-IAM 权限中间件）。

## 目录

- `app/` — data_scope / models / permissions / main / errors
- `tests/` — 25 个回归用例
- `migrations/0001_probe_records.sql` — 测试表 DDL（仅测试库）
- `make_files.py` — 结构校验（交付文件即源码，无内嵌副本）
- `dev/` — 开发脚手架，非交付代码
