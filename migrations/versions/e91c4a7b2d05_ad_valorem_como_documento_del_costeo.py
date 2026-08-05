"""ad valorem como documento del costeo

Revision ID: e91c4a7b2d05
Revises: c47d2e9a5b31
Create Date: 2026-08-04 22:10:00.000000

En la planilla el Ad Valorem es una fila más de la tabla de documentos, con
su N° doc y su T/C. Se agrega esa línea a los costeos ya cargados para que
aparezca en pantalla; queda en cero, así ninguno cambia de monto hasta que
alguien la complete.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e91c4a7b2d05'
down_revision = 'c47d2e9a5b31'
branch_labels = None
depends_on = None

documentos = sa.table(
    'costeo_importacion_documentos',
    sa.column('id', sa.Integer),
    sa.column('costeo_id', sa.Integer),
    sa.column('rol', sa.String),
    sa.column('orden', sa.Integer),
    sa.column('moneda', sa.String),
    sa.column('valor_clp', sa.Integer),
)


def upgrade():
    conexion = op.get_bind()
    costeos_sin_linea = conexion.execute(
        sa.text(
            "SELECT c.id FROM costeo_importaciones c "
            "WHERE NOT EXISTS (SELECT 1 FROM costeo_importacion_documentos d "
            "                  WHERE d.costeo_id = c.id AND d.rol = 'ad_valorem')"
        )
    ).fetchall()
    for (costeo_id,) in costeos_sin_linea:
        conexion.execute(
            documentos.insert().values(
                costeo_id=costeo_id, rol='ad_valorem', orden=8, moneda='USD', valor_clp=0
            )
        )


def downgrade():
    op.get_bind().execute(
        sa.text("DELETE FROM costeo_importacion_documentos WHERE rol = 'ad_valorem'")
    )
