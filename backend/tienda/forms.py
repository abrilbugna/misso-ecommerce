from django import forms
from .models import OpcionEnvio, TALLES


class PreferenciasSuscripcionForm(forms.Form):
    DESTINOS = [
        ('mismo', 'Para mí'),
        ('regalo', 'Para otra persona, como regalo'),
    ]
    TALLES_SUSCRIPCION = [*TALLES, ('ayuda', 'Necesito ayuda con el talle')]
    TIPOS = [
        ('conjuntos', 'Solo conjuntos armados'),
        ('bombachas', 'Solo packs de bombachas'),
        ('indistinto', 'Me gustan ambos'),
    ]
    ESTILOS = [
        ('clasico', 'Clásico y simple'),
        ('detalles', 'Con encaje o detalles'),
        ('indistinto', 'Me da igual'),
    ]

    destino = forms.ChoiceField(choices=DESTINOS, widget=forms.RadioSelect)
    talle = forms.ChoiceField(choices=TALLES_SUSCRIPCION, required=False, widget=forms.RadioSelect)
    tipo_prenda = forms.ChoiceField(choices=TIPOS, required=False, widget=forms.RadioSelect)
    color_preferido = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'Por ejemplo: negro, blanco o rosa'}),
    )
    color_evitar = forms.CharField(
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'Por ejemplo: verde o amarillo'}),
    )
    estilo = forms.ChoiceField(choices=ESTILOS, required=False, widget=forms.RadioSelect)
    carta = forms.CharField(required=False, max_length=400, widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Escribí un mensaje para incluir en la carta'}))
    comentarios = forms.CharField(
        required=False,
        max_length=400,
        widget=forms.Textarea(attrs={'rows': 4, 'placeholder': 'Contanos cualquier otro detalle que te gustaría que tengamos en cuenta'}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('destino') == 'mismo':
            for field in ('talle', 'tipo_prenda', 'estilo'):
                if not cleaned.get(field):
                    self.add_error(field, 'Elegí una opción para continuar.')
        elif cleaned.get('destino') == 'regalo' and not cleaned.get('talle'):
            self.add_error('talle', 'Elegí un talle para el regalo.')
        return cleaned

class CheckoutForm(forms.Form):
    nombre = forms.CharField(max_length=200, label='Nombre completo')
    email = forms.EmailField(label='Email')
    telefono = forms.CharField(max_length=20, label='Teléfono')
    direccion = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'id': 'direccion'
        }),
        label='Dirección'
    )
    envio = forms.ModelChoiceField(
        queryset=OpcionEnvio.objects.filter(activo=True),
        label='Opción de envío',
        empty_label='Elegí una opción'
    )
    metodo_pago = forms.ChoiceField(
        choices=[
            ('efectivo', 'Efectivo — abonás al retirar'),
            ('transferencia', 'Transferencia bancaria'),
            ('mercadopago', 'MercadoPago — (recargo del 10%)'),
        ],
        label='Método de pago',
        widget=forms.RadioSelect
    )

    def clean_email(self):
        return self.cleaned_data['email']

    def clean_telefono(self):
        telefono = self.cleaned_data['telefono']
        if not telefono.replace('+', '').replace('-', '').replace(' ', '').isdigit():
            raise forms.ValidationError('Ingresá solo números.')
        return telefono
