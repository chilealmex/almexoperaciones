"""El Libro Mayor en la conciliación con el SII

El mayor dice en qué quedó contabilizado cada documento: el IVA en la cuenta
de IVA y el total en la de proveedores o clientes. Si esos dos calzan con lo
informado, el neto quedó bien, porque neto = total − IVA.

Revision ID: e8b24d7f0a19
Revises: d7a3f1c80e52
"""

import sqlalchemy as sa
from alembic import op

revision = "e8b24d7f0a19"
down_revision = "d7a3f1c80e52"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conciliacion_sii_documentos", sa.Column("iva_mayor", sa.BigInteger(), nullable=True))
    op.add_column("conciliacion_sii_documentos", sa.Column("total_mayor", sa.BigInteger(), nullable=True))
    op.add_column("conciliacion_sii_documentos", sa.Column("mayor_estado", sa.String(length=20), nullable=True))
    op.add_column("conciliacion_sii_documentos", sa.Column("mes_mayor", sa.String(length=7), nullable=True))
    op.add_column(
        "conciliacion_sii_libros",
        sa.Column("n_mayor_dif", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("conciliacion_sii_libros", sa.Column("mayor_cuentas", sa.String(length=255), nullable=True))
    op.add_column("conciliacion_sii_libros", sa.Column("mayor_cargado_en", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("conciliacion_sii_libros", "mayor_cargado_en")
    op.drop_column("conciliacion_sii_libros", "mayor_cuentas")
    op.drop_column("conciliacion_sii_libros", "n_mayor_dif")
    op.drop_column("conciliacion_sii_documentos", "mes_mayor")
    op.drop_column("conciliacion_sii_documentos", "mayor_estado")
    op.drop_column("conciliacion_sii_documentos", "total_mayor")
    op.drop_column("conciliacion_sii_documentos", "iva_mayor")
