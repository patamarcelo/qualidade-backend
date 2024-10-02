from django import forms
from .models import PlantioExtratoArea

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

    class Meta:
        model = PlantioExtratoArea
        fields = ['plantio', 'area_plantada', 'aguardando_chuva', 'data_plantio']
        
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
            # 'data_plantio': forms.DateInput(attrs={
            #     'class': 'form-control',
            #     'type': 'date',  # HTML5 date input
            # }),
        }