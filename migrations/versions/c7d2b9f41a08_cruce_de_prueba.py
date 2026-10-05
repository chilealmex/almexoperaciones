"""Cruce de prueba: dos planillas comparadas sin cargarlas al sistema

Comparar no es importar. El maestro de artículos lo miran todos los submódulos
de Inventario, así que escribir en él para poder ver un cruce le cambia los
datos a todos. Esta tabla guarda sólo lo leído de las dos planillas, por
persona, para que los filtros de la pantalla no obliguen a releer los archivos
en cada clic.

Revision ID: c7d2b9f41a08
Revises: a1f4c8e27b60
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d2b9f41a08"
down_revision = "a1f4c8e27b60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cruce_prueba",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("empresa_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("nombre_qms", sa.String(length=255), nullable=True),
        sa.Column("nombre_defontana", sa.String(length=255), nullable=True),
        sa.Column("datos", sa.LargeBinary(), nullable=False),
        sa.Column("creado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["empresa_id"], ["empresas.id"]),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("empresa_id", "usuario_id", name="uq_cruce_prueba_usuario"),
    )


def downgrade():
    op.drop_table("cruce_prueba")
