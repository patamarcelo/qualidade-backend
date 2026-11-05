import re

from django import forms

from .models import Cultura, CULTURA_UI_PRESETS, get_cultura_ui_preset


def color_to_hex(value):
    value = (value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower()
    match = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)", value)
    if match and all(int(channel) <= 255 for channel in match.groups()):
        return "#" + "".join(f"{int(channel):02x}" for channel in match.groups())
    return None


class FarmPolygonExportForm(forms.Form):
    color = forms.ChoiceField(label="Cor de preenchimento")
    opacity = forms.IntegerField(
        label="Opacidade", min_value=0, max_value=100, initial=50,
        help_text="0 = transparente; 100 = totalmente opaco.",
        widget=forms.NumberInput(attrs={"type": "range", "min": 0, "max": 100,
                                       "oninput": "this.nextElementSibling.value = this.value + '%'"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("#facc15", "Amarelo"), ("#35b637", "Verde"),
                   ("#8b4513", "Marrom"), ("#000000", "Preto"), ("#ffffff", "Branco")]
        for name in ("Soja", "Milho", "Arroz", "Feijão"):
            color = color_to_hex(get_cultura_ui_preset(name)["color"]) if name in CULTURA_UI_PRESETS else "#facc15"
            if color:
                choices.append((color, name + " — padrão do sistema"))
        for name in ("Mungo Preto", "Mungo Verde", "Caupi"):
            choices.append((color_to_hex(get_cultura_ui_preset("Feijão", name)["color"]), "Feijão " + name))
        for cultura in Cultura.objects.exclude(map_color__isnull=True).exclude(map_color=""):
            color = color_to_hex(cultura.map_color)
            if color:
                choices.append((color, f"{cultura} — cor cadastrada no mapa"))
        self.fields["color"].choices = choices
        self.fields["color"].initial = "#35b637"
