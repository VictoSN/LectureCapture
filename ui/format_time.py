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
