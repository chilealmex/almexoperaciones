"""marcar en que planilla aparece cada articulo del conteo

Revision ID: a3e7d91c5b26
Revises: f52b8c1e6a94
Create Date: 2026-08-05 16:00:00.000000

Dos marcas por artículo: si vino en la última importación de QMS y si vino en
la de Defontana. Con eso se puede saber cuáles dejaron de existir en ambos
sistemas. Los artículos que ya estaban cargados parten con las dos marcas
puestas, para que nada quede señalado como ausente antes de la próxima
importación.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3e7d91c5b26'
down_revision = 'f52b8c1e6a94'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('items_conteo_inventario', schema=None) as batch_op:
        batch_op.add_column(sa.Column('en_qms', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('en_defontana', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('items_conteo_inventario', schema=None) as batch_op:
        batch_op.drop_column('en_defontana')
        batch_op.drop_column('en_qms')
