from django.apps import AppConfig


class DiamanteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'diamante'

    def ready(self):
        from diamante.scheduler import start
        import diamante.signals
        start()

# your_app/apps.py
# class YourAppConfig(AppConfig):
#     name = 'diamante'

#     def ready(self):
#         from diamante.scheduler import start
#         start()
