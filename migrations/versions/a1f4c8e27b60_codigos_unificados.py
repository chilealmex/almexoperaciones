"""códigos retirados al unificar, para que la unión sobreviva a la importación

Unificar dos líneas del mismo artículo borraba una y no guardaba nada. Como el
importador reconoce al artículo por su código, la siguiente planilla volvía a
traer el código retirado y lo creaba de nuevo: el duplicado reaparecía en cada
carga y había que rehacer el trabajo todos los meses.

Esta tabla guarda hacia dónde apunta cada código retirado. Los dos importadores
la consultan antes de buscar el artículo.

Revision ID: a1f4c8e27b60
Revises: c4d82a7f1e39
"""
from alembic import op
import sqlalchemy as sa


revision = "a1f4c8e27b60"
down_revision = "c4d82a7f1e39"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "codigos_unificados",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("codigo_retirado", sa.String(length=80), nullable=False),
        sa.Column("codigo_vigente", sa.String(length=80), nullable=False),
        sa.Column("clave_retirada", sa.String(length=80), nullable=False),
        sa.Column("clave_vigente", sa.String(length=80), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("creado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "empresa_id", "clave_retirada", name="uq_codigo_unificado_retirada"
        ),
    )
    op.create_index(
        "ix_codigos_unificados_empresa_id", "codigos_unificados", ["empresa_id"]
    )
    op.create_index(
        "ix_codigos_unificados_clave_retirada", "codigos_unificados", ["clave_retirada"]
    )
    op.create_index(
        "ix_codigos_unificados_clave_vigente", "codigos_unificados", ["clave_vigente"]
    )


def downgrade():
    op.drop_index("ix_codigos_unificados_clave_vigente", table_name="codigos_unificados")
    op.drop_index("ix_codigos_unificados_clave_retirada", table_name="codigos_unificados")
    op.drop_index("ix_codigos_unificados_empresa_id", table_name="codigos_unificados")
    op.drop_table("codigos_unificados")
