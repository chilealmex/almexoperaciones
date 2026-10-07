/* El Informe de Artículos: el stock valorizado, con la hora en que se sacó.

   El Informe de Documentos son movimientos: el saldo y el valor de hoy salen de
   arrastrar la última fila. Eso se descuadra cuando entre dos fechas se borra o
   se modifica un comprobante —el arrastre no se entera— o cuando Defontana
   revaloriza por su cuenta. El Informe de Artículos es la foto de lo que
   Defontana tiene de verdad en un momento, y manda sobre el arrastre: el ajuste
   de costo hay que hacerlo contra el valor que el sistema tiene, no contra el
   que debería tener según sus movimientos.

   Con sus archivos reales los dos coinciden en el 97,5% de las cantidades y el
   97,6% de los valores; el 2% que no coincide es lo que se avisa. */
const {porId} = require('./entorno.js');
const {compute, parseMov, parseArticulos, comoEstaHoy, valorizacionImposible, avisoDeFechas, state} =
  require('../../app/static/js/regularizacion.js');

let fallas = 0, hechas = 0;

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

// --- Leer el archivo ---

const CABECERA = [
  ['Informe de Articulos', '', '', '', ''],
  ['Empresa: Shaw Almex Chile SpA', '', '', '', ''],
  ['Fecha de generación: 06-10-2026, 04:17 p. m.', '', '', '', ''],
  ['Filtros: Bodega: Todas  |  Artículo: Todos', '', '', '', ''],
  ['', '', '', '', ''],
  ['Artículo', 'Descripción', 'Stock Disponible', 'Costo Vigente', 'Costo Reposicion'],
];
const hoja = (...filas) => [...CABECERA, ...filas];

escenario('Lee el stock, el costo y la hora en que se sacó', () => {
  const a = parseArticulos(hoja(['BRP-003', 'BROCHA 3"', 209, 1233.82, 0],
                                ['AAA', 'OTRO', 30, 1000, 0]));
  comprobar('dos artículos', 2, a.length);
  comprobar('el código', 'BRP-003', a[0].art);
  comprobar('el stock', 209, a[0].stock);
  comprobar('el costo vigente', 1233.82, a[0].costo);
  comprobar('y el valorizado sale de los dos', 257868.38, Math.round(a[0].valor * 100) / 100);
  comprobar('la hora de la foto', '06-10-2026, 04:17 p. m.', a.fecha);
});

escenario('Si el archivo no trae la hora, no se la inventa', () => {
  const sinFecha = parseArticulos([CABECERA[5], ['AAA', 'OTRO', 30, 1000, 0]]);
  comprobar('fecha nula', null, sinFecha.fecha);
  comprobar('pero los datos se leen igual', 30, sinFecha[0].stock);
});

escenario('Si no es el archivo que corresponde, lo dice', () => {
  let msg = '';
  try { parseArticulos([['Artículo', 'Movimiento'], ['AAA', 'Ingreso']]); }
  catch (e) { msg = e.message; }
  comprobar('avisa qué columnas faltan', true, /Stock Disponible/.test(msg));
  let msg2 = '';
  try { parseArticulos([['Artículo', 'Stock Disponible'], ['AAA', 5]]); }
  catch (e) { msg2 = e.message; }
  comprobar('y si falta el costo, también', true, /Costo Vigente/.test(msg2));
});

// --- Que la foto mande ---

const DIA = (a, m, d) => new Date(a, m - 1, d);
const ing = (q, cu, d) => ({kind: 'in', qty: q, cu, fecha: DIA(2026, 8, d)});

function docsDe(lista) {
  let s = 0, v = 0;
  return lista.map((d, i) => {
    let valor = d.cu * d.qty;
    if (d.kind === 'in') { s += d.qty; v += valor; }
    else { const p = s > 0 ? v / s : 0; valor = p * d.qty; s -= d.qty; v -= valor; }
    return {art: 'AAA', key: 'AAA', nameKey: 'NAAA', tipo: 'FACTURA', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo: s, valor, valorInv: v, um: '',
            orig: 'C', dest: 'C', estado: 'Aprobado', motivo: '', desc: 'PROD AAA'};
  });
}

// 10 a $0 y 20 a $1.000: los movimientos dan 30 unidades por $20.000.
const MOVS = [ing(10, 0, 1), ing(20, 1000, 2)];

