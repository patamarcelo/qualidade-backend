from django.shortcuts import render
from usuario.models import CustomUsuario as User

from rest_framework import viewsets, status
from .serializers import UserSerializer

from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import TokenAuthentication

from rest_framework.response import Response


import json
from django.http import JsonResponse
from django.core.serializers import serialize

from django.db.models import Q


from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from decimal import *
import csv


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    authentication_classes = (TokenAuthentication,)
    permission_classes = (AllowAny,)