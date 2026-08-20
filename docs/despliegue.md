# Despliegue

## Lo primero que hay que saber

**Render NO está aplicando `render.yaml`.**

Está comprobado: el archivo declara `--workers 2 --threads 8` y el servidor
corre `--workers 3`; el archivo declara un `buildCommand` con cuatro tramos y
el panel tiene tres. El panel quedó congelado en algún punto antes del 1 de
agosto de 2026 y no volvió a sincronizarse. Ya había pasado antes: hay un
commit del 24 de julio que revierte un cambio de nombre con el comentario
"Render no lo aplica via Blueprint sync".

**Consecuencia práctica:** cambiar `render.yaml` no cambia nada en el servidor.
El archivo se mantiene porque describe la configuración correcta y porque sirve
si algún día se reconecta el Blueprint, pero **la fuente de verdad es el panel
de Render**. Cualquier cambio hay que copiarlo a mano.

## La configuración que debe estar en el panel

Render → el servicio → **Settings**.

**Build Command**

```
pip install -r requirements.txt && flask db upgrade && python seeds/seed_dev.py
```

**Start Command**

```
gunicorn wsgi:app --workers 2 --threads 8 --preload --timeout 120 --bind 0.0.0.0:$PORT
```

Los procesos `sync` atienden una petición cada uno: con tres personas usando el
sistema quedaban todos ocupados y el chequeo de salud daba la instancia por
caída. Con hilos se atienden 16 a la vez, y `--preload` carga la aplicación una
sola vez antes de dividirse, que en 512 MB se agradece.

**Health Check Path:** `/healthz`

## La base de datos

Está en **Neon**, no en Render. La variable `DATABASE_URL` se pone a mano en
Render → Environment.

**Tiene que apuntar al endpoint directo, no al `-pooler`.** El pooler corta la
conexión durante un `CREATE TABLE` o un `ALTER TABLE`: el cambio se guarda en
la base pero Alembic nunca recibe la confirmación, y Render da el build por
fallido. Se comprobó cinco veces seguidas: todo despliegue con migración fallaba
a los ~30 segundos, y todo despliegue sin migración pasaba.

```
mal:  ...@ep-XXXX-pooler.c-5.us-east-2.aws.neon.tech/neondb?...
bien: ...@ep-XXXX.c-5.us-east-2.aws.neon.tech/neondb?...
```

Con 2 procesos y 8 hilos nunca se pasa de 16 conexiones, así que la conexión
directa sobra y el pooler no aporta nada a cambio de ese problema.

## Variables que no deben quedar puestas

- **`ADMIN_PASSWORD`**: mientras esté, cada despliegue le reescribe la
  contraseña al usuario admin con ese valor, y queda guardada en texto en el
  panel. Se usa una vez y se borra.
- **`RESET_ADMIN_PASSWORD`**: igual; genera una contraseña nueva en cada
  despliegue y la deja en el log del build.

## Cuando un despliegue falla

1. **Mirar el log del build.** Render → Deploys → clic sobre el **texto** de la
   fila (el hash azul lleva a GitHub, no al log). También sirve **Events** en la
   barra izquierda. Ahí está el error real; sin eso, todo lo demás es adivinar.
2. **Abrir `/estado` en la aplicación** (menú de usuario, sólo admin). Dice si
   la base responde, en qué revisión está y cuántas migraciones le faltan. El
   caso peligroso es que el código esté desplegado y la base atrasada: la
   aplicación arranca igual y falla recién cuando alguien entra a una pantalla
   nueva, y `/estado` lo deja a la vista antes.

   Con una limitación que conviene tener clara: `/estado` pide sesión iniciada,
   y la sesión se valida contra la base. **Si la base está caída no vas a poder
   entrar**, así que esa pantalla sirve para el caso silencioso (todo arriba
   pero desincronizado), no para una caída total. En una caída total el
   síntoma ya es el diagnóstico: no se puede iniciar sesión y todo responde
   con error.
3. **Si el error es de Render** ("Service Unavailable" al desplegar, la lista de
   deploys que no carga), revisar **status.render.com**. No hay nada que
   arreglar del lado del proyecto.

### Un despliegue falló pero la migración sí se aplicó

Es el escenario típico del pooler. El `ALTER` quedó guardado y Alembic no
alcanzó a confirmarlo. Se comprueba en `/estado`: si la revisión de la base ya
es la que espera el código, basta con **Manual Deploy → Deploy latest commit**;
al no quedar nada que migrar, el despliegue pasa.

### Aplicar una migración a mano

Si hace falta, desde el SQL Editor de Neon (rama `production`) se puede ver en
qué quedó todo:

```sql
SELECT version_num FROM alembic_version;
```

Y desde un entorno con el código (por ejemplo un Codespace), apuntando
`DATABASE_URL` a la base de producción:

```
export FLASK_APP=wsgi.py
flask db upgrade
```

**Antes de tocar el esquema, sacar un respaldo**: en Neon, Branches → Create
branch desde el estado actual, con `Auto-delete: Never`. Es instantáneo y no
ocupa espacio hasta que la base cambia.

## Antes de empujar un cambio

Las pruebas corren solas en GitHub Actions con cada push (`.github/workflows/pruebas.yml`).
Si aparece la marca roja en el commit, **no desplegar**: el error está en el
código y se ve en el detalle de esa corrida.

Lo que las pruebas no cubren: problemas del entorno. Una variable mal puesta en
el panel, una conexión que se corta, Render caído. Para eso están el log del
build y `/estado`.
