from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import Talhao, Plantio, Projeto
from rest_framework.fields import CurrentUserDefault

from usuario.models import CustomUsuario as User


class TalhaoSerializer(serializers.ModelSerializer):
    plantios = serializers.StringRelatedField(many=True)

    class Meta:
        model = Talhao
        fields = "__all__"


class PlantioSerializer(serializers.ModelSerializer):
    # talhao_name = serializers.CharField(source="talhao.id_talhao")
    # variedade_name = serializers.CharField(source="variedade.variedade")

    class Meta:
        model = Plantio
        # fields = [
        #     "safra",
        #     "ciclo",
        #     "talhao",
        #     # "talhao_name",
        #     "variedade",
        #     # "variedade_name",
        #     "finalizado_plantio",
        #     "finalizado_colheita",
        #     "area_colheita",
        #     "area_parcial",
        # ]
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
