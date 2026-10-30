"""En qué mes quedó contabilizado un documento de la conciliación con el SII

En Defontana el libro en que cae un documento lo decide su "fecha contable",
que es un campo distinto de la fecha del documento. Cuando esa fecha queda en
el mes equivocado, el documento aparece en un período y falta en el otro sin
que ninguno de los dos sistemas esté mal: el SII lo informa en noviembre y el
libro de Defontana lo tiene en octubre.

Anotar en qué mes quedó explica la fila sin tocar montos.

Revision ID: d7a3f1c80e52
Revises: c5e81b3a92d7
"""

import sqlalchemy as sa
from alembic import op

revision = "d7a3f1c80e52"
down_revision = "c5e81b3a92d7"
branch_labels = None
depends_on = None

_FK = "fk_conciliacion_doc_mes_contable_por"


def _es_sqlite() -> bool:
    """SQLite no sabe agregar una llave foránea a una tabla que ya existe.

    Agregarla obliga a rehacer la tabla entera, y acá no vale la pena: la base
    de verdad es PostgreSQL y en SQLite —que es donde corren las pruebas— las
    columnas quedan igual, sólo que sin la restricción.
    """
    return op.get_bind().dialect.name == "sqlite"


def upgrade():
    op.add_column(
        "conciliacion_sii_documentos",
        sa.Column("mes_contable", sa.String(length=7), nullable=True),
    )
    op.add_column(
        "conciliacion_sii_documentos",
        sa.Column("mes_contable_por_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conciliacion_sii_documentos",
        sa.Column("mes_contable_en", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "conciliacion_sii_libros",
        sa.Column("n_otro_mes", sa.Integer(), nullable=False, server_default="0"),
    )
    if not _es_sqlite():
        op.create_foreign_key(
            _FK, "conciliacion_sii_documentos", "usuarios", ["mes_contable_por_id"], ["id"]
        )


def downgrade():
    if not _es_sqlite():
        op.drop_constraint(_FK, "conciliacion_sii_documentos", type_="foreignkey")
    op.drop_column("conciliacion_sii_libros", "n_otro_mes")
    op.drop_column("conciliacion_sii_documentos", "mes_contable_en")
    op.drop_column("conciliacion_sii_documentos", "mes_contable_por_id")
    op.drop_column("conciliacion_sii_documentos", "mes_contable")
