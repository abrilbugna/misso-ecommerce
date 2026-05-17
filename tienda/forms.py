from django import forms

class CheckoutForm(forms.Form):
    nombre = forms.CharField(max_length=200, label='Nombre completo')
    email = forms.EmailField(label='Email')
    telefono = forms.CharField(max_length=20, label='Teléfono')
    direccion = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), label='Dirección')