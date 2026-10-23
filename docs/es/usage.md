# Uso

Ejecuta los comandos dentro de la carpeta de datos del equipo. Los comandos que cambian cosas (`rotate`, `issue`, `revoke`, `sync`, `import`, `arrange`) solo muestran lo que harían si añades `--dry-run`.

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
- Después, `rekey arrange "Acme - {env}"` coloca las claves nuevas en la bóveda correcta y `rekey import` guarda sus valores en 1Password.

## Buscar claves

```bash
rekey ls                     # todo: servicio, cómo se emite, número de lugares, etiquetas
rekey ls project:shop        # un proyecto
rekey ls '*.openai'          # un servicio
rekey where shop.openai      # las plantillas y variables que usan esta clave
```

## Rotar una clave

```bash
rekey rotate shop.openai
```

1. Comprobación previa: lo que falte, como un inicio de sesión, se resuelve en el momento.
2. Un resumen de lo que va a pasar; luego pregunta si empezar.
3. La clave nueva:
   - **Automática:** se emite por API o se genera en local. Si falla (por ejemplo, por falta de permisos), rekey explica el motivo y pasa al navegador.
   - **Navegador:** se abre una página que indica dónde hacer clic. Pega el nombre en el campo de nombre con ⌘V (ya está en tu portapapeles), da a la clave los mismos permisos que la anterior (se muestran sus últimos 4 caracteres), créala y **cópiala**. rekey sigue en cuanto copias. Pulsa `s` para saltarla o `q` para parar.
   - Los códigos de inicio de sesión, la clave anterior o una clave de otro servicio no se aceptan como clave nueva.
   - Una contraseña de base de datos va al final: la anterior deja de funcionar en cuanto se guarda la nueva.
4. Se guarda en 1Password. El valor anterior se conserva hasta revocarlo.
5. Se actualizan todos los lugares. Luego rekey pregunta servicio por servicio si redesplegarlo ahora (por defecto: no). Si reiniciar cortaría sesiones en curso, responde N y despliega luego a tu manera o con `rekey deploy <plantilla>`.
   - Supabase Edge Functions, Fly y Workers lo aplican al instante. GitHub Actions lo usa desde la siguiente ejecución.
   - **Los servicios que leen GCP Secret Manager necesitan un reinicio** para usar la clave nueva.
6. Cuando todos los servicios se han redesplegado, rekey pregunta si revocar ya la clave anterior. Si no, después de tus despliegues:

```bash
rekey revoke shop.openai
```

- Revoke se niega mientras algún lugar tenga todavía el valor anterior. Lee las variables, no lo que un servicio en marcha tiene cargado, así que revoca solo después de los despliegues.
- Revisa todos los lugares con una clave del mismo servicio, porque una clave separada o copiada conserva el valor anterior con otro nombre. Los lugares que no puede leer (variables sensitive de Vercel, secrets de GitHub y Supabase) se listan, y pregunta antes de revocar (por defecto: no).
- En servicios sin API de revocación, rekey muestra los últimos 4 caracteres de la clave anterior y abre la página.
- Si no se puede escribir en algunos lugares, el resto sigue adelante y al final se muestra el comando para reintentarlos.

### En dos pasos

Para revisar antes de que cambie nada, emite primero y pon las claves en su sitio después:

```bash
rekey issue project:shop     # claves nuevas solo en 1Password; ningún lugar cambia
rekey apply project:shop     # escribirlas en todas partes; luego se pregunta cada redespliegue
```

### Cuando algo sale mal

- **Se detuvo a medias:** ejecuta el mismo comando otra vez. Las claves terminadas se saltan; una clave rotada no se vuelve a rotar hasta revocar la anterior.
- **Entró un valor equivocado** (un código de inicio de sesión, otra clave): `rekey rotate <clave> --redo` vuelve a crear la clave nueva; la que hay que revocar sigue siendo la anterior original.
- **Cambias de idea antes de revocar:** `rekey undo <clave>` vuelve a poner la clave anterior en todas partes y, cuando los servicios se han redesplegado, borra la nueva.

