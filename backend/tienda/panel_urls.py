from django.urls import path
from . import panel_views as views, subscription_panel

app_name = 'panel'
urlpatterns = [
    path('suscripciones/', subscription_panel.listado, name='suscripciones'),
    path('suscripciones/<int:pk>/', subscription_panel.detalle, name='suscripcion_detalle'),
    path('login/', views.PanelLoginView.as_view(), name='login'),
    path('logout/', views.cerrar_sesion, name='logout'),
    path('', views.inicio, name='inicio'),
    path('productos/', views.productos, name='productos'),
    path('productos/nuevo/', views.producto_editar, name='producto_nuevo'),
    path('productos/<int:pk>/', views.producto_editar, name='producto_editar'),
    path('pedidos/', views.pedidos, name='pedidos'),
    path('pedidos/<int:pk>/', views.pedido_editar, name='pedido_editar'),
    path('promociones/', views.promociones, name='promociones'),
    path('promociones/nuevo/', views.promocion_editar, name='promocion_nueva'),
    path('promociones/<int:pk>/', views.promocion_editar, name='promocion_editar'),
    path('envios/', views.envios, name='envios'),
    path('envios/nuevo/', views.envio_editar, name='envio_nuevo'),
    path('envios/<int:pk>/', views.envio_editar, name='envio_editar'),
]
