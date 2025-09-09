from datetime import datetime
from .utils import get_date, get_miliseconds
import time
from .read_farm_data import get_applications, get_applications_pluvi
from qualidade_project.mongo_api import generate_file_run
from django.db import connection

from diamante.gmail.gmail_api import send_mail
from django.conf import settings
from django.template.loader import render_to_string


def get_hour_test():
    current_time = datetime.now()
    print('cron job working: ', current_time)
    

def update_farmbox_mongodb_app():
    connection.ensure_connection()
    number_of_days_before = 1
    from_date = get_date(number_of_days_before)
    last_up = get_miliseconds(from_date)
    print(last_up)
    
    
    data_applications = get_applications(updated_last=last_up)
    # print(data_applications)
    for _ in range(2):
        print(time.ctime())
        # Prints the current time with a five second difference
        time.sleep(1)
    type_app = 'Aplicacoes'
    generate_file_run(type_app, data_applications)
    print("\nAplicações Atualizadas.")
    
    number_of_days_before_pluvi = 4
    from_date_pluvi = get_date(number_of_days_before_pluvi)
    last_up_pluvi = get_miliseconds(from_date_pluvi)
    data_applications_pluvi = get_applications_pluvi(updated_last=last_up_pluvi)
    
    type_pluvi = 'Pluvi'
    generate_file_run(type_pluvi, data_applications_pluvi)
    print("\nPluviometrias Atualizadas.")
    
def enviar_email_diario():
    from diamante.models import EmailAberturaST
    """
    Função chamada pelo cron para enviar um e-mail diário às 6:30.
    """
    try:
        html_content = render_to_string("email/email_reuniao.html")
        emails_to_send = EmailAberturaST.objects.filter(atividade__tipo='Reuniao Diaria 0630', ativo=True).values_list('email', flat=True)
        send_mail(
            subject="Reunião Diária - 06:30 até 07:30",
            message=html_content,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=emails_to_send,
            fail_silently=False,
        )
        print('[feito] - Email enviado com sucesso')
    except Exception as e:
        print('[Problema] - Falha em enviar o email: ', e)