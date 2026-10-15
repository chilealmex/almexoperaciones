"""OT internas: el registro que vivía en una planilla

Dos tablas y no una. En la planilla el número de OTI se repite: la misma orden
puede tener varios ítems, hasta 32 en un caso. Medido sobre esas 909 líneas,
dentro de una misma OTI el cliente, la fecha, el estado, la sucursal y la línea
de negocio son siempre los mismos; lo único que cambia de una línea a otra es la
cantidad y la descripción.

El número es único por empresa: es la identidad de la orden, y repetirlo sería
tener dos órdenes distintas con el mismo nombre en boca de todos.

Revision ID: f3c70e5b91d4
Revises: d5a93c617b20
"""

import sqlalchemy as sa
from alembic import op

revision = "f3c70e5b91d4"
down_revision = "d5a93c617b20"
branch_labels = None
depends_on = None

# El mismo tipo que las cantidades del conteo: hay trabajos que se encargan en
# metros o kilos, no sólo en piezas. Los números son los de PRECISION y
# DECIMALES en app/utils/cantidades.py, escritos acá porque una migración no
# debe depender del código de la aplicación: tiene que poder correr tal como
# está aunque ese archivo cambie mañana.
CANTIDAD = sa.Numeric(22, 3)


def upgrade():
    op.create_table(
        "ordenes_trabajo_internas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("fecha_inicio", sa.Date(), nullable=True),
        sa.Column("fecha_termino", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=10), nullable=False),
        sa.Column("customer", sa.String(length=120), nullable=True),
        sa.Column("cliente", sa.String(length=120), nullable=True),
        sa.Column("sucursal", sa.String(length=40), nullable=True),
        sa.Column("linea_negocio", sa.String(length=40), nullable=True),
        sa.Column("ot_qms", sa.String(length=30), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.Column("creado_por_id", sa.Integer(), nullable=True),
        sa.Column("actualizado_en", sa.DateTime(), nullable=True),
        sa.Column("actualizado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuarios.id"]),
        sa.ForeignKeyConstraint(["actualizado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "numero", name="uq_oti_numero"),
    )
    op.create_index("ix_ordenes_trabajo_internas_empresa_id", "ordenes_trabajo_internas", ["empresa_id"])
    op.create_index("ix_ordenes_trabajo_internas_numero", "ordenes_trabajo_internas", ["numero"])
    op.create_index("ix_ordenes_trabajo_internas_estado", "ordenes_trabajo_internas", ["estado"])

    op.create_table(
        "items_oti",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("oti_id", sa.Integer(), nullable=False),
        sa.Column("cantidad", CANTIDAD, nullable=True),
        sa.Column("descripcion", sa.String(length=500), nullable=False),
        sa.ForeignKeyConstraint(["oti_id"], ["ordenes_trabajo_internas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_items_oti_oti_id", "items_oti", ["oti_id"])


def downgrade():
    op.drop_index("ix_items_oti_oti_id", table_name="items_oti")
    op.drop_table("items_oti")
    for indice in ("estado", "numero", "empresa_id"):
        op.drop_index(f"ix_ordenes_trabajo_internas_{indice}", table_name="ordenes_trabajo_internas")
    op.drop_table("ordenes_trabajo_internas")
