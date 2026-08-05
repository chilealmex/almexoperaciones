"""submodulo dif tc pr/cl

Revision ID: b7f4c2a81e39
Revises: a3e7d91c5b26
Create Date: 2026-08-05 18:00:00.000000

Dos tablas para la contabilización mensual de la diferencia de tipo de cambio:
el período (un mes, con su tipo de cambio de cierre) y sus líneas del mayor.
Guardar un período por mes permite conservar el historial: el tipo de cambio
cambia mes a mes y lo ya contabilizado no debe moverse.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7f4c2a81e39'
down_revision = 'a3e7d91c5b26'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'periodos_dif_tc',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('tipo_cambio', sa.Float(), nullable=False),
        sa.Column('estado', sa.String(length=15), nullable=False),
        sa.Column('notas', sa.String(length=255), nullable=True),
        sa.Column('creado_en', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('empresa_id', 'anio', 'mes', name='uq_periodo_dif_tc_mes'),
    )
    op.create_table(
        'lineas_dif_tc',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('periodo_id', sa.Integer(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('cuenta', sa.String(length=30), nullable=True),
        sa.Column('descripcion', sa.String(length=150), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=True),
        sa.Column('tipo', sa.String(length=30), nullable=True),
        sa.Column('numero', sa.String(length=30), nullable=True),
        sa.Column('id_ficha', sa.String(length=30), nullable=True),
        sa.Column('ficha', sa.String(length=150), nullable=True),
        sa.Column('cargo', sa.BigInteger(), nullable=False),
        sa.Column('abono', sa.BigInteger(), nullable=False),
        sa.Column('saldo', sa.BigInteger(), nullable=False),
        sa.Column('codigo_doc', sa.String(length=40), nullable=True),
        sa.Column('documento', sa.String(length=120), nullable=True),
        sa.Column('vencimiento', sa.String(length=20), nullable=True),
        sa.Column('numero_doc', sa.String(length=40), nullable=True),
        sa.Column('tipo_mov', sa.String(length=40), nullable=True),
        sa.Column('serie', sa.String(length=40), nullable=True),
        sa.Column('numero_mov', sa.String(length=40), nullable=True),
        sa.Column('moneda_ref', sa.String(length=20), nullable=True),
        sa.Column('comentario', sa.String(length=255), nullable=True),
        sa.Column('doc_pago', sa.String(length=40), nullable=True),
        sa.Column('numero_doc_pago', sa.String(length=40), nullable=True),
        sa.Column('serie_doc_pago', sa.String(length=40), nullable=True),
        sa.Column('mon_orig', sa.Float(), nullable=True),
        sa.Column('valor_clp', sa.BigInteger(), nullable=False),
        sa.Column('dif_cambio', sa.BigInteger(), nullable=False),
        sa.Column('pct_variacion', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['periodo_id'], ['periodos_dif_tc.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('lineas_dif_tc', schema=None) as batch_op:
        batch_op.create_index('ix_lineas_dif_tc_periodo', ['periodo_id'], unique=False)


def downgrade():
    with op.batch_alter_table('lineas_dif_tc', schema=None) as batch_op:
        batch_op.drop_index('ix_lineas_dif_tc_periodo')
    op.drop_table('lineas_dif_tc')
    op.drop_table('periodos_dif_tc')