function pantalla(foto) {
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  // El monto del ajuste de costo sale del costo escrito a mano: sin eso sólo
  // se muestran las cifras. Estas pruebas lo escriben para comprobar el monto.
  state.hechos = new Map(); state.pmpEdit = new Map([['AAA', 1000]]); state.ajustes = [];
  state.articulos = foto || null;
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  const docs = docsDe(MOVS);
  state.mov = docs;
  const out = compute(docs);
  return {r: out.rows[0], docs};
}

const foto = (stock, costo) => parseArticulos(hoja(['AAA', 'PROD AAA', stock, costo, 0]));

escenario('Sin foto, todo sigue saliendo de los movimientos', () => {
  const p = pantalla(null);
  comprobar('no hay nada que avisar', null, p.r.fotoDifiere);
  comprobar('el ajuste se mide contra los $20.000 del arrastre', 10000, Math.round(p.r.cost.corr.ajuste));
});

escenario('Con foto que coincide, tampoco cambia nada', () => {
  const p = pantalla(foto(30, 20000 / 30));
  comprobar('no avisa diferencia', null, p.r.fotoDifiere);
  comprobar('mismo ajuste', 10000, Math.round(p.r.cost.corr.ajuste));
});

escenario('Si Defontana tiene otro valor, manda la foto', () => {
  // Defontana dice que las 30 valen $120.000 (y no $20.000): puede haberse
  // borrado un comprobante entre medio, o haber revalorizado.
  const p = pantalla(foto(30, 4000));
  comprobar('avisa que no cuadra', true, !!p.r.fotoDifiere);
  comprobar('el valor del arrastre', 20000, Math.round(p.r.fotoDifiere.valorMov));
  comprobar('y el de la foto', 120000, Math.round(p.r.fotoDifiere.valor));
  comprobar('el ajuste se mide contra la foto, no contra el arrastre',
            -90000, Math.round(p.r.cost.corr.ajuste));
  comprobar('y lo explica', true, /no coincide con lo que dan los movimientos/.test(p.r.obs.join(' ')));
  comprobar('diciendo que puede haberse borrado un comprobante', true,
            /borrado o modificado un comprobante/.test(p.r.obs.join(' ')));
});

escenario('Si Defontana tiene otra cantidad, también avisa', () => {
  const p = pantalla(foto(25, 20000 / 30));
  comprobar('avisa', true, !!p.r.fotoDifiere);
  comprobar('es por la cantidad', true, p.r.fotoDifiere.cantMal);
  comprobar('los movimientos dan 30', 30, Math.round(p.r.fotoDifiere.hoyMov));
  comprobar('y Defontana tiene 25', 25, p.r.fotoDifiere.stock);
});

escenario('El stock y el costo de hoy salen de la foto', () => {
  // La foto dice 25 unidades a $4.000; los movimientos dan 30 a $666,67. Si se
  // tomara el stock del arrastre, el ajuste saldría por 30 unidades que no
  // están y el inventario quedaría descuadrado al revés.
  const docs = docsDe(MOVS);
  state.articulos = foto(25, 4000);
  const hoy = comoEstaHoy(docs, 1000);
  comprobar('el stock es el de la foto, no el del arrastre', 25, hoy.stock);
  comprobar('el PMP es el Costo Vigente', 4000, Math.round(hoy.pmp));
  comprobar('el valor es stock por costo', 100000, Math.round(hoy.valor));
  comprobar('debería valer lo habitual por las que hay', 25000, Math.round(hoy.deberiaValer));
  comprobar('así que sobran $75.000', -75000, Math.round(hoy.ajuste));
  // Con el stock del arrastre (30) habría dado otra cosa
  comprobar('y no es lo que daría con el arrastre', true, Math.round(hoy.deberiaValer) !== 30000);
  state.articulos = null;
});

escenario('Valor sin unidades: las unidades de la foto, el valor de la contabilidad', () => {
  // En la foto el valor es stock por costo, así que con stock 0 siempre da 0.
  // Si se tomara el valor de ahí, este caso no se vería nunca: hay que cruzar
  // las unidades reales con el valor contabilizado del informe de documentos.
  const docs = docsDe(MOVS);
  state.articulos = null;
  comprobar('según los movimientos las 30 unidades valen algo: nada raro',
            null, valorizacionImposible(docs));
  // Defontana ya no tiene unidades, pero el inventario sigue valorizado
  state.articulos = foto(0, 0);
  const malo = valorizacionImposible(docs);
  comprobar('con la foto aparece el valor sin unidades', 'valorSinStock', (malo || {}).cual);
  comprobar('con el valor que trae la contabilidad', 20000, Math.round((malo || {}).valor));
  comprobar('y sin unidades', 0, (malo || {}).saldo);
  state.articulos = null;
});

