# Preparación

rekey separa la **herramienta** (este repositorio) de los **datos del equipo** (un repositorio privado con `targets/` y `keys.toml`). Los datos del equipo no contienen valores de claves, pero sí describen tu infraestructura, así que mantenlos privados.

## Todos (10 minutos)

**1. Instala la herramienta y descarga los datos del equipo.** Pon los datos del equipo en la **misma carpeta que tus proyectos**: las rutas `targets/<project>/file/…` se toman desde ahí.

```bash
brew install pipx                                  # si no lo tienes (Linux: https://pipx.pypa.io)
pipx install git+https://github.com/golbin/rekey
git clone <repositorio de datos del equipo> ~/code/keys
```

Ejecuta `rekey` dentro de esa carpeta (o en cualquier carpeta por debajo): encuentra los datos del equipo por sí solo. Actualiza la herramienta con `pipx upgrade rekey`.

**2. CLI de 1Password.**

```bash
brew install 1password-cli        # Linux: https://developer.1password.com/docs/cli/get-started
```

En la app de 1Password: Ajustes → Desarrollador → activa **"Integrar con 1Password CLI"**. Si no ves la bóveda (vault) del equipo, pide acceso a un administrador.

**3. Comprueba.**

```bash
cd ~/code/keys
rekey ls                       # aparece la lista de claves: rekey funciona
op vault get "Acme - Prod"     # aparecen los datos de la bóveda: 1Password funciona
```

Ya puedes [crear un .env local](usage.md#crear-un-env-local).

## Si rotas claves (5 minutos más)

```bash
rekey setup
```

Te dice lo que falta y lo resuelve en el momento:
- Inicio de sesión en las CLI de las plataformas que uses (`vercel`, `railway`, `supabase`, `gcloud`, `gh`…): rekey ejecuta el comando de inicio de sesión y tú solo apruebas en el navegador.
- Claves de administrador (opcional): con ellas, las claves de OpenAI, Cloudflare y Resend se emiten sin navegador. Se guardan en su propia bóveda, `<equipo> - Admin`.

Has terminado cuando diga que todo está listo. `rotate` hace la misma comprobación cada vez que empieza.

## Si tu equipo empieza a usar rekey

Empieza desde el [ejemplo](https://github.com/golbin/rekey-example) (**Use this template** → repositorio privado), o ejecuta esto una vez en un repositorio de datos del equipo vacío:

```bash
mkdir ~/code/keys && cd ~/code/keys && git init
rekey init --vault "Acme - Prod" --source vercel --source supabase --source railway --source gcp:<proyecto>
rekey arrange "Acme - {env}"   # una bóveda por entorno, una clave por proyecto
rekey import all               # guarda en 1Password los valores que se usan hoy
git add . && git commit -m "rekey: initial templates"
```

- `init` lee los archivos .env bajo `~/code` y las plataformas, y escribe las plantillas. Los valores iguales se agrupan en una sola clave, con nombre `<project>.<service>` según el proyecto que más la usa. Un proyecto es un repositorio git, un servicio de Railway o un proyecto de Vercel.
- `arrange` mueve cada clave a la bóveda de su entorno (`Acme - Prod`, `Acme - Dev`, `Acme - Local`) y separa las claves que comparten varios proyectos o entornos, para que una clave filtrada apunte a un solo sitio. Da acceso a Dev y Local a todo el equipo; deja Prod para los pocos que lo necesitan.
- `init` nunca cambia plantillas ni nombres de claves existentes, así que puedes volver a ejecutarlo con más `--source` sin riesgo.
- Revisa el resultado con `git diff`. Las líneas bajo un comentario `# …: guessed` son variables de Vercel cuyo valor no se puede leer y que se emparejaron por nombre.
