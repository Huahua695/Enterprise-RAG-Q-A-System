# 更新日志（CHANGELOG）

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式记录显著变更。

## [2026-09-04] LLM 集成通用化（移除 AgnesAI 专属配置）

### Changed（变更）

- **LLM 配置通用化**：`AGNES_API_KEY` / `AGNES_BASE_URL` / `AGNES_MODEL` 重命名为
  `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`，代码不再内置任何厂商默认值；
  任意 OpenAI 兼容服务（DeepSeek / 通义千问 / Ollama / one-api 等）改
  `backend/.env` 即可接入（⚠️ 破坏性：旧配置名不再读取，需同步改名）。
  原 `AGNES_EMBEDDING_MODEL` 无实际使用处，直接移除。
- `ChatOpenAI` 客户端改为首次问答时惰性构建：未配置 LLM 时后端照常启动
  （上传/检索不受影响），问答接口经 SSE error 事件返回明确的配置指引。
- `EMBEDDING_PROVIDER=openai` 改复用 `LLM_API_KEY` / `LLM_BASE_URL`，
  未配置时构建即报错并给出指引。
- `.env.example`（根目录与 backend/）、`docker-compose.yml`、README、
  e2e 夹具、CI 流水线同步更新。

## [2026-08-31] 测试反馈改进轮

依据 `docs/改进建议.md`（测试工程师 4 项反馈）完成的改进，改动前基线 27 个测试全绿。

### Added（新增）

- **上传文档后台向量化**：上传接口改为 FastAPI BackgroundTasks 异步处理，校验落盘后立即返回
  "已接收"，解析→切块→向量化在后台执行并回写文档状态（`app/services/document_processor.py`）；
  前端每 2s 轮询文档列表直到完成，状态列以 Tag 颜色区分（处理中/已完成/失败），
  失败行 Tooltip 展示原因；生产环境可平滑升级为 Celery + Redis。
- **登录限流持久化**：新增 `login_failures` 表，`LoginRateLimiter` 从进程内存迁移到 SQLite——
  重启不丢、多 worker 共享；窗口起点为首次失败时间，达阈值锁定至窗口结束，过期记录惰性清理。
- **Playwright 端到端测试**（`e2e/`）：登录成功/失败流、建知识库→上传文档→等待后台向量化完成→
  流式问答→断言答案与引用来源；服务未启动或未配置 LLM_API_KEY 时自动跳过。
- **文档状态接口字段**：`DocumentInfo` 补充 `error_message`，前端可展示失败原因。
- 新增测试：限流计数落库断言、后台任务 completed/failed 状态流转（`tests/test_document_processor.py`）。

### Changed（变更）

- 上传接口响应从同步结果（`chunks`）改为接收回执（`document_id` + `status="processing"`）。
- `RAGEngine` 索引读写（`add_documents`/`delete_collection`）加 `threading.Lock` 串行化，
  防止后台任务并发写坏 FAISS 索引。
- README 运行测试章节补充 E2E 用法，目录结构更新。

### Fixed（修复）

- `auth.py` 两处 `datetime.utcnow()` 弃用警告：统一替换为 timezone-aware 新写法生成的
  naive UTC（`_utcnow_naive()`），消除控制台 DeprecationWarning。

### Commits

- `3a849ca` fix: datetime.utcnow 改为 timezone-aware 写法（改进建议④）
- `2a03148` feat: 登录限流计数持久化到 SQLite（改进建议②）
- `2caf19e` feat: 上传文档后台向量化与前端状态轮询（改进建议①）
- `test: Playwright 端到端测试`（改进建议③）

## [2026-08-30 及以前] 项目主体建设

- 核心链路：注册登录（JWT + token 吊销 + 登录限流）、知识库管理、文档上传解析、
  FAISS 向量检索、SSE 流式问答与引用来源、会话管理、Docker Compose 部署。
- Embedding 切换 fastembed 语义模型（BAAI/bge-small-zh-v1.5）并重建索引，
  可插拔工厂支持 local/fastembed/openai 三 provider。
- 安全加固：SECRET_KEY 缺失拒绝启动、上传白名单/大小限制、删除清理、
  faiss 非 ASCII 路径写入修复、日志体系。
- CI：Gitee Go 流水线自动执行 pytest。
- 测试：单元 + 接口测试（认证安全/上传安全/配置基线/Embedding 工厂/日志），
  详见 `docs/测试报告.md`。
