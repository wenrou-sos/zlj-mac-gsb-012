# 食品包装标签校验平台

面向食品制造行业的包装标签合规校验工具。录入**配料表、营养成分、保质期**等标签信息后，平台依据 GB 7718《预包装食品标签通则》与 GB 28050《预包装食品营养标签通则》的核心要求，自动完成**字段完整性、单位规范、营养成分合理性、过敏原提示**四类检查，并实时生成标签预览。

## 功能特性

- **标签录入**：食品名称、净含量、配料表、营养成分（1+4 核心营养素）、保质期、贮存条件、生产者信息、许可证编号等
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
│   ├── main.py             # 路由：标签 CRUD + 校验接口 + 静态托管
│   ├── validators.py       # 校验引擎（字段/单位/营养/过敏原）
│   ├── models.py           # SQLAlchemy 模型
│   ├── schemas.py          # Pydantic 入参模型
│   ├── database.py         # SQLite 连接
│   └── requirements.txt
├── frontend/               # Vue 3 前端
│   └── src/
│       ├── App.vue         # 主界面（表单 + 校验 + 预览）
│       └── components/     # LabelForm / ValidationPanel / LabelPreview
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
| POST | `/api/validate` | 校验标签数据（不落库），返回检查结果、检出过敏原、NRV 表、到期日 |
| GET | `/api/labels` | 标签列表 |
| POST | `/api/labels` | 新建标签 |
| GET / PUT / DELETE | `/api/labels/{id}` | 查询 / 更新 / 删除 |
| GET | `/api/labels/{id}/validate` | 校验已保存的标签 |
| GET | `/api/health` | 健康检查 |

校验结果中每项检查包含 `category`（field / unit / nutrition / allergen）、`status`（pass / warning / error）与中文说明，整体结论分为 `pass`（通过）、`warning`（有警告）、`fail`（存在错误）。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATA_DIR` | `backend/data`（容器内 `/app/data`） | SQLite 数据目录 |
| `DATABASE_URL` | `sqlite:///{DATA_DIR}/labels.db` | 数据库连接串 |
