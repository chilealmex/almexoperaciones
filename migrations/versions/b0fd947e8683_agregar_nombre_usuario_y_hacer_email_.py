"""Agregar nombre_usuario y hacer email opcional

Revision ID: b0fd947e8683
Revises: 1e2f5d1d3eb7
Create Date: 2026-07-24 17:00:05.625945

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b0fd947e8683'
down_revision = '1e2f5d1d3eb7'
branch_labels = None
depends_on = None


def upgrade():
    # Se agrega como nullable primero para poder rellenar filas existentes antes de exigir NOT NULL.
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('nombre_usuario', sa.String(length=50), nullable=True))
        batch_op.alter_column('email',
               existing_type=sa.VARCHAR(length=120),
               nullable=True)

    connection = op.get_bind()
    usuarios = sa.table(
        'usuarios',
        sa.column('id', sa.Integer),
        sa.column('email', sa.String),
        sa.column('nombre_usuario', sa.String),
    )
    for row in connection.execute(sa.select(usuarios.c.id, usuarios.c.email)).fetchall():
        base = (row.email or f"usuario{row.id}").split("@")[0].lower()
        connection.execute(
            usuarios.update().where(usuarios.c.id == row.id).values(nombre_usuario=base)
        )

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.alter_column('nombre_usuario', existing_type=sa.String(length=50), nullable=False)
        batch_op.create_index(batch_op.f('ix_usuarios_nombre_usuario'), ['nombre_usuario'], unique=True)


def downgrade():
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usuarios_nombre_usuario'))
        batch_op.alter_column('email',
               existing_type=sa.VARCHAR(length=120),
               nullable=False)
        batch_op.drop_column('nombre_usuario')
