# TomBot — Plan

Qué se decidió y por qué, en qué se desvió el proyecto de la especificación original
y qué queda por hacer. Cómo funciona hoy está en [`README.md`](README.md).

_Última revisión: 2026-10-11. Fuentes: `schema.sql`, `docker-compose.yml`,
`.env.example`, la lista de archivos versionados, el historial de git hasta
`8136c83` y la especificación original (PDF, borrada en `d52373f` por obsoleta)._

## 1. Principios que se mantienen

Vienen de la especificación original y siguen valiendo:

- Aplicación personal, de un solo usuario, sin autenticación de usuarios (hay un
  token opcional para cuando se expone en la LAN).
- **La colección del usuario es la fuente de verdad** de lo que se posee. El
  catálogo externo no define la estructura de colección.
- **Catálogo, meta de colección, colección y precio son cosas separadas.** Un
  reimport del catálogo no puede destruir registros de colección.
- Las variantes físicas se conservan en el inventario pero **no crean cartas
  lógicas distintas** para la completitud.
- Todo el acceso a SQLite pasa por `PokemonRepo`.
- Las imágenes viven en el filesystem, no en SQLite.
- Los precios son estimaciones, no una valoración garantizada.
- Sin OCR ni reconocimiento automático de cartas: la identificación es manual.
- Se usa cómodamente desde el teléfono; subir fotos desde el móvil es un caso
  prioritario.

## 2. Desviaciones respecto de la especificación original

| Tema | Especificación (PDF) | Hoy | Motivo |
| --- | --- | --- | --- |
| Fuente de catálogo y precios | Cardmarket "u otra API compatible" | **tcggo, única** (pasó antes por pokemontcg.io y TCGdex) | Los adaptadores anteriores daban un solo precio a todas las impresiones de una carta y valuaban mal cada reprint. |
| Importar el catálogo | `POST /api/cards/import` | Import **por set** desde Mantenimiento → Sets, sin bootstrap | tcggo cobra por request pasado un cupo; importar un set entero cuesta pocos requests y después todo es local. |
| Sets personalizados | tabla `set_cards` (lista explícita) | **Reglas** (`rules_json`) materializadas en **slots** (`set_slots`, `set_slot_cards`) | Permite subconjuntos, exclusiones por rareza o por carta y agrupar reprints como una misma carta lógica, sin dejar de tener el catálogo completo. |
| Fotos | una imagen por registro (`collection.image`) | tabla `collection_photos` (N por copia), y **subir reemplaza** | "Una foto por variante, con swipe" no cabía en una columna; después se decidió que subir pise lo anterior (ver 3). |
| Condiciones | NM / LP / MP / HP / Damaged | Escala renombrada (de `M/NM` hacia abajo, ver `config.CONDITIONS`) | _Motivo sin registrar._ El cambio está en `dc14f4b` (27-ago). |
| Variante | Holo / non-holo / reprints… | La **impresión exacta de Cardmarket** (`market_products`) elegida en un selector de versiones | Es lo que hace que el precio sea una consulta y no una adivinanza. |
| Precio | `price_cache` por carta y variante | Lectura **local** por id de impresión, con multiplicadores de condición e idioma, ×2 por primera edición y precio manual por impresión | Una fila sin impresión elegida queda sin precio: un número equivocado es peor que ninguno. |
| Refresco de precios | cron mensual | Igual (mensual), en un contenedor `scheduler` propio, más un botón manual en el dashboard | Un planificador dentro del proceso web se perdería con un reinicio. |
| Estructura del proyecto | `app.py`, `api/routes.py`, `templates/`, `static/pokemon.js` | Paquete `tombot/` con blueprints por área y `static/js/` modular | Crecimiento natural. |
| Esquema | seis tablas conceptuales | Unas 25, sin migraciones | Ver README → Convenciones. |

**Agregado que no estaba en el PDF:** Hall of Fame (0–8) por carta; objetivo de
copias por carta, con nota; ocultar sets; completitud laxa (experimental); vista de
Faltantes; reimport de sets; búsqueda global agrupada por reprint; revisión de datos;
herramientas de CSV para metadatos de carta y objetivos; presupuesto de requests con
ventana móvil y límite por minuto; sello de versión de la compilación; CI en GitHub
Actions; modal de carta separado para desktop y mobile.

## 3. Decisiones tomadas

1. **tcggo como única fuente** (28-ago). Se eliminaron los demás adaptadores.
2. **`schema.sql` sin migraciones** (28-ago). Estado nuevo por set va en una tabla
   nueva, no en una columna.
