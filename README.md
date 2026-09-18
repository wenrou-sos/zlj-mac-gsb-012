# 食品包装标签校验平台

面向食品制造行业的包装标签合规校验工具。录入**配料表、营养成分、保质期**等标签信息后，平台依据 GB 7718《预包装食品标签通则》与 GB 28050《预包装食品营养标签通则》的核心要求，自动完成**字段完整性、单位规范、营养成分合理性、过敏原提示**四类检查，并实时生成标签预览。

平台内置**可版本化的法规规则包**：规则以草稿形式编辑（启停 + 参数），发布后冻结快照并按生效日期自动启用；每条标签都会记录校验时使用的规则版本，新规则发布后可一键批量重检历史标签并对比新旧结果差异。

## 功能特性

- **标签录入**：食品名称、净含量、配料表、营养成分（1+4 核心营养素）、保质期、贮存条件、生产者信息、许可证编号等
- **自动校验**（保存前实时反馈，18 条可配置规则）：
  - 字段完整性：强制标示内容缺漏、生产日期格式、SC 许可证编号格式（`SC`+14 位数字）、产品标准号格式
  - 单位规范：净含量单位（g/kg/mL/L）、换算阈值可配、保质期单位与量级建议
  - 营养成分：核心营养素齐全性（必填项可配）、能量折算核对（容差可配）、修约要求、高钠提示（阈值可配）
  - 过敏原提示：扫描配料表中的常见致敏物质（关键词表可配），缺失提示语时给出警告，支持一键填充
- **规则中心**：
  - 规则包版本管理：草稿 → 发布 → 按生效日期自动生效，已发布包不可变
  - 规则启停与参数配置（容差、阈值、正则、关键词表等）
  - 批量重检：新规则发布后后台重跑全部历史标签，逐条展示新旧结果差异
  - 版本追溯：每次校验留痕（规则版本 + 完整结果），标签列表直接显示所用版本
- **标签预览**：按真实标签版式渲染，含营养成分表（项目 / 每 100g / NRV%）、保质期到期日推算
- **标签管理**：多标签保存、切换、删除，SQLite 持久化

## 规则包工作机制

- **草稿可编辑，发布即冻结**：已发布的规则包不可修改、不可删除，保证历史校验可复现
- **生效日期**：发布时设定，可设为未来日期（到期自动生效）；当前生效包 = 已发布且生效日期 ≤ 今天中最新者
- **快照隔离**：每次校验在请求开始时解析一次生效包并固化为内存快照；批量重检在任务启动时固定快照。因此**校验 / 重检执行期间发布新规则包，不会影响正在执行的任务**
- **差异对比**：重检按检查项编码对齐新旧结果，区分「新增检查项 / 不再触发 / 结果变化」三类差异

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
│   ├── rules.py            # 规则定义注册表（18 条规则 + 参数 schema）
│   ├── validators.py       # 校验引擎：按规则包快照执行
│   ├── rule_service.py     # 规则包解析/发布、校验留痕、批量重检、差异计算
│   ├── models.py           # SQLAlchemy 模型（标签/规则包/校验记录/重检任务）
│   ├── schemas.py          # Pydantic 入参模型
│   ├── database.py         # SQLite 连接
│   └── requirements.txt
├── frontend/               # Vue 3 前端
│   └── src/
│       ├── App.vue         # 主界面（标签校验 / 规则中心 双视图）
│       └── components/     # LabelForm / ValidationPanel / LabelPreview / RuleCenter
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

### 标签与校验

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/validate?package_id=` | 校验标签数据（不落库）；默认用当前生效包，可指定任意版本预览 |
| GET | `/api/labels` | 标签列表（含最近校验的规则版本与结论） |
| POST | `/api/labels` | 新建标签（保存即校验并留痕） |
| GET / PUT / DELETE | `/api/labels/{id}` | 查询 / 更新（重新校验留痕）/ 删除 |
| GET | `/api/labels/{id}/validate` | 用当前生效包校验已保存标签并留痕 |
| GET | `/api/labels/{id}/validations` | 标签的校验历史（每次所用规则版本与结论） |

### 规则包

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/rule-definitions` | 全部规则定义与参数 schema |
| GET | `/api/rule-packages` | 规则包列表（含「当前生效」标记） |
| POST | `/api/rule-packages` | 新建草稿（默认克隆当前生效包，可用 `base_id` 指定） |
| GET / PUT / DELETE | `/api/rule-packages/{id}` | 详情 / 更新草稿 / 删除草稿（已发布包只读） |
| POST | `/api/rule-packages/{id}/publish` | 发布草稿并设定生效日期（快照冻结） |
| POST | `/api/rule-packages/{id}/recheck` | 用该包批量重检全部历史标签（后台任务） |
| GET | `/api/recheck-jobs` / `/api/recheck-jobs/{id}` | 重检任务进度与逐标签新旧差异 |

校验结果中每项检查包含 `category`（field / unit / nutrition / allergen）、`status`（pass / warning / error）、`rule`（所属规则编码）与中文说明，整体结论分为 `pass`（通过）、`warning`（有警告）、`fail`（存在错误）；响应同时携带本次所用的 `rule_version`。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_DIR` | `backend/data`（容器内 `/app/data`） | SQLite 数据目录 |
| `DATABASE_URL` | `sqlite:///{DATA_DIR}/labels.db` | 数据库连接串 |
