"""cantidades y costos del conteo en bigint

El entero normal de PostgreSQL llega a 2.147.483.647. Una celda de la planilla
con un costo o un stock por sobre ese valor no se guardaba mal: reventaba la
importación completa con un error 500, sin cargar nada y sin decir por qué.

Revision ID: e4c81a72d5b9
Revises: d9b3e6c04f18
"""
from alembic import op
import sqlalchemy as sa


revision = "e4c81a72d5b9"
down_revision = "d9b3e6c04f18"
branch_labels = None
depends_on = None

# (tabla, columna, admite nulos)
COLUMNAS = [
    ("items_conteo_inventario", "cantidad_qms", False),
    ("items_conteo_inventario", "cantidad_defontana", False),
    ("items_conteo_inventario", "cantidad_fisica", True),
    ("items_conteo_inventario", "costo_unitario_qms", True),
    ("items_conteo_inventario", "costo_unitario_defontana", True),
    ("toma_inventario_detalles", "cantidad_qms", False),
    ("toma_inventario_detalles", "cantidad_defontana", False),
    ("toma_inventario_detalles", "cantidad_fisica", True),
    ("toma_inventario_detalles", "costo_unitario_qms", True),
    ("toma_inventario_detalles", "costo_unitario_defontana", True),
]


def _cambiar(destino, origen):
    for tabla, columna, admite_nulos in COLUMNAS:
        with op.batch_alter_table(tabla) as batch:
            batch.alter_column(
                columna,
                existing_type=origen,
                type_=destino,
                existing_nullable=admite_nulos,
            )


def upgrade():
    _cambiar(sa.BigInteger(), sa.Integer())


def downgrade():
    _cambiar(sa.Integer(), sa.BigInteger())
