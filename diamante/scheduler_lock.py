# scheduler_lock.py
from django.db import connection

def acquire_scheduler_lock(lock_id=777001):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s);", [lock_id])
        return cursor.fetchone()[0]