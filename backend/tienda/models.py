from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
import cloudinary.models

CATEGORIA_ROPA_DEPORTIVA = 'ropa-deportiva'

CATEGORIAS = [
    ('conjuntos armados', 'Conjuntos armados'),
    ('bralettes', 'Bralettes'),
    ('bombachas', 'Bombachas'),
    ('babydoll', 'Babydolls'),
    ('otros', 'Otros'),
    (CATEGORIA_ROPA_DEPORTIVA, 'Ropa deportiva'),
]

class OpcionEnvio(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    costo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.nombre} — ${self.costo}'

class CodigoPromocional(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    descuento_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text='Ej: 15 para 15% de descuento')
    descuento_fijo = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text='Monto fijo en pesos')
    activo = models.BooleanField(default=True)
    usos_maximos = models.PositiveIntegerField(null=True, blank=True, help_text='Dejar vacío para usos ilimitados')
    usos_actuales = models.PositiveIntegerField(default=0)
    fecha_expiracion = models.DateField(null=True, blank=True, help_text='Dejar vacío si no expira')

    class Meta:
        verbose_name = 'Código promocional'
        verbose_name_plural = 'Códigos promocionales'

    def __str__(self):
        if self.descuento_porcentaje:
            return f'{self.codigo} ({self.descuento_porcentaje}% off)'
        return f'{self.codigo} (${self.descuento_fijo} off)'

    def es_valido(self):
        from django.utils import timezone
        if not self.activo:
            return False
        if self.usos_maximos and self.usos_actuales >= self.usos_maximos:
            return False
        if self.fecha_expiracion and self.fecha_expiracion < timezone.now().date():
            return False
        return True

    def calcular_descuento(self, total):
        if self.descuento_porcentaje:
            return round(total * self.descuento_porcentaje / 100, 2)
        if self.descuento_fijo:
            return min(self.descuento_fijo, total)
        return 0


class NewsletterContacto(models.Model):
    email = models.EmailField(unique=True)
    consentimiento_comercial = models.BooleanField(default=False)
    consentimiento_fecha = models.DateTimeField()
    activo = models.BooleanField(default=True)
    codigo_promocional = models.OneToOneField(
        CodigoPromocional, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='contacto_newsletter',
    )
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

class Producto(models.Model):
    TIPO_CHOICES = [('individual', 'Producto individual'), ('conjunto', 'Conjunto')]
    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES, default='individual')
    parte_superior = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='conjuntos_superiores')
    parte_inferior = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='conjuntos_inferiores')
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)
    categoria = models.CharField(max_length=50, choices=CATEGORIAS, default='otros')
    creado = models.DateTimeField(auto_now_add=True)
    destacado = models.BooleanField(default=False)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.tipo == 'conjunto':
            if self.pk and (self.conjuntos_superiores.exists() or self.conjuntos_inferiores.exists()):
                raise ValidationError('Esta prenda integra otros conjuntos y debe seguir siendo individual.')
            if not self.parte_superior_id or not self.parte_inferior_id:
                raise ValidationError('Elegí una prenda superior y una inferior.')
            if self.pk and self.pk in (self.parte_superior_id, self.parte_inferior_id):
                raise ValidationError('Un conjunto no puede incluirse a sí mismo.')
            if self.parte_superior_id == self.parte_inferior_id:
                raise ValidationError('Elegí dos prendas diferentes.')
            if self.parte_superior.tipo != 'individual' or self.parte_inferior.tipo != 'individual':
                raise ValidationError('Las partes del conjunto deben ser productos individuales.')
            if self.pk and self.colores.exists():
                raise ValidationError('Un conjunto no puede tener variantes de inventario propias.')
        elif self.parte_superior_id or self.parte_inferior_id:
            raise ValidationError('Solo los conjuntos pueden vincular prendas.')

    def __str__(self):
        return self.nombre

    def imagen_principal(self):
        return self.imagenes.order_by('orden').first()

    def get_imagen_url(self):
        img = self.imagen_principal()
        return img.imagen.url if img else None

