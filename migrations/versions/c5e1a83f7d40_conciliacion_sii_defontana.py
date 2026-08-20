"""conciliación SII / Defontana de los libros de compras y ventas

Cada mes hay que comprobar que lo que el SII tiene registrado a nombre de la
empresa esté contabilizado igual en Defontana. Se guardan el período, el cruce
de cada libro con sus totales ya calculados, y el detalle documento por
documento con lo que dice cada sistema en cada columna.

Escrita a mano y no autogenerada: el autogenerate arrastraba cambios de índices
ajenos y proponía borrar tablas antiguas que siguen en uso.

Revision ID: c5e1a83f7d40
Revises: b7f3d9a04e21
"""
from alembic import op
import sqlalchemy as sa


revision = "c5e1a83f7d40"
down_revision = "b7f3d9a04e21"
branch_labels = None
depends_on = None

# Los montos van en BigInteger: son sumas de un mes completo de facturación y
# el entero normal de PostgreSQL se queda corto en 2.147 millones.
MONTO = sa.BigInteger


def upgrade():
    op.create_table(
        "conciliaciones_sii",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("anio", sa.Integer(), nullable=False),
        sa.Column("mes", sa.Integer(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "anio", "mes", name="uq_conciliacion_sii_mes"),
    )

    op.create_table(
        "conciliacion_sii_libros",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conciliacion_id", sa.Integer(), nullable=False),
        sa.Column("libro", sa.String(length=10), nullable=False),
        sa.Column("archivo_sii", sa.String(length=255), nullable=True),
        sa.Column("archivo_defontana", sa.String(length=255), nullable=True),
        sa.Column("cargado_en", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
        sa.Column("cargado_por_id", sa.Integer(), nullable=True),
        sa.Column("cargas", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("n_coincide", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_solo_sii", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_solo_defontana", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_dif_monto", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("n_dif_datos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("neto_sii", MONTO(), nullable=False, server_default="0"),
        sa.Column("neto_defontana", MONTO(), nullable=False, server_default="0"),
        sa.Column("exento_sii", MONTO(), nullable=False, server_default="0"),
        sa.Column("exento_defontana", MONTO(), nullable=False, server_default="0"),
        sa.Column("iva_sii", MONTO(), nullable=False, server_default="0"),
        sa.Column("iva_defontana", MONTO(), nullable=False, server_default="0"),
        sa.Column("total_sii", MONTO(), nullable=False, server_default="0"),
        sa.Column("total_defontana", MONTO(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["conciliacion_id"], ["conciliaciones_sii.id"]),
        sa.ForeignKeyConstraint(["cargado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conciliacion_id", "libro", name="uq_conciliacion_sii_libro"),
    )
    op.create_index(
        "ix_conciliacion_sii_libros_conciliacion_id",
        "conciliacion_sii_libros", ["conciliacion_id"],
    )

    op.create_table(
        "conciliacion_sii_documentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("libro_id", sa.Integer(), nullable=False),
        sa.Column("tipo_doc", sa.String(length=10), nullable=False),
        sa.Column("tipo_doc_desc", sa.String(length=60), nullable=True),
        sa.Column("folio", sa.String(length=40), nullable=False),
        sa.Column("fecha", sa.String(length=20), nullable=True),
        sa.Column("rut_sii", sa.String(length=20), nullable=True),
        sa.Column("contraparte_sii", sa.String(length=200), nullable=True),
        sa.Column("rut_defontana", sa.String(length=20), nullable=True),
        sa.Column("contraparte_defontana", sa.String(length=200), nullable=True),
        sa.Column("neto_sii", MONTO(), nullable=False, server_default="0"),
        sa.Column("neto_defontana", MONTO(), nullable=False, server_default="0"),
        sa.Column("exento_sii", MONTO(), nullable=False, server_default="0"),
        sa.Column("exento_defontana", MONTO(), nullable=False, server_default="0"),
        sa.Column("iva_sii", MONTO(), nullable=False, server_default="0"),
        sa.Column("iva_defontana", MONTO(), nullable=False, server_default="0"),
        sa.Column("total_sii", MONTO(), nullable=False, server_default="0"),
        sa.Column("total_defontana", MONTO(), nullable=False, server_default="0"),
        sa.Column("dif_neto", MONTO(), nullable=False, server_default="0"),
        sa.Column("dif_exento", MONTO(), nullable=False, server_default="0"),
        sa.Column("dif_iva", MONTO(), nullable=False, server_default="0"),
        sa.Column("diferencia", MONTO(), nullable=False, server_default="0"),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("diferencia_descrita", sa.String(length=400), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["libro_id"], ["conciliacion_sii_libros.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conciliacion_sii_documentos_libro_id",
        "conciliacion_sii_documentos", ["libro_id"],
    )


def downgrade():
    op.drop_index("ix_conciliacion_sii_documentos_libro_id", table_name="conciliacion_sii_documentos")
    op.drop_table("conciliacion_sii_documentos")
    op.drop_index("ix_conciliacion_sii_libros_conciliacion_id", table_name="conciliacion_sii_libros")
    op.drop_table("conciliacion_sii_libros")
    op.drop_table("conciliaciones_sii")
