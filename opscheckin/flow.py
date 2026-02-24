from datetime import time

SLOTS = [
    ("AGENDA",   time(6, 0),  "Bom dia! Qual a sua agenda hoje?"),
    ("STARTED",  time(8, 0),  "Você já iniciou a 1ª atividade? Responda: 1-Sim | 2-Não | 3-Mudou a agenda"),
    ("NOW",      time(10, 0), "O que você está fazendo agora? (responda em 1 frase)"),
    ("BLOCKERS", time(12, 0), "Tem algum impedimento agora? Responda: 1-Não | 2-Sim"),
    ("PROGRESS", time(14, 0), "Progresso do dia: 1-0/25 | 2-25/50 | 3-50/75 | 4-75/100"),
    ("NEXT",     time(16, 0), "Qual a próxima atividade? (1 frase)"),
    ("WRAPUP",   time(18, 0), "Resumo do dia (3 linhas): ✅ Concluído | ⏳ Pendente | ⚠️ Problemas"),
]