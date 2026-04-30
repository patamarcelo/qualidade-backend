# opscheckin/urls.py
from django.urls import path
from .views import whatsapp_webhook
from .views_board import board_view, board_updates, board_thread_messages

urlpatterns = [
    path("whatsapp/webhook/", whatsapp_webhook, name="whatsapp_webhook"),
    path("board/", board_view, name="opscheckin_board"),
    path("board/updates/", board_updates, name="opscheckin_board_updates"),
    path("board/thread/messages/", board_thread_messages, name="board_thread_messages"),
]
