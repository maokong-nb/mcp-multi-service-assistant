"""天气 MCP 服务：基于 Open-Meteo 免费 API（无需 API key）。"""
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("weather-service")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo WMO 天气码 → 中文描述（常用部分）
WEATHER_CODES = {
    0: "晴", 1: "大致晴", 2: "局部多云", 3: "阴",
    45: "雾", 48: "冻雾",
    51: "小毛毛雨", 53: "毛毛雨", 55: "浓毛毛雨",
    56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "强冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "小阵雨", 81: "阵雨", 82: "强阵雨",
    85: "小阵雪", 86: "强阵雪",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
}


def _desc(code: int) -> str:
    return WEATHER_CODES.get(code, f"天气码 {code}")


async def _geocode(city: str):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(GEOCODE_URL, params={"name": city, "count": 1, "language": "zh"})
        r.raise_for_status()
        results = r.json().get("results")
        return results[0] if results else None


@mcp.tool()
async def get_current_weather(city: str) -> str:
    """查询指定城市当前天气，返回天气状况、气温、湿度、风速。city 为城市名，如 深圳、北京、Tokyo。"""
    loc = await _geocode(city)
    if not loc:
        return f"未找到城市：{city}，请检查城市名"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(FORECAST_URL, params={
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        })
        r.raise_for_status()
        cur = r.json()["current"]
    return (
        f"{loc['name']}（{loc.get('country', '')}）当前：{_desc(cur['weather_code'])}，"
        f"气温 {cur['temperature_2m']}°C，湿度 {cur['relative_humidity_2m']}%，"
        f"风速 {cur['wind_speed_10m']} km/h"
    )


@mcp.tool()
async def get_weather_forecast(city: str, days: int = 1) -> str:
    """查询指定城市未来天气预报，days 取 1-7，返回每日天气状况、最高/最低气温和降水概率。"""
    days = max(1, min(7, days))
    loc = await _geocode(city)
    if not loc:
        return f"未找到城市：{city}，请检查城市名"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(FORECAST_URL, params={
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": days,
        })
        r.raise_for_status()
        daily = r.json()["daily"]
    lines = []
    for i in range(days):
        lines.append(
            f"{daily['time'][i]}：{_desc(daily['weather_code'][i])}，"
            f"{daily['temperature_2m_min'][i]}~{daily['temperature_2m_max'][i]}°C，"
            f"降水概率 {daily['precipitation_probability_max'][i]}%"
        )
    return f"{loc['name']} 未来 {days} 天预报：\n" + "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
