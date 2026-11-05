"""Las cuentas del Libro Mayor que arman la propuesta del F29

El F29 se llena con lo que las cuentas de impuestos movieron en el mes. Esas
cuentas se van subiendo de a una desde el mayor de Defontana y se quedan
guardadas, con su movimiento separado por mes y por tipo de documento, que es
como el formulario las pide: las facturas del giro en un código, las de
importación en otro y las notas de crédito en otro.

Revision ID: b3f6a1c7d204
Revises: e8b24d7f0a19
"""

import sqlalchemy as sa
from alembic import op

revision = "b3f6a1c7d204"
down_revision = "e8b24d7f0a19"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "f29_cuentas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cuenta", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("concepto", sa.String(length=20), nullable=True),
        sa.Column("signo", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("archivo", sa.String(length=255), nullable=True),
        sa.Column("lineas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cargas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cargado_en", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("cargado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["cargado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cuenta", name="uq_f29_cuenta"),
    )
    op.create_table(
        "f29_movimientos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cuenta_id", sa.Integer(), nullable=False),
        sa.Column("mes", sa.String(length=7), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("debe", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("haber", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lineas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documentos", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["cuenta_id"], ["f29_cuentas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cuenta_id", "mes", "tipo", name="uq_f29_movimiento"),
    )
    op.create_index("ix_f29_movimientos_cuenta_id", "f29_movimientos", ["cuenta_id"])
    op.create_index("ix_f29_movimientos_mes", "f29_movimientos", ["mes"])


def downgrade():
    op.drop_index("ix_f29_movimientos_mes", table_name="f29_movimientos")
    op.drop_index("ix_f29_movimientos_cuenta_id", table_name="f29_movimientos")
    op.drop_table("f29_movimientos")
    op.drop_table("f29_cuentas")
