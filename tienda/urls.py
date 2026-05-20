from django.urls import path
from . import views

urlpatterns = [
    path('', views.catalogo, name='catalogo'),
    path('<int:pk>/', views.detalle, name='detalle'),
    path('agregar/<int:pk>/', views.agregar_carrito, name='agregar_carrito'),
    path('carrito/', views.ver_carrito, name='ver_carrito'),
    path('carrito/eliminar/<int:pk>/', views.eliminar_carrito, name='eliminar_carrito'),
    path('checkout/', views.checkout, name='checkout'),
    path('confirmacion/<int:pk>/', views.confirmacion, name='confirmacion'),
    path('confirmacion/transferencia/<int:pk>/', views.confirmacion_transferencia, name='confirmacion_transferencia'),
    path('pago/mp/<int:pk>/', views.pago_mp, name='pago_mp'),
]