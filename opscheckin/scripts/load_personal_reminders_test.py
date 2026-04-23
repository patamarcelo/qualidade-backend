from datetime import time
from opscheckin.models import (
    Manager,
    NotificationType,
    ManagerNotificationSubscription,
    ManagerPersonalReminder,
)

MANAGER_ID = 1

manager = Manager.objects.get(id=MANAGER_ID)

nt, _ = NotificationType.objects.get_or_create(
    code="personal_reminder",
    defaults={
        "name": "Avisos pessoais",
        "description": "Recebe lembretes pessoais recorrentes do manager",
        "is_active": True,
    },
)

ManagerNotificationSubscription.objects.update_or_create(
    manager=manager,
    notification_type=nt,
    defaults={"is_active": True},
)

# apaga os reminders atuais desse manager para recriar limpo
ManagerPersonalReminder.objects.filter(manager=manager).delete()

weekday_map = {
    "toda segunda": 0,
    "toda terça": 1,
    "toda terca": 1,
    "toda quarta": 2,
    "toda quinta": 3,
    "toda sexta": 4,
    "todo sábado": 5,
    "todo sabado": 5,
    "todo domingo": 6,
}

rows = [
    {
        "code": "lancamento_os_pilotos",
        "title": "lançamento OS pilotos",
        "schedule_type": "weekly",
        "weekday": 1,
        "day_of_month": None,
        "time_of_day": time(7, 30),
        "message_text": "Olá! Hoje é dia de lançar todas as OS dos pilotos da semana passada. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "fechamento_diaristas",
        "title": "fechamento diaristas",
        "schedule_type": "weekly",
        "weekday": 0,
        "day_of_month": None,
        "time_of_day": time(7, 30),
        "message_text": "Olá! Segunda é dia de fechamento do controle dos diaristas. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "preenchimento_cartao_ponto",
        "title": "preenchimento cartão de ponto",
        "schedule_type": "daily",
        "weekday": None,
        "day_of_month": None,
        "time_of_day": time(16, 0),
        "message_text": "Está na hora de iniciar o preenchimento dos cartões de ponto. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "produtos_aplicacao_jv",
        "title": "Produtos aplicação JV",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 20,
        "time_of_day": time(7, 30),
        "message_text": "Olá! Hoje é dia de confirmar com o João Victor quais produtos serão utilizados nas aplicações do próximo mês. Confirme aqui assim que ele responder.",
    },
    {
        "code": "receituario_agronomico_25",
        "title": "Receituário Agronômico",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 25,
        "time_of_day": time(7, 30),
        "message_text": "Olá! Hoje é dia de solicitar ao Cido a entrega do receituário agronômico do próximo mês. Confirme aqui assim que ele entregar.",
    },
    {
        "code": "receituario_agronomico_05",
        "title": "Receituário Agronômico",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 5,
        "time_of_day": time(8, 0),
        "message_text": "Olá! Confirme se o Cido entregou o receituário agronômico desse mês e salve-o, escaneado na pasta na rede. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "nfs_produtos",
        "title": "NFs Produtos",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 5,
        "time_of_day": time(8, 0),
        "message_text": "Olá! Solicite ao responsável da UBS, o envio das notas fiscais dos produtos que serão utilizados nas aplicações, conforme receituário agronômico. Salve na pasta na rede. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "fechamento_produtividade_ajudantes",
        "title": "Fechamento produtividade ajudantes",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 20,
        "time_of_day": time(8, 0),
        "message_text": "Olá! Hoje é dia de enviar ao DP o fechamento da produtividade do ajudante de calda dos aviões, para inserir na folha de pagamento. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "relatorio_mapa",
        "title": "Relatório MAPA",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 20,
        "time_of_day": time(10, 0),
        "message_text": "Olá! Hoje é dia de enviar ao Jurídico o relatório mensal de atividades da aviação no MAPA. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "confirmacao_protocolo",
        "title": "Confirmação de protocolo",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 5,
        "time_of_day": time(8, 0),
        "message_text": "Olá! Confirme com o departamento jurídico o protocolo do relatório do mês anterior.",
    },
    {
        "code": "malha_fiscal_aviacao",
        "title": "Malha fiscal da Aviação",
        "schedule_type": "weekly",
        "weekday": 3,
        "day_of_month": None,
        "time_of_day": time(13, 0),
        "message_text": "Olá! Hoje é dia de revisar a malha fiscal das notas da aviação. Utilize seu período da tarde para focar nessa demanda. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "nf_dos_pilotos",
        "title": "NF dos Pilotos",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 15,
        "time_of_day": time(8, 0),
        "message_text": "Olá! Hoje é dia de cobrar a NF dos pilotos da PR paga no começo do mês. Lance e acompanhe a baixa da compensação. Confirme aqui assim que concluir a atividade.",
    },
    {
        "code": "limpeza_escritorio",
        "title": "Limpeza escritório",
        "schedule_type": "daily",
        "weekday": None,
        "day_of_month": None,
        "time_of_day": time(7, 30),
        "message_text": "Olá! Lembre-se de manter limpo e organizado o escritório, banheiros e cantina do Hangar. A limpeza e organização reflete nosso trabalho! Confirme aqui assim que concluir essa atividade.",
    },
    {
        "code": "limpeza_teia_aranha",
        "title": "Limpeza teia de aranha",
        "schedule_type": "weekly",
        "weekday": 3,
        "day_of_month": None,
        "time_of_day": time(7, 30),
        "message_text": "Olá! Lembre-se hoje de incluir nas demandas da diarista, a remoção das teias de aranha do escritório, almoxarifado, banheiros, cantina. Confirme aqui assim que concluir essa atividade.",
    },
    {
        "code": "limpeza_hangar_patio",
        "title": "Limpeza Hangar/Pátio",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 20,
        "time_of_day": time(7, 30),
        "message_text": "Olá! Hoje é dia de acompanhar a limpeza geral dos hangares e pátios, remoção de mato, limpeza de paredes, canaletas, catação de lixos. Confirmar aqui assim que concluir a atividade.",
    },
    {
        "code": "revisao_extintores",
        "title": "Revisão Extintores",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 18,
        "time_of_day": time(8, 0),
        "message_text": "Olá! Hoje é dia de revisar a validade dos extintores gerais do Hangar. Havendo necessidade de recarga, enviar a UBS aos cuidados do jurídico, e acompanhar o retorno. Confirmar aqui assim que concluir a atividade.",
    },
    {
        "code": "revisao_infraestrutura",
        "title": "Revisão Infraestrutura",
        "schedule_type": "monthly",
        "weekday": None,
        "day_of_month": 18,
        "time_of_day": time(8, 0),
        "message_text": "Olá! Hoje é dia de revisar o funcionamento de todas as lâmpadas, torneiras, chuveiros, sanitários, maçanetas. Havendo necessidade de conserto, priorizar a correção e acompanhar a conclusão. Confirmar aqui assim que concluir a atividade.",
    },
]

created_ids = []

for row in rows:
    obj = ManagerPersonalReminder.objects.create(
        manager=manager,
        code=row["code"],
        title=row["title"],
        description="Carga inicial via shell a partir da planilha Kellyta(Hangar)",
        is_active=True,
        schedule_type=row["schedule_type"],
        time_of_day=row["time_of_day"],
        weekday=row["weekday"],
        day_of_month=row["day_of_month"],
        delivery_mode=ManagerPersonalReminder.DELIVERY_TEMPLATE,
        response_mode=ManagerPersonalReminder.RESPONSE_BUTTON,
        message_text=row["message_text"],
        allowed_window_minutes=30,
    )
    created_ids.append(obj.id)

print("manager:", manager.id, manager.name)
print("subscription_ok:", nt.code)
print("created:", len(created_ids))
print("ids:", created_ids)