import requests

from colorama import init as colorama_init
from colorama import Fore
from colorama import Style

from qualidade_project.settings import FARMBOX_ID

harvests = (
    [
        {
            "id": 2605,
            "name": "2021/2022",
            "start_date": "2021-05-01",
            "end_date": "2022-04-30",
        },
        {
            "id": 2608,
            "name": "2022/2023",
            "start_date": "2022-05-01",
            "end_date": "2023-06-20",
        },
        {
            "id": 2607,
            "name": "2023/2024",
            "start_date": "2023-04-01",
            "end_date": "2024-04-30",
        },{
            "id": 3840,
            "name": "2024/2025",
            "start_date": "2024-04-01",
            "end_date": "2025-04-30",
            "rain_start_date": "2024-04-01",
            "rain_end_date": "2025-04-30"
        }
    ],
)

headers = {
    "Content-Type": "application/json",
    "Authorization": FARMBOX_ID,
}

safra_22_23 = list(harvests)[0][1]["id"]
safra_23_24 = list(harvests)[0][2]["id"]

dict_area_app = []
last_page_app = 0
deleted_app_array = []


dict_area_app_pluvi = []
last_page_app_pluvi = 0
deleted_app_array_pluvi = []

def get_applications(page=None, updated_last=None, safra=safra_23_24, url=None):
    global dict_area_app, last_page_app, deleted_app_array

    if url:
        api_url = url
    else:
        api_url = f"https://farmbox.cc/api/v1/applications"
        if updated_last:
            api_url = (
                f"https://farmbox.cc/api/v1/applications?updated_since={updated_last}"
            )

    print(api_url)
    try:
        response = requests.get(api_url, headers=headers)
        data = response.json()
        deleted_app_array = data["deleted_since"]
        for i in data["applications"]:
            dict_area_app.append(i)
        next_page = None

        if data["next_page_url"] != None:
            next_page = data["next_page_url"]
            print("\n")
            print(f"Proximo Pagina: {next_page}")
            print("\n\n")
            url = f"https://farmbox.cc{next_page}"
            if next_page:
                try:
                    get_applications(page=next_page, updated_last=updated_last, url=url)
                except Exception as e:
                    print("erro em pegar os dados da página selecionada", e)
        else:
            if last_page_app == 0:
                print(
                    f"{Fore.YELLOW}Sem atualizações no período selecionado{Style.RESET_ALL}"
                )
            else:
                print(
                    f"{Fore.GREEN}Todas as páginas já foram retornadas{Style.RESET_ALL}"
                )
    except Exception as e:
        print("error na pagina, finalizando o código", e)

    return [dict_area_app, deleted_app_array]

def get_applications_pluvi(page=None, updated_last=None, safra=safra_23_24, url=None):
    global dict_area_app_pluvi, last_page_app_pluvi, deleted_app_array_pluvi

    if url:
        api_url = url
    else:
        api_url = f"https://farmbox.cc/api/v1/pluviometer_monitorings"
        if updated_last:
            api_url = f"https://farmbox.cc/api/v1/pluviometer_monitorings?updated_since={updated_last}"

    print(api_url)
    try:
        response = requests.get(api_url, headers=headers)
        data = response.json()
        deleted_app_array_pluvi = data["deleted_since"]
        for i in data["pluviometer_monitorings"]:
            dict_area_app_pluvi.append(i)
        next_page = None

        if data["next_page_url"] != None:
            next_page = data["next_page_url"]
            print("\n")
            print(f"Proximo Pagina: {next_page}")
            print("\n\n")
            url = f"https://farmbox.cc{next_page}"
            if next_page:
                try:
                    get_applications_pluvi(
                        page=next_page, updated_last=updated_last, url=url
                    )
                except Exception as e:
                    print("erro em pegar os dados da página selecionada", e)
        else:
            if last_page_app_pluvi == 0:
                print(
                    f"{Fore.YELLOW}Sem atualizações no período selecionado{Style.RESET_ALL}"
                )
            else:
                print(
                    f"{Fore.GREEN}Todas as páginas já foram retornadas{Style.RESET_ALL}"
                )
    except Exception as e:
        print("error na pagina, finalizando o código", e)

    for i in dict_area_app_pluvi:
        print(i)

    return [dict_area_app_pluvi, deleted_app_array_pluvi]