class ColorProducto(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='colores')
    nombre = models.CharField(max_length=50)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.producto_id and self.producto.tipo == 'conjunto':
            raise ValidationError('Los conjuntos usan los colores y el stock de sus prendas.')

    def __str__(self):
        return f'{self.producto.nombre} — {self.nombre}'

TALLES = [
    ('XS', 'XS'), ('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL'),
    ('85', '85'),
    ('90', '90'),
    ('95', '95'),
    ('100', '100'),
]

class TalleProducto(models.Model):
    color = models.ForeignKey(ColorProducto, on_delete=models.CASCADE, related_name='talles')
    talle = models.CharField(max_length=10, choices=TALLES)
    stock = models.IntegerField(default=0)

    class Meta:
        unique_together = ('color', 'talle')

    def __str__(self):
        return f'{self.color} — Talle {self.talle} ({self.stock} unid.)'

class ImagenProducto(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='imagenes')
    color = models.ForeignKey(ColorProducto, on_delete=models.SET_NULL, null=True, blank=True, related_name='imagenes')
    imagen = cloudinary.models.CloudinaryField('imagen')
    orden = models.PositiveIntegerField(default=0, help_text='Menor número = aparece primero')

    class Meta:
        ordering = ['orden']

    def __str__(self):
        color_str = f' ({self.color.nombre})' if self.color else ''
        return f'{self.producto.nombre}{color_str} — #{self.orden}'

class VideoProducto(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='videos')
    video = cloudinary.models.CloudinaryField('video', resource_type='video')
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden']

    def __str__(self):
        return f'{self.producto.nombre} — Video #{self.orden}'

class Carrito(models.Model):
    session_key = models.CharField(max_length=40)
    creado = models.DateTimeField(auto_now_add=True)

class ItemCarrito(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField(default=1)
    color = models.ForeignKey(ColorProducto, on_delete=models.SET_NULL, null=True, blank=True)
    talle = models.ForeignKey(TalleProducto, on_delete=models.SET_NULL, null=True, blank=True)
    talle_inferior = models.ForeignKey(TalleProducto, on_delete=models.SET_NULL, null=True, blank=True, related_name='items_carrito_inferiores')

    def subtotal(self):
        return self.producto.precio * self.cantidad

    def imagen_mostrar(self):
        if self.color:
            img = self.producto.imagenes.filter(color=self.color).first()
            if img:
                return img
        return self.producto.imagenes.first()

METODOS_PAGO = [
    ('efectivo', 'Efectivo'),
    ('transferencia', 'Transferencia'),
    ('mercadopago', 'MercadoPago'),
]

ESTADOS_ORDEN = [
    ('en_proceso', 'En proceso'),
    ('confirmado', 'Confirmado'),
    ('en_envio', 'En envío'),
    ('entregado', 'Entregado'),
    ('cancelado', 'Cancelado'),
]

class Orden(models.Model):
    nombre = models.CharField(max_length=200)
    email = models.EmailField()
    telefono = models.CharField(max_length=20)
    direccion = models.TextField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    codigo_promo = models.ForeignKey(CodigoPromocional, on_delete=models.SET_NULL, null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    envio = models.ForeignKey(OpcionEnvio, on_delete=models.SET_NULL, null=True)
    metodo_pago = models.CharField(max_length=20, choices=METODOS_PAGO, default='efectivo')
    creado = models.DateTimeField(auto_now_add=True)
    pagado = models.BooleanField(default=False)
    estado = models.CharField(max_length=20, choices=ESTADOS_ORDEN, default='en_proceso')
    version = models.PositiveIntegerField(default=0, editable=False)
    seguimiento_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    dni_hash = models.CharField(max_length=67, blank=True, default='', editable=False)
    pago_origen = models.CharField(max_length=20, blank=True, editable=False, choices=[
        ('manual', 'Confirmación manual'), ('mercadopago', 'Verificado por Mercado Pago'),
        ('historico', 'Pago histórico (origen no registrado)'),
    ])
    pago_confirmado_at = models.DateTimeField(null=True, blank=True, editable=False)
    mp_payment_id = models.CharField(max_length=100, null=True, blank=True, unique=True, editable=False)
    transportista = models.CharField(max_length=30, blank=True, choices=[
        ('correo_argentino', 'Correo Argentino'), ('retiro', 'Retiro'), ('otro', 'Otro / entrega sin tracking postal'),
    ])
    codigo_seguimiento = models.CharField(max_length=40, blank=True)
    plazo_dias_habiles = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(90)])
    despachado_at = models.DateTimeField(null=True, blank=True, editable=False)
    entregado_at = models.DateTimeField(null=True, blank=True, editable=False)
    finalizado_historico = models.BooleanField(default=False, editable=False)
    emails_iniciales_preexistentes = models.BooleanField(default=False, editable=False)

    def __str__(self):
        return f'Orden {self.pk} - {self.nombre}'


