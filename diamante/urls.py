from django.contrib import admin
from django.urls import path
from rest_framework import routers
from django.conf.urls import include

from .views_api import TalaoViewSet

router = routers.DefaultRouter()
router.register("", TalaoViewSet)


urlpatterns = [
    path("", include(router.urls)),
]
