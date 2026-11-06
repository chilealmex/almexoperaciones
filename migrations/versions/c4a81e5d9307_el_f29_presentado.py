"""El F29 ya presentado, leído de su PDF

Para poder poner lado a lado lo que se declaró y lo que dice la contabilidad.
Se guarda un formulario por mes, con el valor de cada código: volver a subirlo
reemplaza al anterior, que es lo que pasa cuando se rectifica.

Revision ID: c4a81e5d9307
Revises: b3f6a1c7d204
"""

import sqlalchemy as sa
from alembic import op

revision = "c4a81e5d9307"
down_revision = "b3f6a1c7d204"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "f29_declarados",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mes", sa.String(length=7), nullable=False),
        sa.Column("folio", sa.String(length=30), nullable=True),
        sa.Column("archivo", sa.String(length=255), nullable=True),
        sa.Column("cargado_en", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("cargado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["cargado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mes", name="uq_f29_declarado_mes"),
    )
    op.create_table(
        "f29_declarado_codigos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("declarado_id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=6), nullable=False),
        sa.Column("valor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["declarado_id"], ["f29_declarados.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("declarado_id", "codigo", name="uq_f29_declarado_codigo"),
    )
    op.create_index(
        "ix_f29_declarado_codigos_declarado_id", "f29_declarado_codigos", ["declarado_id"]
    )


def downgrade():
    op.drop_index("ix_f29_declarado_codigos_declarado_id", table_name="f29_declarado_codigos")
    op.drop_table("f29_declarado_codigos")
    op.drop_table("f29_declarados")
