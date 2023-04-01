from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import Talhao
from rest_framework.fields import CurrentUserDefault

from usuario.models import CustomUsuario as User


class TalhaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Talhao
        fields = "__all__"
