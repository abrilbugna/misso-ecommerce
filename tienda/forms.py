from django import forms
from .models import OpcionEnvio

class CheckoutForm(forms.Form):
    nombre = forms.CharField(max_length=200, label='Nombre completo')
    email = forms.EmailField(label='Email')
    telefono = forms.CharField(max_length=20, label='Teléfono')
    direccion = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), label='Dirección')
    envio = forms.ModelChoiceField(
        queryset=OpcionEnvio.objects.filter(activo=True),
        label='Opción de envío',
        empty_label='Elegí una opción'
    )
    metodo_pago = forms.ChoiceField(
        choices=[
            ('efectivo', 'Efectivo — abonás al retirar'),
            ('transferencia', 'Transferencia bancaria'),
            ('mercadopago', 'MercadoPago'),
        ],
        label='Método de pago',
        widget=forms.RadioSelect
    )