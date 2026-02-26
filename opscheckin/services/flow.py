from datetime import time

# (step, horario, texto)
SLOTS = [
    ("AGENDA",  time(6, 10), "Bom dia! Qual a sua agenda hoje? (pode mandar em tópicos)"),
    ("STATUS_1", time(8, 0),  "Check-in 1/5: como está agora? Algum bloqueio?"),
    ("STATUS_2", time(10, 0), "Check-in 2/5: como está agora? Algum bloqueio?"),
    ("STATUS_3", time(13, 0), "Check-in 3/5: como está agora? Algum bloqueio?"),
    ("STATUS_4", time(15, 30), "Check-in 4/5: como está agora? Algum bloqueio?"),
    ("STATUS_5", time(18, 0), "Fechando o dia — algo pendente/importante?"),
]


def slot_text(step: str) -> str:
    slot_map = {s: msg for s, _t, msg in SLOTS}
    return slot_map.get(step, "")