class EmailOrden(models.Model):
    """Durable, immutable delivery attempts; a resend is an explicit new record."""
    orden = models.ForeignKey(Orden, on_delete=models.PROTECT, related_name='emails')
    tipo = models.CharField(max_length=20, choices=[('inicial', 'Pedido recibido'), ('admin', 'Aviso a MISSO'), ('despacho', 'Despacho'), ('acceso', 'Enlace de seguimiento solicitado')])
    secuencia = models.PositiveIntegerField(default=1)
    clave = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payload = models.JSONField(default=dict)
    creado = models.DateTimeField(auto_now_add=True)
    primer_intento_at = models.DateTimeField(null=True, blank=True)
    enviado_at = models.DateTimeField(null=True, blank=True)
    proximo_intento_at = models.DateTimeField(null=True, blank=True)
    retirado_at = models.DateTimeField(null=True, blank=True)
    intentos = models.PositiveIntegerField(default=0)
    proveedor_id = models.CharField(max_length=100, blank=True)
    error = models.CharField(max_length=200, blank=True)
    revision_manual = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['orden', 'tipo', 'secuencia'], name='unique_order_email_sequence')]
        ordering = ['creado', 'pk']

    @property
    def estado_envio(self):
        if self.retirado_at:
            return 'Reemplazado / detenido'
        if self.enviado_at:
            return 'Enviado'
        if self.revision_manual:
            return 'Requiere revisión en Resend'
        if self.error:
            return 'Falló · reintento pendiente'
        return 'Pendiente'


class IntentoSeguimiento(models.Model):
    """Shared rate limits across workers, with no raw IPs or emails stored."""
    clave = models.CharField(max_length=64, unique=True)
    inicio = models.DateTimeField()
    intentos = models.PositiveIntegerField(default=0)

class ItemOrden(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    color = models.ForeignKey(ColorProducto, on_delete=models.SET_NULL, null=True, blank=True)
    talle = models.ForeignKey(TalleProducto, on_delete=models.PROTECT, null=True, blank=True)
    talle_inferior = models.ForeignKey(TalleProducto, on_delete=models.PROTECT, null=True, blank=True, related_name='items_orden_inferiores')
    nombre_historico = models.CharField(max_length=200, blank=True)
    color_historico = models.CharField(max_length=50, blank=True)
    talle_historico = models.CharField(max_length=10, blank=True)
    detalle_superior = models.CharField(max_length=300, blank=True)
    detalle_inferior = models.CharField(max_length=300, blank=True)

    @property
    def nombre_compra(self):
        return self.nombre_historico or self.producto.nombre

    @property
    def color_compra(self):
        return self.color_historico or (self.color.nombre if self.color else 'Sin color')

    @property
    def talle_compra(self):
        return self.talle_historico or (self.talle.talle if self.talle else 'Sin talle')

    def subtotal(self):
        return self.precio * self.cantidad

    def imagen_mostrar(self):
        if self.color:
            img = self.producto.imagenes.filter(color=self.color).first()
            if img:
                return img
        return self.producto.imagenes.first()
# Registered in the same Django app; isolated from the purchase models above.
from .subscription_models import Suscripcion, PagoSuscripcion, EventoMercadoPago, EmailSuscripcion
