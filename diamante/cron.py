from datetime import datetime

def get_hour_test():
    current_time = datetime.now()
    print('cron job working: ', current_time)