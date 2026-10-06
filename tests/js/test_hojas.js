/* De qué hoja del Excel se leen los datos.

   Un informe exportado con una tabla dinámica adelante deja los datos en la
   segunda hoja. Leyendo sólo la primera, el archivo entero fallaba con "no
   encontré las columnas", que suena a archivo equivocado y no a hoja
   equivocada: no había forma de darse cuenta. */
require('./entorno.js');

const CABECERA = ['Tipo Documento', 'Estado', 'Folio', 'Fecha', 'Bod. Origen', 'Bod. Destino',
                  'Motivo', 'Movimiento', 'Artículo', 'Descripción', 'Cant. Movimiento',
                  'U. Medida', 'Valor Movimiento', 'Saldo Inventario', 'Valor Inventario'];
const FILA = ['PARTE DE ENTRADA', 'Aprobado', '1', '2026-01-02', '', 'BODEGA CENTRAL',
              'COMPRA', 'Ingreso', 'ART-1', 'ARTICULO', '5', 'UN', '5000', '5', '5000'];
const DINAMICA = [['Etiquetas de fila', 'Suma de Cant. Movimiento', 'Suma de saldo'],
                  ['ART-1', '5', '5000']];

function libroCon(hojas) {
  global.XLSX = {read: () => ({SheetNames: Object.keys(hojas), Sheets: hojas}),
                 utils: {sheet_to_json: h => h}};
  delete require.cache[require.resolve('../../app/static/js/regularizacion.js')];
  return require('../../app/static/js/regularizacion.js');
}

let fallas = 0, hechas = 0;

// Un escenario que revienta cuenta como falla, no como caída: si no, el
// primero que falla esconde a todos los que vienen detrás.
function escenario(titulo, fn) {
  console.log('\n' + titulo);
  try { fn(); }
  catch (e) { fallas++; hechas++; console.log(`  ✘ reventó: ${e.message}`); }
}

function comprobar(titulo, esperado, obtenido) {
  hechas++;
  if (esperado === obtenido) { console.log(`  ✔ ${titulo}`); return; }
  fallas++;
  console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`);
}

escenario('Con la tabla dinámica adelante (el caso de ella)', () => {
  const mod = libroCon({Hoja1: DINAMICA, Informe: [CABECERA, FILA]});
  const movs = mod.leerDeCualquierHoja(XLSX.read(), mod.parseMov);
  comprobar('encuentra los datos en la segunda hoja', 1, movs.length);
  comprobar('y los lee bien', 'ART-1', movs[0].art);
});

escenario('Con una sola hoja, como siempre', () => {
  const mod = libroCon({Informe: [CABECERA, FILA]});
  comprobar('se lee igual', 1, mod.leerDeCualquierHoja(XLSX.read(), mod.parseMov).length);
});

escenario('Cuando ninguna hoja sirve, el aviso sigue siendo el de antes', () => {
  const mod = libroCon({Hoja1: DINAMICA, Otra: [['a', 'b'], ['1', '2']]});
  let mensaje = '';
  try { mod.leerDeCualquierHoja(XLSX.read(), mod.parseMov); }
  catch (e) { mensaje = e.message; }
  comprobar('dice que no encontró las columnas', true, /Artículo|Movimiento/.test(mensaje));
});

escenario('Una hoja vacía adelante no detiene la búsqueda', () => {
  const mod = libroCon({Vacia: [], Informe: [CABECERA, FILA]});
  comprobar('sigue hasta la que tiene datos', 1, mod.leerDeCualquierHoja(XLSX.read(), mod.parseMov).length);
});

escenario('El reconocimiento de "esto es un Informe" también mira todas las hojas', () => {
  const mod = libroCon({Hoja1: DINAMICA, Informe: [CABECERA, FILA]});
  const filas = mod.filasConLasColumnas(XLSX.read(), ['ARTICULO', 'MOVIMIENTO']);
  comprobar('devuelve las filas de la hoja buena', 'Artículo', filas[0][8]);
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
