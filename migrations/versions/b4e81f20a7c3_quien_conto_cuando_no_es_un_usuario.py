"""Quién contó, cuando no es un usuario del sistema

El conteo físico se puede subir desde un Excel, y la columna "Contado por" de
esa planilla trae el nombre de quien contó en bodega. Muchos de ellos no tienen
cuenta en el sistema, así que no hay a qué usuario apuntar: el nombre escrito es
todo el registro que existe de quién fue.

Se guarda tal cual en una columna de texto, al lado del vínculo al usuario. Si
el nombre sí corresponde a un usuario, manda el vínculo —es el dato más firme— y
esta columna queda vacía.

Va también en los detalles archivados: sin eso, finalizar una toma borraría el
nombre justo cuando pasa a ser historial.

Revision ID: b4e81f20a7c3
Revises: c7d2b9f41a08
"""

import sqlalchemy as sa
from alembic import op

revision = "b4e81f20a7c3"
down_revision = "c7d2b9f41a08"
branch_labels = None
depends_on = None

TABLAS = ("items_conteo_inventario", "toma_inventario_detalles")


def upgrade():
    for tabla in TABLAS:
        op.add_column(tabla, sa.Column("contado_por_texto", sa.String(length=150), nullable=True))


def downgrade():
    for tabla in TABLAS:
        op.drop_column(tabla, "contado_por_texto")
