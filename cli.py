"""命令行入口：python cli.py [--session my-session]"""
import argparse
import asyncio
import uuid

from host.agent import Agent


async def main():
    parser = argparse.ArgumentParser(description="MCP 多服务智能助手 CLI")
    parser.add_argument("--session", default=f"cli-{uuid.uuid4().hex[:6]}",
                        help="会话 ID，相同 ID 共享对话记忆")
    args = parser.parse_args()

    agent = Agent()
    await agent.connect()
    print(f"助手已启动（session={args.session}，模型={'mock' if agent.llm.__class__.__name__ == 'MockLLM' else 'llm'}）")
    print("输入 quit 退出，输入 clear 清空本会话记忆\n")
    try:
        while True:
            q = input("你：").strip()
            if not q:
                continue
            if q.lower() in ("quit", "exit"):
                break
            res = await agent.chat(q, session_id=args.session)
            print(f"助手：{res['reply']}")
            if res["tool_calls"]:
                used = ", ".join(f"{c['tool']}({c['status']})" for c in res["tool_calls"])
                print(f"  [工具调用] {used}")
            print()
    finally:
        await agent.close()


if __name__ == "__main__":
    asyncio.run(main())
