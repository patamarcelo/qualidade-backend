from django import forms
from .models import PlantioExtratoArea, Programa
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.utils.safestring import mark_safe


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
    def __init__(self, *args, **kwargs):
        super(PlantioExtratoAreaForm, self).__init__(*args, **kwargs)
        print("Custom form loaded!")
        
        # Get the instance safely
        instance = kwargs.get('instance', None)
        
        if instance and instance.data_plantio:
            # Set the date format for existing instances
            self.fields['data_plantio'].initial = instance.data_plantio.strftime('%Y-%m-%d')
        
        # Update widgets here
        # self.fields['data_plantio'].widget.attrs.update({
        #     'class': 'form-control',
        #     'type': 'date',  # HTML5 date input
        # })
    
    
    def clean(self):
        cleaned_data = super().clean()
        plantio = cleaned_data.get('plantio')
        area_plantada_form = cleaned_data.get('area_plantada')
        plantio_finalizado = cleaned_data.get('finalizado_plantio')
        area_plantada_form = area_plantada_form if area_plantada_form is not None else 0
        plantio_add_ativo = cleaned_data.get('ativo')
        if plantio:
            # Access fields from the Plantio model, e.g., area_planejamento_plantio
            area_planejamento = plantio.area_planejamento_plantio
            # print('Area Disponível conforme planejamento: ', area_planejamento)
            
            # print('area Informada: ', area_plantada_form)
            
            # If this is an update (not a new instance), exclude the current instance from the total area calculation
            if self.instance and self.instance.pk:
                total_area = PlantioExtratoArea.objects.filter(plantio=plantio, ativo=True).exclude(pk=self.instance.pk).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )['total_area_plantada'] or 0
            else:
                # For new instances, include all areas
                total_area = PlantioExtratoArea.objects.filter(plantio=plantio, ativo=True).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )['total_area_plantada'] or 0

            # print('Total Area Já Apontada: ', total_area)
            
            # # You can now use this field for validation or other logic
            # if area_planejamento and area_planejamento < 50:
            #     raise ValidationError(
            #         f'The planned planting area (area_planejamento_plantio) is too small: {area_planejamento}.'
            #     )

            area_total_informada = total_area + area_plantada_form
            # print('area total informada: ', area_total_informada)
            # format_area_planejamento = 
            if self.instance.pk and self.instance.ativo and plantio_add_ativo is False:
                # Está desativando agora, então pode ajustar alguma lógica
                print(f'Desativando: removendo {area_plantada_form} da área planejada.')

                # Exemplo: atualizar a área disponível (se aplicável)
                total_area = PlantioExtratoArea.objects.filter(plantio=plantio, ativo=True).exclude(pk=self.instance.pk).aggregate(
                    total_area_plantada=Sum("area_plantada")
                )['total_area_plantada'] or 0
                new_area = total_area if plantio.area_planejamento_plantio >= total_area else plantio.area_planejamento_plantio
                # if total_area > plantio.area_planejamento_plantio:
                #     Adicionar
                plantio.area_colheita = new_area
                plantio.save()
            else:
                # pass
                if area_planejamento < area_total_informada:
                    raise ValidationError(
                        f"Area total disponível:  {str(area_planejamento).replace('.', ',')}, Area total já informada plantada:  ({str(total_area).replace('.', ',')}), Area ainda disponível: {str((area_planejamento - total_area)).replace('.', ',')}"
                    )
                if area_plantada_form == 0 and plantio_finalizado == False:
                    raise ValidationError(
                        f"Area Precisa ser informada, ou Plantio Finalizado precisa ser informado"
                    )

        return cleaned_data

    class Meta:
        model = PlantioExtratoArea
        fields = ['plantio', 'area_plantada', 'aguardando_chuva', 'data_plantio', 'finalizado_plantio']
        
        # Customize widgets for responsiveness
        widgets = {
            'area_plantada': forms.NumberInput(attrs={
                'class': 'form-control',
                'inputmode': 'decimal',  # Number keypad for mobile devices
                'step': '0.01',
                'placeholder': 'Area Plantada',
            }),
            'aguardando_chuva': forms.CheckboxInput(attrs={
                'class': 'form-check-input check-custom',
            }),
            'finalizado_plantio': forms.CheckboxInput(attrs={
                'class': 'form-check-input check-custom',
            }),
            # 'data_plantio': forms.DateInput(attrs={
            #     'class': 'form-control',
            #     'type': 'date',  # HTML5 date input
            # }),
        }
        
    