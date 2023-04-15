from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import Talhao, Plantio, Projeto, Defensivo
from rest_framework.fields import CurrentUserDefault

from usuario.models import CustomUsuario as User


class TalhaoSerializer(serializers.ModelSerializer):
    plantios = serializers.StringRelatedField(many=True)

    class Meta:
        model = Talhao
        fields = "__all__"


class PlantioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plantio
        fields = "__all__"


class DefensivoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Defensivo
        fields = "__all__"


# class ProjetoSeralizer(serializers.ModelSerializer):
#     fazenda_nome = serializers.CharField(source="fazenda.nome")

#     class Meta:
#         model = Projeto
#         fields = [
#             "nome",
#             "id",
#             "fazenda_nome",
#         ]
