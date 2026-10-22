"""Marcar un artículo del conteo como activo fijo, y guardar su bodega

Revision ID: b4d1f0a27c35
Revises: a7e42d9c5b13
Create Date: 2026-10-22

Un activo fijo no es stock de bodega, pero aparece igual en las planillas de
QMS y de Defontana. La marca permite distinguirlo al contar; va en el artículo,
así que sobrevive a finalizar la toma y a las importaciones siguientes.
"""

import sqlalchemy as sa
from alembic import op

revision = "b4d1f0a27c35"
down_revision = "a7e42d9c5b13"
branch_labels = None
depends_on = None


def upgrade():
    # server_default para las filas que ya existen: la columna es NOT NULL y sin
    # él la migración falla en una base con datos.
    op.add_column(
        "items_conteo_inventario",
        sa.Column("activo_fijo", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("items_conteo_inventario", "activo_fijo", server_default=None)
    # La bodega es el recinto y la ubicación el lugar dentro de él: dos
    # columnas distintas. Defontana ya la mandaba en sus planillas y se leía
    # sin guardarla.
    op.add_column("items_conteo_inventario", sa.Column("bodega", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("items_conteo_inventario", "bodega")
    op.drop_column("items_conteo_inventario", "activo_fijo")
