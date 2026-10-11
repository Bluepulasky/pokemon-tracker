# TomBot — Pokémon card tracker

La mejor aplicación web personal para trackear pokemon, self-hosted y de un solo usuario
que NUNCA se va a vender comercialmente (la tenes atroden matt), para llevar MI
colección física de cartas Pokémon: qué cartas tenés, cuáles te faltan para
completar cada set y cuánto vale la colección.

> Este archivo reemplaza a todos los .md anteriores que eran una poronga. Lo que
> viene a futuro, las decisiones tomadas y las desviaciones respecto de la
> especificación original están en [`PLAN.md`](PLAN.md).

## Qué hace hoy

- **Catálogo** de sets y cartas importado desde tcggo, un set por vez, desde
  Mantenimiento → Sets. Imágenes de catálogo cacheadas en disco.
- **Metas de colección** (sets personalizados) definidas por reglas sobre uno o más
  sets oficiales, con excepciones carta por carta (★) y selección rápida por lote.
- **Inventario físico**: por carta, variante, condición, idioma y cantidad, con la
  impresión exacta de Cardmarket elegida en un selector de versiones.
- **Progreso de completitud** por set y global, con modo estricto o custom
  (cualquier impresión cuenta).
- **Vistas**: Dashboard, Sets (agrupados por era), detalle de set, Cartas
  (inventario / todas), Faltantes, Mantenimiento.
- **Valoración** desde precios locales por impresión, con multiplicadores de
  condición e idioma, ×2 por primera edición y precio manual por impresión.
  Historial mensual de valor.
- **Hall of Fame** (0–8) por carta y **objetivo de copias** por carta, con nota.
- **Fotos propias** por copia, con foto de portada para el grupo de reprints.
- **Modal de carta** con dos implementaciones: desktop y mobile (ver más abajo).
- **Revisión de datos** (`services/health.py`) que busca inconsistencias.
- **PWA liviana** (manifest + favicons) pensada para usarse desde el teléfono.

## Arquitectura

- **App factory de Flask** (`tombot/__init__.py`) que registra los blueprints de
  `tombot/api/`: `catalog`, `collection`, `prices`, `sets`, `stats`.
- **`PokemonRepo`** (`tombot/services/repository.py`) es el **único** lugar que
  escribe SQL. Todo lo demás pasa por él.
- **SQLite** (`tombot/services/schema.sql`): WAL, `foreign_keys=ON`, conexiones por
  hilo, `tx()` reentrante.
- **Frontend**: SPA en JavaScript vanilla, sin paso de build, en `static/js/`,
  cargada como módulos ES. Si papa. Usamos Js vanilla por que somos pijudos.
  Nada de react. Nada de vue. No reinventemos la rueda.
- **Servicios** (`tombot/services/`): `market_import` y `tcggo_catalog` (import),
  `pricing`, `setbuilder`, `bulk`, `card_meta`, `health`, `images`, `budget`,
  `httpcache`, `jobs`, `tcg_series`, `printing_variants`, y el adaptador
  `sources/tcggo.py`.
- **CLI** (`tombot/cli/`): comandos de `flask` para esquema, precios y snapshots.
- **Docker**: dos contenedores con la misma imagen, `app` (web) y `scheduler`.

Estructura de carpetas relevante:

```
app.py                      punto de entrada
tombot/
  api/                      blueprints (catalog, collection, prices, sets, stats)
  services/                 repository, schema.sql, importadores, precios, health…
  cli/                      comandos flask
  data/card_meta.csv        tipo/color de energía por carta
static/js/                  pokemon.js (SPA), api.js, ui.js, modal*.js
static/css/style.css
templates/index.html
scripts/                    entrypoint.sh, check_js.sh, demo_seed.py, …
tests/                      pytest (fixtures de tcggo en tests/fixtures/)
data/  media/               base de datos y fotos (volúmenes; no se versionan)
```

## Única fuente de datos: tcggo

Catálogo, imágenes, versiones de Cardmarket **y** precios salen de **tcggo**
(CardMarket API TCG en RapidAPI). No hay otra fuente: los adaptadores viejos de
pokemontcg.io y TCGdex se eliminaron porque cada uno asignaba un solo precio a
todas las impresiones de una carta, y eso valuaba mal cada reprint.

