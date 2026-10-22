# Uso

Ejecuta los comandos dentro de la carpeta de datos del equipo. Los comandos que cambian cosas (`rotate`, `revoke`, `sync`, `import`) solo muestran lo que harían si añades `--dry-run`.

## Crear un .env local

```bash
rekey sync targets/file/shop/web/.env.local.tpl
```

- Las claves se rellenan desde 1Password. Las demás líneas del archivo no se tocan.
- Las plantillas locales solo tienen **claves**. Escribe tú la configuración local (puertos y similares) o cópiala del `.env.example` del proyecto.
- Para compartir una configuración local con el equipo, añade una línea `CLAVE=valor` a la plantilla. A partir del siguiente `sync` también se escribe.

## Convertir un .env existente en plantilla

```bash
rekey init ~/code/shop/web/.env.local                   # un archivo
rekey init ~/code/shop --with-settings                   # todos los .env de una carpeta, con la configuración normal
```

- Las claves se convierten en referencias `{{ op://… }}`. Si un valor ya es una clave de tus plantillas, se reutiliza esa clave.
- Si la plantilla ya existe, solo se añaden las variables que faltan; las líneas que editaste no cambian.
- Sin `--with-settings`, la configuración normal (puertos, URL…) no entra en las plantillas locales.
- Después, `rekey import` guarda los valores nuevos en 1Password.

## Buscar claves

```bash
rekey ls                     # todo: servicio, cómo se emite, número de lugares, etiquetas
rekey ls 'openai.*'          # solo algunas
rekey where openai.shop      # las plantillas y variables que usan esta clave
```

## Rotar una clave

```bash
rekey rotate openai.shop
```

1. Comprobación previa: lo que falte, como un inicio de sesión, se resuelve en el momento.
2. Un resumen de lo que va a pasar; luego pregunta si empezar.
3. La clave nueva:
   - **Automática:** se emite por API o se genera en local. Si falla (por ejemplo, por falta de permisos), rekey explica el motivo y pasa al navegador.
   - **Navegador:** se abre una página. Pega el nombre en el campo de nombre con ⌘V (ya está en tu portapapeles), crea la clave y **cópiala**. rekey sigue en cuanto copias. Pulsa `s` para saltarla o `q` para parar.
   - Si copias la clave anterior o una clave de otro servicio, te avisa. Si la clave nueva no funciona, puedes copiarla otra vez.
   - ¿Te detuviste a medias? Ejecuta el mismo comando otra vez: las claves ya hechas se saltan. ¿La clave nueva quedó mal? `rekey rotate <clave> --redo`.
   - ¿Cambias de idea antes de revocar? `rekey undo <clave>` vuelve a poner la clave anterior en todas partes y borra la nueva.
4. Se guarda en 1Password. El valor anterior se conserva hasta revocarlo.
5. Se actualizan todos los lugares. Luego rekey pregunta si redesplegar ahora Vercel production y Railway (por defecto: no) y, si dices que sí, espera a que estén sanos.
   - Si reiniciar cortaría sesiones en curso, responde N y despliega luego a tu manera o con `rekey deploy <plantilla>`.
   - Supabase Edge Functions, Fly y Workers lo aplican al instante. GitHub Actions lo usa desde la siguiente ejecución.
   - **Los servicios que leen GCP Secret Manager necesitan un reinicio** para usar la clave nueva.
6. rekey pregunta si revocar ya la clave anterior. Responde N para observar un poco más, y después:

```bash
rekey revoke openai.shop
```

- Si el valor anterior todavía se usa en algún sitio, se detiene y muestra el comando que debes ejecutar.
- En servicios sin API de revocación, rekey muestra los últimos 4 caracteres de la clave anterior y abre la página.
- Si algo se interrumpe, ejecuta el mismo comando otra vez: continúa con lo que falta. Una clave rotada no se vuelve a rotar hasta revocar la anterior.
- Si no se puede escribir en algunos lugares, el resto sigue adelante y al final se muestra el comando para reintentarlos.

