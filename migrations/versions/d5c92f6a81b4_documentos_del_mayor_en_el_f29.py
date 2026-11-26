"""Cada documento del mayor, para el F29

Los movimientos se guardan agrupados por mes y tipo, que es como el formulario
los declara. Cuando un código no calza con lo declarado hay que poder mirar
factura por factura: en julio de 2026 la diferencia del código 502 resultó ser
una sola, la 5804 por 1.473.479.

Revision ID: d5c92f6a81b4
Revises: c4a81e5d9307
"""

import sqlalchemy as sa
from alembic import op

revision = "d5c92f6a81b4"
down_revision = "c4a81e5d9307"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "f29_documentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cuenta_id", sa.Integer(), nullable=False),
        sa.Column("mes", sa.String(length=7), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("folio", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("rut", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("glosa", sa.String(length=200), nullable=True),
        sa.Column("monto", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lineas", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["cuenta_id"], ["f29_cuentas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cuenta_id", "mes", "tipo", "folio", "rut", name="uq_f29_documento"),
    )
    op.create_index("ix_f29_documentos_cuenta_id", "f29_documentos", ["cuenta_id"])
    op.create_index("ix_f29_documentos_mes", "f29_documentos", ["mes"])


def downgrade():
    op.drop_index("ix_f29_documentos_mes", table_name="f29_documentos")
    op.drop_index("ix_f29_documentos_cuenta_id", table_name="f29_documentos")
    op.drop_table("f29_documentos")
