import datetime
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs

import requests
from django.conf import settings


FARMBOX_BASE_URL = "https://farmbox.cc"
DEFAULT_TIMEOUT = 45


def get_milliseconds_from_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime.datetime):
        dt_obj = value
    elif isinstance(value, datetime.date):
        dt_obj = datetime.datetime.combine(value, datetime.time.min)
    else:
        raw = str(value).strip()

        try:
            dt_obj = datetime.datetime.strptime(raw, "%Y-%m-%d %H:%M")
        except ValueError:
            dt_obj = datetime.datetime.strptime(raw, "%Y-%m-%d")

    return int(dt_obj.timestamp() * 1000)


def _get_headers():
    return {
        "Content-Type": "application/json",
        "Authorization": settings.FARMBOX_ID,
    }


def _build_plantations_url(harvest_id, updated_since_ms=None, page=None):
    url = f"{FARMBOX_BASE_URL}/api/v1/plantations?from_harvest_ids={harvest_id}"

    if page:
        url = f"{url}&page={page}"

    if updated_since_ms:
        url = f"{url}&updated_since={updated_since_ms}"

    return url


def _fetch_url(url, timeout=DEFAULT_TIMEOUT):
    started_at = time.perf_counter()

    response = requests.get(url, headers=_get_headers(), timeout=timeout)

    try:
        data = response.json()
    except Exception:
        raise ValueError(
            f"Farmbox retornou JSON inválido. "
            f"Status: {response.status_code}. Texto: {response.text[:500]}"
        )

    if response.status_code not in [200, 201]:
        raise ValueError(
            f"Erro Farmbox. Status: {response.status_code}. Resposta: {data}"
        )

    elapsed = round(time.perf_counter() - started_at, 3)

    return {
        "url": url,
        "elapsed": elapsed,
        "data": data,
    }


def _extract_page_number(url):
    if not url:
        return None

    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        page = qs.get("page", [None])[0]

        if page is None:
            return None

        return int(page)
    except Exception:
        return None


def _discover_total_pages_from_first_response(first_data):
    """
    Tenta descobrir o total de páginas já na primeira resposta.

    Suporta os cenários mais prováveis:
    - total_pages direto
    - total + per_page
    - count + per_page
    - total_count + per_page
    - meta.total_pages
    - pagination.total_pages
    - last_page_url com page=N
    - fallback: next_page_url page=2 => pelo menos 2 páginas
    """

    candidates = [
        first_data.get("total_pages"),
        first_data.get("pages"),
        first_data.get("last_page"),
        first_data.get("meta", {}).get("total_pages") if isinstance(first_data.get("meta"), dict) else None,
        first_data.get("pagination", {}).get("total_pages") if isinstance(first_data.get("pagination"), dict) else None,
    ]

    for value in candidates:
        try:
            if value:
                return int(value)
        except Exception:
            pass

    last_page_url = (
        first_data.get("last_page_url")
        or first_data.get("last")
        or first_data.get("meta", {}).get("last_page_url") if isinstance(first_data.get("meta"), dict) else None
    )

    last_page = _extract_page_number(last_page_url)
    if last_page:
        return last_page

    total = (
        first_data.get("total")
        or first_data.get("count")
        or first_data.get("total_count")
        or first_data.get("meta", {}).get("total") if isinstance(first_data.get("meta"), dict) else None
    )

    per_page = (
        first_data.get("per_page")
        or first_data.get("limit")
        or first_data.get("page_size")
        or first_data.get("meta", {}).get("per_page") if isinstance(first_data.get("meta"), dict) else None
    )

    try:
        if total and per_page:
            return int(math.ceil(int(total) / int(per_page)))
    except Exception:
        pass

    next_page = _extract_page_number(first_data.get("next_page_url"))

    if next_page:
        return next_page

    return 1


def fetch_farmbox_plantations_parallel(
    harvest_id,
    updated_since_ms=None,
    max_workers=10,
    timeout=DEFAULT_TIMEOUT,
):
    """
    Fluxo performático:
    1) Busca página 1.
    2) Descobre total de páginas pela primeira resposta.
    3) Busca páginas 2..N em paralelo.
    4) Junta tudo mantendo resultado único.

    Essa função substitui a paginação sequencial do endpoint.
    """

    started_at = time.perf_counter()

    first_url = _build_plantations_url(
        harvest_id=harvest_id,
        updated_since_ms=updated_since_ms,
    )

    first_result = _fetch_url(first_url, timeout=timeout)
    first_data = first_result["data"]

    plantations = list(first_data.get("plantations") or [])

    total_pages = _discover_total_pages_from_first_response(first_data)

    # Se a API só retornou next_page_url e não retornou total real,
    # total_pages pode virar 2. Nesse caso, ainda funciona, mas não descobre tudo.
    # Ideal é confirmar o campo exato retornado pelo Farmbox.
    pages_to_fetch = list(range(2, total_pages + 1))

    page_results = []
    errors = []

    if pages_to_fetch:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _fetch_url,
                    _build_plantations_url(
                        harvest_id=harvest_id,
                        updated_since_ms=updated_since_ms,
                        page=page,
                    ),
                    timeout,
                ): page
                for page in pages_to_fetch
            }

            for future in as_completed(futures):
                page = futures[future]

                try:
                    result = future.result()
                    data = result["data"]
                    items = data.get("plantations") or []

                    page_results.append({
                        "page": page,
                        "count": len(items),
                        "elapsed": result["elapsed"],
                    })

                    plantations.extend(items)

                except Exception as e:
                    errors.append({
                        "page": page,
                        "error": str(e),
                    })

    elapsed_total = round(time.perf_counter() - started_at, 3)

    return {
        "plantations": plantations,
        "meta": {
            "harvest_id": harvest_id,
            "updated_since_ms": updated_since_ms,
            "total_pages": total_pages,
            "pages_requested_parallel": len(pages_to_fetch),
            "total_received": len(plantations),
            "elapsed_total": elapsed_total,
            "first_page_elapsed": first_result["elapsed"],
            "page_results": sorted(page_results, key=lambda x: x["page"]),
            "errors": errors,
        },
    }