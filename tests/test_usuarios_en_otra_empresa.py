"""Cuentas repartidas en más de una empresa: verlo y arreglarlo.

Todo lo que muestra el sistema —inventario, contratos, activos, contabilidad—
está filtrado por la empresa del usuario. Dos cuentas en empresas distintas
trabajan sobre datos distintos sin que nada lo diga: cada una ve una pantalla
que se ve perfectamente normal, con sus artículos y sus cantidades.

Pasó de verdad. Una cuenta importó las planillas y quedó viendo 494 artículos;
las demás siguieron viendo los ~3.000 de antes, en el computador y en el
celular, y no cambiaba ni recargando ni volviendo a entrar. Desde afuera
parecía que el sistema no se actualizaba para los demás usuarios.

Lo que faltaba no era un arreglo en el inventario: era poder ver que las
cuentas estaban separadas. El listado de usuarios no mostraba la empresa, así
que no había dónde darse cuenta.
"""

from datetime import date

from app.models.conteo_inventario import ItemConteoInventario
from app.models.empresa import Empresa
from app.models.usuario import Rol, Usuario
from tests.conftest import login
from tests.test_permissions import _crear_superadmin


def _otra_empresa(db):
    otra = Empresa(rut="77.111.111-1", razon_social="Otra Empresa SPA")
    db.session.add(otra)
    db.session.commit()
    return otra


def _usuario_en(db, empresa, rol, nombre="Pedro Bodega", usuario="pedro"):
    persona = Usuario(
        empresa_id=empresa.id,
        nombre_completo=nombre,
        nombre_usuario=usuario,
        email=f"{usuario}@test.cl",
        rol_id=rol.id,
    )
    persona.set_password("password123")
    db.session.add(persona)
    db.session.commit()
    return persona


# --- Verlo ----------------------------------------------------------------


def _fila_de(texto, nombre):
    """La fila de esa persona en el listado.

    Se mira la fila y no la página entera: el aviso de arriba también nombra
    las empresas, así que buscarlas en todo el texto daba por buena una tabla
    que no mostraba ninguna.
    """
    cuerpo = texto[texto.index("<tbody>"):texto.index("</tbody>")]
    return next(f for f in cuerpo.split("<tr>") if nombre in f)


def test_el_listado_muestra_la_empresa_de_cada_cuenta(client, db, empresa, roles):
    _crear_superadmin(db, empresa)
    _usuario_en(db, _otra_empresa(db), roles["bodega"])
    login(client, "super@test.cl")

    texto = client.get("/admin/usuarios").get_data(as_text=True)

    assert "Empresa de Prueba SPA" in _fila_de(texto, "Super")
    assert "Otra Empresa SPA" in _fila_de(texto, "Pedro Bodega")


def test_avisa_cuando_las_cuentas_estan_repartidas(client, db, empresa, roles):
    """Es el aviso que faltaba: sin él, la separación no se ve en ninguna parte."""
    _crear_superadmin(db, empresa)
    _usuario_en(db, _otra_empresa(db), roles["bodega"])
    login(client, "super@test.cl")

    texto = client.get("/admin/usuarios").get_data(as_text=True)

    assert "Las cuentas están repartidas en 2 empresas" in texto
    assert "lo que una importa, las otras no lo ven nunca" in texto
    assert "otra empresa" in texto          # la marca en la fila
    assert "/admin/empresas" in texto       # y dónde mirar para decidir


def test_no_avisa_nada_cuando_estan_todas_juntas(client, db, empresa, roles, usuario_admin):
    """El aviso tiene que salir sólo cuando pasa: si saliera siempre, dejaría
    de leerse justo el día que importa."""
    _crear_superadmin(db, empresa)
    login(client, "super@test.cl")

    texto = client.get("/admin/usuarios").get_data(as_text=True)

    assert "repartidas" not in texto
    assert "otra empresa" not in texto


def test_un_admin_normal_solo_ve_las_cuentas_de_su_empresa(client, db, empresa, roles, usuario_admin):
    """Administrar cuentas de otra empresa no es cosa suya, y verlas mezcladas
    sin saber de cuál son es peor que no verlas."""
    _usuario_en(db, _otra_empresa(db), roles["bodega"], nombre="Ajeno", usuario="ajeno")
    login(client, "admin@test.cl")

    texto = client.get("/admin/usuarios").get_data(as_text=True)

    assert "Admin de Prueba" in texto
    assert "Ajeno" not in texto


def test_la_pantalla_de_empresas_dice_donde_esta_cargado_el_trabajo(client, db, empresa, roles):
    """Para decidir cuál es la empresa de verdad hay que ver dónde están los
    datos: la que quedó por error está casi vacía."""
    _crear_superadmin(db, empresa)
    otra = _otra_empresa(db)
    db.session.add_all([
        ItemConteoInventario(empresa_id=empresa.id, codigo="A-1", nombre="Uno",
                             cantidad_qms=1, cantidad_defontana=1),
        ItemConteoInventario(empresa_id=empresa.id, codigo="A-2", nombre="Dos",
                             cantidad_qms=1, cantidad_defontana=1),
        ItemConteoInventario(empresa_id=otra.id, codigo="B-1", nombre="Viejo",
                             cantidad_qms=1, cantidad_defontana=1),
    ])
    db.session.commit()
    login(client, "super@test.cl")

    texto = client.get("/admin/empresas").get_data(as_text=True)
    fila_prueba = texto[texto.index("Empresa de Prueba SPA"):].split("</tr>")[0]
    fila_otra = texto[texto.index("Otra Empresa SPA"):].split("</tr>")[0]

    assert ">2<" in fila_prueba       # sus dos artículos
    assert ">1<" in fila_otra         # el de la otra
    assert "la tuya" in fila_prueba   # y cuál es la de uno


