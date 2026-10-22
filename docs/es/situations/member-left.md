# Alguien dejó el equipo

**1. Quita primero su acceso**, antes de cambiar claves:
- Bóvedas de 1Password, la organización de GitHub y el equipo de cada plataforma (Vercel, Railway, Supabase, GCP…)

**2. Rota las claves que podía ver.**

```bash
rekey rotate all                                  # tenía acceso a toda la bóveda
rekey rotate 'in:vercel/shop/*' 'in:file/shop/*'  # solo trabajaba en algunos proyectos
```

Si hay muchas claves, deja que terminen las automáticas y pulsa `q` en los pasos de navegador. Continúa luego con el comando que muestra rekey.

**3. Elimina las claves que creó.** En la lista de claves de cada servicio, borra las que creó esa persona. Las claves creadas por rekey se llaman `rekey-…`.
