"""Coloque este arquivo em <seu_app>/management/commands/."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError


def normalize(value: object) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


class Command(BaseCommand):
    help = "Atualiza impureza das Colheitas existentes a partir do JSON de classificação."

    def add_arguments(self, parser):
        parser.add_argument("arquivo_json", type=Path)
        parser.add_argument("--app-label", required=True, help="App Django que contém o model Colheita.")
        parser.add_argument("--romaneio", help="Atualiza somente um romaneio para validação.")
        parser.add_argument("--dry-run", action="store_true", help="Valida e gera relatório, sem gravar.")
        parser.add_argument("--confirmar", action="store_true", help="Efetiva a atualização. Obrigatório fora do dry-run.")
        parser.add_argument("--relatorio", type=Path, default=Path("relatorio_importacao_impurezas.json"))

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["confirmar"]:
            raise CommandError("Use --dry-run ou --confirmar.")
        if options["dry_run"] and options["confirmar"]:
            raise CommandError("Use apenas um entre --dry-run e --confirmar.")

        try:
            Colheita = apps.get_model(options["app_label"], "Colheita")
        except LookupError as error:
            raise CommandError(f"Model Colheita não encontrado no app '{options['app_label']}'.") from error

        try:
            payload = json.loads(options["arquivo_json"].read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise CommandError(f"Arquivo não encontrado: {options['arquivo_json']}") from error

        items = payload.get("cargas_para_importar", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise CommandError("O JSON deve ser uma lista ou conter 'cargas_para_importar'.")

        selected_romaneio = str(options["romaneio"]) if options["romaneio"] else None
        report = {"modo": "dry-run" if options["dry_run"] else "confirmar", "atualizadas": [], "bloqueadas": [], "nao_encontradas": []}

        for item in items:
            romaneio = str(item["romaneio"])
            if selected_romaneio and romaneio != selected_romaneio:
                continue

            impureza = Decimal(str(item["impureza"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            placa_esperada = normalize(item["placa_referencia"])
            cargas = list(
                Colheita.objects.select_related("deposito", "plantio__variedade__cultura")
                .filter(romaneio=romaneio)
                .order_by("id")
            )

            if not cargas:
                report["nao_encontradas"].append({"romaneio": romaneio, "motivo": "Nenhuma Colheita com este romaneio."})
                continue

            placas_encontradas = {normalize(carga.placa) for carga in cargas}
            cargas = [carga for carga in cargas if normalize(carga.placa) == placa_esperada]
            if not cargas:
                report["bloqueadas"].append({
                    "romaneio": romaneio,
                    "motivo": "Nenhuma Colheita com a placa esperada; nenhuma atualização foi aplicada.",
                    "placa_esperada": item["placa_referencia"],
                    "placas_encontradas": sorted(placas_encontradas),
                })
                continue

            culturas = {carga.plantio.variedade.cultura.cultura for carga in cargas}
            if culturas != {"Feijão"}:
                report["bloqueadas"].append({"romaneio": romaneio, "motivo": "Cultura divergente; esperado Feijão.", "culturas": sorted(culturas)})
                continue

            depositos_fazendao = [carga.id for carga in cargas if carga.deposito.id_d == 4]
            if depositos_fazendao:
                report["bloqueadas"].append({
                    "romaneio": romaneio,
                    "motivo": "Depósito Fazendão possui tolerância própria de 1%; revisão manual necessária.",
                    "colheita_ids": depositos_fazendao,
                })
                continue

            altered = []
            for carga in cargas:
                before = str(carga.impureza) if carga.impureza is not None else None
                if not options["dry_run"]:
                    carga.impureza = impureza
                    carga.save()  # Recalcula descontos e pesos pelo model.
                altered.append({"colheita_id": carga.id, "impureza_anterior": before, "impureza_nova": str(impureza)})

            report["atualizadas"].append({
                "romaneio": romaneio,
                "ticket_referencia": item.get("ticket_referencia"),
                "placa": item["placa_referencia"],
                "carga_pdf": item.get("carga_pdf"),
                "itens": altered,
            })

        options["relatorio"].write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(
            f"{report['modo']}: {len(report['atualizadas'])} romaneio(s) válidos, "
            f"{len(report['bloqueadas'])} bloqueado(s), {len(report['nao_encontradas'])} não encontrado(s)."
        ))
        self.stdout.write(f"Relatório: {options['relatorio']}")
