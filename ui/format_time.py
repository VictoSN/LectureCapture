from datetime import datetime, timedelta

def FormatTime(date: datetime) -> str:
    if not date:
        return ""
    now = datetime.now()

    if date.date() == now.date():
        return date.strftime("Today, %H:%M")
    if date.date() == (now.date() - timedelta(days=1)):
        return date.strftime("Yesterday, %H:%M")
    return date.strftime("%A %#d %B, %H:%M")

def FormatDetailedTime(date: datetime) -> str:
    if not date:
        return ""
    return date.strftime("%A %#d %B, %H:%M:%S")

def FormatClock(seconds: float, pad_minutes: bool = False) -> str:
    """Elapsed time as a clock: H:MM:SS once there's a whole hour, else M:SS
    (or MM:SS with pad_minutes for the fixed-width footer clock). Truncates
    fractional seconds."""
    s = max(0, int(seconds))
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}" if pad_minutes else f"{m}:{sec:02d}"
