#!/usr/local/bin/python3

from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi
import certifi

import os


from bson.json_util import dumps
import json

from qualidade_project.settings import MONGO_PASS_DEFENSIVOS

from colorama import init as colorama_init
from colorama import Fore
from colorama import Style


def conect_mongo_db():
    cluster = f"mongodb+srv://patamarceloNode:{MONGO_PASS_DEFENSIVOS}@cluster0.xsfalnv.mongodb.net/?retryWrites=true&w=majority"
    client = MongoClient(cluster, tlsCAFile=certifi.where())
    db = client["farmbox"]
    aplicacoes = db["aplicacoes"]
    aplicacoes_pluvi = db["pluviometria"]

    try:
        client.admin.command("ping")
        print("Pinged your deployment. You successfully connected to MongoDB!")
    except Exception as e:
        print("problema para consultar o DB: ", e)

    return [aplicacoes, aplicacoes_pluvi]


def read_data_from_db(aplicacoes):
    cursor = aplicacoes.find({"date": {"$gte": "2023-05-01"}, "status": "sought"})

    list_cursor = list(cursor)
    json_data = dumps(list_cursor)
    data = json.loads(json_data)

    print(type(data))
    count = 1
    for i in data:
        print("Número: ", count)
        count += 1
        id = i["id"]
        app = i["code"]
        date = i["date"]
        final_date = i["end_date"]
        status = i["status"]
        plantations = i["plantations"]
        plantation = [x["plantation"]["farm_name"] for x in plantations][0]
        print(plantation)
        print(
            f"ID: {id} - App: {app} - Data: {date} - Data Final: {final_date} - Status: {status}"
        )
        print("\n")
    return json_data


def read_json_file(file):
    with open(f"{file}.json") as user_file:
        file_contents = user_file.read()
        parsed_json = json.loads(file_contents)
        new_list = parsed_json
    return new_list


def update_data_from_farm(aplicacoes, data, id):
    result = aplicacoes.update_one({"id": id}, {"$set": data}, upsert=True)
    print(result)
    return result


def update_mongo_db(db_name):
    file_read = "dataset-2023-07-06 14:54"
    data_from_json = read_json_file(file_read)
    for obj in data_from_json:
        id_json = obj["id"]
        print(id_json)
        update_data_from_farm(db_name, obj, id_json)
        
        

def delete_data_from_farm(aplicacoes, ids):
    result = aplicacoes.delete_many(
        {
            "id": {"$in": ids},
        }
    )
    print(result)
    return result

def update_mongo_db_many(db_name, data_from_json):
    # /Aplicacoes
    print(f"{Fore.GREEN}Start Update Aplications{Style.RESET_ALL}")
    list_to_update = []
    for obj in data_from_json[0]:
        id_json = obj["id"]
        # print(id_json)
        list_to_update.append(UpdateOne({"id": id_json}, {"$set": obj}, upsert=True))
        # update_data_from_farm(db_name[0], obj, id_json)
    result = db_name[0].bulk_write(list_to_update)
    print(f"Encontrados {result.matched_count} documentos e atualizados {result.modified_count} documentos.")

    delete_data_from_farm(db_name[0], data_from_json[1])


def generate_file_run(data_from_farm):
    # get_applications_cal()
    db_name = conect_mongo_db()
    # read_data_from_db(db_name)
    update_mongo_db_many(db_name, data_from_farm)
    # update_mongo_db(db_name)


# This is added so that many files can reuse the function get_database()
if __name__ == "__main__":
    pass
    # db_name = conect_mongo_db()

    # read_data_from_db(db_name)

    # update_mongo_db(db_name)
