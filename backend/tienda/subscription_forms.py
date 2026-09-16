from django import forms
from .forms import PreferenciasSuscripcionForm
from .models import Suscripcion

# Labels are copied from the existing template, not inferred from field names.
PREGUNTAS = {
    'destino': '¿Para quién es la suscripción?',
    'talle': '¿Qué talle usa?',
    'tipo_prenda': '¿Qué preferís recibir?',
    'color_preferido': '¿Hay algún color que te guste más?',
    'color_evitar': '¿Hay algún color que no quieras recibir?',
    'estilo': '¿Qué estilo te gusta?',
    'carta': '¿Querés sumar una carta?',
    'comentarios': '¿Algo más que quieras contarnos?',
}


class SuscripcionForm(PreferenciasSuscripcionForm):
    nombre = forms.CharField(max_length=200, label='Nombre completo', widget=forms.TextInput(attrs={'autocomplete': 'name'}))
    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    telefono = forms.CharField(max_length=30, label='Teléfono', widget=forms.TextInput(attrs={'autocomplete': 'tel', 'inputmode': 'tel'}))
    terminos_aceptados = forms.BooleanField(required=True, label='Leí y acepto los Términos y Condiciones de Misso', error_messages={'required': 'Aceptá los Términos y Condiciones para continuar.'})
    submission_token = forms.CharField(widget=forms.HiddenInput)

    def clean_telefono(self):
        value = self.cleaned_data['telefono']
        digits = ''.join(c for c in value if c.isdigit())
        if not 7 <= len(digits) <= 20 or any(c not in '0123456789 +()-' for c in value):
            raise forms.ValidationError('Ingresá un teléfono válido.')
        return value

    def snapshot(self):
        fields = []
        for key in [*PREGUNTAS, 'nombre', 'email', 'telefono']:
            field = self.fields[key]
            value = self.cleaned_data[key]
            choices = dict(getattr(field, 'choices', []))
            label = choices.get(value, value) if not isinstance(value, list) else [choices.get(v, v) for v in value]
            fields.append({'campo': key, 'pregunta': PREGUNTAS.get(key, field.label), 'valor': value, 'respuesta': label or 'Sin respuesta'})
        return {'version': 1, 'campos': fields}


class SuscripcionFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=200, label='Buscar')
    estado = forms.ChoiceField(required=False, choices=[('', 'Todos'), *Suscripcion.Estado.choices])
    desde = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hasta = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
