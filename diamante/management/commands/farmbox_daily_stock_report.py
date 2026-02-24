import os
import json
import ssl
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from django.core.management.base import BaseCommand

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

# 👇 ajusta o import conforme o caminho real no seu projeto
# Ex: from core.gmail_api import send_mail_gmail_api
from diamante.gmail.gmail_api import send_mail_gmail_api
from diamante.models import EmailAberturaST


BASE_URL = "https://farmbox.cc"
API_BASE = f"{BASE_URL}/api/v1"
TZ = ZoneInfo("America/Sao_Paulo")


def make_ssl_context():
    insecure = (os.environ.get("FARMBOX_INSECURE_SSL") or "").strip().lower() in ("1", "true", "yes")
    if not insecure:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


SSL_CONTEXT = make_ssl_context()


def http_get_json(url: str, headers: dict) -> dict:
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, context=SSL_CONTEXT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise RuntimeError(f"HTTPError {e.code} em {url}\n{body}") from e
    except URLError as e:
        raise RuntimeError(f"URLError em {url}: {e}") from e


def fetch_all_pages_list(headers: dict, first_url: str, root_key: str) -> list:
    url = first_url
    out = []
    while True:
        data = http_get_json(url, headers=headers)
        out.extend(data.get(root_key) or [])
        next_url = data.get("next_page_url")
        if not next_url:
            break
        url = urljoin(BASE_URL, next_url)
    return out


def fetch_movimentations_since(headers: dict, by_start_date: str) -> list:
    q = urlencode({"by_start_date": by_start_date})
    url = f"{API_BASE}/movimentations?{q}"
    return fetch_all_pages_list(headers, url, "movimentations")


def fetch_users_map(headers: dict) -> dict:
    users = fetch_all_pages_list(headers, f"{API_BASE}/users", "users")
    out = {}
    for u in users:
        uid = u.get("id")
        if uid is None:
            continue
        out[int(uid)] = (u.get("name") or "").strip() or f"#{uid}"
    return out


def fetch_inputs_map(headers: dict) -> dict:
    inputs = fetch_all_pages_list(headers, f"{API_BASE}/inputs", "inputs")

    out = {}

    for i in inputs:

        iid = i.get("id")
        if iid is None:
            continue

        input_type = (i.get("input_type_name") or "").strip().lower()

        # 🔴 REMOVE "Operação"
        if input_type == "operação":
            continue

        name = (i.get("name") or "").strip()
        if not name:
            name = f"#{iid}"

        out[int(iid)] = name

    return out


def fetch_storages_map(headers: dict) -> dict:
    storages = fetch_all_pages_list(headers, f"{API_BASE}/storages", "storages")
    out = {}
    for s in storages:
        sid = s.get("id")
        if sid is None:
            continue
        out[int(sid)] = (s.get("name") or "").strip() or f"#{sid}"
    return out


def fmt_br_2(n: float) -> str:
    try:
        x = float(n or 0)
    except Exception:
        x = 0.0
    s = f"{x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def date_br(iso_yyyy_mm_dd: str) -> str:
    try:
        return datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return iso_yyyy_mm_dd or ""


def enrich_rows(rows, users_map, inputs_map, storages_map):
    enriched = []
    for r in rows:
        input_id = r.get("input_id")
        storage_id = r.get("storage_id")
        user_id = r.get("user_id")

        app = r.get("application_info") or {}
        batch = r.get("batch_info") or {}

        enriched.append({
            # ids
            "id": r.get("id"),
            "input_id": input_id,
            "storage_id": storage_id,
            "user_id": user_id,

            # nomes
            "product_name": inputs_map.get(int(input_id), f"#{input_id}") if input_id is not None else "",
            "storage_name": storages_map.get(int(storage_id), f"#{storage_id}") if storage_id is not None else "",
            "user_name": users_map.get(int(user_id), f"#{user_id}") if user_id is not None else "",

            # core
            "date": r.get("date"),
            "movimentation_type": r.get("movimentation_type"),
            "quantity": float(r.get("quantity") or 0),
            "unit": r.get("unit") or "",

            # extras
            "observation": r.get("observation"),
            "invoice_number": r.get("invoice_number"),
            "invoice_file_url": r.get("invoice_file_url"),

            # batch
            "batch_id": batch.get("batch_id"),
            "batch_number": batch.get("batch_number"),
            "validity": batch.get("validity"),

            # application
            "application_id": app.get("application_id"),
            "application_code": app.get("code"),
        })
    return enriched


