"""La bodega y la marca de activo fijo, también en la toma cerrada

Revision ID: c5e81b3a92d7
Revises: b4d1f0a27c35
Create Date: 2026-10-26

Al cerrar una toma se guarda una foto de cada artículo. Esa foto no llevaba la
bodega ni la marca de activo fijo, así que el informe de una toma cerrada no
las podía mostrar.

"activo_fijo" queda nulo a propósito en vez de falso: así se distingue una toma
cerrada antes de que existiera la columna —donde el dato no se sabe— de un
artículo que no es activo fijo.
"""

import sqlalchemy as sa
from alembic import op

revision = "c5e81b3a92d7"
down_revision = "b4d1f0a27c35"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("toma_inventario_detalles", sa.Column("bodega", sa.String(length=255), nullable=True))
    op.add_column("toma_inventario_detalles", sa.Column("activo_fijo", sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column("toma_inventario_detalles", "activo_fijo")
    op.drop_column("toma_inventario_detalles", "bodega")
