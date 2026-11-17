# catalog-sync

Descarga una vez por semana los catálogos de los supermercados de Cuenca y publica un fichero
por cadena más un índice. La app los baja y busca en local.

| Cadena | Origen | Notas |
|---|---|---|
| Mercadona | API de su tienda online | Almacén 4606 (el de Cuenca) |
| Ahorramás | Rejilla de productos de su web | Una petición por página de 48 productos |
| Lidl | Servicio de catálogo de la app Lidl Plus | Tienda ES0573 (Cuenca). Servicio interno: puede cambiar sin aviso |

Carrefour y Dia bloquean las descargas automáticas y no se sincronizan aquí.

## Uso

```sh
python3 -m unittest discover -s tests -t .     # tests (sin red)
python3 run.py --out /tmp/catalogo --limit 1   # prueba rápida real
python3 run.py --out /tmp/catalogo             # pasada completa
./publish.sh                                    # pasada completa + subida a la rama `catalog` (desde tu Mac)
```

Solo usa la biblioteca estándar de Python (3.9 o superior).

## Salida

- `<cadena>.json.gz`: `{schema, store, syncedAt, products[]}`. Cada producto lleva `id`, `name`,
  `price`, `brand`, `size`, `unitPrice`, `unitLabel`, `image`, `cat`, `sub` y `catOrder`.
- `index.json`: por cadena, `name`, `file`, `count`, `syncedAt`, `sha256` y `stale`.

URL pública: `https://raw.githubusercontent.com/miguelmg4/MiVanApp-releases/catalog/index.json`

## Cuando una cadena falla

Si la descarga falla, viene vacía o trae menos de la mitad de productos que la vez anterior, se
conserva el fichero anterior y el índice marca esa cadena con `stale: true`. Las demás se publican
con normalidad. El comando solo devuelve error si fallan todas.

## Añadir una cadena

Crea `sync/stores/<cadena>.py` con funciones puras de parseo y un `fetch(http, limit=None)` que
devuelva una lista de `Product`, añade sus tests con respuestas guardadas en `tests/fixtures/` y
regístrala en `STORES` dentro de `run.py`.

## Actualización semanal

El flujo `.github/workflows/catalog-sync.yml` de este repositorio lo ejecuta cada lunes a las 05:00 UTC
y publica en la rama `catalog` con el permiso de escritura que GitHub da al propio repositorio.
Se puede lanzar a mano desde la pestaña Actions («Run workflow»).

Si algún supermercado no se actualiza, la ejecución termina en error después de publicar los demás
y GitHub manda un correo. Si todo va bien no llega ningún aviso.
