from rest_framework import serializers
from rest_framework.authtoken.models import Token
from .models import (
    Talhao,
    Plantio,
    Projeto,
    Defensivo,
    Aplicacao,
    Colheita,
    Visitas,
    RegistroVisitas,
    StProtheusIntegration,
    ColheitaPlantioExtratoArea
)
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
fields = "__all__"
#         fields = [
#             "nome",
#             "id",
#             "fazenda_nome",
#         ]


class ColheitaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Colheita
        fields = "__all__"
        # fields = [
        #     "peso_tara",
        #     "peso_bruto",
        #     "umidade",
        #     "desconto_umidade",
        #     "impureza",
        #     "desconto_impureza",
        #     "bandinha",
        #     "desconto_bandinha",
        #     "peso_liquido",
        #     "peso_scs_liquido",
        #     "peso_scs_limpo_e_seco",
        #     "deposito",
        # ]


class ProjetosSerializer(serializers.ModelSerializer):
    def to_representation(self, value):
        return value.nome

    class Meta:
        model = Projeto
        fields = "__all__"


class VisitasSerializer(serializers.ModelSerializer):
    fazenda_title = serializers.CharField(source="fazenda.nome", read_only=True)
    projetos = ProjetosSerializer(source="projeto", read_only=True, many=True)

    class Meta:
        model = Visitas
        fields = "__all__"


class RegistroVisitasSerializer(serializers.ModelSerializer):
    visita_title = serializers.CharField(source="visita.fazenda.nome", read_only=True)
    visita_data = serializers.CharField(source="visita.data", read_only=True)

    class Meta:
        model = RegistroVisitas
        fields = [
            "visita",
            # "image",
            "image_url",
            "image_title",
            "obs",
            "visita_title",
            "visita_data",
        ]


class StProtheusIntegrationSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = StProtheusIntegration
        fields = "__all__"

class ColheitaPlantioExtratoAreaSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = ColheitaPlantioExtratoArea
        fields = "__all__"