escenario('El mismo producto con varios códigos en la foto: se suman', () => {
  // En su archivo el stock valorizado trae 0506507001 con 0 unidades y
  // 506507001 con 2, o 42400-014 Rev.2 / 42400-014Rev.2 / 42400-014Rev2 con el
  // stock en uno solo. Quedándose con el primero, si ése es el que tiene 0, el
  // producto parece sin unidades: cuatro de las seis "valorizaciones
  // imposibles" que salían eran eso.
  const docs = docsDe(MOVS);
  state.articulos = parseArticulos(hoja(
    ['0AAA', 'PROD AAA', 0, 2699, 0],
    ['AAA', 'PROD AAA', 2, 4278, 0]));
  const hoy = comoEstaHoy(docs, 1000);
  comprobar('las unidades se suman', 2, hoy.stock);
  comprobar('y el valor también', 8556, Math.round(hoy.valor));
  comprobar('el costo es el promedio ponderado', 4278, Math.round(hoy.pmp));
  comprobar('no es una valorización imposible', null, valorizacionImposible(docs));
  state.articulos = null;
});

escenario('Sin unidades en ninguno de sus códigos, el costo que queda es el que hay', () => {
  const docs = docsDe(MOVS);
  state.articulos = parseArticulos(hoja(
    ['AAA-X', 'PROD AAA', 0, 0, 0],
    ['AAA', 'PROD AAA', 0, 1193505, 0]));
  const hoy = comoEstaHoy(docs, 1000);
  comprobar('cero unidades', 0, hoy.stock);
  // El informe de documentos todavía le tiene valor: eso sí está mal
  const malo = valorizacionImposible(docs);
  comprobar('y el inventario sigue valorizado: imposible', 'valorSinStock', (malo || {}).cual);
  state.articulos = null;
});

escenario('Stock negativo según la foto', () => {
  const docs = docsDe(MOVS);
  state.articulos = foto(-3, 1000);
  comprobar('se marca', 'stockNegativo', (valorizacionImposible(docs) || {}).cual);
  state.articulos = null;
});

// --- El Informe de Inventario ---
//
// Defontana da dos informes de stock valorizado. El de Inventario es mejor:
// trae el Total valorizado de verdad y la bodega, en vez de obligar a
// multiplicar stock por costo. Pero sólo lista lo que tiene stock.

const INV = (...filas) => [
  ['Informe de Inventario'], ['Empresa: Shaw Almex Chile SpA'],
  ['Fecha de generación: 07-10-2026, 09:20 a. m.'], [],
  ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
  ...filas,
];

escenario('Lee el Informe de Inventario, con su bodega y su Total', () => {
  const a = parseArticulos(INV(['BRP-003', 'BROCHA 3"', 'BODEGA CENTRAL', 209, 'UN', 1233.82, 257867.45]));
  comprobar('un artículo', 1, a.length);
  comprobar('el saldo', 209, a[0].stock);
  comprobar('el valor unidad', 1233.82, a[0].costo);
  comprobar('la bodega', 'BODEGA CENTRAL', a[0].bodega);
  comprobar('el valor es el Total, no saldo por costo', 257867.45, a[0].valor);
  comprobar('y se sabe que el valor es de verdad', true, a.valorReal);
  comprobar('la hora', '07-10-2026, 09:20 a. m.', a.fecha);
});

escenario('El de Artículos sigue sirviendo, pero su valor es calculado', () => {
  const a = parseArticulos(hoja(['AAA', 'PROD AAA', 30, 1000, 0]));
  comprobar('lo lee igual', 30, a[0].stock);
  comprobar('pero el valor es stock por costo', false, a.valorReal);
});

