"""historial de regularizaciones guardadas

Al empezar una regularización nueva, lo que estaba en uso (archivos y estado)
se copia a estas tablas para poder volver a verlo cuando se quiera.

Revision ID: c4d82a7f1e39
Revises: b3e91d6f28ac
"""
from alembic import op
import sqlalchemy as sa


revision = "c4d82a7f1e39"
down_revision = "b3e91d6f28ac"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "regularizacion_historial",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=150), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("creado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_regularizacion_historial_empresa_id", "regularizacion_historial", ["empresa_id"])
    op.create_table(
        "regularizacion_historial_archivos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("historial_id", sa.Integer(), nullable=False),
        sa.Column("clave", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=True),
        sa.Column("contenido", sa.LargeBinary(), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["historial_id"], ["regularizacion_historial.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_regularizacion_historial_archivos_historial_id", "regularizacion_historial_archivos", ["historial_id"])


def downgrade():
    op.drop_index("ix_regularizacion_historial_archivos_historial_id", table_name="regularizacion_historial_archivos")
    op.drop_table("regularizacion_historial_archivos")
    op.drop_index("ix_regularizacion_historial_empresa_id", table_name="regularizacion_historial")
    op.drop_table("regularizacion_historial")
