import atexit
import logging
import threading

import psycopg2
from django.conf import settings


logger = logging.getLogger(__name__)

_lock_guard = threading.Lock()
_scheduler_lock_connection = None
_scheduler_lock_id = None


def acquire_scheduler_lock(lock_id=777001):
    """
    Tenta adquirir um advisory lock PostgreSQL usando uma conexão exclusiva.

    O lock permanece ativo enquanto esta conexão continuar aberta.
    A conexão não é gerenciada pelo Django e não deve ser usada pelos jobs.
    """
    global _scheduler_lock_connection
    global _scheduler_lock_id

    with _lock_guard:
        if (
            _scheduler_lock_connection is not None
            and _scheduler_lock_connection.closed == 0
            and _scheduler_lock_id == lock_id
        ):
            logger.info(
                "[Scheduler] Advisory lock %s já está ativo neste processo.",
                lock_id,
            )
            return True

        db_config = settings.DATABASES["default"]
        db_options = db_config.get("OPTIONS", {})

        connection_params = {
            "dbname": db_config["NAME"],
            "user": db_config["USER"],
            "password": db_config["PASSWORD"],
            "host": db_config["HOST"],
            "port": db_config["PORT"],
            "connect_timeout": db_options.get("connect_timeout", 10),
        }

        sslmode = db_options.get("sslmode")
        if sslmode:
            connection_params["sslmode"] = sslmode

        lock_connection = None

        try:
            lock_connection = psycopg2.connect(**connection_params)
            lock_connection.autocommit = True

            with lock_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_try_advisory_lock(%s);",
                    [lock_id],
                )
                row = cursor.fetchone()

            acquired = bool(row and row[0])

            if not acquired:
                lock_connection.close()

                logger.warning(
                    "[Scheduler] Advisory lock %s já está ocupado. "
                    "Outra instância do scheduler está ativa.",
                    lock_id,
                )
                return False

            _scheduler_lock_connection = lock_connection
            _scheduler_lock_id = lock_id

            logger.info(
                "[Scheduler] Advisory lock %s adquirido em conexão exclusiva.",
                lock_id,
            )
            return True

        except Exception:
            if lock_connection is not None:
                try:
                    lock_connection.close()
                except Exception:
                    pass

            logger.exception(
                "[Scheduler] Erro ao adquirir advisory lock %s.",
                lock_id,
            )
            return False


def scheduler_lock_is_alive():
    """
    Verifica se a conexão exclusiva que mantém o lock continua ativa.
    """
    with _lock_guard:
        lock_connection = _scheduler_lock_connection

        if lock_connection is None or lock_connection.closed != 0:
            return False

        try:
            with lock_connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()

            return row == (1,)

        except Exception:
            logger.exception(
                "[Scheduler] A conexão do advisory lock foi perdida."
            )
            return False


def release_scheduler_lock():
    """
    Libera explicitamente o advisory lock e fecha sua conexão exclusiva.

    O PostgreSQL também libera o lock automaticamente caso o processo morra
    ou a conexão seja encerrada.
    """
    global _scheduler_lock_connection
    global _scheduler_lock_id

    with _lock_guard:
        lock_connection = _scheduler_lock_connection
        lock_id = _scheduler_lock_id

        _scheduler_lock_connection = None
        _scheduler_lock_id = None

        if lock_connection is None:
            return

        try:
            if lock_connection.closed == 0 and lock_id is not None:
                with lock_connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(%s);",
                        [lock_id],
                    )
                    row = cursor.fetchone()

                released = bool(row and row[0])

                if released:
                    logger.info(
                        "[Scheduler] Advisory lock %s liberado.",
                        lock_id,
                    )
                else:
                    logger.warning(
                        "[Scheduler] Advisory lock %s não estava ativo "
                        "nesta conexão.",
                        lock_id,
                    )

        except Exception:
            logger.exception(
                "[Scheduler] Erro ao liberar advisory lock %s.",
                lock_id,
            )

        finally:
            try:
                lock_connection.close()
            except Exception:
                logger.exception(
                    "[Scheduler] Erro ao fechar a conexão exclusiva do lock."
                )


atexit.register(release_scheduler_lock)
