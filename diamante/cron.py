from datetime import datetime
from .utils import get_date, get_miliseconds
import time
from .read_farm_data import get_applications
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
    generate_file_run(data_applications)
    print("\nAplicações Atualizadas.")
        