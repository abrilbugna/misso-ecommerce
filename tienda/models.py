from django.db import models

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
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    activo = models.BooleanField(default=True)
    categoria = models.CharField(max_length=50, choices=CATEGORIAS, default='otros')
    creado = models.DateTimeField(auto_now_add=True)
    destacado = models.BooleanField(default=False)
    imagen = models.ImageField(upload_to='productos/sin_variante/', null=True, blank=True)

    def __str__(self):
        return self.nombre

class Carrito(models.Model):
    session_key = models.CharField(max_length=40)
    creado = models.DateTimeField(auto_now_add=True)

class ItemCarrito(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField(default=1)
    color = models.ForeignKey('ColorProducto', on_delete=models.SET_NULL, null=True, blank=True)
    talle = models.ForeignKey('TalleProducto', on_delete=models.SET_NULL, null=True, blank=True)

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
    color = models.ForeignKey('ColorProducto', on_delete=models.SET_NULL, null=True, blank=True)
    talle = models.ForeignKey('TalleProducto', on_delete=models.SET_NULL, null=True, blank=True)

    def subtotal(self):
        return self.precio * self.cantidad

class ColorProducto(models.Model):
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE, related_name='colores')
    nombre = models.CharField(max_length=50)
    imagen = models.ImageField(upload_to='productos/colores/')

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