tcggo es **medido**: el plan cobra por request pasado un cupo diario. Toda llamada
pasa por `RequestBudget` (`services/budget.py`), que cuenta los requests en la base
sobre una ventana móvil de 24 h y se niega a enviar uno pasado el tope
(`TCGGO_DAILY_LIMIT`, 40 por defecto). Además hay un límite por minuto (#50). La
key va en `.env` como `TCGGO_API_KEY`.

Los sets se importan **de a uno desde Mantenimiento → Sets**. No hay bootstrap: una
instalación nueva es un esquema vacío, y importar un set es lo que lo llena.
Importar guarda las cartas del set y sus productos de Cardmarket (con precios) en
`market_products`, y crea una meta de colección para ese set. Los sets ya
importados tienen un botón **Reimportar**.

**Particularidades de tcggo que conviene conocer:**

- Sus nombres no coinciden con los comunes: Base Set se llama **"Base"**. Por eso
  la búsqueda al agregar un set cachea el catálogo completo una vez
  (`list_all_episodes`) y compara **localmente y en ambos sentidos** (un set
  coincide si su nombre contiene la consulta *o* la consulta contiene su nombre).
  `search_episodes` (su búsqueda cruda) sola no encuentra "Base Set".
- Su campo `series` es ralo e inconsistente (vacío en casi todos los sets): no
  agrupar por él; se usa la era según fecha de lanzamiento (`tcg_series.py`).
- En algunos sets omite el `logo` al importar; la tarjeta de Sets usa el logo del
  episodio cacheado (`COALESCE(NULLIF(os.logo_url,''), me.logo)`).
- El selector de versiones lista los **reprints de todos los sets importados** por
  nombre de carta; al elegir uno, el item queda registrado contra la carta/set de
  ese reprint.
- Los reprints se emparejan por una **clave de nombre normalizada** (`name_key`,
  #102) y por ilustrador, no por el nombre literal ni por número.
- La rareza de una carta se decide por su **primera tirada de impresión**, no por
  el stock actual (#105).

## Modelo de datos

**Catálogo** (se puede sobrescribir en un reimport):

- **`official_sets` + `cards`**: el catálogo, de un import de tcggo. Los ids de
  carta son `{codigo_set}-{numero}` (ej. `bs-4`). Siempre el set completo.
  `supertype` (Pokémon / Trainer / Energy) viene de tcggo; `types_json` (tipo de
  energía / color) **no** — tcggo no tiene ese campo — y se completa solo con el CSV
  de metadatos (`tombot/data/card_meta.csv`, aplicado desde Mantenimiento o con
  `flask fix-card-meta`); un reimport no debe vaciarlo. La vista Cartas filtra
  ambos ejes por separado (`type` y `color`).
- **`market_products`**: una fila por **impresión** de una carta en un set
  importado, con su precio y su propia URL de Cardmarket. Las versiones de una
  carta son sus impresiones. La clave es `(episode_id, card_id, version)` sobre un
  id propio; **`cardmarket_id` es un atributo, nullable y no único**. Tiene que
  serlo: tcggo estampa distintas tiradas con un mismo id (el Charizard de Base Set
  1st Edition Shadowless y el Shadowless son ambos el producto 660224, a 50.000 y
  2.000 EUR) y en otras no manda id. Con esa clave, Base Set guardaba 193 de las
  307 impresiones y 11 cartas de Base Set 2 desaparecían del catálogo (#68). La
  clave usa `card_id` y no `code`: Celebrations guarda dos cartas distintas bajo
  "CEL 2".
- **`card_printings`**: agrupa impresiones de una misma carta lógica
  (`print_group` = carta de la impresión más antigua, estable entre reimports).
  `source` distingue `slot` (agrupado a mano en una meta, autoritativo), `auto`
  (heurística del importador, solo una pista) y `manual`.
- **`market_episodes`**: el catálogo de sets de tcggo (~180), cargado con el botón
  "Sincronizar lista de sets" de Mantenimiento para que la búsqueda sea local.
  **`set_episodes`** mapea un set del catálogo a su episodio de tcggo.

**Metas de colección** (de uso del usuario; un reimport nunca las toca):

- **`collection_sets` + `set_slots` + `set_slot_cards`**: una *meta de colección*,
  definida por una **regla** sobre uno o más sets del catálogo. Un slot es un
  objetivo de completitud, que se satisface teniendo cualquier carta miembro. Las
  reglas viven en `collection_sets.rules_json` y `SetBuilder` las materializa en
  slots. El catálogo sigue completo aunque lo que *coleccionás* cambie: reglas de
  rareza (`exclude_rarities`, etc.) más excepciones por carta (`include_cards` /
  `exclude_cards`); el ★ y la barra de selección rápida del detalle de set escriben
  ahí. El `source` de un slot es `rule` o `manual`; una reconstrucción no toca los
  manuales.
- **`set_hidden`**: sets ocultos de la página Sets y de los totales (se conservan;
  se muestran de nuevo desde Mantenimiento). **`set_loose_completion`**: bandera
  experimental por set, "cualquier impresión poseída cuenta". Ambas son tablas de
  presencia.

**Colección:**

- **`collection_items`**: lo que poseés físicamente. Único por `(card_id, variant,
  condition, language)`, más `market_product_id`: la **impresión** exacta elegida
  en el modal, o sea un `market_products.id`, no un id de producto de Cardmarket.
  También `first_edition`.
- **`collection_photos`**: fotos por item (ver "Fotos").
- **`card_ratings`**: Hall of Fame 0–8 **por carta lógica**, no por copia. Tabla
  propia para que sobreviva a un reimport.
- **`card_targets`**: por carta, cuántas copias cuentan como completo (`target`) y
  una `note` de texto libre (qué impresión buscar, #94). El valor por defecto (1,
  sin nota) se guarda como ausencia.

**Precios e historia:**

- **`price_cache`**: el precio resuelto por impresión poseída.
- **`price_modifiers`**: multiplicadores editables; hoy solo se siembra, lee y edita
  el tipo `condition`.
- **`price_history`** (un precio por carta y día) y **`price_quotes`** (todas las
  cotizaciones recibidas, para detectar cuando dos fuentes discrepan).
- **`collection_snapshots`**: foto periódica de cartas únicas, físicas, sets,
  completitud y valor, para los gráficos de evolución.
- **`api_requests`** (un registro por request enviado, para la ventana móvil del
  presupuesto) y **`app_meta`** (clave/valor).

## Sets y completitud

- El detalle de set muestra **el set entero** (cada carta, vía
  `set_cards_with_state`), cada una marcada como `collecting` (¿es un slot?) y
  `owned`. Los filtros son del lado del cliente; el ★ por carta y la barra de
  selección rápida (`PUT /sets/<id>/collect`) modifican la regla.
- **`set_progress()` es la única fuente de completitud**: la página Sets, los
  totales del dashboard y el snapshot mensual suman todos de ahí. Cambiar qué
  cuenta (oculto, laxo) en esa consulta lo cambia en los tres. Listar todos los
  sets (`set_id=None`) omite los ocultos; la consulta de un set devuelve ese set
  igual.
- La página Sets agrupa por **era del TCG**, derivada de `release_date` contra una
  línea de tiempo chica en `services/tcg_series.py`.
- Una misma pregunta, "¿tengo esta carta?", se responde igual en todas las pantallas
  (#82).

## Fotos

- Una foto es un archivo bajo `media/collection/` más una miniatura bajo
  `media/thumbs/`; la base solo guarda los nombres. Límite de subida:
  `MAX_UPLOAD_MB` (25 por defecto).
- **Subir una foto a una copia reemplaza a las que ya tenía**, a propósito: se borran
  la fila y el archivo viejos, y la nueva hereda `is_primary` / `is_cover`. El
  rollback, si hace falta, se hace con snapshot (ver "Operación"). Hoy no es atómico:
  está resuelto en la ruta `POST /collection/<id>/photos`.
- `is_primary`: a lo sumo una por **copia**. `is_cover`: la foto que representa a
  **todo el grupo de reprints** en una grilla, elegida a mano; a lo sumo una por
  copia, y `set_cover_photo` además limpia la marca en el resto del grupo, cosa que
  el índice no puede expresar. Con 0 en todas, la elección es automática (la de
  mejor condición).

## Precios

Los precios se leen **localmente** desde `market_products` por el id de impresión de
cada fila poseída: ninguna llamada de red por carta, ninguna adivinanza sobre qué
impresión es una variante. Una fila sin producto elegido queda sin precio (un número
equivocado es peor que ninguno). Reimportar un set es lo que refresca sus precios.
Ver `services/pricing.py`.

Sobre el precio base se aplican, en el cliente (vista previa) y en el servidor
(valor guardado, redondeado igual al centavo): el multiplicador de condición, el de
idioma y ×2 por primera edición. Un **precio manual** pertenece a la impresión que se
edita (#88).

## Frontend

- `static/js/pokemon.js`: router por hash y vistas (`dashboard`, `sets`, `set`,
  `cartas` / `collection`, `missing`, `mantenimiento`).
- `static/js/api.js`, `ui.js`: cliente de la API y utilidades de interfaz.
- **Modal de carta**, dividido en cuatro módulos que comparten una sola API pública
  (`initModal`, `closeModal`, `openCard`, siempre desde `./modal.js`):
  - `modal.js`: entrada. Elige desktop o mobile **al abrir** según
    `matchMedia('(max-width: 600px)')` (`isMobile()` en `modal-core.js`).
  - `modal-core.js`: estado compartido, cierre, bloqueo de scroll y token de apertura
    que invalida cargas en vuelo.
  - `modal-desktop.js`: dos columnas, con navegación por flechas del teclado.
  - `modal-mobile.js`: una columna, con swipe entre cartas, panel inferior
    desplegable para añadir copias, toque en la carta para darla vuelta y mostrar el
    escaneo, y modo de edición de copias con guardado en vivo. Todo su CSS usa el
    prefijo `.mm-` y no comparte clases con desktop.
- **Validación**: los módulos se cargan como ES modules, así que hay que validar con
  `node --check` sobre una copia `.mjs`; `node --check archivo.js` lo parsea como
  CommonJS y esconde una llave faltante. Ver `scripts/check_js.sh`.

## API

Todo bajo `/api`. Los blueprints se montan en `/api` (catálogo y estadísticas),
`/api/collection`, `/api/prices` y `/api/sets`.

| Área | Rutas |
| --- | --- |
| Catálogo | `GET /healthz`, `/meta`, `/cards`, `/cards/<id>`, `/search`; `PUT /cards/<id>/target`, `/cards/<id>/rating` |
| Mantenimiento | `POST /maintenance/sync-catalog`; `GET /maintenance/episodes`; `POST /maintenance/episodes/<id>/import`; `GET /maintenance/hidden-sets`, `/health`, `/status`; objetivos: `GET /maintenance/targets/export`, `POST /maintenance/targets/import`; metadatos: `POST /maintenance/card-meta/apply`, `/import`, `GET /export` |
| Sets | `GET /sets`, `/sets/<id>`, `/sets/<id>/missing`, `/sets/<id>/mode`; `POST /sets`, `/sets/<id>/rebuild`; `PUT /sets/<id>`, `/loose`, `/hidden`, `/card/<card_id>`, `/collect`, `/mode`; `DELETE /sets/<id>` |
| Colección | `GET /collection`, `/collection/<id>`, `/collection/by-card/<card_id>`; `POST /collection`; `PUT`/`DELETE /collection/<id>`; fotos: `POST /collection/<id>/photos`, `PUT`/`DELETE /collection/photos/<photo_id>` |
| Precios | `GET /prices/<card_id>`, `/prices/<card_id>/quotes`, `/prices/history`, `/prices/modifiers`, `/prices/versions`; `POST /prices/refresh`, `/prices/refresh-async`; `PUT /prices/manual/<card_id>/<variant>`, `/prices/modifiers/<kind>/<key>` |
| Estadísticas | `GET /dashboard`, `/stats/history` |

## Convenciones

- **`schema.sql` es la única fuente de verdad. No hay migraciones.** Un cambio de
  esquema es una edición de `schema.sql`; `init_db` solo lo ejecuta y es
  idempotente. **Ojo:** cada sentencia es `CREATE ... IF NOT EXISTS`, así que una
  **tabla** nueva aparece en una base ya poblada en el próximo `init-db`, pero una
  **columna** nueva en una tabla existente **no**. Para agregar estado por set que
  deba sobrevivir sin recrear la base (como `set_hidden` o `set_loose_completion`),
  usá una **tabla nueva** chica, no una columna. Una columna solo sirve cuando
  perder la base vieja es aceptable (se reconstruye de los imports). Cambiar la
  **clave** de una tabla es lo único que `init_db` no puede lograr: la tabla vieja
  simplemente sobrevive, así que hace falta un drop explícito, y `market_products`
  es la única tabla donde eso es seguro (no tiene nada que el usuario haya escrito
  y un reimport la reconstruye entera; ver
  `_retire_product_keyed_market_products`). Una columna de la que depende un
  **índice** en `schema.sql` (`is_cover`) debe agregarse con un `ALTER TABLE` que
  corra **antes** de `executescript`, o `CREATE INDEX` falla con "no such column" en
  una base existente; los demás `ALTER` corren después (ver
  `_add_cover_column_to_photos`). `note` en `card_targets` y `first_edition` en
  `collection_items` se agregan con el mismo mecanismo de autocuración de `init_db`.
- **Después de cambiar `schema.sql`, el reinicio corre `init_db` solo con el
  entrypoint de Docker.** Correr `waitress` o `flask run` directo no lo hace: hay que
  ejecutar `flask init-db` una vez, o falta la tabla ("no such table").
- **Los fallbacks silenciosos son el enemigo.** La mayoría de los bugs vinieron de una
  búsqueda que falló y devolvió algo verosímil (un multiplicador ausente → 1,00, un
  id de set desconocido → "set moderno"). Preferí fallar o avisar antes que adivinar.
  `services/health.py` (Mantenimiento → Revisión de datos) busca activamente estas
  inconsistencias.
- **Una sola instancia local.** Un servidor, una base; para cambiar de rama, checkout
  más reinicio. La key de tcggo se mide por key, así que varias instancias con una
  misma key gastan de más.
- Leer los datos del elemento y no su posición en pantalla: un formulario de edición
  que recupera valores por el orden de las etiquetas se rompe en silencio cuando una
  etiqueta se mueve (#83, #87).

## Comandos y ejecución

```
flask init-db     # crea el esquema (idempotente). El arranque lo corre; no hay bootstrap.
flask prices      # revalúa la colección desde los productos importados (local, sin red)
flask snapshot    # escribe un snapshot de la colección para los gráficos de historia
flask monthly     # precios + snapshot (lo que llama el cron)
flask scheduler   # corre `monthly` programado, bloqueante (su propio contenedor)
flask fix-card-meta  # aplica tombot/data/card_meta.csv
```

```
docker compose up -d        # app + scheduler
docker compose up -d app    # solo la web, sin scheduler
pytest                      # corre la suite
```

La integración continua corre en GitHub Actions (`.github/workflows/ci.yml`).

## Configuración

Todo se configura en `.env` (ver `.env.example`); el `docker-compose.yml` no debería
necesitar edición. El puerto publicado es `8090:8080`.

| Variable | Para qué sirve |
| --- | --- |
| `TCGGO_API_KEY` | key de tcggo (nunca se versiona) |
| `TCGGO_DAILY_LIMIT` | tope duro de requests en 24 h (40); mantenerlo **por debajo** del límite real del plan |
| `DATA_PATH`, `MEDIA_PATH` | dónde viven la base y las fotos en el host |
| `PUID`, `PGID`, `TZ` | dueño de los archivos y zona horaria (`Europe/Madrid`) |
| `APP_TOKEN` | token de acceso; no hay login. Vacío = sin auth. El navegador lo necesita una vez: `localStorage.setItem('app_token', '<valor>')` |
| `SCHEDULER_CRON_DAY`, `SCHEDULER_CRON_HOUR` | día del mes y hora del refresco programado (por defecto día 1, 04:00) |
| `SCHEDULER_RUN_ON_START` | `1` = correr también una vez al iniciar |
| `PRICE_STALE_DAYS` | antigüedad a partir de la cual un precio se considera viejo (25) |
| `CARDMARKET_LOCALE` | idioma de los links a Cardmarket (`es`) |
| `MAX_UPLOAD_MB` | tamaño máximo de foto (25) |
| `WEB_THREADS`, `WEB_TIMEOUT` | ajuste del servidor web |

## Operación

- **Datos que importan:** `data/` (SQLite) y `media/collection/` + `media/thumbs/`.
  El catálogo y los precios se reconstruyen reimportando; lo que **no** se puede
  reconstruir es lo que escribiste vos: colección, fotos, metas, ratings, objetivos.
- **Rollback:** se hace con un snapshot del sistema de archivos del host, anterior al
  cambio. Tomá uno antes de cualquier operación destructiva (reimportar sets, cambios
  de esquema, borrados masivos). _Falta documentar el comando y el dataset exactos._
- **Refresco programado:** el contenedor `scheduler` corre `flask monthly` (precios +
  snapshot) una vez por mes, en su propio contenedor a propósito: un planificador
  dentro del proceso web ataría la corrida a la vida del servidor, y un reinicio a
  mitad de un refresco la perdería. Comparte con la web el mismo cupo diario, porque
  el conteo vive en la base.
- **Qué versión corre:** el compose monta `./.git` en solo lectura para que la app
  informe de qué commit sirve. Un `unknown` honesto vale más que una versión inventada,
  y es la forma de distinguir un bug de una imagen que nunca se reconstruyó.

## Para quien revise o modifique el código (incluida una IA)

- El cupo de tcggo es **plata real** pasado el tope diario. No hagas llamadas en vivo
  a tcggo a la ligera: el selector de versiones y los precios leen de datos locales ya
  importados. `scripts/tcggo_live_check.py` existe para verificaciones explícitas.
- Antes de tocar SQL: solo en `PokemonRepo`.
- Antes de tocar el esquema: leer "Convenciones".
- Los tests con fixtures reales de tcggo (`tests/fixtures/tcggo/`) fijan casos
  difíciles (Charizard 1st Edition Shadowless, reprints de Flareon, Southern Islands).
  Un bug nuevo de catálogo o de precios debería entrar como test con su fixture.