def aggregate(enriched):
    by_product = {}   # (product_name, unit) -> {in,out}
    by_user = {}
    by_storage = {}
    sum_in = 0.0
    sum_out = 0.0

    for r in enriched:
        t = (r.get("movimentation_type") or "").lower().strip()
        qty = float(r.get("quantity") or 0)
        unit = r.get("unit") or ""
        prod = r.get("product_name") or "(sem produto)"
        usr = r.get("user_name") or "(sem usuário)"
        sto = r.get("storage_name") or "(sem almox)"

        by_product.setdefault((prod, unit), {"in": 0.0, "out": 0.0})
        by_user.setdefault((usr, unit), {"out": 0.0})
        by_storage.setdefault((sto, unit), {"out": 0.0})

        if t == "in":
            sum_in += qty
            by_product[(prod, unit)]["in"] += qty
        elif t == "out":
            sum_out += qty
            by_product[(prod, unit)]["out"] += qty
            by_user[(usr, unit)]["out"] += qty
            by_storage[(sto, unit)]["out"] += qty

    prod_rows = []
    for (prod, unit), v in by_product.items():
        prod_rows.append({
            "product": prod,
            "unit": unit,
            "in": v["in"],
            "out": v["out"],
            "balance": v["in"] - v["out"],
        })
    prod_rows.sort(key=lambda x: (x["out"], x["product"]), reverse=True)

    user_rows = []
    for (usr, unit), v in by_user.items():
        user_rows.append({"user": usr, "unit": unit, "out": v["out"]})
    user_rows.sort(key=lambda x: (x["out"], x["user"]), reverse=True)

    storage_rows = []
    for (sto, unit), v in by_storage.items():
        storage_rows.append({"storage": sto, "unit": unit, "out": v["out"]})
    storage_rows.sort(key=lambda x: (x["out"], x["storage"]), reverse=True)

    return {
        "sum_in": sum_in,
        "sum_out": sum_out,
        "balance": sum_in - sum_out,
        "products": prod_rows,
        "users": user_rows,
        "storages": storage_rows,
    }


def build_email_html(report_date_iso: str, agg: dict):
    top_products = agg["products"][:25]
    top_users = agg["users"][:15]
    top_storages = agg["storages"][:15]

    def tr_prod(p):
        return f"""
          <tr>
            <td style="padding:8px 10px;border-bottom:1px solid #e9e9ef;">{p["product"]}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e9e9ef;text-align:right;">{fmt_br_2(p["in"])}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e9e9ef;text-align:right;">{fmt_br_2(p["out"])}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e9e9ef;text-align:right;">{fmt_br_2(p["balance"])}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e9e9ef;">{p["unit"]}</td>
          </tr>
        """

    def tr_simple(label, out, unit):
        return f"""
          <tr>
            <td style="padding:8px 10px;border-bottom:1px solid #e9e9ef;">{label}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e9e9ef;text-align:right;">{fmt_br_2(out)}</td>
            <td style="padding:8px 10px;border-bottom:1px solid #e9e9ef;">{unit}</td>
          </tr>
        """

    html = f"""
    <div style="font-family:Arial, Helvetica, sans-serif; color:#111;">
      <h2 style="margin:0 0 8px;">Relatório diário de estoque — {date_br(report_date_iso)}</h2>

      <div style="display:flex; gap:12px; flex-wrap:wrap; margin:10px 0 14px;">
        <div style="padding:10px 12px; border:1px solid #e9e9ef; border-radius:10px;">
          <div style="font-size:12px; color:#666;">Entrada (IN)</div>
          <div style="font-size:18px; font-weight:800;">{fmt_br_2(agg["sum_in"])}</div>
        </div>
        <div style="padding:10px 12px; border:1px solid #e9e9ef; border-radius:10px;">
          <div style="font-size:12px; color:#666;">Saída (OUT)</div>
          <div style="font-size:18px; font-weight:800;">{fmt_br_2(agg["sum_out"])}</div>
        </div>
        <div style="padding:10px 12px; border:1px solid #e9e9ef; border-radius:10px;">
          <div style="font-size:12px; color:#666;">Saldo (IN - OUT)</div>
          <div style="font-size:18px; font-weight:800;">{fmt_br_2(agg["balance"])}</div>
        </div>
      </div>

      <h3 style="margin:18px 0 8px;">Consolidado por produto (Top 25 por OUT)</h3>
      <table style="border-collapse:collapse; width:100%; max-width:980px; border:1px solid #e9e9ef;">
        <thead>
          <tr style="background:#f7f7fb;">
            <th style="text-align:left; padding:8px 10px; border-bottom:1px solid #e9e9ef;">Produto</th>
            <th style="text-align:right; padding:8px 10px; border-bottom:1px solid #e9e9ef;">IN</th>
            <th style="text-align:right; padding:8px 10px; border-bottom:1px solid #e9e9ef;">OUT</th>
            <th style="text-align:right; padding:8px 10px; border-bottom:1px solid #e9e9ef;">Saldo</th>
            <th style="text-align:left; padding:8px 10px; border-bottom:1px solid #e9e9ef;">Un</th>
          </tr>
        </thead>
        <tbody>
          {''.join(tr_prod(p) for p in top_products) or '<tr><td colspan="5" style="padding:10px;">Sem dados.</td></tr>'}
        </tbody>
      </table>

      <div style="display:flex; gap:16px; flex-wrap:wrap; margin-top:16px;">
        <div style="flex:1; min-width:320px;">
          <h3 style="margin:0 0 8px;">Top usuários (OUT)</h3>
          <table style="border-collapse:collapse; width:100%; border:1px solid #e9e9ef;">
            <thead>
              <tr style="background:#f7f7fb;">
                <th style="text-align:left; padding:8px 10px; border-bottom:1px solid #e9e9ef;">Usuário</th>
                <th style="text-align:right; padding:8px 10px; border-bottom:1px solid #e9e9ef;">OUT</th>
                <th style="text-align:left; padding:8px 10px; border-bottom:1px solid #e9e9ef;">Un</th>
              </tr>
            </thead>
            <tbody>
              {''.join(tr_simple(x["user"], x["out"], x["unit"]) for x in top_users) or '<tr><td colspan="3" style="padding:10px;">Sem dados.</td></tr>'}
            </tbody>
          </table>
        </div>

        <div style="flex:1; min-width:320px;">
          <h3 style="margin:0 0 8px;">Top almoxarifados (OUT)</h3>
          <table style="border-collapse:collapse; width:100%; border:1px solid #e9e9ef;">
            <thead>
              <tr style="background:#f7f7fb;">
                <th style="text-align:left; padding:8px 10px; border-bottom:1px solid #e9e9ef;">Almox</th>
                <th style="text-align:right; padding:8px 10px; border-bottom:1px solid #e9e9ef;">OUT</th>
                <th style="text-align:left; padding:8px 10px; border-bottom:1px solid #e9e9ef;">Un</th>
              </tr>
            </thead>
            <tbody>
              {''.join(tr_simple(x["storage"], x["out"], x["unit"]) for x in top_storages) or '<tr><td colspan="3" style="padding:10px;">Sem dados.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>

      <p style="color:#666; font-size:12px; margin-top:14px;">
        Anexo: Excel com dados completos (RAW + consolidados).
      </p>
    </div>
    """
    return html