## Varias claves a la vez

```bash
rekey rotate project:shop                  # todas las claves de un proyecto (su repo, servicio de Railway, proyecto de Vercel…)
rekey rotate tag:breach-2026               # por una etiqueta de keys.toml
rekey rotate 'in:railway/*'                # todas las claves que usan estas plantillas
rekey rotate '*.cartesia'                  # por nombre
rekey rotate tag:breach-2026 --only shop   # acotar: un proyecto o servicio, un nombre, tag:, in:, project:
```

Primero van las automáticas; después los pasos de navegador, agrupados por servicio; las contraseñas de base de datos van al final.

## Una bóveda por entorno, una clave por proyecto

```bash
rekey arrange "Acme - {env}" --dry-run     # ver el plan
rekey arrange "Acme - {env}"
```

- Cada clave pasa a la bóveda del entorno que la usa: `Acme - Prod`, `Acme - Dev` o `Acme - Local`.
- Una clave que comparten varios proyectos o entornos se separa, una por proyecto y entorno, con nombre `<project>.<service>`. Hasta el siguiente `rotate` las partes tienen el mismo valor; después, una filtración apunta a un solo proyecto.
- No se separan: los tokens entre tus propios servicios (`.self.`), las contraseñas de base de datos, las claves locked y las claves pendientes de revocar.
- Los elementos de 1Password se mueven y se renombran, nunca se borran. Revisa con `git diff` y haz commit.
- Los datos del equipo anteriores a rekey 0.3 nombran las claves `<service>.<project>`; añade `--old-names` una vez para renombrarlas.

## Cambiar la configuración

Las plantillas de plataformas también contienen configuración normal.

```bash
# edita targets/vercel/shop/production.tpl y luego
rekey diff targets/vercel/shop/production.tpl   # compara con lo que está en producción
rekey sync targets/vercel/shop/production.tpl   # escríbelo; se pregunta el redespliegue
git commit -am "shop: change APP_URL"
```

`sync all` escribe en todas las plataformas. Úsalo solo cuando sea necesario.

## Añadir una clave

1. Añade una línea en cada plantilla que la necesite. Nombra las claves `<project>.<service>`; los tokens que comparten tus propias apps son `<project>.self.<uso>`.
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/shop.stripe/credential }}
   ```
2. Dale un valor: `rekey import shop.stripe` si el valor ya está en uso, o `rekey rotate shop.stripe` para emitir uno nuevo.
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

Solo se escriben las variables de la plantilla. Nada más cambia en el destino. Una variable de Railway que referencia otro servicio (`${{ api.OPENAI_API_KEY }}`) nunca se sobrescribe: rekey se detiene y lo indica.

**Nombres de claves**: `<project>.<service>[.<uso>]`. El servicio decide cómo se emite la clave (`shop.openai` → OpenAI); `self` significa que la genera rekey, `other` que una persona la emite en el navegador.

**keys.toml** solo recoge excepciones:

```toml
["shop.self.data-master-key"]
locked = "motivo"                 # rotate la salta (solo --force lo anula)
note = "leer antes de rotar"      # se muestra en rotate y where
tags = ["check", "retire"]        # check: rotate la salta / retire: queda fuera de "all"
page = "https://…"                # página que se abre en el paso de navegador
```

**Claves de administrador**: con los elementos `rekey.openai-admin`, `rekey.cloudflare-admin`, `rekey.resend-admin` y `rekey.anthropic-admin` (para revocar) en cualquiera de tus bóvedas, normalmente la de Prod, esos servicios son automáticos. `rekey setup` te ayuda a añadirlos.

**Variables de entorno**: `REKEY_HOME` (carpeta de datos del equipo; por defecto, la carpeta más cercana hacia arriba que tenga `targets/` o `keys.toml`), `REKEY_ROOT` (carpeta base de `file/`; por defecto, la carpeta superior de `REKEY_HOME`), `REKEY_STORE=file:<ruta>` (un archivo en lugar de 1Password, para pruebas), `REKEY_NO_BROWSER=1`, `REKEY_LANG` (en, ko, zh, ja, es)
