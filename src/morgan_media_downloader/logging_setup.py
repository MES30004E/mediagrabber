from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from .paths import logs_dir


def redact_secrets(message: str) -> str:
    message = re.sub(r"(?i)(\b[a-z][a-z0-9+.-]*://[^:/@\s]+:)[^@/\s]+@", r"\1[redacted]@", message)
    message = re.sub(r"(?i)([?&](?:token|key|auth|signature|sig|password|code)=)[^&\s]+", r"\1[redacted]", message)
    message = re.sub(
        r"(?i)\b(authorization|cookie|set-cookie|sapisid|sid|hsid|ssid|access_token|refresh_token|proxy_password)\s*[:=]\s*[^\s,;]+",
        r"\1=[redacted]", message,
    )
    # Signed/CDN URLs commonly use opaque query keys. Removing the complete
    # query is safer than attempting to enumerate every provider's secret name.
    message = re.sub(r"(?i)(https?://[^\s?#]+)\?[^\s]+", r"\1?[query redacted]", message)
    message = re.sub(r"(?i)\b(session[_ -]?id\s*[:=]\s*)[^\s,;]+", r"\1[redacted]", message)
    return message


class SecretFilter(logging.Filter):
    SENSITIVE = ("password", "cookie", "authorization", "access_token", "refresh_token")

    def filter(self, record: logging.LogRecord) -> bool:
        original = record.getMessage()
        cleaned = redact_secrets(original)
        if cleaned != original or any(term in original.lower() for term in self.SENSITIVE):
            record.msg = cleaned
            record.args = ()
        return True


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("morgan_media_downloader")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(
            logs_dir() / "application.log", maxBytes=1_000_000, backupCount=4, encoding="utf-8"
        )
        handler.addFilter(SecretFilter())
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    return logger
