/* Dos códigos que vienen por separado en un mismo archivo son dos artículos.

   La pantalla cruza los códigos ignorando signos: así hace coincidir
   "AA-STN-2-5,5" de QMS con "AA-STN-2-5.5" de Defontana, que es la misma pieza
   escrita por dos sistemas. Pero cuando los dos códigos vienen en EL MISMO
   archivo, el sistema que lo exportó tiene dos fichas, no una escrita de dos
   maneras: TCA-HEX-3-4 y TCA-HEX-3/4 están los dos en el conteo y los dos en
   Defontana, y la pantalla los juntaba, mostrando el conteo de uno como
   "conteo anterior no usado" del otro. No había cómo separarlos. */
const {elemento, porId} = require('./entorno.js');

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  if (esperado === obtenido) { console.log(`  ✔ ${titulo}`); return; }
  fallas++;
  console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`);
}

// El módulo lee las parejas confirmadas al cargarse, así que para probarlas hay
// que volver a cargarlo. De paso queda limpio lo que se separó en el escenario
// anterior.
function conUniones(pares) {
  porId.set('regx-config', Object.assign(elemento(), {
    textContent: JSON.stringify({uniones: pares}),
  }));
  delete require.cache[require.resolve('../../app/static/js/regularizacion.js')];
  const mod = require('../../app/static/js/regularizacion.js');
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  return mod;
}

const DIA = (a, m, d) => new Date(a, m - 1, d);
const iso = d => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
                 '-' + String(d.getDate()).padStart(2, '0');

const CAB_MOV = ['Tipo Documento', 'Estado', 'Folio', 'Fecha', 'Bod. Origen', 'Bod. Destino', 'Motivo',
                 'Movimiento', 'Artículo', 'Descripción', 'Cant. Movimiento', 'U. Medida',
                 'Valor Movimiento', 'Saldo Inventario', 'Valor Inventario'];
const CAB_STOCK = ['Código', 'Nombre', 'Stock físico', 'Fecha del conteo'];
const CAB_QMS = ['Código Único', 'Descripción', 'Stock', 'Unidad', 'Valor unitario'];

// Subir un archivo: se lee y se anotan los códigos que trae, que es lo que
// hace el cargador de la pantalla con cada archivo que entra.
function subir(mod, key, parser, filas) {
  const data = parser(filas);
  mod.state[key] = data;
  mod.anotarChoques(data);
  return data;
}

function conteo(mod, filas) {
  return subir(mod, 'stock', mod.parseStock, [CAB_STOCK,
    ...filas.map(f => [f.code, 'DESCRIPCION DE ' + f.code, f.stock, iso(f.fecha)])]);
}

function documentos(mod, filas) {
  const saldos = new Map();
  const cuerpo = filas.map((f, i) => {
    const saldo = (saldos.get(f.code) || 0) + f.qty;
    saldos.set(f.code, saldo);
    return ['PARTE DE ENTRADA', 'Aprobado', String(i + 1), iso(f.fecha), '', 'CENTRAL', '',
            'Ingreso', f.code, 'DESCRIPCION DE ' + f.code, f.qty, 'UN',
            f.qty * 1000, saldo, saldo * 1000];
  });
  return subir(mod, 'mov', mod.parseMov, [CAB_MOV, ...cuerpo]);
}

function filasDe(mod) {
  mod.state.recount = new Map(); mod.state.hechos = new Map(); mod.state.pmpEdit = new Map();
  mod.state.movCuando = new Map(); mod.state.ajSi = new Set(); mod.state.ajNo = new Set();
  mod.state.rows = mod.compute(mod.state.mov).rows;
  return mod.state.rows;
}

const AYER = DIA(2026, 8, 19), HOY = DIA(2026, 10, 20);

console.log('\nDos códigos del mismo conteo quedan separados');
{
  // Es el caso de TCA-HEX-3-4: contado hace poco, y TCA-HEX-3/4 contado en 0 el
  // 19-08. La pantalla mostraba el segundo como "conteo anterior no usado" del
  // primero, y el conteo de 0 le borraba la cuenta buena.
  const mod = conUniones([]);
  conteo(mod, [{code: 'TCA-HEX-3-4', stock: 4, fecha: HOY},
               {code: 'TCA-HEX-3/4', stock: 0, fecha: AYER}]);
  documentos(mod, [{code: 'TCA-HEX-3-4', qty: 4, fecha: DIA(2026, 7, 1)}]);
  const filas = filasDe(mod);

  comprobar('salen los dos artículos', 2, filas.length);
  const uno = filas.find(r => r.code === 'TCA-HEX-3-4');
  comprobar('cada uno con su propio conteo', 4, uno && uno.s && uno.s.stock);
  comprobar('y sin "conteo anterior no usado" del otro', 0,
            uno && uno.s && uno.s.previos ? uno.s.previos.length : 0);
  const otro = filas.find(r => r.code === 'TCA-HEX-3/4');
  comprobar('el otro queda con el suyo', 0, otro && otro.s ? otro.s.stock : null);
}

console.log('\nEntre archivos distintos siguen cruzando');
{
  // La coma y el punto son la misma pieza escrita por dos sistemas: QMS la
  // escribe "AA-STN-2-5,5" y Defontana "AA-STN-2-5.5". Separarlas dejaría el
  // artículo faltando por un lado y sobrando por el otro.
  const mod = conUniones([]);
  conteo(mod, [{code: 'AA-STN-2-5,5', stock: 7, fecha: HOY}]);
  documentos(mod, [{code: 'AA-STN-2-5.5', qty: 7, fecha: DIA(2026, 7, 1)}]);
  const filas = filasDe(mod);

  comprobar('es un solo artículo', 1, filas.length);
  comprobar('con el conteo puesto', 7, filas[0].s && filas[0].s.stock);
  comprobar('y los movimientos del otro código', 7, filas[0].sysAtCount);
}

console.log('\nLa separación vale aunque el choque aparezca en el último archivo');
{
  // Al cargar lo guardado los archivos entran de a uno: el de QMS primero y el
  // conteo después. Las claves repartidas antes de saber del choque tienen que
  // volver a sacarse, o el stock de QMS queda pegado al artículo equivocado.
  const mod = conUniones([]);
  subir(mod, 'qms', mod.parseQms, [CAB_QMS, ['TCA-HEX-3-4', 'TUERCA', 9, 'UN', 100]]);
  conteo(mod, [{code: 'TCA-HEX-3-4', stock: 4, fecha: HOY},
               {code: 'TCA-HEX-3/4', stock: 0, fecha: AYER}]);
  documentos(mod, [{code: 'TCA-HEX-3-4', qty: 4, fecha: DIA(2026, 7, 1)}]);
  const filas = filasDe(mod);
  mod.computeQms();

  comprobar('siguen siendo dos', 2, filas.length);
  const cel = (code, col) => {
    const r = filas.find(f => f.code === code);
    return r ? mod.regExport(r)[col] : 'no está la fila de ' + code;
  };
  comprobar('el stock de QMS cae en el código que QMS nombra', 9, cel('TCA-HEX-3-4', 'Stock QMS'));
  comprobar('y el otro no se queda con stock que no es suyo', '', cel('TCA-HEX-3/4', 'Stock QMS'));
  comprobar('que QMS no lo tenga se dice', 'No está en QMS', cel('TCA-HEX-3/4', 'Cruce con QMS'));
}

console.log('\nEl choque también se ve en el informe de Defontana');
{
  // El Informe de Inventario del 27-10 trae los dos códigos, y el de
  // Documentos los mueve por separado: ahí Defontana ya dijo que son dos
  // artículos, aunque el conteo traiga sólo uno de ellos.
  const mod = conUniones([]);
  conteo(mod, [{code: 'TCA-HEX-3-4', stock: 4, fecha: HOY}]);
  documentos(mod, [{code: 'TCA-HEX-3-4', qty: 4, fecha: DIA(2026, 7, 1)},
                   {code: 'TCA-HEX-3/4', qty: 9, fecha: DIA(2026, 7, 2)}]);
  const filas = filasDe(mod);

  comprobar('son dos artículos', 2, filas.length);
  const otro = filas.find(r => r.code === 'TCA-HEX-3/4');
  comprobar('el que no se contó queda sin conteo', true, !(otro && otro.s));
  comprobar('con su propio saldo', 9, otro ? otro.sysNow : null);
}

console.log('\nUna pareja confirmada a mano manda sobre la separación');
{
  // Si son el mismo artículo de verdad, se unen en Unificar códigos y la
  // pantalla respeta esa decisión aunque los dos códigos vengan en el conteo.
  const mod = conUniones([['TCA-HEX-3/4', 'TCA-HEX-3-4']]);
  conteo(mod, [{code: 'TCA-HEX-3-4', stock: 4, fecha: HOY},
               {code: 'TCA-HEX-3/4', stock: 0, fecha: AYER}]);
  documentos(mod, [{code: 'TCA-HEX-3-4', qty: 4, fecha: DIA(2026, 7, 1)}]);
  const filas = filasDe(mod);

  comprobar('queda un solo artículo', 1, filas.length);
  comprobar('con el conteo más nuevo', 4, filas[0].s && filas[0].s.stock);
}

console.log('\nLos ceros de relleno no separan nada');
{
  // "011-CON-OTH-01" y "11-CON-OTH-01" son el mismo código para el maestro: el
  // cero lo pone quien exporta. Vengan juntos o separados, es un artículo.
  const mod = conUniones([]);
  conteo(mod, [{code: '011-CON-OTH-01', stock: 3, fecha: HOY},
               {code: '11-CON-OTH-01', stock: 3, fecha: AYER}]);
  documentos(mod, [{code: '11-CON-OTH-01', qty: 3, fecha: DIA(2026, 7, 1)}]);

  comprobar('sigue siendo un solo artículo', 1, filasDe(mod).length);
}

console.log('\nUn espacio de más tampoco');
{
  // QMS escribe "EM-R-Pantalla BG3" y Defontana "EM-R-PantallaBG3": el espacio
  // no cambia de qué artículo se habla, ni dentro ni fuera del archivo.
  const mod = conUniones([]);
  conteo(mod, [{code: 'EM-R-Pantalla BG3', stock: 2, fecha: HOY}]);
  documentos(mod, [{code: 'EM-R-PantallaBG3', qty: 2, fecha: DIA(2026, 7, 1)}]);

  comprobar('un artículo', 1, filasDe(mod).length);
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
