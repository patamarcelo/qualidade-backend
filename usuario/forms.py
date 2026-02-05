from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

from .models import CustomUsuario


class CustomUsuarioCreationForm(UserCreationForm):
    email = forms.EmailField(label="E-mail", required=True)

    class Meta:
        model = CustomUsuario
        fields = ("email", "origin_app", "first_name", "last_name", "fone")

    def save(self, commit=True):
        user = super().save(commit=False)

        # garante consistência com AbstractUser.username UNIQUE
        user.email = (self.cleaned_data.get("email") or "").strip().lower()
        user.username = user.email

        # password já é setada pelo UserCreationForm via password1/password2
        if commit:
            user.save()
        return user


class CustomUsuarioChangeForm(UserChangeForm):
    class Meta:
        model = CustomUsuario
        fields = "__all__"
