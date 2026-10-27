/* Subir los archivos sin que se pierdan, y darse cuenta cuando se perdieron.

   Render atiende una petición por proceso. Soltando los cinco archivos
   seguidos salían cinco POST a la vez y los grandes se caían: el 20-10 quedó
   guardado sólo AJUSTES, el más chico. Y cuando uno falla, en el sistema sigue
   el anterior: al recargar vuelve, y se siguen calculando ajustes contra
   movimientos que ya no existen.

   Acá se comprueba que van de a uno, que se reintenta lo que puede andar bien
   al segundo intento, que se dice el motivo, y que un informe bajado dos veces
   se detecta. */
const {porId} = require('./entorno.js');

// El módulo lee su configuración del JSON que la página le deja; sin esto se
// cree sin permiso de guardar y no intenta nada.
porId.set('regx-config', {textContent: JSON.stringify(
  {guardar: true, guardados: {}, url: '/inventario/regularizacion/guardado/__CLAVE__', historial: false, uniones: [], csrf: 't'})});
global.FormData = class { append(){} };

const R = require('../../app/static/js/regularizacion.js');
const {parseMov, avisoDeDuplicados, guardarArchivo, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const archivo = nombre => ({name: nombre});

// ---------- Que vayan de a uno ----------

async function deAUno(){
  console.log('\nLos archivos se suben de a uno, nunca dos a la vez');
  let enVuelo = 0, maximo = 0, pedidos = 0;
  global.fetch = () => {
    pedidos++; enVuelo++; maximo = Math.max(maximo, enVuelo);
    return new Promise(r => setTimeout(() => { enVuelo--; r({ok: true, json: () => Promise.resolve({ok: true})}); }, 20));
  };
  const todos = await Promise.all([
    guardarArchivo('conteo', archivo('conteo.xlsx')),
    guardarArchivo('informe', archivo('documentos.xlsx')),
    guardarArchivo('articulos', archivo('inventario.xlsx')),
  ]);
  comprobar('se mandaron los tres', 3, pedidos);
  comprobar('nunca hubo dos en vuelo', 1, maximo);
  comprobar('los tres se guardaron', 3, todos.filter(x => x && x.ok).length);
}

// ---------- Reintentos ----------

async function reintenta(){
  console.log('\nUn error del servidor se reintenta');
  let n = 0;
  global.fetch = () => { n++; return Promise.resolve(n === 1
    ? {ok: false, status: 502}
    : {ok: true, json: () => Promise.resolve({ok: true})}); };
  const r = await guardarArchivo('informe', archivo('documentos.xlsx'));
  comprobar('lo intentó dos veces', 2, n);
  comprobar('y la segunda quedó guardado', true, !!(r && r.ok));
}

async function noReintentaPermiso(){
  console.log('\nUn error de permiso no se reintenta: no se arregla solo');
  let n = 0;
  global.fetch = () => { n++; return Promise.resolve({ok: false, status: 403}); };
  let msg = null;
  try { await guardarArchivo('conteo', archivo('conteo.xlsx')); } catch(e){ msg = e.message; }
  comprobar('un solo intento', 1, n);
  comprobar('y dice por qué', 'no tienes permiso para guardar (403)', msg);
}

async function diceElMotivo(){
  console.log('\nCuando falla, se dice el motivo y no "no se pudo guardar" a secas');
  global.fetch = () => Promise.resolve({ok: false, status: 413});
  let msg = null;
  try { await guardarArchivo('informe', archivo('documentos.xlsx')); } catch(e){ msg = e.message; }
  comprobar('el motivo con su código', 'el archivo es muy grande (413)', msg);
  global.fetch = () => Promise.resolve({ok: false, status: 418});
  let otro = null;
  try { await guardarArchivo('informe', archivo('documentos.xlsx')); } catch(e){ otro = e.message; }
  comprobar('un código desconocido igual se muestra', 'error del servidor (418)', otro);
}

async function sesionCaida(){
  console.log('\nCon la sesión caída se dice eso, no un error de JSON');
  // El POST termina redirigido a la pantalla de entrar, que contesta 200 con
  // HTML. Antes se veía "Unexpected token '<', "<!doctype"...".
  let n = 0;
  global.fetch = () => { n++; return Promise.resolve({
    ok: true,
    headers: {get: () => 'text/html; charset=utf-8'},
    json: () => Promise.reject(new SyntaxError('Unexpected token \'<\'')),
  }); };
  let msg = null;
  try { await guardarArchivo('conteo', archivo('conteo.xlsx')); } catch(e){ msg = e.message; }
  comprobar('un solo intento: no se arregla solo', 1, n);
  comprobar('y dice qué hacer', 'la sesión expiró: vuelve a entrar y súbelo de nuevo', msg);
}

async function sinRed(){
  console.log('\nSin respuesta del servidor se reintenta y después se avisa');
  let n = 0;
  global.fetch = () => { n++; return Promise.reject(new Error('network')); };
  let msg = null;
  try { await guardarArchivo('conteo', archivo('conteo.xlsx')); } catch(e){ msg = e.message; }
  comprobar('tres intentos', 3, n);
  comprobar('y se dice qué pasó', 'no hubo respuesta del servidor', msg);
}

// ---------- El informe bajado dos veces ----------

const CAB = ['Tipo Documento', 'Folio', 'Fecha', 'Artículo', 'Descripción', 'Movimiento',
             'Cant. Movimiento', 'Saldo Inventario', 'Valor Inventario', 'Estado'];
const linea = (folio, art, cant, saldo) =>
  ['PARTE DE ENTRADA', folio, '10-10-2026', art, 'PROD ' + art, 'INGRESO', cant, saldo, saldo * 100, 'Aprobado'];

function duplicados(){
  console.log('\nUn informe bajado dos veces se detecta');
  const sano = parseMov([CAB, linea('100', 'AAA', 5, 5), linea('101', 'BBB', 3, 3)]);
  comprobar('un informe normal no trae repetidas', 0, sano.repetidas);

  // El mismo documento puede traer dos veces el mismo artículo: es legítimo, y
  // se distingue porque el saldo arrastrado avanza. En sus informes sanos hay
  // 35 o 36 casos así.
  const dosVeces = parseMov([CAB, linea('100', 'AAA', 5, 5), linea('100', 'AAA', 5, 10)]);
  comprobar('dos líneas iguales con distinto saldo no son repetidas', 0, dosVeces.repetidas);

  const bajadoDosVeces = parseMov([CAB, linea('100', 'AAA', 5, 5), linea('101', 'BBB', 3, 3),
                                        linea('100', 'AAA', 5, 5), linea('101', 'BBB', 3, 3)]);
  comprobar('la línea repetida entera sí', 2, bajadoDosVeces.repetidas);

  state.mov = sano; state.mov2 = null; state.ajustes = null;
  comprobar('con el informe sano no se avisa nada', null, avisoDeDuplicados());

  state.mov = bajadoDosVeces;
  const aviso = avisoDeDuplicados();
  comprobar('con el duplicado se avisa', true, !!aviso && aviso.includes('2 líneas repetidas de 4'));
  comprobar('y se dice qué hacer', true, !!aviso && aviso.includes('Vuelve a bajarlo de Defontana'));

  // También los otros dos archivos de movimientos.
  state.mov = sano; state.ajustes = bajadoDosVeces;
  comprobar('el archivo de ajustes también se mira', true, !!(avisoDeDuplicados() || '').includes('El archivo de ajustes'));
  state.ajustes = null; state.mov2 = bajadoDosVeces;
  comprobar('y el informe con los ajustes', true, !!(avisoDeDuplicados() || '').includes('El informe con los ajustes'));
  state.mov2 = null; state.mov = [];
}

(async () => {
  await deAUno();
  await reintenta();
  await noReintentaPermiso();
  await diceElMotivo();
  await sesionCaida();
  await sinRed();
  duplicados();
  console.log(`\n${hechas - fallas}/${hechas} comprobaciones`);
  if (fallas) process.exit(1);
})();
