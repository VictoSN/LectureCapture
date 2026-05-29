from datetime import datetime, timedelta

def FormatTime(date: datetime):
    if date:
        now = datetime.now()

        if date.date() == now.date():
            formatted = date.strftime("Today, %H:%M")
        elif date.date() == (now.date() - timedelta(days=1)):
            formatted = date.strftime("Yesterday, %H:%M")
        else:
            formatted = date.strftime("%A %#d %B, %H:%M")

        return formatted or ""

def FormatDetailedTime(date: datetime):
    if date:
        return date.strftime("%A %#d %B, %H:%M:%S") or ""