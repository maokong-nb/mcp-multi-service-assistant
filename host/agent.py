"""Agent 主循环：连接多个 MCP 服务 → 注册工具 → LLM 多步工具调用 → 记忆与日志。"""
import json
import sys
import time
from contextlib import AsyncExitStack
from datetime import datetime
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from host.llm import make_llm
from host.logging_utils import log_tool_call
from host.memory import SessionMemory

ROOT = Path(__file__).resolve().parent.parent

try:  # 可选：从 .env 读取 LLM_API_KEY 等配置
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

SERVERS = {
    "datetime": ROOT / "servers" / "datetime_server.py",
    "weather": ROOT / "servers" / "weather_server.py",
    "notes": ROOT / "servers" / "notes_server.py",
}

SYSTEM_PROMPT = """你是一个多服务智能助手，当前日期 {today}。你可以通过工具完成以下事情：
- datetime 服务：查询当前时间、日期推算、时区换算、日期差
- weather 服务：查询城市实时天气和未来 1-7 天预报
- notes 服务：创建、搜索、列出、删除笔记

行为要求：
1. 需要实时信息（时间、天气）、日期推算或时区换算、或需要读写笔记时，必须调用工具，不要凭记忆编造或心算。
2. 用户一句话包含多个需求时，按依赖顺序依次调用工具，后面的工具可以利用前面工具的结果。
3. 工具返回"错误"或"未找到"时，如实转告用户并给出修正建议，不要假装成功。
4. 用户追问之前提过的信息时，先回看对话历史；历史里有的内容直接引用作答，不要在有依据的情况下声称"没查到"或"没保存成功"。
5. 用简洁的中文回答，关键信息（日期、温度、笔记编号）要保留。
"""

MAX_TOOL_ROUNDS = 8


class Agent:
    def __init__(self):
        self.llm = make_llm()
        self.sessions = {}    # server 名 -> ClientSession
        self.tools = []       # OpenAI function-calling 格式
        self._tool_map = {}   # 工具名 -> server 名
        self._stack = None

    async def connect(self):
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for name, path in SERVERS.items():
            params = StdioServerParameters(command=sys.executable, args=[str(path)])
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
            for t in listed.tools:
                self._tool_map[t.name] = name
                self.tools.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema,
                    },
                })
            self.sessions[name] = session

    async def chat(self, user_text: str, session_id: str = "default") -> dict:
        memory = SessionMemory(session_id)
        memory.add({"role": "user", "content": user_text})
        system = SYSTEM_PROMPT.format(today=datetime.now().strftime("%Y-%m-%d"))
        messages = [{"role": "system", "content": system}] + memory.history()

        calls_made, prompt_tokens, completion_tokens = [], 0, 0
        for _ in range(MAX_TOOL_ROUNDS):
            resp = self.llm.chat(messages, self.tools)
            prompt_tokens += resp.prompt_tokens
            completion_tokens += resp.completion_tokens

            if not resp.tool_calls:
                memory.add({"role": "assistant", "content": resp.content})
                return {
                    "reply": resp.content,
                    "tool_calls": calls_made,
                    "usage": {"prompt": prompt_tokens, "completion": completion_tokens},
                }

            messages.append({
                "role": "assistant",
                "content": resp.content,
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"],
                                  "arguments": json.dumps(tc["arguments"], ensure_ascii=False)}}
                    for tc in resp.tool_calls
                ],
            })
            for tc in resp.tool_calls:
                server = self._tool_map.get(tc["name"])
                t0 = time.time()
                try:
                    if server is None:
                        raise ValueError(f"未注册的工具：{tc['name']}")
                    result = await self.sessions[server].call_tool(tc["name"], tc["arguments"])
                    text = "".join(b.text for b in result.content if hasattr(b, "text"))
                    status = "error" if result.isError else "ok"
                except Exception as e:  # 工具异常不中断对话，反馈给 LLM 让它修正或转告
                    text, status = f"工具调用失败：{e}", "error"
                log_tool_call(session_id, tc["name"], tc["arguments"], text,
                              (time.time() - t0) * 1000, status)
                calls_made.append({"tool": tc["name"], "args": tc["arguments"], "status": status})
                messages.append({"role": "tool", "tool_call_id": tc["id"],
                                 "name": tc["name"], "content": text})

        return {"reply": "（达到最大工具调用轮数，请把问题拆小一点再试）",
                "tool_calls": calls_made,
                "usage": {"prompt": prompt_tokens, "completion": completion_tokens}}

    async def close(self):
        if self._stack:
            await self._stack.aclose()
