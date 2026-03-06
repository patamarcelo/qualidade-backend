from django.utils import timezone

from opscheckin.models import DailyCheckin, AgendaItem


def _fmt_dt_br(dt):
    if not dt:
        return ""
    local_dt = timezone.localtime(dt)
    return local_dt.strftime("%H:%M")


def _status_emoji(item):
    if item.status == "done":
        return "✅"
    if item.status == "skip":
        return "⛔"
    return "⏳"


def _status_and_items_for_manager(manager, day):
    checkin = (
        DailyCheckin.objects
        .filter(manager=manager, date=day)
        .first()
    )

    if not checkin:
        return {
            "manager": manager,
            "status": "no_checkin",
            "status_label": "⏳ Não respondeu",
            "answered_at": "",
            "items": [],
            "done_count": 0,
            "open_count": 0,
            "skip_count": 0,
            "total_count": 0,
        }

    agenda_q = (
        checkin.questions
        .filter(step="AGENDA")
        .order_by("-id")
        .first()
    )

    items = list(
        AgendaItem.objects
        .filter(checkin=checkin)
        .order_by("idx")
    )

    done_count = sum(1 for x in items if x.status == "done")
    open_count = sum(1 for x in items if x.status == "open")
    skip_count = sum(1 for x in items if x.status == "skip")
    total_count = len(items)

    if agenda_q and agenda_q.status == "answered":
        answered_at = _fmt_dt_br(agenda_q.answered_at)
        if items:
            return {
                "manager": manager,
                "status": "answered",
                "status_label": f"✅ Respondeu às {answered_at}" if answered_at else "✅ Respondeu",
                "answered_at": answered_at,
                "items": items,
                "done_count": done_count,
                "open_count": open_count,
                "skip_count": skip_count,
                "total_count": total_count,
            }
        return {
            "manager": manager,
            "status": "answered_no_items",
            "status_label": f"⚠️ Respondeu às {answered_at}, mas sem itens válidos" if answered_at else "⚠️ Respondeu, mas sem itens válidos",
            "answered_at": answered_at,
            "items": [],
            "done_count": 0,
            "open_count": 0,
            "skip_count": 0,
            "total_count": 0,
        }

    return {
        "manager": manager,
        "status": "no_answer",
        "status_label": "⏳ Não respondeu",
        "answered_at": "",
        "items": [],
        "done_count": 0,
        "open_count": 0,
        "skip_count": 0,
        "total_count": 0,
    }


def build_director_agenda_summary(*, day, managers):
    entries = [_status_and_items_for_manager(m, day) for m in managers]

    total = len(entries)
    answered = sum(1 for e in entries if e["status"] == "answered")
    pending = sum(1 for e in entries if e["status"] in {"no_checkin", "no_answer"})
    invalid = sum(1 for e in entries if e["status"] == "answered_no_items")

    total_items = sum(e["total_count"] for e in entries)
    total_done = sum(e["done_count"] for e in entries)
    total_open = sum(e["open_count"] for e in entries)
    total_skip = sum(e["skip_count"] for e in entries)

    day_br = day.strftime("%d/%m/%Y")
    lines = [f"📋 Resumo das agendas — {day_br}", ""]

    for idx, entry in enumerate(entries, start=1):
        lines.append(f"{idx}) {entry['manager'].name}")
        lines.append(f"Status: {entry['status_label']}")

        if entry["total_count"] > 0:
            lines.append(
                f"Progresso: {entry['done_count']}/{entry['total_count']} concluídas"
            )
            if entry["open_count"]:
                lines.append(f"Pendentes: {entry['open_count']}")
            if entry["skip_count"]:
                lines.append(f"Puladas: {entry['skip_count']}")

        lines.append("Itens:")

        if entry["items"]:
            for it in entry["items"]:
                lines.append(f"{_status_emoji(it)} {it.idx}) {it.text}")
        else:
            lines.append("• Sem agenda enviada")

        lines.append("")

    lines.append("Resumo geral:")
    lines.append(f"• Managers com agenda válida: {answered}/{total}")
    lines.append(f"• Managers sem resposta: {pending}/{total}")
    if invalid:
        lines.append(f"• Respostas sem itens válidos: {invalid}/{total}")
    lines.append(f"• Itens concluídos: {total_done}/{total_items}" if total_items else "• Itens concluídos: 0/0")
    if total_open:
        lines.append(f"• Itens pendentes: {total_open}")
    if total_skip:
        lines.append(f"• Itens pulados: {total_skip}")

    return "\n".join(lines).strip()