"""ad valorem manual por producto del costeo

Revision ID: c47d2e9a5b31
Revises: b26f8a1b1f2d
Create Date: 2026-08-04 21:05:00.000000

Permite escribir a mano el monto de Ad Valorem de una línea de producto,
para cuando la DIN trae un monto distinto al teórico de CIF x tasa. Si la
columna queda en NULL, el monto se sigue calculando automáticamente.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c47d2e9a5b31'
down_revision = 'b26f8a1b1f2d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('costeo_importacion_productos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ad_valorem_manual_clp', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('costeo_importacion_productos', schema=None) as batch_op:
        batch_op.drop_column('ad_valorem_manual_clp')
