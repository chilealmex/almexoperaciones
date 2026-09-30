"""rastro de la última importación de inventario por sistema

Guarda qué archivo se subió de QMS y de Defontana, cuándo, quién y qué trajo.
Una fila por empresa y por sistema, que se reemplaza en cada subida: la
pregunta que responde es "¿el stock que estoy mirando está al día?".

Sólo crea una tabla nueva: no toca ni lee ninguna existente.

Revision ID: a1c58e3b04d7
Revises: f7c2a9d41e63
"""
import sqlalchemy as sa
from alembic import op


revision = "a1c58e3b04d7"
down_revision = "f7c2a9d41e63"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "importaciones_inventario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("sistema", sa.String(length=20), nullable=False),
        sa.Column("archivo", sa.String(length=255), nullable=True),
        sa.Column("importado_en", sa.DateTime(), nullable=False),
        sa.Column("importado_por_id", sa.Integer(), nullable=True),
        sa.Column("total_codigos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actualizados", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["importado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "sistema", name="uq_importacion_inventario_sistema"),
    )


def downgrade():
    op.drop_table("importaciones_inventario")
