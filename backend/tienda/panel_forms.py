"""Backoffice forms. All business validation runs on the server."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.forms import BaseInlineFormSet, inlineformset_factory
from .models import (Producto, ColorProducto, TalleProducto, ImagenProducto,
                     VideoProducto, Orden, CodigoPromocional, OpcionEnvio)

LOW_STOCK_LIMIT = 2


class PanelLoginForm(AuthenticationForm):
    username = forms.CharField(label='Usuario o email', widget=forms.TextInput(attrs={'autocomplete': 'username', 'autofocus': True}))

    def clean(self):
        value = self.cleaned_data.get('username', '')
        User = get_user_model()
        # Exact usernames take precedence; ambiguous emails are never guessed.
        if not User.objects.filter(username=value).exists():
            matches = list(User.objects.filter(email__iexact=value).values_list('username', flat=True)[:2])
            if len(matches) == 1:
                self.cleaned_data['username'] = matches[0]
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError('Esta cuenta no tiene acceso al panel.', code='invalid_login')


class ProductoForm(forms.ModelForm):
    precio = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, label='Precio')

    class Meta:
        model = Producto
        fields = ['nombre', 'descripcion', 'precio', 'categoria', 'activo', 'destacado']
        labels = {'descripcion': 'Descripción', 'categoria': 'Categoría'}
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 4})}


class ColorForm(forms.ModelForm):
    class Meta:
        model = ColorProducto
        fields = ['nombre']
        labels = {'nombre': 'Color'}

    def clean_nombre(self):
        name = self.cleaned_data['nombre'].strip()
        if self.instance.pk and name != self.instance.nombre:
            if self.instance.itemorden_set.exists() or TalleProducto.objects.filter(color=self.instance, itemorden__isnull=False).exists():
                raise forms.ValidationError('Este color está utilizado en pedidos. Conservá su nombre histórico y agregá otro color.')
        return name


class TalleForm(forms.ModelForm):
    stock = forms.IntegerField(min_value=0, label='Stock')

    class Meta:
        model = TalleProducto
        fields = ['talle', 'stock']

    def clean_talle(self):
        value = self.cleaned_data['talle']
        if self.instance.pk and value != self.instance.talle and self.instance.itemorden_set.exists():
            raise forms.ValidationError('Este talle está utilizado en pedidos. Agregá una variante nueva.')
        return value


class ScopedInlineFormSet(BaseInlineFormSet):
    """Reject substituted IDs and omitted existing rows, including forged management data."""
    def clean(self):
        super().clean()
        expected = set(self.get_queryset().values_list('pk', flat=True))
        received = []
        for index, form in enumerate(self.forms):
            obj = form.cleaned_data.get('id') if hasattr(form, 'cleaned_data') else None
            if obj:
                received.append(obj.pk)
                if index >= self.initial_form_count():
                    raise forms.ValidationError('Una fila nueva no puede reutilizar un registro existente.')
        if (set(received) != expected or len(received) != len(expected)
                or self.initial_form_count() != len(expected)):
            raise forms.ValidationError('La información cambió o contiene registros ajenos. Recargá la ficha antes de guardar.')


class ColorFormSetBase(ScopedInlineFormSet):
    def clean(self):
        super().clean()
        seen = set()
        for form in self.forms:
            name = form.cleaned_data.get('nombre', '').casefold()
            if name and name in seen:
                raise forms.ValidationError('No repitas el mismo color dentro del producto.')
            seen.add(name)


class MediaFormMixin:
    media_field = ''
    max_size = 0
    allowed_types = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_media = getattr(self.instance, self.media_field, None)
        self.initial[self.media_field] = None

    def clean(self):
        cleaned = super().clean()
        upload = cleaned.get(self.media_field)
        if not upload and not self.instance.pk and not cleaned.get('DELETE') and self.media_field not in self.errors:
            self.add_error(self.media_field, 'Seleccioná un archivo.')
        if upload:
            if upload.size > self.max_size:
                self.add_error(self.media_field, f'El archivo supera los {self.max_size // (1024 * 1024)} MB.')
            if upload.content_type not in self.allowed_types:
                self.add_error(self.media_field, 'Este formato de archivo no está permitido.')
        elif self.instance.pk:
            cleaned[self.media_field] = self.original_media
        return cleaned


class ImagenForm(MediaFormMixin, forms.ModelForm):
    # Plain file fields defer Cloudinary upload until every formset is valid.
    imagen = forms.ImageField(required=False, label='Archivo de imagen', widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp,image/gif', 'data-preview': 'image'}))
    color_ref = forms.ChoiceField(required=False, label='Color (opcional)')
    media_field = 'imagen'
    max_size = 10 * 1024 * 1024
    allowed_types = ('image/jpeg', 'image/png', 'image/webp', 'image/gif')

    class Meta:
        model = ImagenProducto
        fields = ['imagen', 'orden']

    def __init__(self, *args, color_choices=(), color_refs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['color_ref'].choices = [('', 'General · todos los colores'), *color_choices]
        if self.instance.pk:
            self.initial['color_ref'] = (color_refs or {}).get(self.instance.color_id, '')
        self.order_fields(['imagen', 'color_ref', 'orden'])


class VideoForm(MediaFormMixin, forms.ModelForm):
    video = forms.FileField(required=False, label='Archivo de video', widget=forms.FileInput(attrs={'accept': 'video/mp4,video/quicktime,video/webm', 'data-preview': 'video'}))
    media_field = 'video'
    max_size = 50 * 1024 * 1024
    allowed_types = ('video/mp4', 'video/quicktime', 'video/webm')

    class Meta:
        model = VideoProducto
        fields = ['video', 'orden']


ColorFormSet = inlineformset_factory(Producto, ColorProducto, form=ColorForm, formset=ColorFormSetBase, extra=0, can_delete=False, max_num=50, validate_max=True, absolute_max=60)
TalleFormSet = inlineformset_factory(ColorProducto, TalleProducto, form=TalleForm, formset=ScopedInlineFormSet, extra=0, can_delete=False, max_num=4, validate_max=True, absolute_max=8)
ImagenFormSet = inlineformset_factory(Producto, ImagenProducto, form=ImagenForm, formset=ScopedInlineFormSet, extra=0, can_delete=True, max_num=50, validate_max=True, absolute_max=60)
VideoFormSet = inlineformset_factory(Producto, VideoProducto, form=VideoForm, formset=ScopedInlineFormSet, extra=0, can_delete=True, max_num=20, validate_max=True, absolute_max=25)


class ConfirmChangesForm(forms.Form):
    confirm_delete = forms.BooleanField(required=False, label='Confirmo quitar los archivos marcados de este producto.')
    revision = forms.CharField(widget=forms.HiddenInput)


class OrdenForm(forms.ModelForm):
    confirmar = forms.BooleanField(label='Confirmo el estado y la condición de pago de este pedido.')
    revision = forms.CharField(widget=forms.HiddenInput)

    class Meta:
        model = Orden
        fields = ['estado', 'pagado']


class PromocionForm(forms.ModelForm):
    class Meta:
        model = CodigoPromocional
        fields = ['codigo', 'descuento_porcentaje', 'descuento_fijo', 'activo', 'usos_maximos', 'fecha_expiracion']
        labels = {'codigo': 'Código', 'descuento_porcentaje': 'Descuento (%)', 'descuento_fijo': 'Descuento fijo', 'usos_maximos': 'Usos máximos', 'fecha_expiracion': 'Expiración'}
        widgets = {'fecha_expiracion': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})}

    def clean_codigo(self):
        code = self.cleaned_data['codigo'].strip().upper()
        if CodigoPromocional.objects.filter(codigo__iexact=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ya existe un código con este nombre.')
        return code

    def clean(self):
        data = super().clean()
        pct, fixed = data.get('descuento_porcentaje'), data.get('descuento_fijo')
        if (pct is None) == (fixed is None):
            raise forms.ValidationError('Elegí exactamente un descuento: porcentaje o monto fijo.')
        if pct is not None and not 0 < pct <= 100:
            self.add_error('descuento_porcentaje', 'Ingresá un porcentaje mayor que 0 y hasta 100.')
        if fixed is not None and fixed <= 0:
            self.add_error('descuento_fijo', 'El descuento debe ser mayor que cero.')
        limit = data.get('usos_maximos')
        if limit is not None and (limit < 1 or limit < self.instance.usos_actuales):
            self.add_error('usos_maximos', 'Debe ser positivo y no menor que los usos actuales.')
        return data


class EnvioForm(forms.ModelForm):
    costo = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0, label='Costo')

    class Meta:
        model = OpcionEnvio
        fields = ['nombre', 'descripcion', 'costo', 'activo']
        labels = {'descripcion': 'Descripción'}
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 3})}


class ProductoFilterForm(forms.Form):
    q = forms.CharField(required=False, label='Buscar producto')
    activo = forms.ChoiceField(required=False, choices=[('', 'Todos'), ('1', 'Activos'), ('0', 'Inactivos')], label='Disponibilidad')
    categoria = forms.ChoiceField(required=False, choices=[('', 'Todas'), *Producto._meta.get_field('categoria').choices], label='Categoría')
    destacado = forms.ChoiceField(required=False, choices=[('', 'Todos'), ('1', 'Destacados'), ('0', 'No destacados')], label='Destacados')
    stock = forms.ChoiceField(required=False, choices=[('', 'Todo el inventario'), ('zero', 'Sin stock'), ('low', 'Con stock bajo'), ('available', 'Con stock'), ('unconfigured', 'Sin variantes')], label='Stock')


class OrdenFilterForm(forms.Form):
    q = forms.CharField(required=False, label='Nombre, email, teléfono o ID')
    estado = forms.ChoiceField(required=False, choices=[('', 'Todos'), *Orden._meta.get_field('estado').choices], label='Estado')
    pagado = forms.ChoiceField(required=False, choices=[('', 'Todos'), ('1', 'Pagados'), ('0', 'Pendientes')], label='Pago')
    metodo_pago = forms.ChoiceField(required=False, choices=[('', 'Todos'), *Orden._meta.get_field('metodo_pago').choices], label='Método de pago')
    desde = forms.DateField(required=False, label='Desde', widget=forms.DateInput(attrs={'type': 'date'}))
    hasta = forms.DateField(required=False, label='Hasta', widget=forms.DateInput(attrs={'type': 'date'}))

    def clean(self):
        data = super().clean()
        if data.get('desde') and data.get('hasta') and data['desde'] > data['hasta']:
            raise forms.ValidationError('La fecha inicial debe ser anterior a la final.')
        return data
