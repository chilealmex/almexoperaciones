"""archivos guardados del submódulo Regularización

Guarda en la base los informes de Defontana subidos a Regularización y el
estado de la pantalla (recuentos, PMP editados, documentos de ajuste), para que
no haya que volver a subirlos cada vez. Van en la base y no en el disco porque
el disco de Render se borra en cada despliegue.

Revision ID: f7c2a9d41e63
Revises: e8b3c04d95f1
"""
from alembic import op
import sqlalchemy as sa


revision = "f7c2a9d41e63"
down_revision = "e8b3c04d95f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "regularizacion_archivos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("clave", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=True),
        sa.Column("contenido", sa.LargeBinary(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "clave", name="uq_regularizacion_empresa_clave"),
    )


def downgrade():
    op.drop_table("regularizacion_archivos")
