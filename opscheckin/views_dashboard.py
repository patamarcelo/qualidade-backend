# from .models import DailyCheckin
# import timezone

# # opscheckin/views_dashboard.py
# def checkins_today_view(request):
#     today = timezone.localdate()
#     checkins = (
#         DailyCheckin.objects
#         .filter(date=today)
#         .prefetch_related("questions", "manager")
#     )
#     return render(request, "opscheckin/checkins_today.html", {
#         "checkins": checkins
#     })