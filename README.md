# Misso — tienda online

El proyecto usa Django. El backend consulta la base de datos y genera las páginas del frontend a partir de plantillas HTML. Ambos se ejecutan con el mismo servidor; no hace falta iniciar un servidor de frontend separado.

## Dónde va cada cosa

```text
misso-ecommerce/
├── frontend/                 # Todo lo que se muestra en el navegador
│   ├── templates/tienda/     # Páginas HTML con etiquetas de Django
│   │   └── base.html         # Estructura común: navegación y pie de página
│   └── static/
│       ├── css/              # Estilos: base.css y un archivo por página
│       ├── js/               # Interacciones: menú, producto, carrito y checkout
│       ├── images/           # Imágenes propias del sitio
│       └── fonts/            # Tipografías
├── backend/
│   ├── misso/                # Configuración general de Django
│   │   ├── settings.py       # Base de datos, plantillas, servicios y variables
│   │   ├── urls.py           # Rutas principales
│   │   ├── wsgi.py           # Entrada del servidor de producción
│   │   └── asgi.py           # Entrada para servidores ASGI
│   └── tienda/               # Funcionalidad del ecommerce
│       ├── models.py         # Productos, carrito, pedidos, talles y descuentos
│       ├── views.py          # Procesamiento de las solicitudes y pagos
│       ├── urls.py           # Direcciones de las páginas de la tienda
│       ├── forms.py          # Formulario de checkout y validación
│       ├── admin.py          # Panel de administración
│       ├── context_processors.py # Cantidad del carrito disponible en HTML
│       ├── email_utils.py    # Envío de correos y contenido de comprobantes
│       ├── migrations/       # Historial de cambios de la base de datos
│       └── tests.py          # Lugar para pruebas del backend
├── docs/                     # Guías de desarrollo
├── manage.py                 # Comandos de Django desde la raíz
├── requirements.txt          # Dependencias de Python
└── .env.example              # Ejemplo de configuración local
```

## Ejecutar en desarrollo

Usar Python 3.12 o superior y ejecutar desde la raíz del proyecto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Editar `.env` antes de iniciar. El sitio estará en http://127.0.0.1:8000/ y la administración en http://127.0.0.1:8000/admin/. Sin `DATABASE_URL` se usa `db.sqlite3` en la raíz. Las imágenes de productos usan Cloudinary; pagos, correos y mapas necesitan las credenciales del servicio correspondiente.

## Verificar y desplegar

```bash
python manage.py check
python manage.py test
python manage.py collectstatic --noinput
```

`tests.py` todavía no contiene pruebas funcionales. `check` comprueba la configuración, pero no valida compras ni integraciones externas.

**La carpeta del backend cambió.** En Render u otro servidor, mantener la raíz del repositorio como directorio de trabajo y actualizar el comando de inicio a:

```bash
gunicorn --chdir backend misso.wsgi:application
```

Para un servidor ASGI, agregar igualmente `backend/` al path de Python y usar `misso.asgi:application`. Las dependencias y `manage.py` siguen en la raíz. La base de datos local y la salida `staticfiles/` conservan su ubicación. En producción, configurar las variables en el proveedor, usar una clave secreta propia y `DEBUG=False`.

Ver [la guía de organización](docs/ESTRUCTURA.md) para saber qué archivos editar según el cambio.
