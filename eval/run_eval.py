"""评测脚本：运行 eval/dataset.json，输出工具选择准确率、答案命中率、时延与成本。

用法：
    python eval/run_eval.py            # 完整评测
    MOCK_LLM=1 python eval/run_eval.py # 离线链路验证（结果不代表真实模型表现）

结果写入 eval/results/，并在终端打印汇总。
"""
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from host.agent import Agent  # noqa: E402

# 价格按 DeepSeek 官方刊例（元/百万 token），换模型时改这里
PRICE_IN_PER_M = 2.0
PRICE_OUT_PER_M = 8.0

DATASET = Path(__file__).parent / "dataset.json"
OUT_DIR = Path(__file__).parent / "results"


async def run():
    items = json.loads(DATASET.read_text(encoding="utf-8"))
    agent = Agent()
    await agent.connect()
    is_mock = agent.llm.__class__.__name__ == "MockLLM"
    records = []
    try:
        for item in items:
            session_id = f"eval-{item['id']}-{int(time.time())}"
            turns = item.get("turns", [item["question"]])
            called, reply, latency = [], "", 0.0
            prompt_tokens = completion_tokens = 0
            for turn in turns:
                t0 = time.time()
                res = await agent.chat(turn, session_id=session_id)
                latency += time.time() - t0
                reply = res["reply"]
                called += [c["tool"] for c in res["tool_calls"]]
                prompt_tokens += res["usage"]["prompt"]
                completion_tokens += res["usage"]["completion"]
            tool_ok = set(item.get("expected_tools", [])).issubset(set(called))
            kw = item.get("answer_keywords", [])
            kw_ok = all(k in reply for k in kw) if kw else True
            cost = prompt_tokens * PRICE_IN_PER_M / 1e6 + completion_tokens * PRICE_OUT_PER_M / 1e6
            records.append({
                "id": item["id"], "category": item["category"],
                "question": item["question"],
                "expected_tools": item.get("expected_tools", []), "called_tools": called,
                "tool_ok": tool_ok, "answer_ok": kw_ok,
                "latency_s": round(latency, 2),
                "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                "cost_cny": round(cost, 6),
                "reply_preview": reply[:120],
            })
            print(f"[{item['id']:>2}] {item['category']:<10} 工具{'✓' if tool_ok else '✗'} "
                  f"答案{'✓' if kw_ok else '✗'} {latency:.1f}s  {item['question'][:24]}")
    finally:
        await agent.close()

    n = len(records)
    summary = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "llm_mode": "mock（仅链路验证）" if is_mock else "llm",
        "total": n,
        "tool_accuracy": round(sum(r["tool_ok"] for r in records) / n, 4),
        "answer_accuracy": round(sum(r["answer_ok"] for r in records) / n, 4),
        "both_ok": round(sum(r["tool_ok"] and r["answer_ok"] for r in records) / n, 4),
        "avg_latency_s": round(sum(r["latency_s"] for r in records) / n, 2),
        "total_cost_cny": round(sum(r["cost_cny"] for r in records), 4),
        "avg_cost_cny": round(sum(r["cost_cny"] for r in records) / n, 6),
    }
    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (OUT_DIR / f"eval-{ts}.json").write_text(
        json.dumps({"summary": summary, "records": records}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print("\n===== 汇总 =====")
    for k, v in summary.items():
        print(f"{k}: {v}")
    if is_mock:
        print("\n注意：本次为 mock 链路验证，结果不代表真实模型表现。"
              "配置 LLM_API_KEY 后重跑得到正式评测结果。")


if __name__ == "__main__":
    asyncio.run(run())
