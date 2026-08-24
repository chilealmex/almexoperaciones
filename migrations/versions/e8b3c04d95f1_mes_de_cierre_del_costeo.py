"""mes de cierre de la importación en el costeo

El mes contable en que se cierra la importación no se deduce de la fecha de
llegada: lo que llega a fin de mes suele cerrarse en el mes siguiente. Se
guarda como fecha —siempre el día 1— para poder agrupar y filtrar por mes con
las mismas funciones que el resto del módulo.

Revision ID: e8b3c04d95f1
Revises: d2f6a19c4b73
"""
from alembic import op
import sqlalchemy as sa


revision = "e8b3c04d95f1"
down_revision = "d2f6a19c4b73"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("costeo_importaciones") as batch:
        batch.add_column(sa.Column("mes_cierre", sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table("costeo_importaciones") as batch:
        batch.drop_column("mes_cierre")