3. **`market_products` se clavea por impresión, no por producto de Cardmarket**
   (#68). tcggo repite el id de producto entre tiradas distintas.
4. **El Hall of Fame y el objetivo de copias son por carta lógica, no por copia**
   (#76), y viven en tablas propias para sobrevivir a un reimport.
5. **El cupo de la API se cuenta en la base**, con ventana móvil de 24 h, así un
   reinicio no devuelve el cupo y la web y el scheduler comparten uno solo.
6. **Modal de carta separado para desktop y mobile** (10-oct). Las estructuras y la
   navegación son tan distintas (flechas de teclado contra swipe) que no se podían
   reaprovechar ni las clases de CSS. Se elige al abrir, por ancho de ventana.
7. **Subir una foto pisa de verdad las anteriores de esa copia** (11-oct). Es a
   propósito; si hace falta volver atrás, se restaura un snapshot. La foto nueva
   hereda `is_primary` e `is_cover`.
8. **Modal mobile: tocar la carta la da vuelta** y cambia el panel inferior de
   "Añadir copia" a "Editar copias", con **guardado en vivo** y sin
   Guardar/Cancelar. El giro está disponible para toda carta con copias, aunque no
   haya escaneo (el reverso es la carta apagada). Borrar una variante pide un segundo
   toque. Para cambiar la impresión de una variante se la borra y se carga de nuevo.
9. **Colores del modal mobile:** el objetivo se ve en verde cuando las copias lo
   alcanzan o superan; el Hall of Fame, en azul cuando es mayor a 1.

## 4. Historia resumida

| Fecha | Qué pasó |
| --- | --- |
| 25-ago | Proyecto inicial (esquema, catálogo, sets, API, SPA), Docker, Hall of Fame, vista Cartas, impresiones múltiples. |
| 26-ago | CI y tests de comportamiento; objetivos de copias y filtros; adaptador TCGdex y precios por tirada; se borra la documentación original. |
| 27-ago | tcggo con presupuesto de requests; selector de versiones de Cardmarket; pestaña Mantenimiento; renombre de condiciones. |
| 28-ago | Refactor a **tcggo único, sin bootstrap ni migraciones**; metas por reglas; sets agrupados por era; ocultar sets; sincronizar catálogo. |
| 29-ago | Completitud laxa (experimental). |
| 1-sep | Selector de versión único; reprints por nombre y artista; CSV de metadatos; límite por minuto; botón Reimportar. |
| 3-sep | Multiplicador de idioma con vista previa en vivo; el reimport reconstruye las metas. |
| 6-sep | Filtros separados de supertipo y color. |
| 8-sep | **`market_products` por impresión (#68)**; arreglos de duplicados y colisiones (#69). |
| 10-sep | Una ficha por carta, valorada por todas sus copias (#78); un rating por carta (#76). |
| 12 y 13-sep | Etiqueta de impresión en el modal (#83), una sola respuesta a "¿la tengo?" (#82), precio manual por impresión (#88). |
| 15-sep a 6-oct | Mucho trabajo de interfaz y dashboard; nota en el objetivo (#94); una foto principal por copia (#93); portada de grupo y borrar foto desde el lightbox (#99); pestaña Faltantes rehecha; búsqueda agrupada por reprint (#104); rareza por primera tirada (#105); clave de nombre normalizada (#102). |
| 10-oct | **Modal nuevo**: desktop y mobile separados. |
| 11-oct | Subir foto reemplaza la anterior. |

## 5. Pendientes

Lo de acá sale de lo revisado, no de la lista de issues de GitHub (que no se
revisó): hay que cruzarlos.

### Modal mobile

- Editar **primera edición** y **precio manual** (hoy solo en desktop).
- El botón "atrás" de Android cambia el hash y cierra la vista entera, no el modal.
- **Teléfono en horizontal:** pasa de 600 px de ancho y abre el modal de desktop;
  hace falta un criterio mejor (por ejemplo, táctil con poca altura) y un diseño
  apaisado para el modal mobile.
- Afinar en un teléfono real: `--mm-peek`, el espacio `GAP` entre cartas y el límite
  de `OPEN_FRAC`.
- Revisar que el escaneo se vea en tamaño completo: se usa `photoUrl(p, false)`, y si
  ese parámetro significa "miniatura", la foto sale pixelada.

### Fotos

- Hacer **atómico** el reemplazo (un `replace_photos` en el repositorio, en una sola
  transacción), en vez de varias operaciones sueltas en la ruta.
- Con una sola foto por copia, `is_primary` ya no elige nada y **"Marcar como
  principal" del lightbox de desktop queda sin función**; `is_cover` ("Usar como
  portada") sí sigue valiendo, porque decide entre los reprints de un grupo.
- Decidir si el esquema vuelve a **una foto por copia** (hoy sigue permitiendo N).

### Higiene del repositorio

- Están versionados `.cache/tcggo/*.json` y `.coverage`. Deberían estar en
  `.gitignore` y fuera del índice (`git rm -r --cached .cache .coverage`).
- `media/tombot_favicon_bg.psd` está versionado: decidir si va.
- Borrar `CLAUDE.md` y `docs/README.md` ahora que este README los reemplaza.
- `schema.sql` arrastra comentarios huérfanos de tablas que ya no existen (bloques
  sobre el episodio de tcggo, el presupuesto y el catálogo de episodios sin tabla
  debajo), y restos de proveedores viejos: `price_quotes.provider` menciona
  `tcgdex | pokemontcgio` y `cards.external_ids_json` guarda un id de pokemontcg.io.
  `api_budget` parece haber sido reemplazada por `api_requests`: **verificar que no
  se use antes de borrarla**.

### Configuración

- `.env.example` documenta `APP_PORT`, `BIND_ADDR`, `WEB_CONCURRENCY` y
  `HTTP_MAX_BACKOFF`, pero el `docker-compose.yml` publica `8090:8080` fijo y no pasa
  esas cuatro variables al contenedor. O se conectan, o se sacan del ejemplo.
- Confirmar el scheduler real: el compose y el ejemplo lo dejan **mensual** (día 1,
  04:00, hora de Madrid). Si el `.env` verdadero lo cambia, el README debe decirlo.

### Frontend (a verificar en el `pokemon.js` actual)

- `sorter()` no tenía una clave para "Por pendientes" (`still_needed`), que el menú
  ofrece, y caía al orden por número.
- `stampVersion()` crea el elemento con el sello de la compilación, pero no lo inserta
  en la página.
- Había manejadores de `#q-collect .qs-btn` (selección por lote) sin HTML que los
  use en la plantilla.

### Operación

- Documentar el **procedimiento de snapshot y rollback** con el comando y el dataset
  exactos.
- Cruzar este plan con los issues abiertos de GitHub.

## 6. Fuera de alcance

- OCR o reconocimiento de cartas por visión.
- Autenticación de usuarios y multiusuario.
- Otras fuentes de precios mientras tcggo cubra lo que hace falta.