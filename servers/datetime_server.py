"""日期时间 MCP 服务：当前时间、日期推算、时区换算、日期差。"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("datetime-service")

WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        raise ValueError(f"未知时区：{name}，请使用 IANA 时区名，如 Asia/Shanghai、America/New_York")


@mcp.tool()
def get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """获取指定时区的当前时间。timezone 为 IANA 时区名，如 Asia/Shanghai、America/New_York、Europe/London。"""
    now = datetime.now(_tz(timezone))
    return f"{timezone} 当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}（{WEEKDAY_ZH[now.weekday()]}）"


@mcp.tool()
def days_from_now(days: int, timezone: str = "Asia/Shanghai") -> str:
    """计算距今天 N 天之后（负数表示之前）的日期和星期。"""
    target = datetime.now(_tz(timezone)) + timedelta(days=days)
    direction = "之后" if days >= 0 else "之前"
    return f"{abs(days)} 天{direction}是 {target.strftime('%Y-%m-%d')}（{WEEKDAY_ZH[target.weekday()]}）"


@mcp.tool()
def date_diff(date1: str, date2: str) -> str:
    """计算两个日期相差的天数，日期格式为 YYYY-MM-DD。"""
    try:
        d1 = datetime.strptime(date1, "%Y-%m-%d").date()
        d2 = datetime.strptime(date2, "%Y-%m-%d").date()
    except ValueError:
        return f"错误：日期格式无效（收到 {date1!r}、{date2!r}），需要 YYYY-MM-DD 且为真实存在的日期"
    return f"{date1} 与 {date2} 相差 {abs((d2 - d1).days)} 天"


@mcp.tool()
def convert_timezone(time_str: str, from_tz: str, to_tz: str) -> str:
    """把一个时间从源时区换算到目标时区。time_str 格式 YYYY-MM-DD HH:MM，时区用 IANA 名。"""
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M").replace(tzinfo=_tz(from_tz))
    except ValueError:
        return f"错误：时间格式无效（收到 {time_str!r}），需要 YYYY-MM-DD HH:MM"
    target = dt.astimezone(_tz(to_tz))
    return f"{time_str}（{from_tz}）= {target.strftime('%Y-%m-%d %H:%M')}（{to_tz}，{WEEKDAY_ZH[target.weekday()]}）"


if __name__ == "__main__":
    mcp.run()
