"""cerrar el período de la conciliación SII

El mes se carga eligiendo año y mes en una lista, y equivocarse en esa lista
reemplazaba en silencio un mes que ya estaba conciliado —los archivos de julio
quedaron cargados también en agosto—. Cerrar el período lo deja de solo
lectura, y sólo un superadmin puede reabrirlo.

Revision ID: d2f6a19c4b73
Revises: a4d7b21c9e38
"""
from alembic import op
import sqlalchemy as sa


revision = "d2f6a19c4b73"
down_revision = "a4d7b21c9e38"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conciliaciones_sii") as batch:
        batch.add_column(sa.Column(
            "estado", sa.String(length=20), nullable=False, server_default="abierto"
        ))
        batch.add_column(sa.Column("cerrado_en", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("cerrado_por_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_conciliacion_sii_cerrado_por",
            "usuarios", ["cerrado_por_id"], ["id"],
        )


def downgrade():
    with op.batch_alter_table("conciliaciones_sii") as batch:
        batch.drop_constraint("fk_conciliacion_sii_cerrado_por", type_="foreignkey")
        batch.drop_column("cerrado_por_id")
        batch.drop_column("cerrado_en")
        batch.drop_column("estado")
