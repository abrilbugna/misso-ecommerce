from django.db import models

CATEGORIAS = [
    ('conjuntos', 'Conjuntos'),
    ('bralettes', 'Bralettes'),
    ('bombachas', 'Bombachas'),
    ('accesorios', 'Accesorios'),
    ('otros', 'Otros'),
]

class Producto(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    imagen = models.ImageField(upload_to='productos/')
    stock = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)
    categoria = models.CharField(max_length=50, choices=CATEGORIAS, default='otros')
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

class Carrito(models.Model):
    session_key = models.CharField(max_length=40)
    creado = models.DateTimeField(auto_now_add=True)

class ItemCarrito(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField(default=1)

    def subtotal(self):
        return self.producto.precio * self.cantidad

class Orden(models.Model):
    nombre = models.CharField(max_length=200)
    email = models.EmailField()
    telefono = models.CharField(max_length=20)
    direccion = models.TextField()
    total = models.DecimalField(max_digits=10, decimal_places=2)
    creado = models.DateTimeField(auto_now_add=True)
    pagado = models.BooleanField(default=False)

    def __str__(self):
        return f'Orden {self.pk} - {self.nombre}'

class ItemOrden(models.Model):
    orden = models.ForeignKey(Orden, on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)

    def subtotal(self):
        return self.precio * self.cantidad