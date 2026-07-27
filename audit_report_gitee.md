# Gitee 项目隐私 / 安全审计报告

- **审计时间**：2026-07-29
- **仓库**：`https://gitee.com/hhhhhhdw223/rag.git`
- **方法**：只读审计。通过 `git fetch` 拉取远端后，直接以提交哈希核查 Gitee 上**实际存在**的文件内容。
- **核查对象**：Gitee `master`（`0ebf436`）+ 已开启的 PR #1（`1732a166`）。本地提交 `1dae28e` 经验证是 PR #1 的祖先，故也已暴露。

---

## 一、结论速览

| 严重度 | 问题 | 文件:行 | 是否在 Gitee 暴露 |
|--------|------|---------|-------------------|
| 🔴 严重 | **真实 Agnes API Key 泄露** | `backend/app/core/config.py:15` | ✅ 是（master + PR #1 均含） |
| 🔴 严重 | **JWT 签名密钥硬编码默认值** | `backend/app/core/config.py:10` | ✅ 是 |
| 🟠 中等 | PostgreSQL 弱口令默认 `postgres/postgres` | `backend/app/core/config.py:7` | ✅ 是 |
| 🟡 较低 | 内部项目路径/环境信息、默认口令 `admin/123456` 被跟踪 | `.workbuddy/memory/*`、`README.md` | ✅ 是（无真实 PII，但泄露内部上下文） |
| 🟢 安全 | 用户数据（*.db / *.faiss / *.pkl / 上传文件） | `backend/db_data/`、`backend/vector_db/` | ❌ 否（已被 .gitignore 忽略，仅 `uploads/.gitkeep` 空占位文件在库） |

> **好消息**：本项目的真实用户数据（SQLite 数据库、FAISS 向量索引、上传的文档）**全部未被推送**，即使代码泄露也不会带出用户隐私数据。数据库密码本身是 bcrypt 哈希存储，非明文。

---

## 二、详细风险

### 🔴 风险 1：真实可用的 Agnes API Key 已公开（最高优先级）
- **位置**：`backend/app/core/config.py:15`
- **内容**：`AGNES_API_KEY = "sk-x8zRR5mR8Q6…（共 51 字符，完整值已落入 Gitee）"`
- **为何严重**：这是一个 `sk-` 前缀、可联网调用的真实密钥。一旦进入公开/私有仓库历史，任何能看到仓库的人都可盗刷你的 LLM 额度，产生费用甚至被用于违规用途。
- **扩散点**：`backend/app/services/rag_service.py` 直接用该值调用 `ChatOpenAI`。
- **现状**：在 Gitee `master` 与 PR #1 两个分支中均已存在。

### 🔴 风险 2：JWT 签名密钥为公开硬编码值
- **位置**：`backend/app/core/config.py:10`
- **内容**：`SECRET_KEY = "rag-knowledge-base-secret-key-2026-change-in-production"`
- **为何严重**：JWT 用此密钥做 HS256 签名/验签（`security.py:28` 签发、`:42` 验签）。该值是写死在源码里的公开字符串——任何人拿到就能**伪造任意用户（含 admin）的登录令牌**，实现账户接管。
- **触发条件**：若部署时未用 `.env` 覆盖此默认值，则生产环境直接使用该公开密钥。

### 🟠 风险 3：数据库连接弱口令默认值
- **位置**：`backend/app/core/config.py:7`
- **内容**：`DATABASE_URL` 默认 `postgresql://postgres:postgres@localhost:5432/...`
- **影响**：若部署时未覆盖，数据库将以 `postgres/postgres` 弱口令运行，易被本地/内网爆破。

### 🟡 风险 4：内部信息 / 默认口令文档化
- `.workbuddy/memory/MEMORY.md` 与 `2026-07-26.md` 被 git 跟踪，含本机绝对路径 `E:\vibe项目\RAG`、环境事实、默认口令 `admin/123456` 等。无真实个人 PII，但泄露项目内部上下文。
- `README.md`（第 53、75 行）明文记录了默认管理员账号 `admin / 123456`，属于弱口令文档化，建议上线前修改并避免在文档中固化。

---

## 三、👤 你必须做的事（只有你能做，我无法代劳）

> 以下动作涉及第三方账号后台与密钥本身，**必须由你本人操作**。

### 1. 立即作废并轮换 Agnes API Key（最紧急）
1. 登录 Agnes / APIHub 控制台（即 `https://apihub.agnes-ai.com` 对应的管理后台）。
2. 找到已暴露的密钥 `sk-x8zRR5mR8Q6…`，**直接作废/删除**它。
3. **重新生成**一个新 Key。
4. 新 Key **只放进** `backend/.env`（该文件已被 .gitignore 忽略，**不要**写回 `config.py`）。
5. 检查账单，确认无异常调用。

### 2. 更换 JWT SECRET_KEY
- 生成一个高强度随机值，例如运行 `openssl rand -hex 32`，把结果写入 `backend/.env`：
  ```
  SECRET_KEY=<新随机值>
  ```
- 这样部署时会覆盖 `config.py` 里的公开默认值。

### 3. 修改默认管理员口令
- 上线前把 `admin / 123456` 改成强密码（通过 `/change-password` 接口或数据库改 `users` 表）。

---

## 四、🔧 我可以帮你做的事（需你点头后执行，均为可选）

| 动作 | 说明 | 破坏性？ |
|------|------|----------|
| 改 `config.py` 去硬编码 | 把 `AGNES_API_KEY`/`SECRET_KEY`/`DATABASE_URL` 改为纯环境变量读取（不再内联真实值/弱口令默认） | 否 |
| 补全 `.gitignore` | 加入 `.workbuddy/memory/`、`backend/db_data/`、`backend/vector_db/`，避免内部信息/数据入库 | 否 |
| 重写 git 历史清除密钥 | 用 `git filter-repo` 把已提交的密钥从所有历史 commit 中抹掉 | **是（强推，会改变历史）** |
| 强制推送 + 关闭 PR #1 | 把清洗后的历史强推到 Gitee，并关闭已暴露的 PR #1 | **是** |

> ⚠️ 注意：**即便做了历史清理与强推，密钥轮换（第三节）仍然必须做**——因为密钥曾经公开过，旧 Key 必须作废。历史清理只是"减小暴露面"，不能替代轮换。

---

## 五、附录：核查证据（已脱敏）

- Gitee `master`（`0ebf436`）与 PR #1（`1732a166`）的 `backend/app/core/config.py` 均含：
  - 第 15 行：`AGNES_API_KEY = "sk-x8z…[已脱敏，共 51 字符]"`
  - 第 10 行：`SECRET_KEY = "rag-knowledge-base-secret-key-2026-change-in-production"`
- 用户数据核查：`git ls-tree -r 0ebf436` 中匹配 `*.db|*.faiss|*.pkl|uploads/|db_data/|vector_db/` 的**仅有** `backend/app/uploads/.gitkeep`（空占位文件），无真实数据文件。
- 全树扫描未发现除 `config.py` 之外的其他真实密钥；其余 `password/token/secret` 命中均为正常代码（bcrypt 哈希、JWT 函数、Schema 字段定义）。
