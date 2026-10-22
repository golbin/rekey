# Se filtró una clave

Una clave acabó en un commit, en un log o en una captura de pantalla.

```bash
rekey where <nombre de la clave>      # ¿no sabes el nombre? prueba rekey ls '*.openai' o rekey ls project:shop
rekey rotate <nombre de la clave>
```

Redespliega cada servicio cuando te lo pida y luego **responde y cuando pregunte si revocar ya la clave anterior**: no hay motivo para esperar con una clave filtrada. Si no te lo preguntó, algún lugar falló o no se redesplegó: arréglalo con el comando que mostró, despliega y luego ejecuta `rekey revoke <nombre de la clave>`.

Después:
- Una clave que quedó en el historial de git ya está revocada, así que no hace falta reescribir el historial. Si el repositorio era público, revisa en los registros de uso del servicio si hay llamadas que no reconoces.
- Si también pusiste la clave en algún sitio que rekey no conoce (otro repositorio, un equipo personal, el panel de un tercero), cámbiala allí también y añade ese lugar a una plantilla.
