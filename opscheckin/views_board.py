from django.shortcuts import render
from django.utils import timezone
from .models import DailyCheckin


def board_view(request):
    today = timezone.localdate()

    checkins = (
        DailyCheckin.objects
        .select_related("manager")
        .prefetch_related("questions")
        .filter(date=today)
    )

    return render(request, "opscheckin/board.html", {"checkins": checkins})