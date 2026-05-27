# 可观测性（structlog + LangFuse）

## structlog

后端在 `app/observability/logging.py` 中配置结构化日志。默认随应用启动启用，无需额外服务。

## LangFuse（可选）

1. 启动栈（含 LangFuse 与独立库）：

   ```bash
   docker compose up -d postgres redis backend langfuse
   ```

   首次创建 Postgres 卷时会执行 `docker/postgres/init/01-create-langfuse-db.sql` 创建 `langfuse` 库。

2. 浏览器打开 http://127.0.0.1:3001 ，注册项目并复制 Public/Secret Key。

3. 在 `.env` 中设置：

   ```env
   LANGFUSE_ENABLED=true
   LANGFUSE_HOST=http://127.0.0.1:3001
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   ```

4. 安装可选依赖：`pip install langfuse`（见 `requirements.txt` 注释行）。

DeepSeek `_chat` 在启用后通过 `maybe_observe` 记录 span；未配置 key 时自动降级为无追踪。
