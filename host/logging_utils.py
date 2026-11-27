"""工具调用日志：JSONL 格式，一行一次调用，便于复盘和评测。"""
import json
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "tool_calls.jsonl"


def log_tool_call(session_id: str, tool: str, args: dict, result: str,
                  latency_ms: float, status: str = "ok"):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "session_id": session_id,
        "tool": tool,
        "args": args,
        "result_preview": str(result)[:200],
        "latency_ms": round(latency_ms, 1),
        "status": status,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_logs(limit: int = 50) -> list:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(x) for x in lines[-limit:]]
