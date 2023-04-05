from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import Talhao, Plantio
from rest_framework.fields import CurrentUserDefault

from usuario.models import CustomUsuario as User


class TalhaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Talhao
        fields = "__all__"


class PlantioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plantio
        fields = "__all__"
