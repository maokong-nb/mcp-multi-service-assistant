"""笔记 MCP 服务：创建、搜索、列出、删除笔记，SQLite 持久化。"""
import sqlite3
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "notes.db"

mcp = FastMCP("notes-service")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )"""
    )
    return conn


@mcp.tool()
def create_note(title: str, content: str, tags: str = "") -> str:
    """创建一条笔记。title 为标题，content 为正文，tags 为逗号分隔的标签（可空）。"""
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO notes(title, content, tags, created_at) VALUES(?,?,?,?)",
            (title, content, tags, datetime.now().isoformat(timespec="seconds")),
        )
        return f"已创建笔记 #{cur.lastrowid}：{title}"


@mcp.tool()
def search_notes(keyword: str) -> str:
    """按关键词搜索笔记，匹配标题、正文和标签，返回最近 10 条。"""
    like = f"%{keyword}%"
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, title, content, tags, created_at FROM notes "
            "WHERE title LIKE ? OR content LIKE ? OR tags LIKE ? ORDER BY id DESC LIMIT 10",
            (like, like, like),
        ).fetchall()
    if not rows:
        return f"未找到包含「{keyword}」的笔记"
    return "\n".join(
        f"#{r[0]} [{r[1]}] {r[2][:60]}（标签：{r[3] or '无'}，{r[4]}）" for r in rows
    )


@mcp.tool()
def list_notes(limit: int = 10) -> str:
    """列出最近创建的笔记，limit 为返回条数（最多 50）。"""
    limit = max(1, min(50, limit))
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, title, tags, created_at FROM notes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    if not rows:
        return "还没有任何笔记"
    return "\n".join(f"#{r[0]} [{r[1]}]（标签：{r[2] or '无'}，{r[3]}）" for r in rows)


@mcp.tool()
def delete_note(note_id: int) -> str:
    """按 ID 删除一条笔记。"""
    with _conn() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        if cur.rowcount == 0:
            return f"笔记 #{note_id} 不存在"
        return f"已删除笔记 #{note_id}"


if __name__ == "__main__":
    mcp.run()
