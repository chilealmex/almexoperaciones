"""códigos distintos que son el mismo artículo en QMS y en Defontana

Tabla de traducción permanente, no una fusión de una sola vez: el importador
la consulta en cada carga, así que una pareja se confirma una vez y cruza para
siempre.

Sólo crea una tabla nueva: no toca ni lee ninguna existente.

Revision ID: b3e91d6f28ac
Revises: a1c58e3b04d7
"""
import sqlalchemy as sa
from alembic import op


revision = "b3e91d6f28ac"
down_revision = "a1c58e3b04d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "equivalencias_codigos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("codigo_qms", sa.String(length=80), nullable=False),
        sa.Column("codigo_defontana", sa.String(length=80), nullable=False),
        sa.Column("clave_qms", sa.String(length=80), nullable=False),
        sa.Column("clave_defontana", sa.String(length=80), nullable=False),
        sa.Column("puntaje", sa.Integer(), nullable=True),
        sa.Column("motivo", sa.String(length=120), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("creado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "clave_defontana", name="uq_equivalencia_defontana"),
    )
    op.create_index("ix_equivalencias_codigos_empresa_id", "equivalencias_codigos", ["empresa_id"])
    op.create_index("ix_equivalencias_codigos_clave_qms", "equivalencias_codigos", ["clave_qms"])
    op.create_index("ix_equivalencias_codigos_clave_defontana", "equivalencias_codigos", ["clave_defontana"])


def downgrade():
    op.drop_index("ix_equivalencias_codigos_clave_defontana", table_name="equivalencias_codigos")
    op.drop_index("ix_equivalencias_codigos_clave_qms", table_name="equivalencias_codigos")
    op.drop_index("ix_equivalencias_codigos_empresa_id", table_name="equivalencias_codigos")
    op.drop_table("equivalencias_codigos")
