/* El ajuste que propone Regularización.

   La regla: se ajusta la diferencia AL MOMENTO DE CONTAR. Los movimientos
   posteriores no entran, porque ya están registrados en Defontana y volver a
   considerarlos pide ajustar dos veces por lo mismo. */
const {porId} = require('./entorno.js');
const {compute, ajusteDelConteo, pendiente, hoyDe, parseStock, parseArticulos, regRow, regExport, docSteps, state} = require('../../app/static/js/regularizacion.js');

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const DIA = (a, m, d) => new Date(a, m - 1, d);

/* Arma el estado como lo dejaría la lectura de los archivos y corre el cálculo.
   `docs` son las filas del Informe de Documentos, en orden. */
function escenario({contado, fechaConteo, saldoInicial, docs, bodega = '*', soloAprobados = false}) {
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: soloAprobados}));
  // El filtro de bodega de la pantalla: '*' son todas.
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: bodega}));
  state.stock = [{code: 'ART-1', key: 'ART1', name: 'ARTICULO', stock: contado,
                  fecha: fechaConteo, por: 'Bodega', estado: 'Contado', um: '', linea: ''}];
  state.recount = new Map();
  state.manual = new Set();
  state.hechos = new Map();
  state.pmpEdit = state.pmpEdit || new Map();

  let saldo = saldoInicial;
  const movimientos = docs.map((d, i) => {
    saldo += d.kind === 'in' ? d.qty : -d.qty;
    return {art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: d.tipo || 'PARTE', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo, valor: 0, costo: 0,
            orig: d.orig || 'CENTRAL', dest: d.dest || 'CENTRAL', estado: d.estado || 'Aprobado', motivo: '',
            _aj: !!d.ajuste};
  });
  return compute(movimientos).rows[0];
}

console.log('\nEl caso de ella: contó 5, Defontana tenía 3, después entraron 10');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)}],
  });
  comprobar('Defontana tenía 3 al conteo', 3, r.sysAtCount);
  comprobar('y tiene 13 hoy', 13, r.sysCalc);
  comprobar('el ajuste es una ENTRADA POR 2, no una salida por 8', 2, ajusteDelConteo(r));
}

console.log('\nLo mismo, pero mirando sólo una bodega y la entrada fue a otra');
{
  // Acá se rompía: el movimiento posterior no entra en la cuenta por el filtro
  // de bodega, pero el saldo de Defontana sí lo trae. Midiendo contra el saldo
  // de hoy salía una salida por 8 —para "llegar a 5"— con 15 en bodega.
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3, bodega: 'CENTRAL',
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15), dest: 'OTRA', orig: 'OTRA'}],
  });
  comprobar('entrada por 2, no salida por 8', 2, ajusteDelConteo(r));
}

console.log('\nLo mismo, con un documento sin aprobar después del conteo');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 10), saldoInicial: 1,
    docs: [{kind: 'in', qty: 2, fecha: DIA(2026, 9, 5)},
           {kind: 'in', qty: 10, fecha: DIA(2026, 9, 15), estado: 'Pendiente'}],
    soloAprobados: true,
  });
  comprobar('entrada por 2', 2, ajusteDelConteo(r));
}

console.log('\nSin movimientos posteriores al conteo');
{
  // Un artículo sin ningún documento no sale en el Informe, así que siempre
  // hay al menos uno: acá, anterior al conteo.
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 10), saldoInicial: 1,
    docs: [{kind: 'in', qty: 2, fecha: DIA(2026, 9, 5)}],
  });
  comprobar('entrada por 2', 2, ajusteDelConteo(r));
}

console.log('\nSobra stock en Defontana: contó 5 y había 8');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 10), saldoInicial: 6,
    docs: [{kind: 'in', qty: 2, fecha: DIA(2026, 9, 5)}],
  });
  comprobar('Defontana tenía 8 al conteo', 8, r.sysAtCount);
  comprobar('salida por 3', -3, ajusteDelConteo(r));
}

