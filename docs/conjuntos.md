# Conjuntos y stock compartido

Crear el top y el short como productos individuales, cada uno con colores,
talles y stock. En un producto nuevo seleccionar «Conjunto», vincular ambas
prendas y cargar su precio e imágenes. Los nombres de color deben coincidir
en ambas prendas (sin distinguir mayúsculas). Cada parte puede usar sus propios
talles. El conjunto no lleva variantes de inventario propias.

## Migraciones necesarias

Antes de servir este código, la base elegida debe tener aplicadas 0022, 0023
y 0024. La última conserva nombres, colores y talles históricos; no elimina
registros. `showmigrations tienda --plan` permite consultar el estado sin
modificar datos. Aplicarlas requiere autorización si la base es producción.

Que `runserver` atienda en 127.0.0.1 no implica que la base sea local:
`DATABASE_URL` en `.env` puede seguir apuntando a Supabase. El error
«column tienda_producto.tipo does not exist» significa que ese esquema aún
no tiene la migración 0022.

## Pruebas aisladas

SQLite:

```sh
.venv/bin/python manage.py test tienda.test_conjuntos tienda.test_panel tienda.test_order_management tienda.test_order_tracking tienda.test_public_storefront.PublicStorefrontTests --settings=misso.test_settings
```

Con un servidor PostgreSQL descartable local, configurar
`MISSO_TEST_DATABASE_URL=postgresql://usuario@127.0.0.1:puerto/misso_test_review`
y ejecutar el mismo comando con `--settings=misso.postgres_test_settings`.
Esta configuración rechaza destinos remotos y nombres sin el prefijo
`misso_test_`. Django crea y destruye la base de pruebas.

El checkout bloquea los productos y las variantes físicas en orden estable,
agrupa sus cantidades y confirma todo en una transacción. Los bloqueos de
carrito se limitan a su propia tabla para admitir las relaciones opcionales
en PostgreSQL. La prueba concurrente en PostgreSQL exige un pedido exitoso
y un rechazo cuando dos compras intentan consumir la última unidad.
