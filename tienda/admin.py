from django.contrib import admin
from .models import Producto, Carrito, ItemCarrito, Orden, ItemOrden, OpcionEnvio, ColorProducto, TalleProducto

class TalleProductoInline(admin.TabularInline):
    model = TalleProducto
    extra = 4

class ColorProductoInline(admin.TabularInline):
    model = ColorProducto
    extra = 1
    show_change_link = True

class ItemOrdenInline(admin.TabularInline):
    model = ItemOrden
    extra = 0
    readonly_fields = ['producto', 'color', 'talle', 'cantidad', 'precio']
    can_delete = False

@admin.register(ColorProducto)
class ColorProductoAdmin(admin.ModelAdmin):
    list_display = ['producto', 'nombre']
    list_filter = ['producto']
    inlines = [TalleProductoInline]

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'precio', 'activo', 'destacado', 'categoria']
    list_editable = ['precio', 'activo', 'destacado']
    search_fields = ['nombre']
    list_filter = ['categoria', 'activo', 'destacado']
    fields = ['nombre', 'descripcion', 'precio', 'categoria', 'activo', 'destacado', 'imagen']
    inlines = [ColorProductoInline]

@admin.register(Carrito)
class CarritoAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'creado']

@admin.register(ItemCarrito)
class ItemCarritoAdmin(admin.ModelAdmin):
    list_display = ['carrito', 'producto', 'cantidad', 'color', 'talle']

@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ['pk', 'nombre', 'email', 'total', 'metodo_pago', 'estado', 'pagado', 'creado']
    list_filter = ['estado', 'metodo_pago', 'pagado']
    list_editable = ['estado']
    readonly_fields = ['nombre', 'email', 'telefono', 'direccion', 'total', 'envio', 'metodo_pago', 'creado', 'pagado']
    inlines = [ItemOrdenInline]

@admin.register(OpcionEnvio)
class OpcionEnvioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'costo', 'activo']
    list_editable = ['costo', 'activo']