console.log('\nYa se hizo el ajuste: no se puede pedir dos veces');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)},
           {kind: 'in', qty: 2, fecha: DIA(2026, 9, 20), tipo: 'PARTE DE ENTRADA', ajuste: true}],
  });
  comprobar('el ajuste sigue siendo 2 en total', 2, ajusteDelConteo(r));
}

console.log('\nCuadrado: contó 5 y había 5, con movimientos después');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 5,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)},
           {kind: 'out', qty: 4, fecha: DIA(2026, 9, 20)}],
  });
  comprobar('no hay nada que ajustar', 0, ajusteDelConteo(r));
}

console.log('\nMovimientos ANTES del conteo: ésos sí cuentan, están en el saldo');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 10), saldoInicial: 1,
    docs: [{kind: 'in', qty: 2, fecha: DIA(2026, 9, 5)}],
  });
  comprobar('Defontana tenía 3 al conteo', 3, r.sysAtCount);
  comprobar('entrada por 2', 2, ajusteDelConteo(r));
}



console.log('\nLas tres columnas de la pantalla tienen que cuadrar entre sí');
{
  // "Debería tener − tiene = ajuste". Si no cuadran, el número correcto se lee
  // como un error y nadie lo aplica.
  const casos = [
    {titulo: 'todas las bodegas', bodega: '*', ajustado: false},
    {titulo: 'una sola bodega', bodega: 'CENTRAL', ajustado: false},
    {titulo: 'con el ajuste ya hecho', bodega: '*', ajustado: true},
  ];
  for (const c of casos) {
    const docs = [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15), dest: 'OTRA', orig: 'OTRA'}];
    if (c.ajustado) docs.push({kind: 'in', qty: 2, fecha: DIA(2026, 9, 20), ajuste: true});
    const r = escenario({contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3, bodega: c.bodega, docs});
    const hoy = hoyDe(r);
    comprobar(`${c.titulo}: debería tener (${r.realNow}) − tiene (${hoy}) = lo que falta`,
              pendiente(r), r.realNow - hoy);
  }
}

console.log('\nCon el informe completo, "debería tener" es lo de siempre');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)}],
  });
  comprobar('contado + lo que entró después = 15', 15, r.realNow);
}


console.log('\nDespués de registrar el ajuste, no se puede volver a pedir');
{
  // Se contaron 5, Defontana tenía 3, entraron 10 y DESPUÉS se hizo la entrada
  // por 2. Ya está: en bodega hay 15 y Defontana dice 15.
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)},
           {kind: 'in', qty: 2, fecha: DIA(2026, 9, 20), tipo: 'PARTE DE ENTRADA', ajuste: true}],
  });
  comprobar('Defontana tiene 15 hoy', 15, hoyDe(r));
  comprobar('lo que falta ajustar es 0', 0, pendiente(r));
  comprobar('y debería tener 15 hoy, no 17', 15, r.realNow);
}

