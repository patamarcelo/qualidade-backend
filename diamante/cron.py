from datetime import datetime
from .utils import get_date, get_miliseconds
import time
from .read_farm_data import get_applications, get_applications_pluvi
from qualidade_project.mongo_api import generate_file_run

def get_hour_test():
    current_time = datetime.now()
    print('cron job working: ', current_time)
    

def update_farmbox_mongodb_app():
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
        