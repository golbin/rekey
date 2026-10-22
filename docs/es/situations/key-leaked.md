# Se filtró una clave

Una clave acabó en un commit, en un log o en una captura de pantalla.

```bash
rekey where <nombre de la clave>      # ¿no sabes el nombre? prueba rekey ls 'openai.*'
rekey rotate <nombre de la clave>
```

Al terminar, **responde y cuando pregunte si revocar ya la clave anterior**. No hay motivo para esperar con una clave filtrada. Si no te lo preguntó, algún lugar falló: arréglalo con el comando que mostró y luego ejecuta `rekey revoke <nombre de la clave>`.

Después:
- Una clave que quedó en el historial de git ya está revocada, así que no hace falta reescribir el historial. Si el repositorio era público, revisa en los registros de uso del servicio si hay llamadas que no reconoces.
- Si también pusiste la clave en algún sitio que rekey no conoce (otro repositorio, un equipo personal, el panel de un tercero), cámbiala allí también y añade ese lugar a una plantilla.
