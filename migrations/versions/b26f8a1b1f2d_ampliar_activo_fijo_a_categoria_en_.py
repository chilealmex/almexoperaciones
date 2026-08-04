"""ampliar activo_fijo a categoria en costeo

Revision ID: b26f8a1b1f2d
Revises: 322f31dc4c1f
Create Date: 2026-08-04 19:45:00.000000

El campo "Activo Fijo" de cada producto del Costeo deja de ser un simple
Sí/No y pasa a guardar el nombre de la categoría de activo fijo elegida
(el mismo catálogo que usa el módulo Activos fijos). Se amplía la columna
para que quepan esos nombres.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b26f8a1b1f2d'
down_revision = '322f31dc4c1f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('costeo_importacion_productos', schema=None) as batch_op:
        batch_op.alter_column(
            'activo_fijo',
            existing_type=sa.String(length=3),
            type_=sa.String(length=80),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table('costeo_importacion_productos', schema=None) as batch_op:
        batch_op.alter_column(
            'activo_fijo',
            existing_type=sa.String(length=80),
            type_=sa.String(length=3),
            existing_nullable=False,
        )