escenario('Un artículo en varias bodegas se suma', () => {
  const docs = docsDe(MOVS);
  state.articulos = parseArticulos(INV(
    ['AAA', 'PROD AAA', 'BODEGA CENTRAL', 20, 'UN', 1000, 20000],
    ['AAA', 'PROD AAA', 'BODEGA INSUMOS', 10, 'UN', 1500, 15000]));
  const hoy = comoEstaHoy(docs, 1000);
  comprobar('las unidades de las dos bodegas', 30, hoy.stock);
  comprobar('y los totales', 35000, Math.round(hoy.valor));
  comprobar('el costo es el promedio ponderado', 1167, Math.round(hoy.pmp));
  state.articulos = null;
});

escenario('Con el Total de verdad se ve el valor sin unidades', () => {
  // Con el de Artículos esto es invisible: el valor es saldo por costo y con
  // saldo 0 siempre da 0. Con el Total de Defontana se ve directo.
  const docs = docsDe(MOVS);
  state.articulos = parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 0, 'UN', 0, 7500]));
  const malo = valorizacionImposible(docs);
  comprobar('se marca', 'valorSinStock', (malo || {}).cual);
  comprobar('con el Total que trae el informe', 7500, Math.round(malo.valor));
  state.articulos = null;
});

escenario('Lo que no está en el Informe de Inventario, Defontana lo da por agotado', () => {
  // Ese informe sólo lista lo que tiene stock. Si el producto no está pero la
  // contabilidad le tiene valor, es justo el caso "valorizado sin unidades".
  const docs = docsDe(MOVS);
  state.articulos = parseArticulos(INV(['OTRO', 'OTRO PRODUCTO', 'BODEGA CENTRAL', 5, 'UN', 100, 500]));
  const malo = valorizacionImposible(docs);
  comprobar('se marca', 'valorSinStock', (malo || {}).cual);
  comprobar('con el valor de la contabilidad', 20000, Math.round(malo.valor));
  // Pero eso NO se usa para calcular ajustes: ahí sigue mandando el arrastre.
  // Dando por agotado lo que falta, el ajuste saldría por todo el valor del
  // producto, y si el informe viniera filtrado se propondría eso en masa.
  comprobar('el valor de hoy no se calcula sobre un stock inventado', 20000,
            Math.round(comoEstaHoy(docs, 1000).valor));
  const r = pantalla(parseArticulos(INV(['OTRO', 'OTRO PRODUCTO', 'BODEGA CENTRAL', 5, 'UN', 100, 500]))).r;
  comprobar('y el ajuste de costo tampoco: se mide contra el arrastre',
            10000, Math.round(r.cost.corr.ajuste));
  state.articulos = null;
});

escenario('Un producto con dos códigos, y el inventario bajo uno solo', () => {
  // DURALUMINIO-6082 y N-DURALUMINIO-6082 son el mismo producto: el informe de
  // documentos trae los dos y el de inventario sólo el segundo. Mirando el
  // código del primer documento, el producto parecía agotado y salía como
  // valorizado sin unidades, cuando tiene 14 unidades por $161.954.
  const docs = docsDe(MOVS).map((m, i) => i === 0 ? {...m, art: 'X-AAA', key: 'XAAA'} : m);
  state.articulos = parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 30, 'UN', 1000, 30000]));
  comprobar('encuentra el stock por el otro código', 30, comoEstaHoy(docs, 1000).stock);
  comprobar('y no lo da por agotado', null, valorizacionImposible(docs));
  state.articulos = null;
});

// --- Los dos informes, de momentos distintos ---
//
// Se bajan por separado y es fácil que queden de días distintos. Si el de
// documentos es más viejo, le faltan movimientos y los productos que "no
// cuadran" pueden ser sólo eso.

const DOCS = (gen, ...filas) => [
  ['Informe de Documentos de Inventario'], ['Empresa: Shaw Almex Chile SpA'],
  ['Fecha de generación: ' + gen], [],
  ['Tipo Documento', 'Estado', 'Folio', 'Fecha', 'Bod. Origen', 'Bod. Destino', 'Motivo',
   'Movimiento', 'Proveedor', 'Referencia', 'Cliente', 'Artículo', 'Descripción',
   'Cant. Movimiento', 'U. Medida', 'Valor Movimiento', 'Saldo Inventario', 'Valor Inventario'],
  ...filas,
];
const UNA_FILA = fecha => ['PARTE DE ENTRADA', 'Aprobado', 1, fecha, '', 'BODEGA CENTRAL', 'COMPRA',
                  'Ingreso', '', '', '', 'AAA', 'PROD AAA', 10, 'UN', 10000, 10, 10000];

