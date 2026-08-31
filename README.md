# RAG 企业级知识库问答系统

基于 LangChain 框架的电商平台商品知识问答系统，支持多用户管理、知识库管理、流式问答和引用展示。

## 技术栈

### 后端
- **FastAPI** - Python Web 框架
- **LangChain** - AI 应用开发框架
- **FAISS** - 向量索引（本地持久化，按知识库隔离）
- **SQLite**（默认）/ **PostgreSQL**（可选） - 关系型数据库
- **SQLAlchemy** - ORM 框架
- **JWT** - 身份认证

### 前端
- **React 18 + TypeScript** - 前端框架
- **Ant Design** - UI 组件库
- **Tailwind CSS** - 样式方案
- **Vite** - 构建工具

### AI 服务
- **Agnes AI API（agnes-2.0-flash）** - 大语言模型，负责答案生成（流式）
- **本地哈希 Embedding（jieba 分词 + MD5 hashing trick）** - 检索向量化

> 说明：Agnes API 仅提供对话/图像/视频模型，无 embedding 模型，
> 因此检索向量化采用本地方案（`backend/app/services/local_embeddings.py`）。
> 该模块实现了 LangChain Embeddings 接口，可随时替换为 bge / OpenAI 等真实模型。

## 功能特性

1. **用户管理**: 注册、登录、登出（服务端吊销 token）、登录失败限流（默认 15 分钟窗口 5 次）、密码修改、角色权限控制（admin/user）
2. **管理员后台**: 知识库创建/删除、文档上传（PDF/Word/TXT/Excel）与向量化索引
3. **知识库问答**: 流式输出（SSE）、引用片段展示、多知识库联合检索
4. **会话管理**: 新建/切换/删除会话，首条消息自动命名，历史持久化

## 环境要求

- Python 3.13+
- Node.js 18+
- 无需安装 PostgreSQL / Redis / ChromaDB

## 快速开始

### 1. 安装依赖（仅首次需要）

后端：创建虚拟环境、安装依赖，并从模板创建 `.env`：

```bash
cd backend
python -m venv .venv      # 若提示无 python 命令，改用：py -3.13 -m venv .venv
./.venv/Scripts/pip install -r requirements.txt
cp .env.example .env
```

编辑 `backend/.env`，至少填写 `SECRET_KEY`（随机字符串，用于 JWT 签名，
**未配置时后端将拒绝启动**）和 `AGNES_API_KEY`（问答功能依赖，获取方式见
`.env.example` 内注释）。

前端：

```bash
cd frontend
npm install
```

> PowerShell 用户请把 `./.venv/Scripts/pip` 写作 `.venv\Scripts\pip`，`cp` 写作 `copy`。

### 2. 初始化数据库（首次或删库后执行）

```bash
cd backend
./.venv/Scripts/python.exe init_db.py
```

完成三件事：建表 → 创建管理员（admin / 123456）→ 导入示例电商商品并构建向量索引。

### 3. 启动后端

```bash
cd backend
./.venv/Scripts/python.exe run.py
```

后端运行在 http://localhost:8000（API 文档：http://localhost:8000/docs）

### 4. 启动前端

```bash
cd frontend
npm run dev
```

前端运行在 http://localhost:5173，Vite 已将 `/api` 代理到后端 8000 端口。

## 默认账户

- **管理员**: 用户名 `admin`，密码 `123456`（可进入"知识库管理"页）
- 普通用户可通过注册页面创建账号

## 目录结构

```
RAG/
├── backend/                    # 后端项目
│   ├── app/
│   │   ├── core/              # 核心配置（config/database/security）
│   │   ├── models/            # 6 张数据表模型
│   │   ├── routes/            # API 路由（auth/chat/knowledge_base）
│   │   ├── schemas/           # Pydantic 数据验证
│   │   └── services/          # rag_service（FAISS RAG 引擎）
│   │                          # local_embeddings（本地哈希向量化）
│   │                          # document_parser（PDF/Word/TXT/Excel 解析）
│   ├── db_data/               # 运行数据（不入库）：SQLite main.db、
│   │                          # 上传文件 uploads/、FAISS 索引 vector_db/
│   ├── sample_data/           # 示例电商商品数据
│   ├── .venv/                 # Python 虚拟环境（本地创建，不入库）
│   ├── .env                   # 环境变量（本地创建，不入库）
│   ├── requirements.txt
│   ├── init_db.py             # 数据库初始化脚本
│   └── run.py                 # 启动脚本
└── frontend/                  # 前端项目
    ├── src/
    │   ├── components/        # ProtectedRoute 路由保护
    │   ├── pages/             # Login/Register/ChatPage/KnowledgeBase
    │   ├── services/          # api/authService/chatService
    │   └── styles/            # 暖色调全局样式
    └── vite.config.ts         # 含 /api 代理配置
```

## 运行测试

```bash
cd backend
./.venv/Scripts/python.exe -m pytest
```

当前覆盖配置安全基线（SECRET_KEY 启动校验、路径默认值统一），
测试范围与结果详见 [docs/测试报告.md](docs/测试报告.md)。

CI：推送至 master 会触发 [Gitee Go](https://gitee.com/features/gitee-go) 流水线
自动执行 pytest（配置见 `.workflow/master-pipeline.yml`，首次使用需在仓库
「流水线」页面启用 Gitee Go）。

## Docker 部署（可选）

不想配本地 Python/Node 环境时，可用 Docker Compose 一键起前后端：

```bash
cp .env.example .env          # 填写 SECRET_KEY 与 AGNES_API_KEY
docker compose up -d --build
```

- 前端：http://localhost:8080（nginx 托管构建产物并反代 `/api`，SSE 流式已适配）
- 后端：http://localhost:8000/docs
- 数据（SQLite/向量索引/上传文件/日志）持久化在宿主机 `./docker-data/`

首次启动后初始化示例数据：

```bash
docker compose exec backend python init_db.py
```

## 常见问题

**Q: 如何切换到 PostgreSQL？**
编辑 `backend/.env`，将 `DATABASE_URL` 改为
`postgresql://postgres:密码@localhost:5432/rag_knowledge_base`，
并 `pip install "psycopg[binary]"`，然后重新执行 `init_db.py`。

**Q: 如何替换为真实 Embedding 模型？**
修改 `backend/app/services/rag_service.py` 中 `self.embeddings` 的实例化，
替换为任意实现 LangChain Embeddings 接口的类（如 `OpenAIEmbeddings`、
`HuggingFaceBgeEmbeddings`），替换后删除 `db_data/vector_db/` 并重新上传文档。

**Q: 后端修改代码后没有自动重载？**
uvicorn 的 watchfiles 在部分中文路径环境下监听不稳定，手动重启 `run.py` 即可。

## 许可证

本项目基于 [MIT License](LICENSE) 发布。