## Varias claves a la vez

```bash
rekey rotate 'cartesia.*'              # por nombre
rekey rotate tag:breach-2026           # por una etiqueta de keys.toml
rekey rotate 'in:vercel/shop/*'        # todas las claves que usan estas plantillas
rekey rotate project:shop          # todas las claves de un proyecto (su repo, servicio de Railway, proyecto de Vercel…)
rekey rotate tag:breach-2026 --only openai   # acotar: un servicio, un proyecto (in:…), una etiqueta
```

Primero van las automáticas; los pasos de navegador van al final, agrupados por servicio.

### Una clave por proyecto

Si varios proyectos comparten una clave, una filtración no dice de dónde salió y hay que cambiar todos. Sepárala:

```bash
rekey split 'cartesia.*'      # cartesia.shop → cartesia.shop, cartesia.blog, …
rekey rotate 'cartesia.*'     # cada proyecto recibe su propia clave
```

Las claves que deben tener un solo valor no se tocan: tokens entre tus propios servicios, contraseñas de base de datos y claves locked.

## Cambiar la configuración

Las plantillas de plataformas también contienen configuración normal.

```bash
# edita targets/vercel/shop/production.tpl y luego
rekey diff targets/vercel/shop/production.tpl            # compara con lo que está en producción
rekey sync targets/vercel/shop/production.tpl --deploy   # escríbelo y vuelve a desplegar
git commit -am "shop: change APP_URL"
```

`sync all` escribe en todas las plataformas. Úsalo solo cuando sea necesario.

## Añadir una clave

1. Añade una línea en cada plantilla que la necesite. Nombra las claves `<servicio>.<proyecto>`; los tokens que comparten tus propias apps son `self.<proyecto>.<uso>`.
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/stripe.shop/credential }}
   ```
2. Dale un valor: `rekey import stripe.shop` si el valor ya está en uso, o `rekey rotate stripe.shop` para emitir uno nuevo.
3. `git commit`

Para dejar de usar una clave en un sitio, borra su línea.

## Referencia

**Ruta de la plantilla = a dónde van los valores** (dentro de `targets/`, sin `.tpl`)

| Ruta | Destino |
|---|---|
| `file/<ruta>` | un archivo local (relativo a la carpeta que contiene la carpeta de datos del equipo) |
| `vercel/<proyecto>/<production·preview·development>` | Vercel |
| `railway/<proyecto>/<entorno>/<servicio>` | Railway |
| `supabase/<project ref>` | Supabase Edge Function secrets |
| `gcp/<proyecto>` | GCP Secret Manager |
| `github/<owner>/<repo>[/<entorno>]` | GitHub Actions secrets |
| `fly/<app>`, `worker/<nombre>` | Fly, Cloudflare Workers |

Solo se escriben las variables de la plantilla. Nada más cambia en el destino.

**keys.toml** solo recoge excepciones:

```toml
["self.shop.data-master-key"]
locked = "motivo"                 # rotate la salta (solo --force lo anula)
note = "leer antes de rotar"      # se muestra en rotate y where
tags = ["check", "retire"]        # check: rotate la salta / retire: queda fuera de "all"
page = "https://…"                # página que se abre en el paso de navegador
```

**Claves de administrador**: con los elementos `rekey.openai-admin`, `rekey.cloudflare-admin`, `rekey.resend-admin` y `rekey.anthropic-admin` (para revocar) en la misma bóveda, esos servicios son automáticos. `rekey setup` te ayuda a añadirlos.

**Variables de entorno**: `REKEY_HOME` (carpeta de datos del equipo; por defecto, la carpeta más cercana hacia arriba que tenga `targets/` o `keys.toml`), `REKEY_ROOT` (carpeta base de `file/`; por defecto, la carpeta superior de `REKEY_HOME`), `REKEY_STORE=file:<ruta>` (un archivo en lugar de 1Password, para pruebas), `REKEY_NO_BROWSER=1`, `REKEY_LANG` (en, ko, zh, ja, es)
