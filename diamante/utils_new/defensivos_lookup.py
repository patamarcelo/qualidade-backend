from typing import Optional
from diamante.models import Defensivo  # ajuste para o nome do seu app


def resolve_defensivo_nome(input_id) -> Optional[str]:
    """
    Recebe input_id da Farmbox e retorna nome do produto
    """
    try:
        input_id = int(input_id)
    except (TypeError, ValueError):
        return None

    defensivo = (
        Defensivo.objects
        .filter(id_farmbox=input_id)
        .only("produto")
        .first()
    )

    if defensivo:
        return defensivo.produto

    return None