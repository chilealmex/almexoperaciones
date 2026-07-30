"""Permisos de usuario a nivel de submódulo

Revision ID: 99a787d146a7
Revises: b4f8e2c917aa
Create Date: 2026-07-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '99a787d146a7'
down_revision = 'b4f8e2c917aa'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('permisos_usuario', schema=None) as batch_op:
        batch_op.add_column(sa.Column('submodulo', sa.String(length=40), nullable=False, server_default=''))
        batch_op.drop_constraint('uq_usuario_modulo', type_='unique')
        batch_op.create_unique_constraint('uq_usuario_modulo_submodulo', ['usuario_id', 'modulo', 'submodulo'])


def downgrade():
    with op.batch_alter_table('permisos_usuario', schema=None) as batch_op:
        batch_op.drop_constraint('uq_usuario_modulo_submodulo', type_='unique')
        batch_op.create_unique_constraint('uq_usuario_modulo', ['usuario_id', 'modulo'])
        batch_op.drop_column('submodulo')
