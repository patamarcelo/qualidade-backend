from django import forms
from .models import PlantioExtratoArea, Programa, Variedade, Plantio, BackgroundTaskStatus, Defensivo
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils.safestring import mark_safe

from django.contrib.admin.widgets import AdminDateWidget
from django.contrib.admin.widgets import AutocompleteSelect
from django.contrib import admin

from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError


from decimal import Decimal

from .models import PlantioExtratoArea
from .utils_new.utils_kml import parse_kml_content


class AdminDateWidgetComOntem(AdminDateWidget):
    template_name = "admin/widgets/data_com_ontem.html"
    

class ProgramaAdminForm(forms.ModelForm):
    duplicar = forms.BooleanField(required=False, label="Duplicar de outro programa?")
    keep_price = forms.BooleanField(required=False, label="Manter o Custo?")
    programa_base = forms.ModelChoiceField(
        queryset=Programa.objects.filter(ativo=True),
        required=False,
        label="Programa base para duplicação"
    )
    class Meta:
        model = Programa
        fields = "__all__"



class PlantioExtratoAreaForm(forms.ModelForm):
    kml_upload = forms.FileField(
        label="Importar KML",
        required=False,
        help_text="Envie um arquivo .kml para salvar e visualizar no admin.",
    )

    class Meta:
        model = PlantioExtratoArea
        fields = [
            "plantio",
            "area_plantada",
            "aguardando_chuva",
            "data_plantio",
            "finalizado_plantio",
            "kml_upload",
        ]
        widgets = {
            "area_plantada": forms.NumberInput(attrs={
                "class": "form-control",
                "inputmode": "decimal",
                "step": "0.01",
                "placeholder": "Area Plantada",
            }),
            "aguardando_chuva": forms.CheckboxInput(attrs={
                "class": "form-check-input check-custom",
            }),
            "finalizado_plantio": forms.CheckboxInput(attrs={
                "class": "form-check-input check-custom",
            }),
            "data_plantio": AdminDateWidgetComOntem(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.data_plantio:
            self.fields["data_plantio"].initial = self.instance.data_plantio.strftime("%Y-%m-%d")

    def clean_kml_upload(self):
        f = self.cleaned_data.get("kml_upload")
        if not f:
            return f

        if not f.name.lower().endswith(".kml"):
            raise ValidationError("Envie um arquivo com extensão .kml")

        return f

    def clean(self):
        cleaned_data = super().clean()

        plantio = cleaned_data.get("plantio")
        area_plantada_form = cleaned_data.get("area_plantada") or 0
        plantio_finalizado = cleaned_data.get("finalizado_plantio")
        plantio_add_ativo = cleaned_data.get("ativo")

        if plantio:
            area_planejamento = plantio.area_planejamento_plantio

            if self.instance and self.instance.pk:
                total_area = PlantioExtratoArea.objects.filter(
                    plantio=plantio,
                    ativo=True
                ).exclude(pk=self.instance.pk).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )["total_area_plantada"] or 0
            else:
                total_area = PlantioExtratoArea.objects.filter(
                    plantio=plantio,
                    ativo=True
                ).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )["total_area_plantada"] or 0

            area_total_informada = total_area + area_plantada_form

            if self.instance.pk and self.instance.ativo and plantio_add_ativo is False:
                total_area = PlantioExtratoArea.objects.filter(
                    plantio=plantio,
                    ativo=True
                ).exclude(pk=self.instance.pk).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )["total_area_plantada"] or 0

                new_area = (
                    total_area
                    if plantio.area_planejamento_plantio >= total_area
                    else plantio.area_planejamento_plantio
                )
                plantio.area_colheita = new_area
                plantio.save()
            else:
                if area_planejamento < area_total_informada:
                    raise ValidationError(
                        f"Area total disponível: {str(area_planejamento).replace('.', ',')}, "
                        f"Area total já informada plantada: ({str(total_area).replace('.', ',')}), "
                        f"Area ainda disponível: {str((area_planejamento - total_area)).replace('.', ',')}"
                    )

                if area_plantada_form == 0 and plantio_finalizado is False:
                    raise ValidationError(
                        "Area precisa ser informada, ou Plantio Finalizado precisa ser informado"
                    )

        return cleaned_data

    def save(self, commit=True):
        obj = super().save(commit=False)

        kml_upload = self.cleaned_data.get("kml_upload")
        if kml_upload:
            raw_content = kml_upload.read().decode("utf-8", errors="ignore")
            parsed = parse_kml_content(raw_content)

            obj.kml_file = kml_upload
            obj.kml_name = kml_upload.name
            obj.kml_content = raw_content
            obj.kml_points = parsed["points"]
            obj.kml_is_closed = parsed["is_closed"]
            obj.kml_area_m2 = Decimal(str(round(parsed["area_m2"], 2)))
            obj.kml_perimeter_m = Decimal(str(round(parsed["perimeter_m"], 2)))

        if commit:
            obj.save()
            self.save_m2m()

        return obj

CLEAR_TOKEN = "__clear__"

