"""tipo de cambio por moneda en dif tc

Revision ID: c8a1f5d37b42
Revises: b7f4c2a81e39
Create Date: 2026-08-05 20:00:00.000000

El tipo de cambio deja de ser uno solo por mes y pasa a ser una tabla por
moneda, como el bloque "Moneda / Tipo de Cambio" de la planilla: cada línea
declara su moneda y se le aplica la que le corresponde.

A los períodos ya cargados se les crean las filas USD y EUR con el tipo de
cambio único que tenían, y sus líneas quedan marcadas como USD, para que
ningún monto cambie con la migración.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8a1f5d37b42'
down_revision = 'b7f4c2a81e39'
branch_labels = None
depends_on = None

tipos_cambio = sa.table(
    'tipos_cambio_dif_tc',
    sa.column('periodo_id', sa.Integer),
    sa.column('moneda', sa.String),
    sa.column('valor', sa.Float),
)


def upgrade():
    op.create_table(
        'tipos_cambio_dif_tc',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('periodo_id', sa.Integer(), nullable=False),
        sa.Column('moneda', sa.String(length=10), nullable=False),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['periodo_id'], ['periodos_dif_tc.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('periodo_id', 'moneda', name='uq_tipo_cambio_dif_tc_moneda'),
    )
    with op.batch_alter_table('tipos_cambio_dif_tc', schema=None) as batch_op:
        batch_op.create_index('ix_tipos_cambio_dif_tc_periodo', ['periodo_id'], unique=False)

    with op.batch_alter_table('lineas_dif_tc', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tipo_moneda', sa.String(length=10), nullable=True))

    conexion = op.get_bind()
    conexion.execute(sa.text("UPDATE lineas_dif_tc SET tipo_moneda = 'USD' WHERE tipo_moneda IS NULL"))
    for periodo_id, valor in conexion.execute(
        sa.text("SELECT id, tipo_cambio FROM periodos_dif_tc")
    ).fetchall():
        for moneda in ("USD", "EUR"):
            conexion.execute(
                tipos_cambio.insert().values(periodo_id=periodo_id, moneda=moneda, valor=valor or 0)
            )


def downgrade():
    with op.batch_alter_table('lineas_dif_tc', schema=None) as batch_op:
        batch_op.drop_column('tipo_moneda')
    with op.batch_alter_table('tipos_cambio_dif_tc', schema=None) as batch_op:
        batch_op.drop_index('ix_tipos_cambio_dif_tc_periodo')
    op.drop_table('tipos_cambio_dif_tc')
