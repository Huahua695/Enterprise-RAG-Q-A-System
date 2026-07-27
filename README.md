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

1. **用户管理**: 注册、登录、密码修改、角色权限控制（admin/user）
2. **管理员后台**: 知识库创建/删除、文档上传（PDF/Word/TXT/Excel）与向量化索引
3. **知识库问答**: 流式输出（SSE）、引用片段展示、多知识库联合检索
4. **会话管理**: 新建/切换/删除会话，首条消息自动命名，历史持久化

## 环境要求

- Python 3.13（项目 venv 已创建于 `backend/.venv`，可直接复用）
- Node.js 18+（依赖已安装于 `frontend/node_modules`）
- 无需安装 PostgreSQL / Redis / ChromaDB

## 快速开始

### 1. 初始化数据库（首次或删库后执行）

```bash
cd backend
./.venv/Scripts/python.exe init_db.py
```

完成三件事：建表 → 创建管理员（admin / 123456）→ 导入示例电商商品并构建向量索引。

### 2. 启动后端

```bash
cd backend
./.venv/Scripts/python.exe run.py
```

后端运行在 http://localhost:8000（API 文档：http://localhost:8000/docs）

### 3. 启动前端

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
│   ├── uploads/               # 上传文件存储
│   ├── vector_db/             # FAISS 索引持久化（按知识库分目录）
│   ├── sample_data/           # 示例电商商品数据
│   ├── .venv/                 # Python 虚拟环境
│   ├── rag.db                 # SQLite 数据库文件
│   ├── .env                   # 环境变量
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

## 常见问题

**Q: 如何切换到 PostgreSQL？**
编辑 `backend/.env`，将 `DATABASE_URL` 改为
`postgresql://postgres:密码@localhost:5432/rag_knowledge_base`，
并 `pip install "psycopg[binary]"`，然后重新执行 `init_db.py`。

**Q: 如何替换为真实 Embedding 模型？**
修改 `backend/app/services/rag_service.py` 中 `self.embeddings` 的实例化，
替换为任意实现 LangChain Embeddings 接口的类（如 `OpenAIEmbeddings`、
`HuggingFaceBgeEmbeddings`），替换后删除 `vector_db/` 并重新上传文档。

**Q: 后端修改代码后没有自动重载？**
uvicorn 的 watchfiles 在部分中文路径环境下监听不稳定，手动重启 `run.py` 即可。

## 许可证

MIT License