class ClearableModelChoiceField(forms.ModelChoiceField):
    """Aceita um token especial para 'limpar' o FK (setar None) sem estourar ValidationError."""
    def clean(self, value):
        # empty_label ('' ou None) continua sendo "sem alteração" → retorna None
        if value in (None, ''):
            return None
        # se veio o token de limpar → retorna None também (mas vamos marcar flag no form)
        if value == CLEAR_TOKEN:
            return None
        # pk normal → valida como sempre
        return super().clean(value)


class UpdateDataPrevistaPlantioForm(forms.Form):
    data_prevista_plantio = forms.DateField(
        widget=forms.TextInput(attrs={'class': 'form-control flatpickr'}),
        input_formats=['%d/%m/%Y'],
        required=False
    )

    # ⬇️ troque para ClearableModelChoiceField
    programa = ClearableModelChoiceField(
        queryset=Programa.objects.filter(ativo=True).order_by('-safra__safra', '-ciclo__ciclo'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="--- (sem alteração) ---"
    )
    variedade = ClearableModelChoiceField(
        queryset=Variedade.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label="--- (sem alteração) ---"
    )

    should_update_on_farm = forms.TypedChoiceField(
        choices=[('false', 'false'), ('true', 'true')],
        coerce=lambda v: v == 'true',
        required=False,
        initial='false',
        widget=forms.HiddenInput
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Insere a opção "Limpar" logo após o empty_label
        prog_choices = list(self.fields['programa'].choices)  # [( '', '--- (sem alteração) ---'), (pk, label), ...]
        var_choices  = list(self.fields['variedade'].choices)

        prog_choices[1:1] = [(CLEAR_TOKEN, "⛔ Limpar Programa")]
        var_choices[1:1]  = [(CLEAR_TOKEN, "⛔ Limpar Variedade")]

        self.fields['programa'].choices = prog_choices
        self.fields['variedade'].choices = var_choices

    def clean(self):
        """Marca flags para distinguir 'sem alteração' (vazio) de 'limpar' (CLEAR_TOKEN)."""
        cleaned = super().clean()
        # O valor bruto do POST:
        raw_prog = self.data.get('programa')
        raw_var  = self.data.get('variedade')

        # flags opcionais para usar na view (se quiser semântica 'não alterar' vs 'limpar')
        cleaned['_clear_programa'] = (raw_prog == CLEAR_TOKEN)
        cleaned['_sent_programa']  = (raw_prog not in (None, ''))  # algo foi escolhido

        cleaned['_clear_variedade'] = (raw_var == CLEAR_TOKEN)
        cleaned['_sent_variedade']  = (raw_var not in (None, ''))

        return cleaned
    
    




class AplicacoesProgramaInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        # se form pai não existe ainda, não valida
        if not self.instance or not getattr(self.instance, "programa_id", None):
            return

        programa_nome = self.instance.programa.nome

        exists_running = BackgroundTaskStatus.objects.filter(
            task_name=programa_nome,
            status__in=["pending", "running"]
        ).exists()

        if exists_running:
            raise ValidationError(
                f"Já existe uma tarefa em andamento para o programa '{programa_nome}'. "
                "Aguarde finalizar para salvar novamente."
            )
            

def _normalizar_nome_produto(nome):
    return " ".join((nome or "").strip().upper().split())


class BulkReplaceAplicacaoForm(forms.Form):
    produto_destino = forms.ModelChoiceField(
        queryset=Defensivo.objects.filter(ativo=True).order_by("produto"),
        label="Novo produto",
        required=True,
        widget=forms.Select(attrs={
            "class": "form-select form-select-sm select-busca-avancada",
            "data-placeholder": "-- Selecione um defensivo --",
        }),
    )

    alterar_dose = forms.BooleanField(
        required=False,
        initial=False,
        label="Alterar dose",
    )

    nova_dose = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=4,
        label="Nova dose",
    )

    zerar_custo = forms.BooleanField(
        required=False,
        initial=False,
        label="Zerar custo",
    )

    def __init__(self, *args, produto_origem=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.produto_origem = produto_origem

        qs = Defensivo.objects.filter(ativo=True).order_by("produto")

        if produto_origem:
            nome_origem_normalizado = _normalizar_nome_produto(produto_origem.produto)

            ids_mesmo_nome_logico = [
                d.pk
                for d in Defensivo.objects.filter(ativo=True).only("id", "produto")
                if _normalizar_nome_produto(d.produto) == nome_origem_normalizado
            ]

            if ids_mesmo_nome_logico:
                qs = qs.exclude(pk__in=ids_mesmo_nome_logico)
            else:
                qs = qs.exclude(pk=produto_origem.pk)

        self.fields["produto_destino"].queryset = qs

    def clean(self):
        cleaned = super().clean()

        produto_destino = cleaned.get("produto_destino")
        alterar_dose = cleaned.get("alterar_dose")
        nova_dose = cleaned.get("nova_dose")

        if not produto_destino:
            raise forms.ValidationError("Selecione o novo produto.")

        if self.produto_origem:
            origem_nome = _normalizar_nome_produto(self.produto_origem.produto)
            destino_nome = _normalizar_nome_produto(produto_destino.produto)

            if origem_nome == destino_nome:
                raise forms.ValidationError(
                    "O novo produto deve ser diferente do produto origem."
                )

        if alterar_dose and nova_dose in [None, ""]:
            self.add_error("nova_dose", "Informe a nova dose para alterar em lote.")

        return cleaned