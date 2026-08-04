"""estado del costeo: solo en_proceso o cerrado

Revision ID: 322f31dc4c1f
Revises: 17a70d823210
Create Date: 2026-08-04 17:30:00.000000

El estado del Costeo se simplifica de 3 valores (en_proceso, listo,
contabilizado) a 2 (en_proceso, cerrado). Los costeos que ya estaban en
"listo" o "contabilizado" pasan a "cerrado".
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '322f31dc4c1f'
down_revision = '17a70d823210'
branch_labels = None
depends_on = None


costeos = sa.table(
    "costeo_importaciones",
    sa.column("id", sa.Integer),
    sa.column("estado", sa.String),
)


def upgrade():
    conn = op.get_bind()
    conn.execute(
        costeos.update()
        .where(costeos.c.estado.in_(["listo", "contabilizado"]))
        .values(estado="cerrado")
    )


def downgrade():
    pass
