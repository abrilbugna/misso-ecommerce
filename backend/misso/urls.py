from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from tienda import views, subscription_views

urlpatterns = [
    path('panel/', include('tienda.panel_urls')),
    path('admin/', admin.site.urls),
    path('', views.inicio, name='inicio'),
    path('suscripcion/comenzar/', subscription_views.comenzar, name='comenzar_suscripcion'),
    path('suscripcion/resultado/<uuid:referencia>/', subscription_views.resultado, name='suscripcion_resultado'),
    path('suscripcion/resultado/<uuid:referencia>/estado/', subscription_views.estado, name='suscripcion_estado'),
    path('mercadopago/webhooks/subscriptions/', subscription_views.webhook, name='suscripciones_webhook'),
    path('suscripcion/', views.informacion_suscripcion, name='informacion_suscripcion'),
    path('tienda/', include('tienda.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) \
  + static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
