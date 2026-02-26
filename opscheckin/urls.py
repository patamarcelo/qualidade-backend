# opscheckin/urls.py
from django.urls import path
from .views import whatsapp_webhook
from .views_board import board_view

urlpatterns = [
    path("whatsapp/webhook/", whatsapp_webhook, name="whatsapp_webhook"),
    path("board/", board_view, name="opscheckin_board"),
]