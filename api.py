"""FastAPI 服务封装：POST /chat、GET /sessions/{id}/history、GET /logs"""
import asyncio
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from host.agent import Agent
from host.logging_utils import read_logs
from host.memory import SessionMemory

app = FastAPI(title="MCP 多服务智能助手", version="0.1.0")
_agent: Agent | None = None


@app.on_event("startup")
async def startup():
    global _agent
    _agent = Agent()
    await _agent.connect()


@app.on_event("shutdown")
async def shutdown():
    await _agent.close()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@app.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or f"api-{id(req) & 0xffff:x}"
    res = await _agent.chat(req.message, session_id=session_id)
    return {"session_id": session_id, **res}


@app.get("/sessions/{session_id}/history")
async def history(session_id: str):
    return {"session_id": session_id, "messages": SessionMemory(session_id).history()}


@app.get("/logs")
async def logs(limit: int = 50):
    return {"logs": read_logs(limit)}


@app.get("/health")
async def health():
    return {"status": "ok", "tools": len(_agent.tools)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
