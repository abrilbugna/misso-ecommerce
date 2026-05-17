from django.contrib import admin
from .models import Producto, Carrito, ItemCarrito, Orden, ItemOrden

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'precio', 'stock', 'activo']
    list_editable = ['precio', 'stock', 'activo']
    search_fields = ['nombre']

@admin.register(Carrito)
class CarritoAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'creado']

@admin.register(ItemCarrito)
class ItemCarritoAdmin(admin.ModelAdmin):
    list_display = ['carrito', 'producto', 'cantidad']

@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ['pk', 'nombre', 'email', 'total', 'pagado', 'creado']
    list_filter = ['pagado']