def autosize(ws, max_col=30):
    for col in range(1, max_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 20


def write_table(ws, headers, rows):
    bold = Font(bold=True)
    ws.append(headers)
    for cell in ws[1]:
        cell.font = bold
        cell.alignment = Alignment(horizontal="center")

    for r in rows:
        ws.append(r)

    autosize(ws, max_col=len(headers))


def build_xlsx_bytes(report_date_iso: str, enriched: list, agg: dict) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)

    ws_raw = wb.create_sheet("RAW")
    raw_headers = [
        "id", "date_iso", "date_br", "movimentation_type", "quantity", "unit",
        "product_name", "input_id",
        "storage_name", "storage_id",
        "user_name", "user_id",
        "application_code", "application_id",
        "batch_id", "batch_number", "validity",
        "invoice_number", "invoice_file_url",
        "observation",
    ]
    raw_rows = []
    for r in enriched:
        raw_rows.append([
            r.get("id"),
            r.get("date"),
            date_br(r.get("date") or ""),
            r.get("movimentation_type"),
            float(r.get("quantity") or 0),
            r.get("unit"),
            r.get("product_name"),
            r.get("input_id"),
            r.get("storage_name"),
            r.get("storage_id"),
            r.get("user_name"),
            r.get("user_id"),
            r.get("application_code"),
            r.get("application_id"),
            r.get("batch_id"),
            r.get("batch_number"),
            r.get("validity"),
            r.get("invoice_number"),
            r.get("invoice_file_url"),
            r.get("observation"),
        ])
    write_table(ws_raw, raw_headers, raw_rows)

    # número no Excel (quantity)
    for row in ws_raw.iter_rows(min_row=2, min_col=5, max_col=5):
        for cell in row:
            cell.number_format = "#,##0.00"

    ws_p = wb.create_sheet("Consolidado_Produto")
    p_headers = ["product", "unit", "in", "out", "balance"]
    p_rows = [[x["product"], x["unit"], x["in"], x["out"], x["balance"]] for x in agg["products"]]
    write_table(ws_p, p_headers, p_rows)
    for col in (3, 4, 5):
        for row in ws_p.iter_rows(min_row=2, min_col=col, max_col=col):
            for cell in row:
                cell.number_format = "#,##0.00"

    ws_u = wb.create_sheet("Consolidado_Usuario_OUT")
    u_headers = ["user", "unit", "out"]
    u_rows = [[x["user"], x["unit"], x["out"]] for x in agg["users"]]
    write_table(ws_u, u_headers, u_rows)
    for row in ws_u.iter_rows(min_row=2, min_col=3, max_col=3):
        for cell in row:
            cell.number_format = "#,##0.00"

    ws_s = wb.create_sheet("Consolidado_Almox_OUT")
    s_headers = ["storage", "unit", "out"]
    s_rows = [[x["storage"], x["unit"], x["out"]] for x in agg["storages"]]
    write_table(ws_s, s_headers, s_rows)
    for row in ws_s.iter_rows(min_row=2, min_col=3, max_col=3):
        for cell in row:
            cell.number_format = "#,##0.00"

    ws_meta = wb.create_sheet("META")
    write_table(ws_meta, ["key", "value"], [
        ["report_date_iso", report_date_iso],
        ["generated_at", datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %z")],
        ["rows", len(enriched)],
    ])

    from io import BytesIO
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


class Command(BaseCommand):
    help = "Coleta movimentações do dia anterior na Farmbox e envia e-mail via Gmail API (HTML + XLSX)"

    def handle(self, *args, **options):
        token = os.environ.get("FARM_API")
        if not token:
            raise RuntimeError("FARMBOX_TOKEN não configurado.")

        # to_list = (os.environ.get("STOCK_REPORT_EMAIL_TO") or "marcelo@gdourado.com.br").split(",")
        # to_list = [x.strip() for x in to_list if x.strip()]
        to_list = EmailAberturaST.objects.filter(atividade__tipo='Estoque Movimento Farmbox', ativo=True).values_list('email', flat=True)
        if not to_list:
            raise RuntimeError("STOCK_REPORT_EMAIL_TO não configurado (lista separada por vírgula).")

        cc_list = (os.environ.get("STOCK_REPORT_EMAIL_CC") or "").split(",")
        cc_list = [x.strip() for x in cc_list if x.strip()]

        from_email = os.environ.get("STOCK_REPORT_EMAIL_FROM") or "me"

        now = datetime.now(TZ)
        report_day = (now.date() - timedelta(days=1))  # ontem
        report_iso = report_day.strftime("%Y-%m-%d")

        headers = {
            "Authorization": token,  # se precisar Bearer: f"Bearer {token}"
            "Accept": "application/json",
            "User-Agent": "farmbox-daily-stock-report/1.0",
        }

        self.stdout.write(f"[1/5] Coletando movimentações desde {report_iso}...")
        rows = fetch_movimentations_since(headers, by_start_date=report_iso)
        rows = [r for r in rows if (r.get("date") == report_iso)]
        self.stdout.write(f"  OK: {len(rows)} linhas do dia {report_iso}")

        self.stdout.write("[2/5] Carregando índices (inputs/users/storages)...")
        users_map = fetch_users_map(headers)
        inputs_map = fetch_inputs_map(headers)
        storages_map = fetch_storages_map(headers)
        
        # remove inputs tipo Operação já aqui
        rows = [
            r for r in rows
            if r.get("input_id") in inputs_map
        ]

        self.stdout.write("[3/5] Enriquecendo + consolidando...")
        enriched = enrich_rows(rows, users_map, inputs_map, storages_map)

        # 🔴 remove movimentações de inputs filtrados (Operação)
        enriched = [
            r for r in enriched
            if r.get("input_id") in inputs_map
        ]
        
        
        agg = aggregate(enriched)

        self.stdout.write("[4/5] Gerando Excel...")
        xlsx_bytes = build_xlsx_bytes(report_iso, enriched, agg)
        xlsx_name = f"estoque_movimentacoes_{report_iso}.xlsx"

        self.stdout.write("[5/5] Enviando via Gmail API...")
        subject = f"Relatório de estoque (Farmbox) — {date_br(report_iso)}"
        html = build_email_html(report_iso, agg)

        attachments = [
            (xlsx_name, xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        ]

        send_mail_gmail_api(
            subject=subject,
            body_html=html,
            from_email=from_email,
            to_emails=to_list,
            cc_emails=cc_list,
            attachments=attachments,
            fail_silently=False,
        )

        self.stdout.write(self.style.SUCCESS(f"Enviado para: {', '.join(to_list)}"))