// El informe llega hasta donde llegue lo que esté más lejos: la cabecera o el
// último movimiento. Por eso las pruebas fijan los dos.
function avisoCon(genDocs, genInv, ultimoMov = '02-01-2026') {
  state.mov = parseMov(DOCS(genDocs, UNA_FILA(ultimoMov)));
  state.articulos = parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 10, 'UN', 1000, 10000])
    .map(r => r[0] && String(r[0]).startsWith('Fecha de generación') ? ['Fecha de generación: ' + genInv] : r));
  return avisoDeFechas();
}

escenario('Avisa cuando el informe de documentos está atrasado', () => {
  const aviso = avisoCon('25-09-2026, 09:01 a. m.', '07-10-2026, 09:20 a. m.');
  comprobar('avisa', true, !!aviso);
  comprobar('dice cuántos días', true, /12 días de diferencia/.test(aviso || ''));
  comprobar('y nombra los dos informes', true,
            /25-09-2026.*07-10-2026/.test(aviso || ''));
  comprobar('y qué hacer', true, /Vuelve a bajarlo/.test(aviso || ''));
});

escenario('No avisa cuando están al mismo momento', () => {
  comprobar('mismo día y hora', null, avisoCon('07-10-2026, 09:20 a. m.', '07-10-2026, 09:20 a. m.'));
  comprobar('unas horas de diferencia no son nada',
            null, avisoCon('07-10-2026, 09:20 a. m.', '07-10-2026, 11:40 a. m.'));
});

escenario('Tampoco avisa si el de documentos es el más nuevo', () => {
  // Ahí no faltan movimientos: sobran, y eso el cálculo ya lo maneja.
  comprobar('sin aviso', null, avisoCon('07-10-2026, 09:20 a. m.', '25-09-2026, 09:01 a. m.'));
});

escenario('La tarde se lee como tarde', () => {
  // "11:00 p. m." leído como las 11 de la mañana son doce horas de error. Acá
  // entre los dos informes hay 10 horas —nada que avisar—, pero leyendo mal la
  // tarde serían 22 y saldría un aviso falso.
  comprobar('diez horas de diferencia: sin aviso',
            null, avisoCon('06-10-2026, 11:00 p. m.', '07-10-2026, 09:00 a. m.', '07-10-2026'));
  // Y al revés, la tarde del día anterior sí deja movimientos fuera
  comprobar('diecisiete horas sí avisan', true,
            /un día de diferencia/.test(avisoCon('06-10-2026, 04:19 p. m.', '07-10-2026, 09:20 a. m.') || ''));
});

escenario('Se cuenta por días, no por horas', () => {
  // Los movimientos no traen hora: quedan a medianoche. Restando timestamps,
  // un inventario sacado a las 8 de la tarde suma casi un día de más y el
  // aviso dice dos días donde hay uno.
  // Sin cabecera manda el movimiento, que queda a medianoche del 07
  const aviso = avisoCon('', '08-10-2026, 08:00 p. m.', '07-10-2026');
  comprobar('avisa', true, !!aviso);
  comprobar('y dice un día, no dos', true, /un día de diferencia/.test(aviso || ''));
  comprobar('no dos', false, /2 días/.test(aviso || ''));
});

escenario('Sin fecha en la cabecera manda el último movimiento', () => {
  // Es lo que pasa cuando los datos se pegan en un Excel que ya existía: la
  // cabecera miente o no está, y el último movimiento es lo único fiable.
  comprobar('sin cabecera pero con movimientos al día, no avisa', null,
            avisoCon('', '07-10-2026, 09:20 a. m.', '07-10-2026'));
  comprobar('sin cabecera y con movimientos viejos, avisa', true,
            /llega hasta el 02-01-2026/.test(avisoCon('', '07-10-2026, 09:20 a. m.') || ''));
  // Y con la cabecera vieja pero movimientos nuevos, tampoco avisa: fue
  // exactamente su caso, un informe que decía 25-09 y traía octubre
  comprobar('cabecera vieja y movimientos nuevos: manda el movimiento', null,
            avisoCon('25-09-2026, 09:01 a. m.', '07-10-2026, 09:20 a. m.', '07-10-2026'));
  state.mov = []; state.articulos = null;
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
