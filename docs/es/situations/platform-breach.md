# Hackearon una plataforma

Vercel, Railway, Supabase u otra plataforma avisó de que las variables de entorno guardadas pueden haber quedado expuestas.

**1. Elige las claves de esa plataforma.**

```bash
rekey ls 'in:railway/*'        # vercel/*, supabase/*, gcp/* … según la plataforma
```

Si la lista está vacía o parece incompleta, vuelve a leer la plataforma para completar las plantillas. Las plantillas y nombres existentes no cambian.

```bash
rekey init --vault "Acme - Prod" --source railway
```

Si alguna vez subiste un .env local completo a esa plataforma, las claves de ese .env también cuentan. Basta con añadir selectores:

```bash
rekey ls 'in:railway/*' 'in:file/shop/api/*'
```

**2. Rótalas** con los mismos selectores:

```bash
rekey rotate 'in:railway/*' 'in:file/shop/api/*'
```

Los pasos de navegador vienen después de los automáticos. Cuando los despliegues estén sanos, revoca enseguida.

**3. Limpia el lado de la plataforma**
- Rota también los tokens de cuenta y de proyecto de esa plataforma (los que usa la CI). Suelen estar en plantillas `github/…`.
- Revisa a qué puede acceder la app de GitHub de la plataforma (GitHub → Settings → Applications).
- Borra los proyectos que ya no uses.
