# Respaldos de la base de datos

Render en plan gratis no hace copias de seguridad. El repositorio incluye un
respaldo automático propio: `.github/workflows/respaldo-base-datos.yml`.

## Cómo queda funcionando (configuración inicial, una sola vez)

1. En Render, entra a la base de datos y copia la **External Database URL**
   (la interna sólo funciona dentro de Render; desde GitHub no se alcanza).
2. En GitHub: **Settings → Secrets and variables → Actions → New repository secret**
   - Nombre: `DATABASE_URL`
   - Valor: la URL que copiaste
3. Listo. Corre todos los días a las 09:10 UTC (05:10 en Chile).

Para comprobar que quedó bien sin esperar al otro día: pestaña **Actions →
Respaldo de la base de datos → Run workflow**. Si el secreto falta o está mal,
la corrida falla con un mensaje que lo dice.

## Dónde quedan las copias

En **Actions → Respaldo de la base de datos**, entra a una corrida y descarga
el artefacto `respaldo-AAAAMMDD-HHMM.dump`.

Se guardan **90 días** y después se borran solas, que es el máximo que permite
GitHub. Si un respaldo te importa a largo plazo (un cierre contable, por
ejemplo), descárgalo y guárdalo aparte.

## Cómo recuperar un respaldo

El archivo está en formato propio de PostgreSQL, se restaura con `pg_restore`.

### Para revisar qué trae, sin tocar nada

```bash
pg_restore --list respaldo-20260807-0910.dump
```

### Para levantarlo en una base de prueba

Conviene hacerlo siempre así primero, antes de tocar producción:

```bash
createdb almex_prueba
pg_restore --dbname=almex_prueba --no-owner --no-acl respaldo-20260807-0910.dump
```

### Para restaurar sobre producción

> **Cuidado:** esto reemplaza los datos actuales. Antes de hacerlo, genera un
> respaldo del estado presente (Actions → Run workflow), por si necesitas
> volver atrás.

```bash
pg_restore \
  --dbname="postgresql://usuario:clave@host/base" \
  --clean --if-exists --no-owner --no-acl \
  respaldo-20260807-0910.dump
```

`--clean --if-exists` borra cada objeto antes de recrearlo, así no chocan las
tablas que ya existen.

### Recuperar una sola tabla

Si sólo se estropeó una cosa —por ejemplo el conteo de inventario— no hace
falta restaurar todo:

```bash
pg_restore --dbname="..." --table=items_conteo_inventario --data-only \
  respaldo-20260807-0910.dump
```

## Qué verifica el respaldo antes de guardarse

Un archivo vacío o truncado es peor que no tener respaldo, porque da una
sensación falsa de seguridad. Antes de subirlo, la corrida comprueba que:

- pesa más de 1000 bytes;
- `pg_restore --list` puede leer su índice (o sea, no está corrupto);
- trae al menos 5 tablas con datos;
- aparecen `items_conteo_inventario`, `provisiones_ingreso`,
  `costeo_importaciones` y `usuarios`.

Si algo de eso falla, la corrida se marca en rojo y **no** sube el archivo, de
modo que un respaldo malo se nota en vez de pasar desapercibido.
