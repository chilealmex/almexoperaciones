"""modulo contabilidad: provision de ingresos

Revision ID: f52b8c1e6a94
Revises: e91c4a7b2d05
Create Date: 2026-08-05 14:30:00.000000

Tabla del submódulo "Provisión de Ingresos": una fila por línea de la hoja
Control de la planilla. La línea se identifica por mes, comprobante de
provisión y OT, que no se repiten en el archivo; esa combinación es única
por empresa para que reimportar el mismo Excel no duplique nada.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f52b8c1e6a94'
down_revision = 'e91c4a7b2d05'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'provisiones_ingreso',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empresa_id', sa.Integer(), nullable=False),
        sa.Column('mes_ano', sa.Date(), nullable=False),
        sa.Column('cbte_prov', sa.String(length=30), nullable=False),
        sa.Column('ot', sa.String(length=30), nullable=False),
        sa.Column('monto_provision', sa.Integer(), nullable=False),
        sa.Column('cliente', sa.String(length=200), nullable=True),
        sa.Column('centro_costos', sa.String(length=60), nullable=True),
        sa.Column('rut', sa.String(length=20), nullable=True),
        sa.Column('obs', sa.String(length=255), nullable=True),
        sa.Column('reversa', sa.Integer(), nullable=True),
        sa.Column('mes_reversa', sa.String(length=60), nullable=True),
        sa.Column('cbte_reversa', sa.String(length=60), nullable=True),
        sa.Column('saldo', sa.Integer(), nullable=False),
        sa.Column('creado_en', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('empresa_id', 'mes_ano', 'cbte_prov', 'ot', name='uq_provision_ingreso_linea'),
    )
    with op.batch_alter_table('provisiones_ingreso', schema=None) as batch_op:
        batch_op.create_index('ix_provisiones_ingreso_empresa', ['empresa_id'], unique=False)


def downgrade():
    with op.batch_alter_table('provisiones_ingreso', schema=None) as batch_op:
        batch_op.drop_index('ix_provisiones_ingreso_empresa')
    op.drop_table('provisiones_ingreso')
