"""cantidades del conteo con decimales

Hay artículos que no se cuentan de a uno: se miden en metros, kilos o litros, y
ahí "12,5" es la cantidad real. Con las columnas en entero no había forma de
registrarlo, y bodega tenía que redondear el conteo físico.

Las cantidades pasan a numeric(22,3). El cambio conserva los valores que ya
están cargados —bigint entra en numeric sin pérdida— y no toca el conteo en
curso; sólo abre los tres decimales.

Revision ID: b7f3d9a04e21
Revises: e4c81a72d5b9
"""
from alembic import op
import sqlalchemy as sa


revision = "b7f3d9a04e21"
down_revision = "e4c81a72d5b9"
branch_labels = None
depends_on = None

# (tabla, columna, admite nulos). Las dos tablas se cambian juntas a propósito:
# al cerrar una toma los valores del cruce vivo se copian tal cual al detalle
# archivado, así que si el archivo siguiera en entero el cierre fallaría.
COLUMNAS = [
    ("items_conteo_inventario", "cantidad_qms", False),
    ("items_conteo_inventario", "cantidad_defontana", False),
    ("items_conteo_inventario", "cantidad_fisica", True),
    ("toma_inventario_detalles", "cantidad_qms", False),
    ("toma_inventario_detalles", "cantidad_defontana", False),
    ("toma_inventario_detalles", "cantidad_fisica", True),
]

# 19 dígitos enteros: el mismo rango que aguantaba el bigint, más 3 decimales.
CANTIDAD = sa.Numeric(22, 3)


def _cambiar(destino, origen):
    for tabla, columna, admite_nulos in COLUMNAS:
        with op.batch_alter_table(tabla) as batch:
            batch.alter_column(
                columna,
                existing_type=origen,
                type_=destino,
                existing_nullable=admite_nulos,
                postgresql_using=f"{columna}::{destino.compile()}",
            )


def upgrade():
    _cambiar(CANTIDAD, sa.BigInteger())


def downgrade():
    # Volver a entero redondea: los decimales que se hayan contado se pierden.
    _cambiar(sa.BigInteger(), CANTIDAD)
