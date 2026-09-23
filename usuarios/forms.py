from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Usuario
from django.contrib.auth.forms import PasswordResetForm


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'placeholder': 'tucorreo@ejemplo.com',
            'class': 'form-input'
        })
    )
    password = forms.CharField(
        label='Contraseña',
        widget=forms.PasswordInput(attrs={
            'placeholder': '••••••••',
            'class': 'form-input'
        })
    )

class RegistroForm(UserCreationForm):
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={
            'placeholder': 'tucorreo@ejemplo.com',
            'class': 'form-input'
        })
    )
    first_name = forms.CharField(
        label='Nombre completo',
        widget=forms.TextInput(attrs={
            'placeholder': 'Tu nombre completo',
            'class': 'form-input'
        })
    )
    telefono = forms.CharField(
        label='Teléfono',
        widget=forms.TextInput(attrs={
            'placeholder': '+57 300 000 0000',
            'class': 'form-input'
        })
    )
    acepta_tratamiento_datos = forms.BooleanField(
        required=True,
        label='Autorizo el tratamiento de mis datos personales',
        error_messages={
            'required': 'Debes autorizar el tratamiento de datos para crear tu cuenta.'
        },
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
    )

    class Meta:
        model = Usuario
        fields = ['first_name', 'email', 'telefono', 'password1', 'password2', 'acepta_tratamiento_datos']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Usuario.objects.filter(username=email).exists():
            raise forms.ValidationError('Ese correo ya tiene una cuenta asociada. Intenta iniciar sesión.')
        return email

class EditarPerfilForm(forms.ModelForm):
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-input'})
    )
    telefono = forms.CharField(
        label='Teléfono',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-input'})
    )

    class Meta:
        model = Usuario
        fields = ['first_name', 'email', 'telefono']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
        }
        labels = {
            'first_name': 'Nombre completo',
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Usuario.objects.exclude(pk=self.instance.pk).filter(username=email).exists():
            raise forms.ValidationError('Ese correo ya tiene una cuenta asociada.')
        return email


class CustomPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not Usuario.objects.filter(email=email).exists():
            raise forms.ValidationError('Ese correo no está registrado en Mimada.')
        return email