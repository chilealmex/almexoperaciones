"""Costo unitario, unidad de medida y categoría en el cruce QMS/Defontana

Revision ID: a1c4f7b93d20
Revises: ec63956c8313
Create Date: 2026-07-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c4f7b93d20'
down_revision = 'ec63956c8313'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('items_conteo_inventario', schema=None) as batch_op:
        batch_op.add_column(sa.Column('categoria', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('costo_unitario_qms', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('costo_unitario_defontana', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('unidad_qms', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('unidad_defontana', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('items_conteo_inventario', schema=None) as batch_op:
        batch_op.drop_column('unidad_defontana')
        batch_op.drop_column('unidad_qms')
        batch_op.drop_column('costo_unitario_defontana')
        batch_op.drop_column('costo_unitario_qms')
        batch_op.drop_column('categoria')
