# 食品包装标签校验平台

面向食品制造行业的包装标签合规校验工具。录入**配料表、营养成分、保质期**等标签信息后，平台依据 GB 7718《预包装食品标签通则》与 GB 28050《预包装食品营养标签通则》的核心要求，自动完成**字段完整性、单位规范、营养成分合理性、过敏原提示**四类检查，并实时生成标签预览。

## 功能特性

- **标签录入**：食品名称、净含量、配料表、营养成分（1+4 核心营养素）、保质期、贮存条件、生产者信息、许可证编号等
- **可版本化法规规则包**：
  - 规则配置（启停、不通过级别、阈值/正则/词表等参数）全部数据驱动，支持草稿 → 发布流转、指定生效日期
  - 已发布版本固化为**不可变 JSON 快照**；正在执行的校验按其版本快照在内存中运行，发布新版本不影响进行中的校验
  - 未到生效日期的版本不会成为线上执行版本（当前生效版本自动解析）
- **校验留痕**：每次保存/手动校验/批量重检都生成校验记录，**钉死使用的规则包版本**与完整结果；标签列表展示最近一次校验的版本与结论，支持查看留痕历史
- **批量重检与差异对比**：新规则发布后可对历史标签后台批量重检，按规则 code 逐条对比新旧结论（新增/停用/级别变化/文案变化、整体结论变好/变差），新结果写入留痕而原记录完整保留
- **自动校验**（保存前实时反馈，共 20+ 项规则）：
  - 字段完整性：强制标示内容缺漏、生产日期格式、SC 许可证编号格式（`SC`+14 位数字）、产品标准号格式
  - 单位规范：净含量单位（g/kg/mL/L）、≥1000g 应换算 kg、保质期单位与量级建议
  - 营养成分：核心营养素齐全性、能量与三大营养素折算核对（±25%）、修约要求、高钠提示、NRV% 自动计算
  - 过敏原提示：自动扫描配料表中的 12 类常见致敏物质（麸质、甲壳类、鱼、蛋、花生、大豆、乳、坚果、芝麻等），缺失提示语时给出警告，支持一键填充
- **标签预览**：按真实标签版式渲染，含营养成分表（项目 / 每 100g / NRV%）、保质期到期日推算
- **标签管理**：多标签保存、切换、删除，SQLite 持久化

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vue 3 + Vite |
| 后端 | FastAPI + SQLAlchemy |
| 数据库 | SQLite（文件库，免安装） |
| 部署 | Docker 多阶段构建，单容器运行 |

## 项目结构

```
├── backend/                # FastAPI 后端
│   ├── main.py             # 路由：标签 CRUD + 校验 + 规则包 + 重检 + 静态托管
│   ├── rule_catalog.py     # 内置规则目录（code/名称/默认级别/参数 schema）
│   ├── rule_engine.py      # 数据驱动校验引擎（按规则包快照执行）
│   ├── rule_service.py     # 规则包草稿/发布/生效解析、配置校验
│   ├── recheck_service.py  # 批量重检后台任务与新旧结果 diff
│   ├── validators.py       # 兼容垫片（入口迁移至 rule_engine）
│   ├── models.py           # SQLAlchemy 模型（标签/规则包/校验留痕/重检批次）
│   ├── schemas.py          # Pydantic 入参模型
│   ├── database.py         # SQLite 连接
│   └── requirements.txt
├── frontend/               # Vue 3 前端
│   └── src/
│       ├── App.vue         # 主界面（标签校验 / 规则中心 两个视图）
│       └── components/
│           ├── LabelForm / ValidationPanel / LabelPreview
│           ├── RuleCenter.vue
│           └── rules/      # 版本列表、草稿编辑器、重检列表/差异
├── Dockerfile              # 多阶段构建（前端构建 + 后端运行）
├── docker-compose.yml
└── start.sh                # 本地一键启动（dev / prod）
```

## 快速开始

### 方式一：本地启动（开发模式）

```bash
./start.sh
```

- 前端：http://localhost:5173 （Vite 热更新，`/api` 已代理到后端）
- 后端：http://localhost:8000/docs （Swagger 接口文档）

### 方式二：本地生产模式

```bash
./start.sh prod
```

构建前端后由 FastAPI 统一托管，直接访问 http://localhost:8000

### 方式三：Docker（推荐交付方式）

```bash
docker build -t label-check .
docker run -d -p 8000:8000 -v label-data:/app/data label-check
```

或使用 compose：

```bash
docker compose up --build -d
```

访问 http://localhost:8000 ，SQLite 数据通过卷 `label-data` 持久化。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/validate?package_id=` | 实时校验（不落库），默认用当前生效包，可指定草稿包试用；返回结果带规则版本戳 |
| GET | `/api/labels` | 标签列表（含最近一次校验的结论、规则版本、时间） |
| POST | `/api/labels` | 新建标签（自动按生效版本校验并留痕） |
| GET / PUT / DELETE | `/api/labels/{id}` | 查询 / 更新（再次留痕）/ 删除 |
| GET | `/api/labels/{id}/validate?package_id=&persist=` | 校验已保存标签，默认生成 manual 留痕 |
| GET | `/api/labels/{id}/validations` | 标签的校验留痕历史（含每次使用的规则版本） |
| GET | `/api/rule-catalog` | 内置规则目录、参数 schema、默认配置 |
| GET | `/api/rule-packages` | 规则包版本列表（可按 status 过滤） |
| GET | `/api/rule-packages/effective` | 当前生效版本 |
| POST | `/api/rule-packages/draft` | 新建草稿（空白或基于已发布版本，自动递增版本号） |
| GET / PUT / DELETE | `/api/rule-packages/{id}` | 草稿详情 / 编辑元信息与全量配置 / 删除（仅草稿） |
| PATCH | `/api/rule-packages/{id}/rules/{code}` | 单条规则启停、不通过级别、参数 |
| POST | `/api/rule-packages/{id}/publish` | 发布草稿（请求体可指定 effective_date） |
| POST | `/api/rule-packages/{id}/archive` | 归档已发布版本 |
| POST | `/api/rechecks` | 发起批量重检（后台执行） |
| GET | `/api/rechecks` / `/api/rechecks/{id}` | 重检任务列表 / 任务详情（含每标签新旧差异） |
| GET | `/api/health` | 健康检查 |

校验结果中每项检查包含 `category`（field / unit / nutrition / allergen）、`status`（pass / warning / error）与中文说明，整体结论分为 `pass`（通过）、`warning`（有警告）、`fail`（存在错误）。

### 规则版本模型与隔离保证

- 规则包配置为自描述快照：`{"params": <全局参数>, "rules": {code: {enabled, severity, params}}}`，
  发布时按内置目录补齐为全量配置后固化；历史版本的校验结果只取决于该版本自身，不受未来目录/默认值变化影响。
- 执行隔离：每次校验一次性把目标版本快照载入 `RuleEngine`（无状态、纯内存执行），
  且已发布包禁止任何修改；因此发布新版本、编辑草稿只影响**之后新发起**的校验，绝不影响执行中的校验与历史留痕。
- 生效解析：未指定版本时取「生效日期 ≤ 今天」的已发布包中生效日期最新者；可发布未来生效版本提前就位。
- 批量重检任务启动时即固定目标版本快照与重检范围（`scope_json`），逐条提交进度，中断后已完成部分保留。


## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_DIR` | `backend/data`（容器内 `/app/data`） | SQLite 数据目录 |
| `DATABASE_URL` | `sqlite:///{DATA_DIR}/labels.db` | 数据库连接串 |
