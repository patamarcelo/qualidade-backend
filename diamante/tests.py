from django.test import TestCase

from diamante.models import Defensivo

# Create your tests here.
import json
import os

def read_qs():
    qs = Defensivo.objects.all()
    for i in qs:
        print(i)

def read_json_file():
    json_path = os.path.join(os.path.dirname(__file__), './teste-files/insumos.json')
    f = open(json_path)
    data = json.load(f)

    list_prods = []
    for i in data:
        produto = i['Nome']
        unidade_medida = "un_ha"
        formulacao = 'unidade'
        id_farmbox = i['Código']
        tipo = "operacao"
        obj_to_add = {
            'produto': produto,
            'unidade': unidade_medida,
            'formulacao': formulacao,
            'id_farmbox': id_farmbox,
            'tipo': tipo,
        }
        try:
            novo_defensivo = Defensivo(
                produto=produto,
                unidade_medida=unidade_medida,
                formulacao=formulacao,
                tipo=tipo,
                id_farmbox=id_farmbox,
            )
            novo_defensivo.save()
            print('Defensivo Salvo', obj_to_add)
        except Exception as e:
            print(f'Erro ao Salvar o defensivo: {e}', obj_to_add)
        list_prods.append(obj_to_add)
    f.close()
    
    return list_prods
        