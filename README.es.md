[English](README.md) · [한국어](README.ko.md) · [中文](README.zh.md) · [日本語](README.ja.md) · **Español**

# rekey

Vuelve a emitir una clave de API con un solo comando, actualízala en todos los lugares donde se usa (.env, Vercel, Railway, Supabase, GCP, GitHub…) y revoca la anterior.

```bash
rekey rotate 'openai.*'   # clave nueva → todos los lugares actualizados → despliegues verificados
rekey revoke 'openai.*'   # clave anterior revocada
```

- No necesitas conocer cada servicio. Las claves que se pueden emitir por API se gestionan solas; para el resto, rekey abre la página correcta y solo tienes que crear la clave y **copiarla**.
- Los valores de las claves nunca aparecen en pantalla. Solo se guardan en 1Password.
- Python 3.11 o superior, solo la biblioteca estándar.
- Por ahora los mensajes de la CLI están en coreano; están previstos mensajes en inglés.

## Cómo funciona

| Qué | Dónde |
|---|---|
| Valores de las claves | 1Password (un elemento por clave) |
| Dónde se usa cada clave y la configuración normal | `targets/**.tpl` en el repositorio privado del equipo |
| Excepciones (bloqueos, etiquetas, notas) | `keys.toml` en el repositorio privado del equipo |

Las plantillas usan la sintaxis propia de 1Password, y la ruta del archivo indica a dónde van los valores.

```
# targets/vercel/shop/production.tpl  →  proyecto de Vercel "shop", production
APP_URL=https://shop.example.com
OPENAI_API_KEY={{ op://Acme - Prod/openai.shop/credential }}
```

## Guías

1. [Preparación](docs/es/setup.md): 10 minutos
2. [Uso](docs/es/usage.md)
3. Situaciones: [Se filtró una clave](docs/es/situations/key-leaked.md) · [Hackearon una plataforma](docs/es/situations/platform-breach.md) · [Alguien dejó el equipo](docs/es/situations/member-left.md)

## Desarrollo

```bash
python3 -m unittest discover -s tests
REKEY_TEST_CLIPBOARD=1 python3 -m unittest discover -s tests -p test_interactive.py   # maneja una terminal real (macOS, usa el portapapeles)
```

MIT License
