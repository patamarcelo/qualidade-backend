from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import Talhao, Plantio, Projeto, Defensivo, Aplicacao
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


class AplicacaoSerializer(serializers.ModelSerializer):
    estagio = serializers.ReadOnlyField(source="operacao.estagio")

    class Meta:
        model = Aplicacao
        fields = [
            "criados",
            "modificado",
            "dose",
            "obs",
            "estagio",
        ]


# class ProjetoSeralizer(serializers.ModelSerializer):
#     fazenda_nome = serializers.CharField(source="fazenda.nome")

#     class Meta:
#         model = Projeto
#         fields = [
#             "nome",
#             "id",
#             "fazenda_nome",
#         ]
