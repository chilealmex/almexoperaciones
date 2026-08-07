"""totales de la toma de inventario en bigint

Los tres totales guardan la valorización de TODO el inventario en pesos. El
entero normal de PostgreSQL llega a 2.147.483.647 (unos 2.147 millones), así
que al cerrar una toma de un inventario grande fallaba con "integer out of
range" y no se podía archivar la toma.

Revision ID: d9b3e6c04f18
Revises: c8a1f5d37b42
"""
from alembic import op
import sqlalchemy as sa


revision = "d9b3e6c04f18"
down_revision = "c8a1f5d37b42"
branch_labels = None
depends_on = None

COLUMNAS = ("valor_qms_total", "valor_defontana_total", "valor_fisico_total")


def upgrade():
    with op.batch_alter_table("tomas_inventario") as batch:
        for columna in COLUMNAS:
            batch.alter_column(
                columna,
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=False,
            )


def downgrade():
    with op.batch_alter_table("tomas_inventario") as batch:
        for columna in COLUMNAS:
            batch.alter_column(
                columna,
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                existing_nullable=False,
            )
