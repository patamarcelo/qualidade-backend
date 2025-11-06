import requests

from colorama import init as colorama_init
from colorama import Fore
from colorama import Style

from qualidade_project.settings import FARMBOX_ID

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin, parse_qs, urlencode, urlunparse
import time

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
        }, {
            "id": 4737,
            "name": "2025/2026",
            "start_date": "2025-04-01",
            "end_date": "2026-04-30",
            "rain_start_date": "2025-04-01",
            "rain_end_date": "2026-04-30"
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

def _fetch_with_retries(session, url, max_tries=4, base_sleep=0.75):
    for attempt in range(1, max_tries + 1):
        try:
            resp = session.get(url, headers=headers, timeout=60)
            if resp.status_code in (429, 500, 502, 503, 504):
                # backoff exponencial com jitter leve
                sleep = base_sleep * (2 ** (attempt - 1)) + (0.05 * attempt)
                print(f"[warn] {resp.status_code} em {url} — retry {attempt}/{max_tries} em {sleep:.2f}s")
                time.sleep(sleep)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt == max_tries:
                print(f"[erro] Falha definitiva em {url}: {e}")
                raise
            sleep = base_sleep * (2 ** (attempt - 1)) + (0.05 * attempt)
            print(f"[warn] Exceção em {url} — retry {attempt}/{max_tries} em {sleep:.2f}s ({e})")
            time.sleep(sleep)

def _build_page_urls_from_next(next_page_url, total_pages):
    """
    Usa o next_page_url de referência para montar as demais páginas (2..N),
    preservando TODOS os parâmetros (ex.: updated_since).
    """
    parsed = urlparse(next_page_url)
    q = parse_qs(parsed.query, keep_blank_values=True)
    # define a faixa de páginas com base no query param "page"
    curr = int(q.get("page", ["2"])[0])  # se não tiver, assume 2
    # monta todas as páginas a partir da atual detectada
    urls = []
    for p in range(curr, int(total_pages) + 1):
        q["page"] = [str(p)]
        new_query = urlencode({k: v[0] if isinstance(v, list) and len(v) == 1 else v
                               for k, v in q.items()}, doseq=True)
        url_p = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", new_query, ""))
        # garante domínio absoluto
        if not parsed.scheme:
            url_p = urljoin("https://farmbox.cc", url_p)
        urls.append(url_p)
    return urls

def _fallback_build_urls(base_api, updated_last, total_pages):
    """
    Fallback para quando o next_page_url não vier: constrói ?page=2..N
    preservando updated_since se fornecido.
    """
    base = f"{base_api}"
    if updated_last:
        sep = "&" if "?" in base else "?"
        base = f"{base}{sep}updated_since={updated_last}"
    urls = []
    for p in range(2, int(total_pages) + 1):
        sep = "&" if "?" in base else "?"
        urls.append(f"{base}{sep}page={p}")
    return urls

def get_applications(page=None, updated_last=None, safra=None, url=None, max_workers=8):
    """
    Mantém o mesmo contrato e variáveis globais.
    - Busca a 1ª página para descobrir paginação/deleted_since
    - Dispara as demais páginas em paralelo
    - Retorna [dict_area_app, deleted_app_array]
    """
    global dict_area_app, last_page_app, deleted_app_array
    
    dict_area_app = []
    last_page_app = 0
    deleted_app_array = []

    base_api = "https://farmbox.cc/api/v1/applications"

    # Constrói URL inicial (prioriza 'url' se fornecido, como o seu original)
    if url:
        first_url = url
    else:
        if updated_last:
            first_url = f"{base_api}?updated_since={updated_last}"
        else:
            first_url = base_api

    print(first_url)

    try:
        with requests.Session() as session:
            # 1) Primeira página (sincronamente)
            data = _fetch_with_retries(session, first_url)

            # coleta deleted_since (costuma vir na primeira)
            deleted_app_array = data.get("deleted_since", [])

            # adiciona resultados iniciais
            apps = data.get("applications", [])
            if apps:
                dict_area_app.extend(apps)

            pagination = data.get("pagination", {}) or {}
            total_pages = int(pagination.get("total_pages", 1))
            current_page = int(pagination.get("current_page", 1))

            # já atualiza a "last_page_app" para o total conhecido
            last_page_app = total_pages

            # 2) Monta URLs restantes
            remaining_urls = []
            if total_pages > current_page:
                nxt = data.get("next_page_url")
                if nxt:
                    # next_page_url pode ser relativo: garantir absoluto e usar como "molde"
                    if nxt.startswith("/"):
                        ref = urljoin("https://farmbox.cc", nxt)
                    else:
                        ref = nxt
                    remaining_urls = _build_page_urls_from_next(ref, total_pages)
                else:
                    # fallback: constrói manualmente
                    remaining_urls = _fallback_build_urls(base_api, updated_last, total_pages)

            # 3) Paraleliza o download das demais páginas
            if remaining_urls:
                # limita workers ao número de páginas restantes, no máx max_workers
                workers = min(max_workers, max(1, len(remaining_urls)))
                print(f"Baixando páginas restantes em paralelo ({workers} workers)...")
                futures = []
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    for u in remaining_urls:
                        futures.append(ex.submit(_fetch_with_retries, session, u))
                    for fut in as_completed(futures):
                        try:
                            page_data = fut.result()
                        except Exception as e:
                            print(f"[erro] Falha ao obter uma página: {e}")
                            continue

                        # agrega
                        page_apps = page_data.get("applications", [])
                        if page_apps:
                            dict_area_app.extend(page_apps)

                        # (se o backend repetir deleted_since, ignore; mantemos o da primeira)
                        # logs opcionais
                        pg = (page_data.get("pagination") or {}).get("current_page")
                        if pg:
                            print(f"✔ Página {pg} concluída ({len(page_apps)} itens)")

            # feedback final
            if total_pages <= 1:
                if last_page_app == 0:
                    print("Sem atualizações no período selecionado")
                else:
                    print("Todas as páginas já foram retornadas")
            else:
                print("Todas as páginas já foram retornadas")

    except Exception as e:
        print("error na pagina, finalizando o código", e)

    # mantém o mesmo retorno
    return [dict_area_app, deleted_app_array]

# def get_applications(page=None, updated_last=None, safra=safra_23_24, url=None):
#     global dict_area_app, last_page_app, deleted_app_array

#     if url:
#         api_url = url
#     else:
#         api_url = f"https://farmbox.cc/api/v1/applications"
#         if updated_last:
#             api_url = (
#                 f"https://farmbox.cc/api/v1/applications?updated_since={updated_last}"
#             )

#     print(api_url)
#     try:
#         response = requests.get(api_url, headers=headers)
#         data = response.json()
#         deleted_app_array = data["deleted_since"]
#         for i in data["applications"]:
#             dict_area_app.append(i)
#         next_page = None

#         if data["next_page_url"] != None:
#             next_page = data["next_page_url"]
#             print("\n")
#             print(f"Proximo Pagina: {next_page}")
#             print("\n\n")
#             url = f"https://farmbox.cc{next_page}"
#             if next_page:
#                 try:
#                     get_applications(page=next_page, updated_last=updated_last, url=url)
#                 except Exception as e:
#                     print("erro em pegar os dados da página selecionada", e)
#         else:
#             if last_page_app == 0:
#                 print(
#                     f"{Fore.YELLOW}Sem atualizações no período selecionado{Style.RESET_ALL}"
#                 )
#             else:
#                 print(
#                     f"{Fore.GREEN}Todas as páginas já foram retornadas{Style.RESET_ALL}"
#                 )
#     except Exception as e:
#         print("error na pagina, finalizando o código", e)

#     return [dict_area_app, deleted_app_array]

# def get_applications_pluvi(page=None, updated_last=None, safra=safra_23_24, url=None):
#     global dict_area_app_pluvi, last_page_app_pluvi, deleted_app_array_pluvi
    

#     if url:
#         api_url = url
#     else:
#         api_url = f"https://farmbox.cc/api/v1/pluviometer_monitorings"
#         if updated_last:
#             api_url = f"https://farmbox.cc/api/v1/pluviometer_monitorings?updated_since={updated_last}"

#     print(api_url)
#     try:
#         response = requests.get(api_url, headers=headers)
#         data = response.json()
#         deleted_app_array_pluvi = data["deleted_since"]
#         for i in data["pluviometer_monitorings"]:
#             dict_area_app_pluvi.append(i)
#         next_page = None

#         if data["next_page_url"] != None:
#             next_page = data["next_page_url"]
#             print("\n")
#             print(f"Proximo Pagina: {next_page}")
#             print("\n\n")
#             url = f"https://farmbox.cc{next_page}"
#             if next_page:
#                 try:
#                     get_applications_pluvi(
#                         page=next_page, updated_last=updated_last, url=url
#                     )
#                 except Exception as e:
#                     print("erro em pegar os dados da página selecionada", e)
#         else:
#             if last_page_app_pluvi == 0:
#                 print(
#                     f"{Fore.YELLOW}Sem atualizações no período selecionado{Style.RESET_ALL}"
#                 )
#             else:
#                 print(
#                     f"{Fore.GREEN}Todas as páginas já foram retornadas{Style.RESET_ALL}"
#                 )
#     except Exception as e:
#         print("error na pagina, finalizando o código", e)

#     # for i in dict_area_app_pluvi:
#     #     print(i)

#     return [dict_area_app_pluvi, deleted_app_array_pluvi]

def get_applications_pluvi(page=None, updated_last=None, safra=safra_23_24, url=None, max_workers=8):
    """
    Mantém o mesmo contrato e variáveis globais.
    - Busca a 1ª página para descobrir paginação/deleted_since
    - Dispara as demais páginas em paralelo
    - Retorna [dict_area_app_pluvi, deleted_app_array_pluvi]
    """
    global dict_area_app_pluvi, last_page_app_pluvi, deleted_app_array_pluvi

    # 🔒 evita lixo de execuções anteriores
    dict_area_app_pluvi = []
    last_page_app_pluvi = 0
    deleted_app_array_pluvi = []

    base_api = "https://farmbox.cc/api/v1/pluviometer_monitorings"

    # URL inicial (prioriza 'url' se fornecido)
    if url:
        first_url = url
    else:
        if updated_last:
            first_url = f"{base_api}?updated_since={updated_last}"
        else:
            first_url = base_api

    print(first_url)

    try:
        with requests.Session() as session:
            # 1) Primeira página
            data = _fetch_with_retries(session, first_url)

            # captura deleted_since (normalmente na primeira)
            deleted_app_array_pluvi = data.get("deleted_since", [])

            # agrega resultados iniciais
            items = data.get("pluviometer_monitorings", [])
            if items:
                dict_area_app_pluvi.extend(items)

            pagination = data.get("pagination", {}) or {}
            total_pages = int(pagination.get("total_pages", 1))
            current_page = int(pagination.get("current_page", 1))
            last_page_app_pluvi = total_pages

            # 2) Monta URLs restantes
            remaining_urls = []
            if total_pages > current_page:
                nxt = data.get("next_page_url")
                if nxt:
                    # garante absoluto e usa como template
                    ref = urljoin("https://farmbox.cc", nxt) if nxt.startswith("/") else nxt
                    remaining_urls = _build_page_urls_from_next(ref, total_pages)
                else:
                    # fallback manual
                    remaining_urls = _fallback_build_urls(base_api, updated_last, total_pages)

            # 3) Paraleliza páginas 2..N
            if remaining_urls:
                workers = min(max_workers, max(1, len(remaining_urls)))
                print(f"Baixando páginas restantes em paralelo ({workers} workers)...")
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = [ex.submit(_fetch_with_retries, session, u) for u in remaining_urls]
                    for fut in as_completed(futures):
                        try:
                            page_data = fut.result()
                        except Exception as e:
                            print(f"[erro] Falha ao obter uma página: {e}")
                            continue

                        page_items = page_data.get("pluviometer_monitorings", [])
                        if page_items:
                            dict_area_app_pluvi.extend(page_items)

                        pg = (page_data.get("pagination") or {}).get("current_page")
                        if pg:
                            print(f"✔ Página {pg} concluída ({len(page_items)} itens)")

            # feedback
            if total_pages <= 1:
                if last_page_app_pluvi == 0:
                    print(f"{Fore.YELLOW}Sem atualizações no período selecionado{Style.RESET_ALL}")
                else:
                    print(f"{Fore.GREEN}Todas as páginas já foram retornadas{Style.RESET_ALL}")
            else:
                print(f"{Fore.GREEN}Todas as páginas já foram retornadas{Style.RESET_ALL}")

    except Exception as e:
        print("error na pagina, finalizando o código", e)

    return [dict_area_app_pluvi, deleted_app_array_pluvi]