console.log('\nContado y Defontana no lo tiene: la entrada es por todo lo contado');
{
  /* BRC-003: contó 9 el 21-08-2026 y el producto no tiene un solo documento
     en el informe ni saldo en el stock valorizado. Antes quedaba como "Sin
     saldo en Defontana" y no se proponía nada: 24 productos y 163 unidades
     contadas sin ninguna propuesta. */
  const articulos = parseArticulos([
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
    ['OTRO', 'Otro producto', 'BODEGA CENTRAL', 5, 'UN', 100, 500],
    // El informe lista también los que están en cero: por eso faltar significa
    // que Defontana no tiene el artículo.
    ['EN-CERO', 'Sin stock', 'BODEGA CENTRAL', 0, 'UN', 0, 0]]);
  state.stock = parseStock([['Código', 'Nombre', 'Stock físico', 'Contado por', 'Fecha y hora del conteo'],
                            ['BRC-003', 'Broca', 9, 'Claudio Leyton', '21-08-2026 10:00']]);
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map(); state.movCuando = new Map();
  state.articulos = articulos;
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));

  const r = compute([{art: 'OTRO', key: state.stock[0].key + 'X', nameKey: '', tipo: 'PARTE DE ENTRADA',
                      folio: '1', fecha: DIA(2026, 1, 2), kind: 'in', qty: 5, saldo: 5, valor: 500,
                      costo: 100, orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', _aj: false}])
    .rows.find(x => x.code === 'BRC-003');
  comprobar('Defontana tenía 0 al conteo', 0, r.sysAtCount);
  comprobar('hay que ingresar los 9 contados', 9, ajusteDelConteo(r));
  comprobar('y se dice por qué', true,
            r.obs.some(o => o.includes('Defontana no tiene este producto')));

  // Si el stock valorizado sí lo tiene, el ajuste es la diferencia contra ese
  // saldo: sin movimientos, lo que Defontana tiene hoy es lo que tenía al
  // contar. Proponer la entrada entera metería unidades que ya están.
  state.stock = parseStock([['Código', 'Nombre', 'Stock físico', 'Contado por', 'Fecha y hora del conteo'],
                            ['OTRO', 'Otro producto', 9, 'Claudio Leyton', '21-08-2026 10:00']]);
  const conFoto = compute([]).rows.find(x => x.code === 'OTRO');
  comprobar('Defontana tenía los 5 del stock valorizado', 5, conFoto.sysAtCount);
  comprobar('así que faltan 4, no 9', 4, ajusteDelConteo(conFoto));
  comprobar('y se dice de dónde salió ese saldo', true,
            conFoto.obs.some(o => o.includes('su saldo sale del stock valorizado')));

  // Con documentos en el informe no se usa la foto: el producto se mueve, y
  // el saldo de hoy no es el que tenía al contar.
  state.stock = parseStock([['Código', 'Nombre', 'Stock físico', 'Contado por', 'Fecha y hora del conteo'],
                            ['SIN-SALDO', 'Con documentos sin saldo', 9, 'Claudio Leyton', '21-08-2026 10:00']]);
  const conDocs = compute([{art: 'SIN-SALDO', key: state.stock[0].key, nameKey: '', tipo: 'PARTE DE ENTRADA',
                            folio: '2', fecha: DIA(2026, 1, 2), kind: 'in', qty: 3, saldo: null, valor: 0,
                            costo: 0, orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', _aj: false}])
    .rows.find(x => x.code === 'SIN-SALDO');
  comprobar('con movimientos no se inventa el saldo', null, ajusteDelConteo(conDocs));

  state.stock = parseStock([['Código', 'Nombre', 'Stock físico', 'Contado por', 'Fecha y hora del conteo'],
                            ['BRC-003', 'Broca', 9, 'Claudio Leyton', '21-08-2026 10:00']]);
  // Sin stock valorizado cargado no se puede afirmar: se queda como estaba.
  state.articulos = null;
  const sinFoto = compute([]).rows.find(x => x.code === 'BRC-003');
  comprobar('sin el Informe de Inventario no se propone nada', null, ajusteDelConteo(sinFoto));

  // Y con un informe filtrado (sin artículos en cero) tampoco: faltar no dice nada.
  state.articulos = parseArticulos([
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
    ['OTRO', 'Otro producto', 'BODEGA CENTRAL', 5, 'UN', 100, 500]]);
  const filtrado = compute([]).rows.find(x => x.code === 'BRC-003');
  comprobar('con el informe filtrado tampoco', null, ajusteDelConteo(filtrado));
}

console.log('\nUna fecha de conteo imposible no es un conteo');
{
  /* En su archivo, 2.308 filas de 3.116 traen la fecha en 0, que Excel lee
     como 31-12-1899, con stock 0 y sin quién contó: son los productos que no
     se contaron. Dándolas por buenas, el producto pasa por contado en 1899 y
     todos sus movimientos quedan "después del conteo"; así uno con su ajuste
     ya hecho terminaba pidiendo que se deshiciera. */
  const filas = parseStock([
    ['Código', 'Nombre', 'Stock físico', 'Contado por', 'Fecha y hora del conteo'],
    ['SIN-CONTAR', 'No se contó', 0, '', 0],
    ['CONTADO', 'Sí se contó', 7, 'Claudio Leyton', '13-10-2026 13:34'],
  ]);
  comprobar('la fila con fecha 0 queda sin fecha', null, filas[0].fecha);
  comprobar('y la contada de verdad la conserva', 2026, filas[1].fecha.getFullYear());

  // Y entonces no se le propone nada: no hay contra qué comparar.
  state.stock = filas;
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map(); state.movCuando = new Map();
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  const mov = [{art: 'SIN-CONTAR', key: filas[0].key, nameKey: '', tipo: 'PARTE DE ENTRADA', folio: '1',
                fecha: DIA(2026, 1, 29), kind: 'in', qty: 310, saldo: 310, valor: 0, costo: 0,
                orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', _aj: false}];
  const r = compute(mov).rows.find(x => x.code === 'SIN-CONTAR');
  comprobar('el producto queda como no contado', false, r.counted);
  comprobar('y no se propone ajuste', null, ajusteDelConteo(r));

  // Pedido así: lo que no se contó queda pendiente de revisión, no cuadrado.
  comprobar('se muestra como pendiente de revisión', true, regRow(r).includes('Pendiente de revisión'));
  comprobar('y lo que corresponde es contarlo', true,
            docSteps(r).some(x => x.txt && x.txt.startsWith('Contar el producto')));
}

/* ---- Lo que YA se ajustó, en el Excel ----

   El archivo de ajustes trae los comprobantes con que se regularizaron las
   diferencias. La pantalla ya los mostraba; al Excel no bajaban, y son los que
   hacen falta para informar de lo hecho —no sólo de lo que falta—. El monto es
   el del propio comprobante, no una estimación con el PMP. */

function conAjusteHecho({contado = 5, saldoInicial = 10, ajuste, costo = null}){
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optSame', Object.assign(porId.get('optSame') || {}, {value: 'before'}));
  state.stock = [{code: 'ART-1', key: 'ART1', name: 'ARTICULO', stock: contado,
                  fecha: DIA(2026, 9, 1), por: 'Bodega', estado: 'Contado', um: '', linea: ''}];
  state.recount = new Map(); state.manual = new Set(); state.hechos = new Map();
  state.pmpEdit = new Map(); state.movCuando = new Map(); state.articulos = null;
  const movs = [{art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: 'PARTE DE ENTRADA', folio: '100',
                 fecha: DIA(2026, 8, 1), kind: 'in', qty: saldoInicial, saldo: saldoInicial,
                 valor: saldoInicial * 1000, valorInv: saldoInicial * 1000, costo: 0,
                 orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', i: 0, _aj: false}];
  if (ajuste) movs.push({art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: ajuste.tipo || 'PARTE DE SALIDA',
    folio: ajuste.folio || '311', fecha: DIA(2026, 9, 10), kind: ajuste.kind || 'out', qty: ajuste.qty,
    saldo: saldoInicial + (ajuste.kind === 'in' ? ajuste.qty : -ajuste.qty),
    valor: ajuste.valor, valorInv: 0, costo: 0,
    orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: 'AJUSTE', i: 1, _aj: true});
  // Un ajuste de costo no mueve unidades: entra con cantidad 0 y sólo valor.
  if (costo) movs.push({art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: costo.tipo || 'AJUSTE COSTO ENTRADA',
    folio: costo.folio || '1', fecha: DIA(2026, 9, 8), kind: costo.kind || 'in', qty: 0,
    saldo: saldoInicial, valor: costo.valor, valorInv: costo.valor, costo: 0,
    orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: 'AJUSTE DE COSTO', i: 2, _aj: false, _ajc: true});
  return compute(movs).rows[0];
}

console.log('\nEl Excel dice cuánto se ajustó y por cuánto');
{
  const r = conAjusteHecho({ajuste: {qty: 5, valor: 5800}});
  const x = regExport(r);
  comprobar('la cantidad, con signo de salida', -5, x['Cantidad ya ajustada']);
  comprobar('y el monto del comprobante', -5800, x['Valor ya ajustado']);
  comprobar('el comprobante sigue saliendo', true, String(x['Comprobante de ajuste']).includes('#311'));
}

console.log('\nEl Excel dice quién contó');
{
  const x = regExport(conAjusteHecho({ajuste: {qty: 5, valor: 5800}}));
  comprobar('el nombre, al lado de la fecha', 'Bodega', x['Contado por']);
  comprobar('y la fecha sigue estando', true, String(x['Fecha conteo']).startsWith('01-09-2026'));
  // Si el producto no se contó, no hay quién: la celda queda vacía aunque la
  // planilla traiga un nombre en esa fila.
  const sin = regExport(conAjusteHecho({contado: null, ajuste: null}));
  comprobar('sin conteo, sin nombre', '', sin['Contado por']);
  comprobar('y sin fecha', '', sin['Fecha conteo']);
}

console.log('\nUna entrada queda en positivo');
{
  const r = conAjusteHecho({contado: 15, ajuste: {kind: 'in', qty: 5, valor: 5800, tipo: 'PARTE DE ENTRADA'}});
  const x = regExport(r);
  comprobar('la cantidad', 5, x['Cantidad ya ajustada']);
  comprobar('y el monto', 5800, x['Valor ya ajustado']);
}

console.log('\nUn comprobante sin monto no esconde la cantidad');
{
  // En sus archivos hay uno así: PARTE DE SALIDA sin valor. La celda del monto
  // queda vacía en vez de un 0 inventado, y la cantidad se ve igual.
  const r = conAjusteHecho({ajuste: {qty: 5, valor: 0}});
  const x = regExport(r);
  comprobar('la cantidad se ve', -5, x['Cantidad ya ajustada']);
  comprobar('y el monto queda vacío', '', x['Valor ya ajustado']);
}

console.log('\nEl ajuste de costo ya hecho también sale, en su propia columna');
{
  // RESP-FLL-3M-6900: le arreglaron el costo con un AJUSTE COSTO ENTRADA por
  // $4.173.180 y ese número sólo salía dentro de la frase de Observaciones.
  const r = conAjusteHecho({ajuste: {qty: 2, valor: 252920}, costo: {valor: 4173180}});
  const x = regExport(r);
  comprobar('el monto del ajuste de costo', 4173180, x['Ajuste de costo ya hecho']);
  comprobar('no se mezcla con el de las unidades', -252920, x['Valor ya ajustado']);
  comprobar('y no mueve la cantidad', -2, x['Cantidad ya ajustada']);
  comprobar('el comprobante también se nombra', true,
            String(x['Comprobante de ajuste']).includes('AJUSTE COSTO ENTRADA'));
}

console.log('\nUna salida de costo resta');
{
  const r = conAjusteHecho({ajuste: null, costo: {valor: 100000, kind: 'out', tipo: 'AJUSTE COSTO SALIDA'}});
  comprobar('queda en negativo', -100000, regExport(r)['Ajuste de costo ya hecho']);
}

console.log('\nSin ajustes hechos, las dos celdas quedan vacías');
{
  const x = regExport(conAjusteHecho({ajuste: null}));
  comprobar('sin cantidad', '', x['Cantidad ya ajustada']);
  comprobar('sin monto', '', x['Valor ya ajustado']);
  // Vacía, no 0: un 0 se suma como si fuera un dato y no lo es.
  comprobar('y sin ajuste de costo', '', x['Ajuste de costo ya hecho']);
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
