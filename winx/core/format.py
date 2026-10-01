"""Small formatting helpers used across the UI."""

from __future__ import annotations

import datetime as _dt

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_size(num: float, precision: int = 1) -> str:
    if num is None or num < 0:
        return "—"
    size = float(num)
    unit = 0
    while size >= 1024 and unit < len(_UNITS) - 1:
        size /= 1024.0
        unit += 1
    if unit == 0:
        return f"{int(size)} {_UNITS[unit]}"
    return f"{size:.{precision}f} {_UNITS[unit]}"


def human_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def human_uptime(boot_ts: float) -> str:
    return human_duration(_dt.datetime.now().timestamp() - boot_ts)


def percent(value: float, total: float) -> int:
    if not total:
        return 0
    return int(round(100.0 * float(value) / float(total)))


def timestamp_str(ts: float | None = None) -> str:
    return _dt.datetime.fromtimestamp(ts or _dt.datetime.now().timestamp()).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural_form or singular + 's')}"


def human_age(seconds: float) -> str:
    """``90`` -> ``'1 minute ago'``; used by the pages' "Updated …" line."""
    seconds = int(max(0, seconds))
    if seconds < 10:
        return "just now"
    if seconds < 90:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    return f"{hours} hour{'s' if hours != 1 else ''} ago"