def test_solo_el_superadmin_entra_a_empresas(client, db, empresa, roles, usuario_admin):
    login(client, "admin@test.cl")

    assert client.get("/admin/empresas").status_code == 403


# --- Arreglarlo -----------------------------------------------------------


def _datos_de(usuario, **cambios):
    datos = {
        "nombre_completo": usuario.nombre_completo,
        "nombre_usuario": usuario.nombre_usuario,
        "email": usuario.email,
        "rol_id": usuario.rol_id,
        "activo": "y",
    }
    datos.update(cambios)
    return datos


def test_el_superadmin_mueve_una_cuenta_a_la_empresa_correcta(client, db, empresa, roles):
    """Es el arreglo: la cuenta pasa a ver los datos con los que trabaja el
    resto. No se mueve ni se borra ningún dato, sólo cambia qué ve."""
    _crear_superadmin(db, empresa)
    perdido = _usuario_en(db, _otra_empresa(db), roles["bodega"])
    login(client, "super@test.cl")

    respuesta = client.post(f"/admin/usuarios/{perdido.id}/editar",
                            data=_datos_de(perdido, empresa_id=empresa.id),
                            follow_redirects=True)

    db.session.refresh(perdido)
    assert perdido.empresa_id == empresa.id
    texto = respuesta.get_data(as_text=True)
    assert "pasó de Otra Empresa SPA a Empresa de Prueba SPA" in texto
    assert "deja de ver los de la anterior" in texto
    assert "Nada se borró" in texto


def test_despues_de_moverla_ve_el_mismo_inventario(client, db, empresa, roles):
    """Lo que se reportó: la otra persona no veía lo que se importaba. Movida
    la cuenta, ve exactamente lo mismo."""
    _crear_superadmin(db, empresa)
    perdido = _usuario_en(db, _otra_empresa(db), roles["bodega"])
    db.session.add(ItemConteoInventario(empresa_id=empresa.id, codigo="NUEVO-1",
                                        nombre="Artículo recién importado",
                                        cantidad_qms=5, cantidad_defontana=5))
    db.session.commit()

    login(client, "pedro@test.cl")
    assert "NUEVO-1" not in client.get("/inventario/stock").get_data(as_text=True)
    client.get("/logout", follow_redirects=True)

    login(client, "super@test.cl")
    client.post(f"/admin/usuarios/{perdido.id}/editar",
                data=_datos_de(perdido, empresa_id=empresa.id), follow_redirects=True)
    client.get("/logout", follow_redirects=True)

    login(client, "pedro@test.cl")
    assert "NUEVO-1" in client.get("/inventario/stock").get_data(as_text=True)


def test_un_admin_normal_no_puede_cambiar_la_empresa(client, db, empresa, roles, usuario_admin):
    """Ni por el formulario ni mandando el campo a mano: cambia todos los
    datos que esa persona ve, y no es una edición más."""
    otra = _otra_empresa(db)
    persona = _usuario_en(db, empresa, roles["bodega"])
    login(client, "admin@test.cl")

    formulario = client.get(f"/admin/usuarios/{persona.id}/editar").get_data(as_text=True)
    assert 'name="empresa_id"' not in formulario

    client.post(f"/admin/usuarios/{persona.id}/editar",
                data=_datos_de(persona, empresa_id=otra.id), follow_redirects=True)

    db.session.refresh(persona)
    assert persona.empresa_id == empresa.id


def test_la_cuenta_nueva_queda_en_la_empresa_de_quien_la_crea(client, db, empresa, roles, usuario_admin):
    # Un admin normal sólo puede crear usuarios del rol "usuario".
    rol_usuario = Rol(clave="usuario", nombre="Usuario")
    db.session.add(rol_usuario)
    _otra_empresa(db)   # existe otra: la nueva cuenta no puede caer ahí
    db.session.commit()
    login(client, "admin@test.cl")

    client.post("/admin/usuarios/nuevo", data={
        "nombre_completo": "Nueva Persona", "nombre_usuario": "nueva",
        "email": "nueva@test.cl", "rol_id": rol_usuario.id,
        "password": "password123", "activo": "y",
    }, follow_redirects=True)

    creada = Usuario.query.filter_by(nombre_usuario="nueva").one()
    assert creada.empresa_id == empresa.id


def test_el_cambio_de_empresa_pide_confirmacion_en_pantalla(client, db, empresa, roles):
    """El desplegable cambia con un clic y lo que hace no se ve hasta que
    alguien reclama que no le aparecen sus datos."""
    _crear_superadmin(db, empresa)
    _otra_empresa(db)
    persona = _usuario_en(db, empresa, roles["bodega"])
    login(client, "super@test.cl")

    texto = client.get(f"/admin/usuarios/{persona.id}/editar").get_data(as_text=True)

    assert 'name="empresa_id"' in texto
    assert "data-confirmar-cambio" in texto
    assert "deja de ver los de ésta" in texto
