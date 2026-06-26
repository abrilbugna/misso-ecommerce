from django.db import models
import cloudinary.models

CATEGORIAS = [
    ('conjuntos armados', 'Conjuntos armados'),
    ('bralettes', 'Bralettes'),
    ('bombachas', 'Bombachas'),
    ('babydoll', 'Babydolls'),
    ('otros', 'Otros'),
]

class OpcionEnvio(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    costo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.nombre} — ${self.costo}'

class Producto(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)
    categoria = models.CharField(max_length=50, choices=CATEGORIAS, default='otros')
    creado = models.DateTimeField(auto_now_add=True)
    destacado = models.BooleanField(default=False)

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

    def __str__(self):
        return f'{self.producto.nombre} — {self.nombre}'

TALLES = [
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

    def subtotal(self):
        return self.producto.precio * self.cantidad

METODOS_PAGO = [
    ('efectivo', 'Efectivo'),
    ('transferencia', 'Transferencia'),
    ('mercadopago', 'MercadoPago'),
]

ESTADOS_ORDEN = [
    ('en_proceso', 'En proceso'),
    ('finalizado', 'Finalizado'),
    ('cancelado', 'Cancelado'),
]

class Orden(models.Model):
    nombre = models.CharField(max_length=200)
    email = models.EmailField()
    telefono = models.CharField(max_length=20)
    direccion = models.TextField()
    total = models.DecimalField(max_digits=10, decimal_places=2)
    envio = models.ForeignKey(OpcionEnvio, on_delete=models.SET_NULL, null=True)
    metodo_pago = models.CharField(max_length=20, choices=METODOS_PAGO, default='efectivo')
    creado = models.DateTimeField(auto_now_add=True)
    pagado = models.BooleanField(default=False)
    estado = models.CharField(max_length=20, choices=ESTADOS_ORDEN, default='en_proceso')

    def __str__(self):
        return f'Orden {self.pk} - {self.nombre}'

class ItemOrden(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    color = models.ForeignKey(ColorProducto, on_delete=models.SET_NULL, null=True, blank=True)
    talle = models.ForeignKey(TalleProducto, on_delete=models.SET_NULL, null=True, blank=True)

    def subtotal(self):
        return self.precio * self.cantidad
