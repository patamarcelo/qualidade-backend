# your_app/scheduler_utils.py
import time
import logging
from django.db import close_old_connections
from django.db.utils import OperationalError

logger = logging.getLogger(__name__)

def safe_job(fn, retries=3, backoff=1.2):
    def wrapped(*args, **kwargs):
        for attempt in range(1, retries + 1):
            try:
                close_old_connections()  # mata conexões mortas antes de usar
                return fn(*args, **kwargs)
            except OperationalError as e:
                logger.exception(f"[scheduler] OperationalError attempt={attempt}/{retries}: {e}")
                close_old_connections()
                if attempt == retries:
                    raise
                time.sleep(backoff ** attempt)
    return wrapped