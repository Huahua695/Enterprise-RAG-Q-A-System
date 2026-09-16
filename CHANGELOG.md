# 更新日志（CHANGELOG）

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 格式记录显著变更。

## [2026-09-16] CI 流水线可用性修复：pythonVersion 对齐 + 用例环境依赖缺陷

### Fixed（修复）

- **`test_fastembed_dispatch` 依赖外部环境变量**（`backend/tests/test_embeddings_factory.py`）：
  该用例直接调用 `build_embeddings()` 并期望分发到 fastembed，但流水线注入了
  `EMBEDDING_PROVIDER=local`，实际返回 `LocalHashEmbeddings` → **CI 首次运行即失败**
  （复现：`1 failed, 36 passed`）。已改为在用例内显式
  `monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "fastembed")`，
  使被测前提由用例自己声明，不再随外部环境漂移。
  同文件的 `test_default_provider_is_fastembed` 本就是按该设计写的（断言出厂默认值），
  本次是把遗漏的那个补齐。
- **`.workflow/master-pipeline.yml` 命令写法**：`pip` / `pip3` / `python` 混用改为统一的
  `python3 -m pip` / `python3 -m pytest`。该插件基础镜像为 CentOS，统一写法可保证
  pip 装入的包与执行 pytest 的解释器是同一个，且不依赖 `python` / `pip` 短名是否存在。

### Changed（变更）

- **`.workflow/master-pipeline.yml` 的 `pythonVersion`**：`'3.12'` → `'3.13'`，
  与本地 `backend/.venv`（Python 3.13.14）对齐，消除版本错位风险。

### 验证

忠实复现 CI 条件（临时隐藏被忽略的 `backend/.env`、清除本机相关环境变量）：

| 条件 | 结果 |
|---|---|
| `EMBEDDING_PROVIDER=local` + 无 `.env`（修复后 CI 实况） | 37 passed |
| 不注入 `EMBEDDING_PROVIDER` + 无 `.env` | 37 passed |
| 本地常规环境（有 `.env`） | 37 passed |
| 同上第一项，但改动前用例代码 | 1 failed, 36 passed（复现 CI 失败） |

## [2026-09-16] 一键双远端推送：`scripts/push_all.py` + `push-all.bat`

### Added（新增）

- **`scripts/push_all.py`**：一条命令把当前分支推到 Gitee（`origin`）与 GitHub（`github`）两个远端。
  当本机访问不了 `github.com`（国内网络常见）时，GitHub 直推会失败，脚本**自动改走
  GitHub Git Data API 兜底**（`blob → tree → commit → PATCH ref`），保留原 author/committer/message，
  生成提交与本地 **sha 完全一致**，属无损搬运。仓库名从 `git remote get-url github` 自动推导，
  令牌优先取环境变量 `GH_TOKEN`，否则读 git 凭据管理器。
- **`push-all.bat`**：双击即用的入口（内部调用上面的脚本），适合不习惯命令行的场景。
- **git 别名**：`git config alias.pushall` 指向同一脚本，命令行敲 `git pushall` 即可。

## [2026-09-16] 仓库复查修复：LLM 超时保护 + .gitignore 误伤 + 配置模板整理

### Added（新增）

- **LLM 请求超时与重试**：`ChatOpenAI` 现在显式下发 `timeout` / `max_retries`，
  由 `LLM_TIMEOUT`（默认 60 秒）与 `LLM_MAX_RETRIES`（默认 2 次）经 `.env` 控制。
  修复前不设超时时走 OpenAI SDK 默认值——**读超时 600 秒**，网关异常时流式回答会
  长时间挂起（实测：仅建立连接不回包的地址会挂满 10 分钟）；改进后 3 秒配置实测
  4.3 秒即中止并抛 `APITimeoutError`。新增 `tests/test_llm_config.py` 6 个用例覆盖。

### Fixed（修复）

- **`.gitignore` 误伤前端数据目录**：第 46 行 `data/`（无前导斜杠）会匹配任意层级的
  `data` 目录，导致 `frontend/src/data/products.ts` 被静默忽略——商品展示功能提交时
  该文件不会入库，他人克隆后前端直接编译失败。改为 `/data/`（仅忽略仓库根目录），
  已验证 `frontend/src/data/**` 恢复可追踪、根目录 `data/` 仍被忽略。
- **配置模板弱默认值**：`backend/.env.example` 的 `SECRET_KEY` 由可被直接沿用的
  示例值改为留空 + 生成命令提示（沿用时启动即失败，而非静默使用弱密钥）。

### Changed（变更）

- **两份配置模板职责说明**：根目录 `.env.example`（docker compose 用）与
  `backend/.env.example`（本地开发用）并非重复文件，各自补充交叉引用注释，
  避免使用者复制错模板；两份均补齐 `LLM_TIMEOUT` / `LLM_MAX_RETRIES` 说明，
  `docker-compose.yml` 同步透传这两个变量。

## [2026-09-07] 问答等待体验优化：商品轮换展示 + 分阶段提示 + 停止生成

### Added（新增）

- **商品介绍轮换卡片**（`ProductShowcase`）：空会话欢迎页与等待答案期间自动轮换展示
  "今日好物"（图片、卖点、示例问题），悬停暂停、圆点可手动切换；欢迎页示例问题
  点击即发送（无会话时自动新建）。
- **停止生成按钮**：问答流式期间"发送"变为"停止"，经 `AbortController` 中断 SSE；
  后端会持久化已生成的部分回答，前端本地同步补一条"（已停止生成）"保持展示。
- 商品素材压缩入库（约 1MB/张 PNG → 26~63KB/张 JPEG，共 7 张宠物用品图），
  展示内容集中配置在 `frontend/src/data/products.ts`，与知识库数据解耦。

### Changed（变更）

- **分阶段等待提示**：等待气泡先显示"正在检索知识库…"，收到 SSE references 事件后
  切换为"已找到 N 条相关资料，正在生成答案…"并伴随打字动画；引用来源改为
  检索完成即展示（此前要等整条回答流结束才可见），流式回答期间同样实时显示引用。
- `chatService.sendQuestion` 新增可选 `signal` 参数支持中断。

### Fixed（修复，实测反馈）

- **流式回答串会话**：流式状态从全局单份改为按会话 ID 隔离（`streams` 字典 +
  每会话独立 AbortController），生成期间切换/新建会话不再把等待与生成气泡显示到
  其他会话；回答完成后仅刷新当前停留会话的消息列表，删除生成中的会话会先中断流。
- **示例问题卡片溢出**："问问看"示例问题较长时超出卡片边框，改为允许换行。
- **示例问题命中率**：示例问题改为对应知识库 1.2/1.3 章节实际记录的条目属性
  （猫粮品牌清单、化毛配方、冻干复水方法、磨牙棒硬度分级、鱼油适用症状等），
  点击后可召回相关条目作答，不再答非所问。

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
