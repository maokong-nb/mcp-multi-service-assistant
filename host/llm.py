"""LLM 客户端封装。

- OpenAILLM：OpenAI 兼容接口，DeepSeek / 通义 / OpenAI 等均可，通过环境变量配置。
- MockLLM：离线规则路由，仅用于在没有 API key 时验证 MCP 链路、会话记忆与日志，
  其评测结果不代表真实模型表现。
"""
import json
import os
import re
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    content: str
    tool_calls: list = field(default_factory=list)  # [{"id","name","arguments"}]
    prompt_tokens: int = 0
    completion_tokens: int = 0


class OpenAILLM:
    def __init__(self):
        from openai import OpenAI

        self.client = OpenAI(
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=os.environ["LLM_API_KEY"],
        )
        self.model = os.getenv("LLM_MODEL", "deepseek-chat")

    def chat(self, messages, tools) -> LLMResponse:
        kwargs = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        tool_calls = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": json.loads(tc.function.arguments or "{}"),
            }
            for tc in (msg.tool_calls or [])
        ]
        usage = resp.usage
        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )


_CITIES = [
    "深圳", "广州", "北京", "上海", "杭州", "香港", "澳门", "成都",
    "武汉", "西安", "南京", "重庆", "东莞", "佛山", "纽约", "伦敦", "东京",
]


class MockLLM:
    """离线链路验证：按关键词路由工具，收到工具结果后原样汇总。"""

    def __init__(self):
        self._n = 0

    def chat(self, messages, tools) -> LLMResponse:
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        done = {m.get("name") for m in messages if m["role"] == "tool"}
        call = self._route(user, done)
        if call:
            self._n += 1
            return LLMResponse("", [{"id": f"mock-{self._n}", "name": call[0], "arguments": call[1]}])
        results = [m["content"] for m in messages if m["role"] == "tool"]
        if results:
            return LLMResponse("；".join(results), [])
        return LLMResponse("（mock 模式：未命中工具规则。配置 LLM_API_KEY 后可使用真实模型回答）", [])

    # ---- 规则路由（仅覆盖评测集中出现的需求形态）----
    @staticmethod
    def _extract_city(text: str) -> str:
        for c in _CITIES:
            if c in text:
                return c
        m = re.search(r"([一-龥]{2,4})市?(?:的)?(?:现在|今天|明天|后天|未来|\s)*(?:天气|气温|热不热|会下雨|预报)", text)
        if not m:
            return "深圳"
        # 去掉开头的动作词，如"查一下""帮我查"
        return re.sub(r"^(查一下|帮我查|帮我|看看|请问|查|问)", "", m.group(1)) or "深圳"

    def _route(self, text, done):
        wants_note = any(k in text for k in ["记", "笔记", "提醒", "备忘", "新建"])
        wants_list = any(k in text for k in ["列出", "哪些笔记", "所有笔记"])
        wants_search = any(k in text for k in ["搜", "找一下", "有没有", "查过"])

        # 日期差
        if any(k in text for k in ["相差", "差几天", "距离"]) and "date_diff" not in done:
            dates = re.findall(r"(\d{4})[-年](\d{1,2})[-月](\d{1,2})", text)
            if len(dates) >= 2:
                fmt = lambda t: f"{t[0]}-{int(t[1]):02d}-{int(t[2]):02d}"
                return ("date_diff", {"date1": fmt(dates[0]), "date2": fmt(dates[1])})

        # N 天后
        m = re.search(r"(\d+)\s*天(?:以?后|之后|前)", text)
        if m and "days_from_now" not in done:
            days = int(m.group(1)) * (-1 if "天前" in text else 1)
            return ("days_from_now", {"days": days})

        # 天气
        if any(k in text for k in ["天气", "下雨", "气温", "热不热", "预报"]):
            city = self._extract_city(text)
            forecastish = any(k in text for k in ["明天", "后天", "未来", "预报", "会下雨"])
            if forecastish and "get_weather_forecast" not in done:
                days = 3 if ("三天" in text or "3天" in text or "3 天" in text) else (2 if "后天" in text else 1)
                return ("get_weather_forecast", {"city": city, "days": days})
            if not forecastish and "get_current_weather" not in done:
                return ("get_current_weather", {"city": city})
            if wants_note and "create_note" not in done:
                return ("create_note", {"title": f"{city}天气记录", "content": f"（mock）{city}天气，详见查询结果", "tags": "天气"})
            return None

        # 当前时间
        if any(k in text for k in ["几点", "现在时间", "当前时间"]):
            tz = "America/New_York" if "纽约" in text else ("Europe/London" if "伦敦" in text else "Asia/Shanghai")
            if "get_current_time" not in done:
                return ("get_current_time", {"timezone": tz})
            if wants_note and "create_note" not in done:
                return ("create_note", {"title": "时间记录", "content": "（mock）当前时间记录", "tags": ""})
            return None

        # 笔记
        if wants_search and "search_notes" not in done:
            m2 = re.search(r"关于(.+?)的笔记", text)
            kw = m2.group(1).strip() if m2 else text.replace("搜一下", "")[:6]
            return ("search_notes", {"keyword": kw.strip()})
        if wants_note and "create_note" not in done:
            body = text.split("：", 1)[1] if "：" in text else text
            return ("create_note", {"title": body[:12], "content": body, "tags": ""})
        if wants_list and "list_notes" not in done:
            return ("list_notes", {"limit": 10})
        return None


def make_llm():
    """有 LLM_API_KEY 且未强制 MOCK_LLM 时用真实模型，否则用 MockLLM 验证链路。"""
    if os.getenv("MOCK_LLM") == "1" or not os.getenv("LLM_API_KEY"):
        return MockLLM()
    return OpenAILLM()
