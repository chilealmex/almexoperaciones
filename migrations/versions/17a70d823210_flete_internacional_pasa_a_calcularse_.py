"""flete internacional pasa a calcularse con T/C y monto total

Revision ID: 17a70d823210
Revises: cbf67da9ab82
Create Date: 2026-08-04 17:00:00.000000

El Flete Internacional del Costeo dejó de ser un monto CLP directo y ahora se
calcula igual que Invoice/Seguro/Crating: Valor CLP = T/C x Monto Total. Para
no perder el CLP ya cargado en los costeos existentes (donde T/C y Monto Total
nunca se usaron), se completan esos dos campos de forma que la fórmula
reproduzca exactamente el mismo CLP que ya estaba guardado.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '17a70d823210'
down_revision = 'cbf67da9ab82'
branch_labels = None
depends_on = None


documentos = sa.table(
    "costeo_importacion_documentos",
    sa.column("id", sa.Integer),
    sa.column("rol", sa.String),
    sa.column("valor_tc", sa.Float),
    sa.column("valor_total_inv", sa.Float),
    sa.column("valor_clp", sa.Integer),
)


def upgrade():
    conn = op.get_bind()
    conn.execute(
        documentos.update()
        .where(documentos.c.rol == "flete_intl")
        .where(sa.or_(documentos.c.valor_total_inv.is_(None), documentos.c.valor_total_inv == 0))
        .where(documentos.c.valor_clp != 0)
        .values(valor_tc=1, valor_total_inv=documentos.c.valor_clp)
    )


def downgrade():
    pass
