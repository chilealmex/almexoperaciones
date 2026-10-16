"""Varias reversas por provisión, en vez de una sola

Una provisión se reversa a veces en partes, en meses distintos y con un
comprobante cada una. El modelo guardaba una sola, y el mes como texto libre
precisamente porque no alcanzaba: cuando se partía había que escribir
"may-26 y jun-26" en una casilla, y entonces el monto de cada mes ya no se
sabía y el saldo quedaba a ojo.

Lo delicado de esta migración es que no se pierda lo que ya está cargado. Antes
de borrar las tres columnas viejas, cada línea que tenga reversa pasa a ser la
primera fila de la tabla nueva, con su mes y su comprobante tal como estaban
escritos. La vuelta atrás hace el camino inverso y devuelve la suma, con los
meses y los comprobantes juntos en el texto; lo que no cabe de vuelta es el
detalle por mes y las notas, porque en la estructura vieja no hay dónde
ponerlos.

Revision ID: a7e42d9c5b13
Revises: f3c70e5b91d4
"""

import sqlalchemy as sa
from alembic import op

revision = "a7e42d9c5b13"
down_revision = "f3c70e5b91d4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reversas_provision",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provision_id", sa.Integer(), nullable=False),
        sa.Column("monto", sa.Integer(), nullable=False),
        sa.Column("mes", sa.String(length=60), nullable=True),
        sa.Column("comprobante", sa.String(length=60), nullable=True),
        sa.Column("nota", sa.Text(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("creado_por_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["provision_id"], ["provisiones_ingreso.id"]),
        sa.ForeignKeyConstraint(["creado_por_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reversas_provision_provision_id", "reversas_provision", ["provision_id"])

    # Lo que ya estaba cargado pasa a ser la primera reversa de su línea. Va
    # antes de borrar las columnas, que es lo único que hace esta migración
    # irreversible si se hace al revés.
    op.execute(
        """
        INSERT INTO reversas_provision (provision_id, monto, mes, comprobante)
        SELECT id, reversa, mes_reversa, cbte_reversa
        FROM provisiones_ingreso
        WHERE reversa IS NOT NULL AND reversa <> 0
        """
    )

    for columna in ("reversa", "mes_reversa", "cbte_reversa"):
        op.drop_column("provisiones_ingreso", columna)


def downgrade():
    op.add_column("provisiones_ingreso", sa.Column("reversa", sa.Integer(), nullable=True))
    op.add_column("provisiones_ingreso", sa.Column("mes_reversa", sa.String(length=60), nullable=True))
    op.add_column("provisiones_ingreso", sa.Column("cbte_reversa", sa.String(length=60), nullable=True))

    # De vuelta cabe una sola, así que se devuelve la suma de todas con los
    # meses y comprobantes juntos en el texto: es lo mismo que se escribía a
    # mano antes y no pierde el monto total, que es lo que cuadra el saldo.
    op.execute(
        """
        UPDATE provisiones_ingreso p SET
            reversa = s.total,
            mes_reversa = s.meses,
            cbte_reversa = s.comprobantes
        FROM (
            SELECT provision_id,
                   SUM(monto) AS total,
                   LEFT(STRING_AGG(DISTINCT COALESCE(mes, ''), ' y '), 60) AS meses,
                   LEFT(STRING_AGG(DISTINCT COALESCE(comprobante, ''), ' y '), 60) AS comprobantes
            FROM reversas_provision GROUP BY provision_id
        ) s
        WHERE p.id = s.provision_id
        """
    )

    op.drop_index("ix_reversas_provision_provision_id", table_name="reversas_provision")
    op.drop_table("reversas_provision")
