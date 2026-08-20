"""aceptar diferencias justificadas en la conciliación SII

Hay descuadres que son correctos y no se van a arreglar nunca: las facturas de
combustible llevan impuesto específico, y el SII y Defontana no lo reparten
igual entre neto e impuestos. Marcarlas como revisadas las saca de lo pendiente
sin ocultarlas ni tocar los montos, y deja constancia de quién lo decidió.

Revision ID: a4d7b21c9e38
Revises: c5e1a83f7d40
"""
from alembic import op
import sqlalchemy as sa


revision = "a4d7b21c9e38"
down_revision = "c5e1a83f7d40"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conciliacion_sii_documentos") as batch:
        batch.add_column(sa.Column(
            "aceptado", sa.Boolean(), nullable=False, server_default=sa.false()
        ))
        batch.add_column(sa.Column("motivo_aceptacion", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("aceptado_por_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("aceptado_en", sa.DateTime(), nullable=True))
        batch.create_foreign_key(
            "fk_conciliacion_documento_aceptado_por",
            "usuarios", ["aceptado_por_id"], ["id"],
        )

    with op.batch_alter_table("conciliacion_sii_libros") as batch:
        batch.add_column(sa.Column(
            "n_aceptados", sa.Integer(), nullable=False, server_default="0"
        ))


def downgrade():
    with op.batch_alter_table("conciliacion_sii_libros") as batch:
        batch.drop_column("n_aceptados")

    with op.batch_alter_table("conciliacion_sii_documentos") as batch:
        batch.drop_constraint("fk_conciliacion_documento_aceptado_por", type_="foreignkey")
        batch.drop_column("aceptado_en")
        batch.drop_column("aceptado_por_id")
        batch.drop_column("motivo_aceptacion")
        batch.drop_column("aceptado")
