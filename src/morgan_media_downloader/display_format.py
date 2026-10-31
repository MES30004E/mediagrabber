"""Shared, presentation-only byte and duration formatting."""


def human_bytes(value: float | int) -> str:
    amount = float(value or 0)
    for suffix in ("B", "KB", "MB", "GB", "TB"):
        if abs(amount) < 1024 or suffix == "TB":
            return f"{amount:.1f} {suffix}"
        amount /= 1024
    return "0 B"


def human_duration(value: float | int | None) -> str:
    if value is None:
        return "—"
    seconds = int(value)
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02d}"
