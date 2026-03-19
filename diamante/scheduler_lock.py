import logging
from django.db import connection

logger = logging.getLogger(__name__)

def acquire_scheduler_lock(lock_id=777001):
    """
    Tenta adquirir um lock consultivo no Postgres.
    Locks de sessão são liberados automaticamente quando a conexão fecha.
    """
    try:
        cursor = connection.cursor()
        # pg_try_advisory_lock retorna True se pegou o lock, False se já estiver ocupado
        cursor.execute("SELECT pg_try_advisory_lock(%s);", [lock_id])
        row = cursor.fetchone()
        
        if row and row[0]:
            logger.info(f"Advisory lock {lock_id} adquirido com sucesso.")
            return True
        
        # Se chegou aqui, outro processo (ou uma sessão zumbi) está segurando o lock
        logger.warning(f"Não foi possível adquirir o lock {lock_id}. Outra instância está ativa.")
        return False

    except Exception as e:
        logger.error(f"Erro ao interagir com o Postgres para advisory lock: {e}")
        # Em caso de erro de DB, assumimos que não temos o lock para evitar duplicidade
        return False