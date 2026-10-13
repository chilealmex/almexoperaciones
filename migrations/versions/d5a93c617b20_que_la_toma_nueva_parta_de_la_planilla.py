"""Que la toma nueva parta de la planilla nueva, no del maestro viejo

Finalizar una toma archivaba el conteo y lo dejaba en blanco, pero los
artículos seguían todos ahí. La toma siguiente empezaba con el maestro de la
anterior, y entre medio pueden haber eliminado un artículo o haberlo dejado
inactivo: bodega terminaba contando cosas que ya no existen.

Esta marca dice si alguna importación de la toma actual ya trajo el artículo.
Al finalizar se apaga en todos; cada importación la enciende en los que trae.
Así Stock y conteo muestra sólo lo que volvió, sin borrar nada: el que no
vuelve queda guardado y fuera de la lista.

Arranca encendida en todas las filas que ya existen. Apagarlas dejaría la
pantalla vacía de golpe, sin que nadie haya finalizado nada.

Revision ID: d5a93c617b20
Revises: b4e81f20a7c3
"""

import sqlalchemy as sa
from alembic import op

revision = "d5a93c617b20"
down_revision = "b4e81f20a7c3"
branch_labels = None
depends_on = None

TABLA = "items_conteo_inventario"
COLUMNA = "importado_en_la_toma"


def upgrade():
    # server_default para que las filas que ya existen queden encendidas, y
    # después se saca: el valor lo pone la aplicación, no la base.
    op.add_column(TABLA, sa.Column(COLUMNA, sa.Boolean(), nullable=False,
                                   server_default=sa.true()))
    op.alter_column(TABLA, COLUMNA, server_default=None)


def downgrade():
    op.drop_column(TABLA, COLUMNA)
