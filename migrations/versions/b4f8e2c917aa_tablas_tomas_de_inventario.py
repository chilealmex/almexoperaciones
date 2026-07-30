"""Tablas para el cierre e historial de tomas de inventario

Revision ID: b4f8e2c917aa
Revises: a1c4f7b93d20
Create Date: 2026-07-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4f8e2c917aa'
down_revision = 'a1c4f7b93d20'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tomas_inventario',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('fecha_inicio', sa.DateTime(), nullable=True),
        sa.Column('fecha_fin', sa.DateTime(), nullable=False),
        sa.Column('cerrado_por_id', sa.Integer(), nullable=False),
        sa.Column('total_articulos', sa.Integer(), nullable=False),
        sa.Column('articulos_contados', sa.Integer(), nullable=False),
        sa.Column('dif_stock', sa.Integer(), nullable=False),
        sa.Column('dif_costo', sa.Integer(), nullable=False),
        sa.Column('dif_unidad', sa.Integer(), nullable=False),
        sa.Column('valor_qms_total', sa.Integer(), nullable=False),
        sa.Column('valor_defontana_total', sa.Integer(), nullable=False),
        sa.Column('valor_fisico_total', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['cerrado_por_id'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'toma_inventario_detalles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('toma_id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=80), nullable=False),
        sa.Column('nombre', sa.String(length=255), nullable=True),
        sa.Column('categoria', sa.String(length=120), nullable=True),
        sa.Column('linea_negocio', sa.String(length=120), nullable=True),
        sa.Column('ubicacion', sa.String(length=255), nullable=True),
        sa.Column('unidad_qms', sa.String(length=20), nullable=True),
        sa.Column('unidad_defontana', sa.String(length=20), nullable=True),
        sa.Column('costo_unitario_qms', sa.Integer(), nullable=True),
        sa.Column('costo_unitario_defontana', sa.Integer(), nullable=True),
        sa.Column('cantidad_qms', sa.Integer(), nullable=False),
        sa.Column('cantidad_defontana', sa.Integer(), nullable=False),
        sa.Column('cantidad_fisica', sa.Integer(), nullable=True),
        sa.Column('contado_por_id', sa.Integer(), nullable=True),
        sa.Column('contado_en', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['contado_por_id'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['toma_id'], ['tomas_inventario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('toma_inventario_detalles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_toma_inventario_detalles_toma_id'), ['toma_id'], unique=False)


def downgrade():
    with op.batch_alter_table('toma_inventario_detalles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_toma_inventario_detalles_toma_id'))
    op.drop_table('toma_inventario_detalles')
    op.drop_table('tomas_inventario')
