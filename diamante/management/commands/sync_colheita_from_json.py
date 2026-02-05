# diamante/management/commands/sync_colheita_from_json.py
import json
from decimal import Decimal, InvalidOperation
from collections import Counter, defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from diamante.models import Colheita


# 📌 JSON na MESMA pasta do command
BASE_DIR = Path(__file__).resolve().parent
JSON_PATH = BASE_DIR / "csvjson.json"


JSON_KEYS = {
    "id": "id farmtruck",
    "umidade": "Umidade",
    "impureza": "Impureza",
    "nf": "NF",
    "peso_bruto": "Soma de Peso Bruto",
    "peso_tara": "Soma de Peso Tara",
    "peso_liquido": "Soma de Peso Liquido",
}


def parse_decimal_pt(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value

    s = str(value).strip()
    if not s:
        return None
    s = s.replace("%", "").strip()
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def to_str_nf(value):
    if value in (None, ""):
        return None
    return str(value).strip()


class Command(BaseCommand):
    help = "Audita e (opcionalmente) sincroniza umidade/impureza/nota_fiscal em Colheita via JSON por id_farmtruck."

    def add_arguments(self, parser):
        parser.add_argument(
            "--should-save",
            action="store_true",
            help="Quando presente, grava no banco chamando save() em cada Colheita.",
        )
        parser.add_argument(
            "--limit-missing",
            type=int,
            default=20,
        )
        parser.add_argument(
            "--limit-dup",
            type=int,
            default=10,
        )

    def handle(self, *args, **options):
        should_save = options["should_save"]
        limit_missing = options["limit_missing"]
        limit_dup = options["limit_dup"]

        # ✅ leitura automática da mesma pasta
        if not JSON_PATH.exists():
            raise Exception(f"Arquivo JSON não encontrado em: {JSON_PATH}")

        self.stdout.write(f"Lendo JSON em: {JSON_PATH}")

        with open(JSON_PATH, "r", encoding="utf-8") as f:
            rows = json.load(f)

        # --- Métricas do JSON
        json_rows = 0
        json_ids = []
        json_sum_bruto = Decimal("0")
        json_sum_tara = Decimal("0")
        json_sum_liq = Decimal("0")

        payload_by_id = {}

        for r in rows:
            json_rows += 1
            fid = (r.get(JSON_KEYS["id"]) or "").strip()
            if not fid:
                continue

            json_ids.append(fid)

            pb = parse_decimal_pt(r.get(JSON_KEYS["peso_bruto"])) or Decimal("0")
            pt = parse_decimal_pt(r.get(JSON_KEYS["peso_tara"])) or Decimal("0")
            pl = parse_decimal_pt(r.get(JSON_KEYS["peso_liquido"])) or Decimal("0")

            json_sum_bruto += pb
            json_sum_tara += pt
            json_sum_liq += pl

            payload_by_id[fid] = {
                "umidade": parse_decimal_pt(r.get(JSON_KEYS["umidade"])),
                "impureza": parse_decimal_pt(r.get(JSON_KEYS["impureza"])),
                "nota_fiscal": to_str_nf(r.get(JSON_KEYS["nf"])),
            }

        json_ids_unique = sorted(set(json_ids))
        json_dup_count = sum(1 for _id, c in Counter(json_ids).items() if c > 1)

        # --- Consulta banco
        qs = Colheita.objects.filter(id_farmtruck__in=json_ids_unique).only(
            "id",
            "id_farmtruck",
            "peso_bruto",
            "peso_tara",
            "umidade",
            "impureza",
            "nota_fiscal",
        )

        found_by_id = defaultdict(list)
        for obj in qs:
            found_by_id[obj.id_farmtruck].append(obj)

        missing_ids = [fid for fid in json_ids_unique if fid not in found_by_id]

        # --- Métricas do banco
        db_matches_records = 0
        db_sum_bruto = Decimal("0")
        db_sum_tara = Decimal("0")
        db_sum_liq = Decimal("0")

        dup_in_db = []
        for fid, objs in found_by_id.items():
            if len(objs) > 1:
                dup_in_db.append((fid, len(objs)))

            for o in objs:
                db_matches_records += 1
                db_sum_bruto += Decimal(o.peso_bruto or 0)
                db_sum_tara += Decimal(o.peso_tara or 0)
                db_sum_liq += Decimal((o.peso_bruto or 0) - (o.peso_tara or 0))

        dup_in_db.sort(key=lambda x: x[1], reverse=True)

        # --- RELATÓRIO
        self.stdout.write("\n=== AUDITORIA JSON -> Colheita (id_farmtruck) ===")
        self.stdout.write(f"Linhas no JSON: {json_rows}")
        self.stdout.write(f"IDs no JSON (total): {len(json_ids)}")
        self.stdout.write(f"IDs no JSON (únicos): {len(json_ids_unique)}")
        self.stdout.write(f"IDs duplicados no JSON: {json_dup_count}")
        self.stdout.write("")
        self.stdout.write(f"IDs encontrados no banco: {len(found_by_id)}")
        self.stdout.write(f"Registros Colheita encontrados: {db_matches_records}")
        self.stdout.write(f"IDs sem match: {len(missing_ids)}")

        if missing_ids:
            self.stdout.write("\n--- Exemplo IDs sem match ---")
            for fid in missing_ids[:limit_missing]:
                self.stdout.write(f"- {fid}")

        if dup_in_db:
            self.stdout.write("\n--- IDs com múltiplas Colheitas ---")
            for fid, n in dup_in_db[:limit_dup]:
                self.stdout.write(f"- {fid}: {n} registros")

        self.stdout.write("\n--- Somatórios JSON ---")
        self.stdout.write(f"Peso Bruto: {json_sum_bruto}")
        self.stdout.write(f"Peso Tara : {json_sum_tara}")
        self.stdout.write(f"Peso Líq  : {json_sum_liq}")

        self.stdout.write("\n--- Somatórios DB ---")
        self.stdout.write(f"Peso Bruto: {db_sum_bruto}")
        self.stdout.write(f"Peso Tara : {db_sum_tara}")
        self.stdout.write(f"Peso Líq  : {db_sum_liq}")

        # 🚨 Só auditoria
        if not should_save:
            self.stdout.write("\n(SEM ALTERAR) Rode novamente com --should-save\n")
            return

        self.stdout.write("\n=== APLICANDO ALTERAÇÕES ===")

        total_saved = 0
        total_changed_rows = 0

        with transaction.atomic():
            for fid, objs in found_by_id.items():
                payload = payload_by_id.get(fid) or {}
                um = payload.get("umidade")
                imp = payload.get("impureza")
                nf = payload.get("nota_fiscal")

                for obj in objs:
                    changed = False

                    if um is not None and obj.umidade != um:
                        obj.umidade = um
                        changed = True

                    if imp is not None and obj.impureza != imp:
                        obj.impureza = imp
                        changed = True

                    if nf is not None and obj.nota_fiscal != nf:
                        obj.nota_fiscal = nf
                        changed = True

                    if changed:
                        total_changed_rows += 1
                        obj.save()
                        total_saved += 1

        self.stdout.write(self.style.SUCCESS(f"Salvos (save chamado): {total_saved}"))
        self.stdout.write(self.style.SUCCESS(f"Registros alterados: {total_changed_rows}"))
        self.stdout.write(self.style.SUCCESS("Concluído.\n"))
