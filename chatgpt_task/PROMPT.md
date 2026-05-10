# ChatGPT Task Scheduler Prototype

## System Requirements

Build a job scheduler with an MCP (Model Context Protocol) interface:
- Users schedule tasks for future execution via MCP tool calls
- A background watcher scans for due jobs and pushes them to a queue
- Workers pull jobs from the queue and execute them
- Support task creation, listing, status checking, and cancellation
- Tool naming follows namespace + action verb pattern (e.g., `task.create`)

### Architecture

```
User → MCP Tool Call → Job Scheduler API → DB
                                            ↓
                              Watcher (scans DB) → Queue → Worker (executes)
```

## Design Questions

Answer these before you start coding:

1. **Watcher vs Cron:** Why separate the watcher from the worker? What problems does a single cron job that both scans and executes have?
- 如果 watcher 和 worker 合在一起，一個慢任務（例如 LLM 執行需要 30 秒）會阻塞整個掃描迴圈，導致其他到期的 job 無法被及時發現
- Watcher 只做輕量的 DB 掃描並把 job id 推入 queue；Worker 專注執行，可獨立 scale
- 職責分離後，watcher 的掃描頻率（每 10 秒）和 worker 的執行時間互不影響

2. **Queue Layer:** Why put a queue between the watcher and worker instead of having the watcher call the worker directly? What are the benefits?
- 解耦：watcher 只需 put(job_id)，不需要知道 worker 的實作細節
- 背壓控制：queue 有容量限制，若 worker 處理不過來，watcher 自動等待而不會無限堆積任務
- 可靠性：job 已進入 queue 就不會因 watcher crash 而遺失（若換成 SQS 等持久化 queue 則更明顯）
- 未來 scale out 方便：可輕易改成多個 worker thread 或跨機器的 message broker（e.g. SQS、RabbitMQ）

3. **Time Bucket Partitioning:** Instead of `SELECT * WHERE scheduled_at <= now()`, why partition jobs by time bucket (e.g., hour)? What happens to query performance at 1M+ jobs without partitioning?
- 因為 time bucket 是具有時間性的, 並且在這task 當中可以依照這時間區間內去執行, 並且可以作為 PK 使用
- 選擇不用的話, 在1M+ jobs 情況下, 會讓DB query 搜尋來以外還需要去做排序, 會沒有效率
- 沒有 time bucket 的情況下，`WHERE scheduled_at <= now()` 是一個 range scan，在 1M+ 筆資料時即使有 index 仍需掃描大量已完成/已取消的歷史 row
- Time bucket 讓 watcher 每次只查詢「當前小時」的那一小批 row，配合 composite index (time_bucket, status)，查詢成本幾乎固定，不隨總資料量成長

4. **Tool Naming:** Why `task.create` instead of `createTask`? How does naming convention affect LLM tool selection accuracy?
- Namespace.verb 格式（task.create, task.cancel）讓 LLM 在面對多個工具時能先依 namespace 縮小候選範圍，再選動詞，降低錯誤選工具的機率
- camelCase 的 createTask 在語意上沒有層級，當工具數量增加（e.g. task.create, reminder.create, note.create）時，LLM 更難從名稱本身判斷工具的分類與用途
- 點分隔的命名方式也與 REST resource 路由的直覺一致，對人類開發者閱讀 tool list 也更清晰

5. **Registry vs If-Else:** Why use a dictionary registry to route tool calls instead of if-else chains? What happens when you need to add the 20th tool?
- 一旦 tool 多, 就會有太多 if-else, 造成程式碼可讀性低
- 許多個if-else 在程式碼當中, 在可讀性跟維運上一定會增加困難度


## Verification

Your prototype is a real MCP server. Test it with the MCP inspector — no Claude needed.

### 1. Start the server (sanity check)

```bash
python -m app.mcp_server
```

The process should hang waiting on stdin (it's a stdio MCP server — that's correct). Ctrl+C to stop. If you see an `ImportError` or other crash, fix that first.

### 2. Run the MCP inspector

Requires Node.js (uses `npx`).

```bash
npx @modelcontextprotocol/inspector python -m app.mcp_server
```

This opens a browser GUI (usually `http://localhost:5173`).

Steps in the GUI:

1. Click **Connect** -> should show 4 tools: `task.create`, `task.list`, `task.status`, `task.cancel`
2. **task.create** -> fill `description="Summarize tech news"`, `scheduled_at="2025-01-01T00:00:00"` (past time so watcher picks it up immediately) -> **Run Tool** -> response should include `{"job_id": 1, "status": "pending", ...}`
3. Wait ~10 seconds, then **task.status** -> `job_id: 1` -> status should now be `"completed"`
4. **task.create** with future time `"2099-12-31T00:00:00"` -> get `job_id: 2`
5. **task.cancel** -> `job_id: 2` -> status `"cancelled"`
6. **task.list** -> see all your jobs

### 3. (Optional) Connect to Claude Desktop / Claude Code

Once the inspector tests pass, the server is ready. To talk to it through Claude:

**Claude Desktop**: edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and add (use absolute paths):

```json
{
  "mcpServers": {
    "task-scheduler": {
      "command": "/absolute/path/to/scaffold/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/scaffold"
    }
  }
}
```

Restart Claude Desktop fully. The 🔨 icon in the chat input should show 4 tools.

**Claude Code**: edit `~/.claude.json` (top-level `mcpServers` for user scope) with the same block, or run `claude mcp add` from inside `scaffold/`.

Then chat:
> "Schedule a task to review PR #123 tomorrow at 9am."
> -> Claude calls `task.create` -> returns job_id
> "What's the status of that task?"
> -> Claude calls `task.status`

## Suggested Tech Stack

Python + the official `mcp` SDK is recommended (already in `requirements.txt` for the Guided Track). Challenge Track may use any language with an MCP SDK.
