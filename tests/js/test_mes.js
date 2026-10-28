/* Los movimientos del mes: lo que movió Defontana contra lo que movió QMS.

   Hasta el ajuste de octubre no se hacían todos los documentos que
   correspondían a los movimientos de inventario —por eso hubo que ajustar—,
   así que desde ahí en adelante hay que ir mirando mes a mes si a un sistema
   le faltó registrar algo.

   Los dos no comparten la numeración de sus comprobantes, pero sí la orden de
   trabajo: Defontana la escribe en "Referencia" ("OT 6368") y QMS la trae en
   su columna OTNro. Ésa es la pieza con que se cruzan. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {parseMov, parseMovQms, parseStock, comparacionDelMes, mesesConMovimientos, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  if (esperado === obtenido) { console.log(`  ✔ ${titulo}`); return; }
  fallas++;
  console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`);
}

const CAB_DEFO = ['Tipo Documento', 'Estado', 'Folio', 'Fecha', 'Bod. Origen', 'Bod. Destino', 'Motivo',
                  'Movimiento', 'Proveedor', 'Referencia', 'Cliente', 'Artículo', 'Descripción',
                  'Cant. Movimiento', 'U. Medida', 'Valor Movimiento', 'Saldo Inventario',
                  'Valor Inventario', 'N Requisicion', 'N Doc. Compra'];
const CAB_ING = ['FechaIngreso', 'codigo_unico', 'descripcion_eng', 'CategoriaNombreCorto',
                 'unidad_medida.simbolo', 'CantidadIngreso', 'ValorUnitarioCLP', 'OTNro_nro', 'oc_almex'];
const CAB_EGR = ['Codigo Unico', 'Linea Negocio', 'Categoria', 'Fecha Egreso', 'Valor Egreso',
                 'Cantidad Egreso', 'Valor Unitario', 'OTNro', 'ubicacion_bodega'];

// Una línea del Informe de Documentos de Defontana.
const defo = ({tipo = 'ENVÍO A PRODUCCIÓN', folio = '1', fecha = '2026-10-09', ref = '', art,
               qty, kind = 'out', oc = '', orig = '', dest = ''}) =>
  [tipo, 'Aprobado', folio, fecha, orig || (kind === 'out' ? 'BODEGA CENTRAL' : ''),
   dest || (kind === 'in' ? 'BODEGA CENTRAL' : ''),
   kind === 'out' ? 'SALIDA' : 'COMPRA', kind === 'in' ? 'Ingreso' : 'Egreso', '', ref, '', art,
   'PRODUCTO ' + art, qty, 'UN', qty * 1000, 10, 10000, '', oc];
const ingreso = ({fecha = '2026-10-09', code, qty, ot = '', oc = ''}) =>
  [fecha, code, 'PRODUCTO ' + code, 'TOOLS', 'UN', qty, 1000, ot, oc];
const egreso = ({fecha = '2026-10-09', code, qty, ot = ''}) =>
  [code, 'FUSION', 'COLD BOND', fecha, qty * 1000, qty, 1000, ot, ''];

// Lo que la pantalla tiene cargado: los documentos de Defontana, los
// movimientos de QMS y el conteo con que se detectan los comprobantes de
// ajuste.
function cargar({documentos = [], ingresos = [], egresos = [], conteo = null, ajustar = true} = {}) {
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  state.mov = parseMov([CAB_DEFO, ...documentos]);
  state.stock = parseStock(conteo || [['Código', 'Stock físico', 'Fecha del conteo'], ['NADA', 0, '2026-10-01']]);
  state.qmsMov = [];
  if (ingresos.length) state.qmsMov = state.qmsMov.concat(parseMovQms([CAB_ING, ...ingresos]));
  if (egresos.length) state.qmsMov = state.qmsMov.concat(parseMovQms([CAB_EGR, ...egresos]));
  if (!state.qmsMov.length) state.qmsMov = null;
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map();
  state.movCuando = new Map(); state.ajSi = new Set(); state.ajNo = new Set(); state.ajustes = null;
  state.docGroupsMain = ajustar ? R.detectarAjustes(state.mov) : [];
  return comparacionDelMes('2026-10');
}

const de = (lista, code) => lista.find(x => x.code === code) || {};

// Tres productos contados el 08-10 y un comprobante de salida del 09-10 que
// ajusta justo sus diferencias: así es como se reconoce un comprobante de
// ajuste, por sus líneas, sin que nadie lo marque.
const CONTEO_AJUSTE = [['Código', 'Nombre', 'Stock físico', 'Fecha del conteo'],
  ['INS-500', 'PRODUCTO INS-500', 6, '2026-10-08'],
  ['INS-501', 'PRODUCTO INS-501', 7, '2026-10-08'],
  ['INS-502', 'PRODUCTO INS-502', 8, '2026-10-08']];
const ENTRADAS_PREVIAS = [
  defo({tipo: 'PARTE DE ENTRADA', folio: '400', fecha: '2026-10-01', art: 'INS-500', qty: 10, kind: 'in'}),
  defo({tipo: 'PARTE DE ENTRADA', folio: '400', fecha: '2026-10-01', art: 'INS-501', qty: 10, kind: 'in'}),
  defo({tipo: 'PARTE DE ENTRADA', folio: '400', fecha: '2026-10-01', art: 'INS-502', qty: 10, kind: 'in'})];
const SALIDA_DE_AJUSTE = [
  defo({tipo: 'PARTE DE SALIDA', folio: '311', fecha: '2026-10-09', art: 'INS-500', qty: 4}),
  defo({tipo: 'PARTE DE SALIDA', folio: '311', fecha: '2026-10-09', art: 'INS-501', qty: 3}),
  defo({tipo: 'PARTE DE SALIDA', folio: '311', fecha: '2026-10-09', art: 'INS-502', qty: 2})];

console.log('\nCon la misma OT y la misma cantidad, cuadra');
{
  const c = cargar({
    documentos: [defo({ref: 'OT 6368', art: 'INS-068', qty: 10})],
    egresos: [egreso({code: 'INS-068', qty: 10, ot: '6368'})],
  });
  comprobar('se compara por OT', 1, c.ots.length);
  comprobar('y cuadra', 'ok', de(c.ots, 'INS-068').st);
  comprobar('sin diferencia', 0, de(c.ots, 'INS-068').dif);
  comprobar('nada queda por producto', 0, c.prods.length);
}

console.log('\nLo que Defontana movió y QMS no, se dice');
{
  const c = cargar({
    documentos: [defo({ref: 'OT 6368', art: 'INS-068', qty: 10}),
                 defo({ref: 'OT 6368', art: 'INS-117', qty: 4})],
    egresos: [egreso({code: 'INS-068', qty: 10, ot: '6368'})],
  });
  comprobar('el que falta en QMS', 'falta_qms', de(c.ots, 'INS-117').st);
  comprobar('con lo que movió Defontana', -4, de(c.ots, 'INS-117').d);
  comprobar('y con su documento a la vista', 'ENVÍO A PRODUCCIÓN #1', de(c.ots, 'INS-117').docs.join(', '));
  comprobar('el otro sigue cuadrando', 'ok', de(c.ots, 'INS-068').st);
}

console.log('\nY lo que QMS movió y Defontana no');
{
  const c = cargar({
    documentos: [defo({ref: 'OT 6368', art: 'INS-068', qty: 10})],
    egresos: [egreso({code: 'INS-068', qty: 10, ot: '6368'}),
              egreso({code: 'INS-221', qty: 2, ot: '6368'})],
  });
  comprobar('lo dice', 'falta_defo', de(c.ots, 'INS-221').st);
  comprobar('con lo que movió QMS', -2, de(c.ots, 'INS-221').q);
  comprobar('y la OT de QMS a la vista', 'OT 6368', de(c.ots, 'INS-221').refs.join(', '));
}

console.log('\nSi los dos lo movieron por distinta cantidad, también');
{
  const c = cargar({
    documentos: [defo({ref: 'OT 6379', art: 'INS-103', qty: 2})],
    egresos: [egreso({code: 'INS-103', qty: 4, ot: '6379'})],
  });
  const x = de(c.ots, 'INS-103');
  comprobar('queda marcado', 'dif', x.st);
  comprobar('Defontana sacó 2', -2, x.d);
  comprobar('QMS sacó 4', -4, x.q);
  comprobar('y la diferencia es de 2', -2, x.dif);
}

console.log('\nVarias líneas de la misma OT y producto se suman');
{
  // Defontana puede partir en dos entregas lo que QMS anotó de una vez.
  const c = cargar({
    documentos: [defo({ref: 'OT 6376', art: 'AA-STC-250A', qty: 18, folio: '1'}),
                 defo({ref: 'OT 6376', art: 'AA-STC-250A', qty: 10, folio: '2'})],
    egresos: [egreso({code: 'AA-STC-250A', qty: 28, ot: '6376'})],
  });
  comprobar('es una sola fila', 1, c.ots.length);
  comprobar('y cuadra', 'ok', de(c.ots, 'AA-STC-250A').st);
  comprobar('con los dos documentos a la vista', 'ENVÍO A PRODUCCIÓN #1, ENVÍO A PRODUCCIÓN #2',
            de(c.ots, 'AA-STC-250A').docs.join(', '));
}

console.log('\nLo que no lleva OT se compara por producto');
{
  const c = cargar({
    documentos: [defo({tipo: 'PARTE DE ENTRADA', folio: '475', art: 'BRP-003', qty: 6, kind: 'in'})],
    ingresos: [ingreso({code: 'BRP-003', qty: 6, oc: '14196'})],
  });
  comprobar('no entra por OT', 0, c.ots.length);
  comprobar('sino por producto', 1, c.prods.length);
  comprobar('y cuadra', 'ok', de(c.prods, 'BRP-003').st);
  comprobar('las entradas suman', 6, de(c.prods, 'BRP-003').d);
}

console.log('\nLa orden de compra no cruza mientras Defontana no la traiga');
{
  // La columna "N Doc. Compra" del informe viene vacía en las 1.535 líneas de
  // octubre. Si la OC de QMS se tomara igual, cada ingreso de QMS saldría como
  // "falta en Defontana" por una orden que Defontana nunca escribió.
  const c = cargar({
    documentos: [defo({tipo: 'PARTE DE ENTRADA', folio: '475', art: 'BRP-003', qty: 6, kind: 'in'})],
    ingresos: [ingreso({code: 'BRP-003', qty: 6, oc: '14196'})],
  });
  comprobar('no se usa el espacio de las OC', false, c.espacios.includes('OC'));
  comprobar('y el producto cuadra igual', 'ok', de(c.prods, 'BRP-003').st);
}

console.log('\nY cuando Defontana sí trae la orden de compra, cruza por ella');
{
  const c = cargar({
    documentos: [defo({tipo: 'PARTE DE ENTRADA', folio: '475', art: 'BRP-003', qty: 6, kind: 'in', oc: '14196'}),
                 defo({tipo: 'PARTE DE ENTRADA', folio: '475', art: 'OTRO', qty: 3, kind: 'in', oc: '14196'})],
    ingresos: [ingreso({code: 'BRP-003', qty: 6, oc: '14196'})],
  });
  comprobar('se usa el espacio de las OC', true, c.espacios.includes('OC'));
  comprobar('lo que cuadra, cuadra', 'ok', de(c.ots, 'BRP-003').st);
  comprobar('y lo que no está en QMS se dice', 'falta_qms', de(c.ots, 'OTRO').st);
  comprobar('con la OC a la vista', 'OC 14196', de(c.ots, 'OTRO').ot);
}

console.log('\nLo que no es un movimiento de verdad no se compara');
{
  const c = cargar({
    documentos: [
      // Un traspaso entre bodegas no entra ni sale del inventario.
      defo({tipo: 'TRASPASO ENTRE BODEGAS', folio: '5', art: 'INS-068', qty: 3, kind: 'in',
            orig: 'BODEGA CENTRAL', dest: 'BODEGA INSUMOS'}),
      // Un ajuste de costo mueve plata, no unidades: viene en cantidad 0.
      defo({tipo: 'AJUSTE COSTO ENTRADA', folio: '2', art: 'INS-117', qty: 0, kind: 'in'}),
    ],
    egresos: [egreso({code: 'OTRO', qty: 1, ot: '6368'})],
  });
  comprobar('el traspaso no aparece', true, !c.filas.some(x => x.code === 'INS-068'));
  comprobar('el ajuste de costo tampoco', true, !c.filas.some(x => x.code === 'INS-117'));
}

console.log('\nLos comprobantes del ajuste de inventario van aparte');
{
  // No son un documento que a alguien se le olvidó: son el ponerse al día con
  // lo que no se documentó antes, y es lo que hay que dejar en QMS.
  const c = cargar({
    conteo: CONTEO_AJUSTE,
    documentos: [...ENTRADAS_PREVIAS, ...SALIDA_DE_AJUSTE],
    egresos: [egreso({code: 'OTRO', qty: 1, ot: '6368'})],
  });
  comprobar('los productos ajustados salen en su propio bloque', 3, c.ajustes.length);
  comprobar('y no entre los movimientos normales', false, c.prods.some(x => x.code === 'INS-500'));
  comprobar('marcados como ajuste', true, de(c.ajustes, 'INS-500').ajuste);
}

console.log('\nHacia atrás no se ofrecen meses');
{
  // Hasta el ajuste, los dos sistemas venían con documentos que no se
  // hicieron: comparar septiembre sólo muestra ese desorden.
  cargar({
    conteo: CONTEO_AJUSTE,
    documentos: [defo({tipo: 'ENVÍO A PRODUCCIÓN', folio: '90', fecha: '2026-08-11', art: 'INS-500', qty: 2}),
                 ...ENTRADAS_PREVIAS, ...SALIDA_DE_AJUSTE],
    egresos: [egreso({code: 'INS-500', qty: 2, ot: '6368', fecha: '2026-08-11'})],
  });
  const meses = mesesConMovimientos();
  comprobar('sólo desde el mes del ajuste', '2026-10', meses.join(', '));
}

console.log('\nEl número que QMS pone en los ingresos no es una OT');
{
  // En la hoja de Ingresos la columna OTNro_nro es otra numeración: de sus
  // 2.743 números, 11 existen como OT en el informe de Defontana. Tomándola
  // por OT, cada ingreso de QMS saldría como una OT entera que a Defontana le
  // falta.
  const c = cargar({
    documentos: [defo({ref: 'OT 6368', art: 'INS-068', qty: 10})],
    egresos: [egreso({code: 'INS-068', qty: 10, ot: '6368'})],
    ingresos: [ingreso({code: 'BRP-003', qty: 4, ot: '117450'})],
  });
  comprobar('no aparece una OT 117450', true, !c.ots.some(x => x.ot === 'OT 117450'));
  comprobar('el ingreso se compara por producto', 'falta_defo', de(c.prods, 'BRP-003').st);
  comprobar('y la OT de verdad sigue cuadrando', 'ok', de(c.ots, 'INS-068').st);
}

console.log('\nLas dos hojas del archivo de QMS se leen, no sólo la primera');
{
  // Ingresos y Egresos vienen en hojas distintas del mismo archivo. Con la
  // primera que se deja leer, la mitad de los movimientos del mes no existe.
  const hojas = {Ingresos: [CAB_ING, ingreso({code: 'BRP-003', qty: 4, oc: '14196'})],
                 Egresos: [CAB_EGR, egreso({code: 'INS-068', qty: 10, ot: '6368'})]};
  global.XLSX.utils.sheet_to_json = hoja => hoja;
  const leidos = R.leerDeTodasLasHojas({SheetNames: ['Ingresos', 'Egresos'], Sheets: hojas}, parseMovQms);

  comprobar('se leen los movimientos de las dos', 2, leidos.length);
  comprobar('la entrada', 'in', (leidos.find(m => m.code === 'BRP-003') || {}).kind);
  comprobar('y la salida', 'out', (leidos.find(m => m.code === 'INS-068') || {}).kind);
}

console.log('\nSin archivo de QMS no se inventa que falte nada');
{
  const c = cargar({documentos: [defo({ref: 'OT 6368', art: 'INS-068', qty: 10})]});
  comprobar('la fila existe', 1, c.filas.length);
  // Sin el archivo, "falta en QMS" es lo único que se puede decir, y la
  // pantalla no muestra la tabla hasta que se sube.
  comprobar('y se ve que QMS no trae nada', 0, de(c.filas, 'INS-068').qMovs.length);
}

console.log('\nEl Excel lleva lo mismo que la tabla');
{
  const c = cargar({
    documentos: [defo({ref: 'OT 6368', art: 'INS-117', qty: 4})],
    egresos: [egreso({code: 'INS-068', qty: 10, ot: '6368'})],
  });
  state.mes = '2026-10';
  const x = R.mesExport(de(c.ots, 'INS-117'));
  comprobar('el mes', 'octubre 2026', x['Mes']);
  comprobar('la OT', 'OT 6368', x['OT / OC']);
  comprobar('lo que movió Defontana', -4, x['Movimiento en Defontana']);
  comprobar('que QMS no lo movió', '', x['Movimiento en QMS']);
  comprobar('y qué pasa', 'Falta en QMS', x['Qué pasa']);
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
