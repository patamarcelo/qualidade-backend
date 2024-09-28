from django import forms
from .models import PlantioExtratoArea

class PlantioExtratoAreaForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PlantioExtratoAreaForm, self).__init__(*args, **kwargs)
        print("Custom form loaded!")
    
    class Meta:
        model = PlantioExtratoArea
        fields = ['plantio', 'area_plantada', 'aguardando_chuva', 'data_plantio']
        
        # Customize widgets for responsiveness
        widgets = {
            # 'plantio': forms.Select(attrs={
            #     'class': 'form-control',  # Admin LTE supports Bootstrap
            # }),
            'area_plantada': forms.NumberInput(attrs={
                'class': 'form-control',
                'inputmode': 'decimal',  # Number keypad for mobile devices
                'step': '0.01',
                'placeholder': 'Area Plantada',
            }),
            'aguardando_chuva': forms.CheckboxInput(attrs={
                'class': 'form-check-input check-custom',
            }),
            'data_plantio': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',  # HTML5 date input
            }),
        }