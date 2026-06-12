from django.contrib import admin
from .models import Producto, Carrito, ItemCarrito, Orden, ItemOrden, OpcionEnvio, ColorProducto, TalleProducto

class TalleProductoInline(admin.TabularInline):
    model = TalleProducto
    extra = 4

class ColorProductoInline(admin.StackedInline):
    model = ColorProducto
    extra = 1
    inlines = [TalleProductoInline]
    show_change_link = True

@admin.register(ColorProducto)
class ColorProductoAdmin(admin.ModelAdmin):
    list_display = ['producto', 'nombre']
    inlines = [TalleProductoInline]

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'precio', 'activo', 'destacado', 'categoria']
    list_editable = ['precio', 'activo', 'destacado']
    search_fields = ['nombre']
    list_filter = ['categoria', 'activo', 'destacado']
    inlines = [ColorProductoInline]

@admin.register(Carrito)
class CarritoAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'creado']

@admin.register(ItemCarrito)
class ItemCarritoAdmin(admin.ModelAdmin):
    list_display = ['carrito', 'producto', 'cantidad', 'color', 'talle']

@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ['pk', 'nombre', 'email', 'total', 'pagado', 'creado']
    list_filter = ['pagado']

@admin.register(OpcionEnvio)
class OpcionEnvioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'costo', 'activo']
    list_editable = ['costo', 'activo']
