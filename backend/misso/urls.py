from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from tienda import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.inicio, name='inicio'),
    path('suscripcion/comenzar/', views.comenzar_suscripcion, name='comenzar_suscripcion'),
    path('suscripcion/', views.informacion_suscripcion, name='informacion_suscripcion'),
    path('tienda/', include('tienda.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) \
  + static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
