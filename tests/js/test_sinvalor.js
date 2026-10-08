/* Productos con unidades en Defontana y valorizados en $0.

   Es un problema distinto de "entró a un costo raro": no es que valga algo
   equivocado, es que no vale nada. Y se resuelve distinto, porque el costo que
   corresponde está casi siempre en su propia compra: el producto entró con
   costo y el inventario quedó en cero. Usar ese monto no es estimar — es el
   número del documento con que entró.

   Antes no se pedían: el sistema decidía si un producto "tenía costo"
   repitiendo sus movimientos, y si la repetición daba un PMP lo daba por
   bueno aunque Defontana lo tuviera en cero. En su inventario son 189
   productos, 5.409 unidades, $30.778.738 que el inventario no cuenta. */
const {porId} = require('./entorno.js');
const {compute, buildPlan, docSteps, parseArticulos, costoDeSuCompra, pmpEditable,
       costoPropuestoSinValor, renderStepsPanel, state} = require('../../app/static/js/regularizacion.js');

let fallas = 0, hechas = 0;
function escenario(t, fn){ console.log('\n' + t); try { fn(); } catch(e){ fallas++; hechas++; console.log(`  ✘ reventó: ${e.message}`); } }
function comprobar(t, esp, obt){ hechas++; if (esp === obt){ console.log(`  ✔ ${t}`); return; } fallas++; console.log(`  ✘ ${t}\n      esperaba ${esp}, obtuvo ${obt}`); }

const DIA = (a, m, d) => new Date(a, m - 1, d);
const ing = (q, cu, d) => ({kind: 'in', qty: q, cu, fecha: DIA(2026, 8, d)});

function docsDe(lista, art = 'AAA') {
  let s = 0, v = 0;
  return lista.map((d, i) => {
    let valor = d.cu * d.qty;
    if (d.kind === 'in') { s += d.qty; v += valor; }
    else { const p = s > 0 ? v / s : 0; valor = p * d.qty; s -= d.qty; v -= valor; }
    return {art, key: art, nameKey: 'N' + art, tipo: 'PARTE DE ENTRADA', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo: s, valor, valorInv: v, um: '',
            orig: 'C', dest: 'C', estado: 'Aprobado', motivo: '', desc: 'PROD ' + art};
  });
}

const INV = (...filas) => [
  ['Informe de Inventario'], ['Empresa: X'], ['Fecha de generación: 07-10-2026, 09:20 a. m.'], [],
  ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'], ...filas,
];

function plan(docs, inventario, costoAMano) {
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  state.hechos = new Map(); state.ajustes = [];
  state.pmpEdit = costoAMano == null ? new Map() : new Map([['AAA', costoAMano]]);
  state.articulos = inventario || null;
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  state.mov = docs;
  const out = compute(docs);
  state.rows = out.rows; state.zero = out.zero;
  return {P: buildPlan(), r: out.rows[0]};
}

// Entró 12 a $5.919 y Defontana lo tiene con las 12 unidades valorizadas en $0
const COMPRADO = docsDe([ing(12, 5919, 1)]);

escenario('El costo sale de su propia compra, no de una referencia', () => {
  const c = costoDeSuCompra(COMPRADO);
  comprobar('el monto del documento', 5919, c.v);
  comprobar('y de qué documento', 'PARTE DE ENTRADA #100', c.doc);
  comprobar('sin compras con costo, nada', null, costoDeSuCompra(docsDe([ing(5, 0, 1)])));
  comprobar('una compra a $1 no es un costo', null, costoDeSuCompra(docsDe([ing(5, 1, 1)])));
  // Con varias compras manda la última
  comprobar('con varias, la última', 7000, costoDeSuCompra(docsDe([ing(5, 5919, 1), ing(5, 7000, 2)])).v);
});

escenario('Si Defontana lo tiene a $0, se pide cargar el costo', () => {
  const {P, r} = plan(COMPRADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 12, 'UN', 0, 0])));
  comprobar('va a su propio paso', 1, P.sinValor.length);
  comprobar('y no al de costos raros', 0, P.cost.length);
  const x = P.sinValor[0];
  comprobar('por las 12 unidades', 12, x.qty);
  comprobar('al costo de su compra', 5919, x.v);
  comprobar('eso es lo que falta de valor', 71028, Math.round(x.v * x.qty));
  comprobar('y dice de dónde sale', true, /PARTE DE ENTRADA #100/.test(x.src));
  comprobar('el paso se llama distinto', true, docSteps(r).some(s => s.k === 'sinvalor'));
});

escenario('A $1 la unidad también está sin costo', () => {
  // Lo que se mira es el valor de UNA unidad, no el total: 355 unidades a $1
  // valorizan $355, que es mayor que cero, y el producto se daba por costeado.
  // Pero $1 es el relleno con que se creó el artículo, no un costo —la misma
  // regla que ya valía para los ingresos—. En su informe eran 16 productos.
  const {P, r} = plan(COMPRADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 12, 'UN', 1, 12])));
  comprobar('entra al paso 2a', 1, P.sinValor.length);
  comprobar('por las 12 unidades', 12, P.sinValor[0].qty);
  comprobar('al costo de su compra', 5919, P.sinValor[0].v);
  comprobar('y el paso lo marca', true, docSteps(r).some(s => s.k === 'sinvalor'));
  // El aviso dice con qué valor están, no "en $0" a secas: a $1 eso se leía
  // como un error, porque en Defontana el producto no aparece en cero.
  comprobar('dice con qué valor unitario están', true,
    JSON.stringify(r).includes('valorizadas en $1 c/u'));
});

escenario('A $2 la unidad ya es un costo: no entra', () => {
  // El corte está en $1. Si fuera "poco valor" habría que elegir cuánto es
  // poco, y eso ya sería estimar.
  const {P} = plan(COMPRADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 12, 'UN', 2, 24])));
  comprobar('no entra al paso 2a', 0, P.sinValor.length);
});

escenario('Sin el informe de inventario, la última fila manda igual', () => {
  // Cuando no está cargado el stock valorizado, lo que queda es la última fila
  // del informe de documentos. Ahí vale la misma regla: 10 unidades por $10 es
  // $1 la unidad, y eso es estar sin costo aunque el total no sea cero.
  const docs = docsDe([ing(10, 1000, 1)]);
  const ultima = {...docs[0], folio: '200', fecha: DIA(2026, 8, 2), kind: 'out', qty: 0,
                  valor: 9990, saldo: 10, valorInv: 10};
  const {P} = plan([...docs, ultima], null);
  comprobar('entra al paso 2a', 1, P.sinValor.length);
  comprobar('por las 10 unidades', 10, P.sinValor[0].qty);
});

escenario('Sin unidades, el valor unitario no dice nada', () => {
  // Con stock 0 no hay unidades a las que cargarles costo, y además dividir
  // por cero daría cualquier cosa.
  const {P} = plan(COMPRADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 0, 'UN', 0, 0])));
  comprobar('no entra al paso 2a', 0, P.sinValor.length);
});

escenario('El costo es el de SU compra, no la mediana de sus compras', () => {
  // Con tres compras a $1.000 y la última a $5.000, la mediana da $1.000. Pero
  // el producto entró a $5.000 y a ese costo quedaron las unidades que hay: el
  // monto exacto es el de su documento, no el de un promedio.
  const docs = docsDe([ing(10, 1000, 1), ing(10, 1000, 2), ing(10, 1000, 3), ing(10, 5000, 4)]);
  comprobar('su propia compra', 5000, costoDeSuCompra(docs).v);
  const {P} = plan(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 40, 'UN', 0, 0])));
  comprobar('y es el que se usa', 5000, P.sinValor[0].v);
  comprobar('no la mediana', false, P.sinValor[0].v === 1000);
  comprobar('el valor que falta sale de ahí', 200000, Math.round(P.sinValor[0].v * P.sinValor[0].qty));
});

escenario('Si Defontana sí le tiene valor, no se pide nada', () => {
  const {P} = plan(COMPRADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 12, 'UN', 5919, 71028])));
  comprobar('no está en el paso de sin valor', 0, P.sinValor.length);
  comprobar('ni en el de costos', 0, P.cost.length);
});

escenario('Manda el inventario, no la repetición de los movimientos', () => {
  // Éste es el error que tenían: los movimientos dan un PMP de $5.919, así que
  // repitiéndolos el producto "tiene costo" y no se pedía nada. Pero Defontana
  // lo tiene en cero, y es Defontana quien valoriza el inventario.
  const sinFoto = plan(COMPRADO, null);
  comprobar('sin el inventario cargado no se entera', 0, sinFoto.P.sinValor.length);
  const conFoto = plan(COMPRADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 12, 'UN', 0, 0])));
  comprobar('con el inventario cargado sí', 1, conFoto.P.sinValor.length);
});

escenario('Sin unidades no se pide nada: no hay qué valorizar', () => {
  const {P} = plan(COMPRADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 0, 'UN', 0, 0])));
  comprobar('no entra', 0, P.sinValor.length);
});

escenario('Sin una compra con costo, se pide el costo a mano', () => {
  const soloACero = docsDe([ing(5, 0, 1)]);
  const {P} = plan(soloACero, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 5, 'UN', 0, 0])));
  comprobar('igual entra al paso', 1, P.sinValor.length);
  comprobar('pero sin costo puesto', null, P.sinValor[0].v);
  comprobar('y lo dice', true, /nunca tuvo una compra con costo/.test(P.sinValor[0].src));
});

escenario('Van ordenados por lo que pesan, para poder cortar', () => {
  const docs = [...docsDe([ing(1, 1000, 1)], 'CHICO'), ...docsDe([ing(50, 9000, 1)], 'GRANDE')];
  const {P} = plan(docs, parseArticulos(INV(
    ['CHICO', 'UNO', 'BODEGA CENTRAL', 1, 'UN', 0, 0],
    ['GRANDE', 'DOS', 'BODEGA CENTRAL', 50, 'UN', 0, 0])));
  comprobar('los dos entran', 2, P.sinValor.length);
  comprobar('primero el que más pesa', 'GRANDE', P.sinValor[0].r.code);
  comprobar('y después el chico', 'CHICO', P.sinValor[1].r.code);
});

// --- Entradas a $0 o $1 que hoy se ven bien ---
//
// Su regla: una entrada a $0 o $1 se revisa siempre que queden unidades, aunque
// el PMP de hoy se vea bien. Un costo de relleno es un error registrado. Pero
// el motivo de que se vea bien importa: puede ser que ya le hicieran un ajuste
// de costo, y entonces cuadra por eso, no porque la entrada fuera inofensiva.

function conUnAjuste(docs) {
  // Un comprobante de ajuste de costo: cantidad 0 y valor, marcado como tal
  return [...docs, {art: 'AAA', key: 'AAA', nameKey: 'NAAA', tipo: 'AJUSTE COSTO ENTRADA',
    folio: '7', fecha: DIA(2026, 8, 9), kind: 'in', qty: 0, valor: 50000,
    saldo: docs[docs.length - 1].saldo, valorInv: docs[docs.length - 1].valorInv, um: '',
    orig: 'C', dest: 'C', estado: 'Aprobado', motivo: 'AJUSTE', desc: 'PROD AAA', _ajc: true}];
}

// Entró 5 a $1 y después 100 a $1.000: hoy el PMP se ve bien
const ACOMODADO = docsDe([ing(5, 1, 1), ing(100, 1000, 2)]);

escenario('Una entrada a $1 se revisa aunque hoy se vea bien', () => {
  const {P, r} = plan(ACOMODADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 105, 'UN', 952.4, 100005])));
  comprobar('aparece para revisar', 1, P.cost.length);
  comprobar('pero sin monto de ajuste', null, P.cost[0].corr);
  comprobar('y la fila no trae un ajuste escondido', null, (r.costExtra || [])[0].rev.ajusteCosto);
  comprobar('y dice cuánto queda y en cuánto está', true, /105 unidades valorizadas/.test(P.cost[0].nota));
  const texto = (r.costExtra || []).map(z => z.rev.txt).join(' ');
  comprobar('explica que lo acomodaron los movimientos', true,
            /movimientos posteriores lo acomodaron/.test(texto));
  comprobar('y no inventa un ajuste de costo que no existe', false, /ajuste de costo \(/.test(texto));
});

escenario('Si cuadra por un ajuste de costo ya hecho, lo dice', () => {
  const {P, r} = plan(conUnAjuste(ACOMODADO), parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 105, 'UN', 952.4, 100005])));
  comprobar('igual aparece para revisar', 1, P.cost.length);
  const texto = P.cost[0].nota + ' ' + (r.costExtra || []).map(z => z.rev.txt).join(' ');
  comprobar('dice que ya hay un ajuste de costo', true, /ajuste de costo \(AJUSTE COSTO ENTRADA #7\)/.test(texto));
  comprobar('y que el valor cuadra por eso', true, /cuadra por eso/.test(texto));
  comprobar('no lo atribuye a los movimientos', false, /movimientos posteriores lo acomodaron/.test(texto));
});

escenario('El 40080-004: no entró a $1, eso lo decía la columna mala', () => {
  // Su caso real. La Parte de Entrada dice $15 por 15 unidades, pero el Valor
  // Inventario subió $8.553.600: entró a $570.240 c/u, lo mismo que costaron
  // en su compra anterior. La columna "Valor Movimiento" no es fiable y por
  // eso no se usa; el costo sale de lo que movió el inventario.
  const docs = docsDe([ing(12, 570240, 1)]);
  docs.push({...docs[0], folio: '200', fecha: DIA(2026, 8, 2), kind: 'out', qty: 12,
             valor: 6842880, saldo: 0, valorInv: 0});
  docs.push({...docs[0], tipo: 'NO OCUPAR2', folio: '83', fecha: DIA(2026, 8, 3), kind: 'in',
             qty: 15, valor: 15, saldo: 15, valorInv: 8553600});
  const {P, r} = plan(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 15, 'UN', 570240, 8553600])));
  comprobar('no se lo trata como una entrada a $1', 0, P.cost.length);
  comprobar('ni como sin valor: Defontana le tiene valor', 0, P.sinValor.length);
  comprobar('el PMP de hoy es el del inventario', 570240,
            Math.round(docs[2].valorInv / docs[2].saldo));
});

// --- Juzgar todas las compras, tengan la historia que tengan ---

escenario('Una sola compra, y a $1: se revisa igual', () => {
  // No hace falta tener con qué comparar: $1 la unidad no es un costo, punto.
  // Y la regla vale aunque el producto tenga una única compra en su historia.
  const docs = docsDe([ing(20, 1, 1)]);
  const {P} = plan(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 20, 'UN', 1, 20])));
  comprobar('se muestra', 1, P.cost.length);
  comprobar('sin inventar un monto', null, P.cost[0].corr);
});

escenario('Una sola compra a precio normal: no se inventa un problema', () => {
  const docs = docsDe([ing(20, 5000, 1)]);
  const {P} = plan(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 20, 'UN', 5000, 100000])));
  comprobar('no se muestra', 0, P.cost.length);
  comprobar('ni como sin valor', 0, P.sinValor.length);
});

escenario('Dos compras muy distintas: no se sabe cuál es la buena, se pregunta', () => {
  // Con dos no hay mediana, así que el producto no se juzga. Pero sí se pueden
  // comparar entre ellas: si una cuesta siete veces la otra, algo pasó.
  const docs = docsDe([ing(10, 978, 1), ing(10, 6800, 2)]);
  const {P, r} = plan(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 20, 'UN', 3889, 77780])));
  comprobar('se muestra', 1, P.cost.length);
  comprobar('como "dos compras a precios muy distintos"', 'Dos compras a precios muy distintos', P.cost[0].doc);
  comprobar('sin proponer monto', null, P.cost[0].corr);
  const z = (r.costExtra || [])[0];
  comprobar('dice cuántas veces', true, /7 veces la otra/.test(z.rev.txt));
  comprobar('y nombra las dos compras', true, /\$978 c\/u.*\$6\.800 c\/u/.test(z.rev.txt));
  comprobar('y que no se sabe cuál es la buena', true, /no se sabe cuál es la buena/.test(z.rev.txt));
});

escenario('Dos compras muy distintas: al escribir el costo sale el ajuste', () => {
  // Preguntar cuál de las dos compras es la buena no cuadra nada por sí solo:
  // una vez que ella decide y escribe el costo, el paso tiene que decir el
  // monto del ajuste y si es entrada o salida. Si no, hay que sacar la cuenta
  // a mano cada vez.
  const docs = docsDe([ing(10, 978, 1), ing(10, 6800, 2)]);
  const inv = parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 20, 'UN', 3889, 77780]));

  const sin = plan(docs, inv);
  const zSin = (sin.r.costExtra || [])[0];
  comprobar('sin costo escrito, sólo se muestra', true, zSin.rev.soloRevisar);
  comprobar('y no hay monto', null, zSin.rev.ajusteCosto);
  comprobar('pide escribir el costo', true, /escribe el costo en la columna PMP/i.test(zSin.rev.hacer));

  // 20 unidades a $6.800 son $136.000 y hoy el inventario vale $77.780
  const caro = plan(docs, inv, 6800);
  const zCaro = (caro.r.costExtra || [])[0];
  comprobar('con el costo caro ya no es sólo revisar', false, zCaro.rev.soloRevisar);
  comprobar('el ajuste sube el valor', 58220, Math.round(zCaro.rev.ajusteCosto));
  comprobar('y es una entrada de costo', true, /Ajuste de costo ENTRADA por \$58\.220/.test(zCaro.rev.hacer));
  comprobar('dice qué poner en Defontana', true, /"Costo Unitario".*\$6\.800/.test(zCaro.rev.hacer));
  comprobar('y de cuánto a cuánto pasa el inventario', true, /\$77\.780 a \$136\.000/.test(zCaro.rev.hacer));

  // Al revés: 20 a $978 son $19.560, hay que sacarle $58.220
  const barato = plan(docs, inv, 978);
  const zBarato = (barato.r.costExtra || [])[0];
  comprobar('con el costo barato el ajuste baja el valor', -58220, Math.round(zBarato.rev.ajusteCosto));
  comprobar('y es una salida de costo', true, /Ajuste de costo SALIDA por \$58\.220/.test(zBarato.rev.hacer));

  // Y el plan lo lleva con su monto, que es lo que ella sigue para cuadrar
  comprobar('el plan lo pide igual', 1, caro.P.cost.length);
  comprobar('con el costo escrito', 6800, caro.P.cost[0].v);
});

escenario('Dos compras parecidas: nada que revisar', () => {
  const docs = docsDe([ing(10, 1000, 1), ing(10, 1200, 2)]);
  const {P} = plan(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 20, 'UN', 1100, 22000])));
  comprobar('no se muestra', 0, P.cost.length);
});

escenario('Dos compras distintas pero sin stock: nada que hacer', () => {
  const docs = docsDe([ing(10, 978, 1), ing(10, 6800, 2), {kind: 'out', qty: 20, cu: 0, fecha: DIA(2026, 8, 3)}]);
  const {P} = plan(docs, parseArticulos(INV(['OTRO', 'OTRO', 'BODEGA CENTRAL', 5, 'UN', 100, 500])));
  comprobar('no se muestra', 0, P.cost.filter(x => x.doc === 'Dos compras a precios muy distintos').length);
});

// --- Verse todos los movimientos, sin excepción ---
//
// Para poder revisar la historia completa de un producto no basta con listar
// los movimientos marcados: hay que ver todo lo que entró y salió, aunque no
// pida nada. Si no, hay que creer que lo que no se muestra está bien.

function vistaMovimientos(docs, inventario) {
  state.view = 'zero';
  const r = plan(docs, inventario);
  state.view = 'reg';
  return r;
}

escenario('La vista de movimientos los lista todos', () => {
  // Tres compras normales: ninguna pide nada, y las tres tienen que verse
  const docs = docsDe([ing(10, 1000, 1), ing(10, 1000, 2), ing(10, 1000, 3)]);
  const sinVer = plan(docs, null);
  comprobar('en Productos no se arman: nadie los mira', 0, sinVer.r.docs.length && state.zero.length);

  const { } = vistaMovimientos(docs, null);
  comprobar('en la vista de movimientos están los tres', 3, state.zero.length);
  comprobar('ninguno pide nada', 0, state.zero.filter(z => z.rev.need).length);
  comprobar('van marcados como normales', 3, state.zero.filter(z => z.normal).length);
});

escenario('Cada movimiento muestra su PMP y cómo quedó el inventario', () => {
  const docs = docsDe([ing(10, 1000, 1), ing(10, 3000, 2)]);
  vistaMovimientos(docs, null);
  const segundo = state.zero.find(z => z.m.folio === '101');
  comprobar('el PMP de esa fila', 2000, Math.round(segundo.pmp));
  comprobar('y lo dice en el texto', true, /20 unidades/.test(segundo.rev.txt));
  comprobar('con el valor del inventario', true, /\$40\.000/.test(segundo.rev.txt));
});

escenario('Los marcados no se duplican al listar todos', () => {
  // Un ingreso a $1 ya está en la lista por estar marcado: no puede aparecer
  // dos veces, una como problema y otra como movimiento normal.
  const docs = docsDe([ing(20, 1, 1)]);
  vistaMovimientos(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 20, 'UN', 1, 20])));
  comprobar('una sola fila para ese movimiento', 1, state.zero.filter(z => z.m.folio === '100').length);
  comprobar('y es la que pide revisarlo', true, state.zero.find(z => z.m.folio === '100').rev.need);
});

escenario('Un producto que ya no tiene stock no se lista', () => {
  // Entraron 10 y salieron las 10: hoy no hay unidades ni valor. Esos
  // movimientos no se pueden arreglar —el costo se fue con la salida— así que
  // mostrarlos sólo obliga a descartarlos a mano. En su informe son 2.387
  // filas de 9.307.
  const docs = docsDe([ing(10, 1000, 1), {kind: 'out', qty: 10, cu: 0, fecha: DIA(2026, 8, 2)}]);
  vistaMovimientos(docs, null);
  comprobar('ni la entrada ni la salida', 0, state.zero.length);

  // Pero si sigue teniendo unidades, se ven las dos
  const quedan = docsDe([ing(10, 1000, 1), {kind: 'out', qty: 4, cu: 0, fecha: DIA(2026, 8, 2)}]);
  vistaMovimientos(quedan, null);
  comprobar('con stock se listan las dos', 2, state.zero.length);
});

escenario('Sin stock pero con valor en el inventario: eso hay que sacarlo', () => {
  // Salieron todas las unidades y el inventario sigue valiendo $5.000. Eso lo
  // dice el stock valorizado: trae el producto con 0 unidades y un Total que
  // no es cero. Es el caso que sí hay que arreglar, así que el filtro no se lo
  // puede comer: se muestra el producto con toda su historia.
  const docs = docsDe([ing(10, 1000, 1)]);
  docs.push({...docs[0], folio: '200', fecha: DIA(2026, 8, 2), kind: 'out', qty: 10,
             valor: 5000, saldo: 0, valorInv: 5000});
  vistaMovimientos(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 0, 'UN', 0, 5000])));
  comprobar('se lista', true, state.zero.length > 0);
  comprobar('con la valorización imposible', true, state.zero.some(z => z.imposible === 'valorSinStock'));
  comprobar('y también sus movimientos', true, state.zero.some(z => z.normal));
});

escenario('Si el inventario no lo trae, hoy está en $0: no se pide nada', () => {
  // El mismo producto, pero el stock valorizado no lo lista. Ese informe sólo
  // trae lo que tiene stock, así que Defontana hoy no le tiene ni unidades ni
  // valor: los $5.000 son del arrastre del informe de documentos, que es una
  // reconstrucción. Pedir un ajuste de costo ahí es pedir un comprobante para
  // dejar en $0 algo que ya está en $0.
  //
  // El informe tiene que estar completo para poder leer la ausencia así: la
  // fila en cero de OTRO-2 es lo que prueba que lista todo el maestro y no
  // sólo lo que tiene stock.
  const docs = docsDe([ing(10, 1000, 1)]);
  docs.push({...docs[0], folio: '200', fecha: DIA(2026, 8, 2), kind: 'out', qty: 10,
             valor: 5000, saldo: 0, valorInv: 5000});
  vistaMovimientos(docs, parseArticulos(INV(
    ['OTRO', 'PROD OTRO', 'BODEGA CENTRAL', 5, 'UN', 100, 500],
    ['OTRO-2', 'PROD OTRO 2', 'BODEGA CENTRAL', 0, 'UN', 0, 0])));
  comprobar('no se marca la valorización imposible', false, state.zero.some(z => z.imposible));
  comprobar('y no se lista nada del producto', 0, state.zero.length);
});

escenario('Con el informe filtrado, el ausente se sigue mostrando', () => {
  // Sin filas en cero no se sabe si el informe lista todo el maestro o sólo lo
  // que tiene stock. Dar por cero lo que falta ahí esconde productos en
  // silencio: con su informe de las 09:20 serían 1.984. Así que sus
  // movimientos se siguen listando, para poder mirarlos.
  //
  // Lo que NO se hace es proponer un ajuste de costo: para eso tiene que
  // decirlo el valorizado.
  const docs = docsDe([ing(10, 1000, 1)]);
  docs.push({...docs[0], folio: '200', fecha: DIA(2026, 8, 2), kind: 'out', qty: 10,
             valor: 5000, saldo: 0, valorInv: 5000});
  vistaMovimientos(docs, parseArticulos(INV(['OTRO', 'PROD OTRO', 'BODEGA CENTRAL', 5, 'UN', 100, 500])));
  comprobar('se lista igual', true, state.zero.length > 0);
  comprobar('pero sin proponer ajuste', false, state.zero.some(z => z.imposible));
});

escenario('El stock que manda es el del inventario, no el arrastrado', () => {
  // El saldo que se arrastra fila a fila del informe de documentos es una
  // reconstrucción; el stock valorizado es lo que Defontana tiene ahora. Si se
  // esconde por el arrastre, se esconde un producto que sí tiene unidades.
  const docs = docsDe([ing(10, 1000, 1), {kind: 'out', qty: 10, cu: 0, fecha: DIA(2026, 8, 2)}]);
  vistaMovimientos(docs, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 4, 'UN', 1000, 4000])));
  comprobar('el arrastre dice 0 pero el inventario dice 4: se lista', 2, state.zero.length);

  // Y al revés: si el inventario dice que no queda nada, no se lista aunque el
  // arrastre crea que sí
  const quedan = docsDe([ing(10, 1000, 1)]);
  vistaMovimientos(quedan, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 0, 'UN', 0, 0])));
  comprobar('el arrastre dice 10 pero el inventario dice 0: no se lista', 0, state.zero.length);
});

escenario('Con el informe viejo, el valor sigue saliendo de los documentos', () => {
  // El Informe de Artículos no trae la columna Total: su valor es stock por
  // costo, así que sin unidades da $0 siempre. Si el filtro se apoyara en eso,
  // el valor sin unidades quedaría escondido justo con el informe en que no se
  // puede ver de otra forma.
  const ART = [['Informe de Articulos'], ['Empresa: X'],
    ['Fecha de generación: 07-10-2026, 09:20 a. m.'], [],
    ['Artículo', 'Descripción', 'Stock Disponible', 'Costo Vigente', 'Costo Reposicion'],
    ['AAA', 'PROD AAA', 0, 0, 0]];
  const docs = docsDe([ing(10, 1000, 1)]);
  docs.push({...docs[0], folio: '200', fecha: DIA(2026, 8, 2), kind: 'out', qty: 10,
             valor: 5000, saldo: 0, valorInv: 5000});
  vistaMovimientos(docs, parseArticulos(ART));
  comprobar('se lista igual', true, state.zero.length > 0);
  // Pero no se propone sacarle valor: ese informe no trae el valorizado de
  // Defontana, así que no puede afirmar que haya valor sin unidades.
  comprobar('sin proponer ajuste de costo', false, state.zero.some(z => z.imposible));
});

escenario('Si el informe no trae el saldo, no se esconde todo', () => {
  // Sin saber el stock no se puede afirmar que no quede nada. Esconder por las
  // dudas dejaría la pantalla en blanco con un informe al que le falta una
  // columna, y parecería que no hay nada que regularizar.
  const docs = docsDe([ing(10, 1000, 1)]).map(m => ({...m, saldo: null, valorInv: null}));
  vistaMovimientos(docs, null);
  comprobar('el movimiento se lista', 1, state.zero.length);
});

escenario('El costo escrito a mano manda sobre el de su propia compra', () => {
  // La columna PMP es donde se corrige lo que el sistema propuso. Antes
  // escribir ahí no cambiaba nada en este paso: el monto seguía saliendo de la
  // compra del producto, así que no había forma de ajustar la propuesta.
  const inv = parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 12, 'UN', 0, 0]));
  const solo = plan(COMPRADO, inv);
  comprobar('sin escribir nada, propone su compra', 5919, solo.P.sinValor[0].v);
  comprobar('y dice de dónde sale', true, /PARTE DE ENTRADA #100/.test(solo.P.sinValor[0].src));

  const aMano = plan(COMPRADO, inv, 8000);
  comprobar('con el costo escrito, manda ése', 8000, aMano.P.sinValor[0].v);
  comprobar('el total se recalcula', 96000, Math.round(aMano.P.sinValor[0].v * aMano.P.sinValor[0].qty));
  comprobar('y lo dice', 'Ingresado a mano', aMano.P.sinValor[0].src);
  comprobar('el paso lo repite', true,
            docSteps(aMano.r).some(x => x.k === 'sinvalor' && /8\.000 c\/u, el costo que escribiste/.test(x.txt)));
});

escenario('En esos productos se puede escribir el costo', () => {
  // La celda del PMP era de sólo lectura salvo que hubiera un ajuste de
  // cantidad. Justo en los productos sin valor —173 de los 204 suyos— no se
  // podía escribir nada, que es donde más falta hace.
  const inv = parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 12, 'UN', 0, 0]));
  const {r} = plan(COMPRADO, inv);
  comprobar('no tiene ajuste de cantidad', false, ['up', 'down', 'check'].includes(r.st));
  comprobar('y aun así se puede escribir su costo', true, pmpEditable(r));

  // Y la casilla llega con el costo propuesto puesto, para revisarlo antes de
  // cargarlo en vez de tener que ir al plan a buscarlo. Sale del mismo lugar
  // que el plan: con sus archivos r.pmp y la propuesta no coinciden en 12 de
  // los 167, y la pantalla y el plan tienen que decir lo mismo.
  comprobar('con el costo propuesto puesto', 5919, costoPropuestoSinValor(r));

  // Uno sano y cuadrado sigue de sólo lectura: ahí no hay nada que poner
  const sano = plan(docsDe([ing(20, 5000, 1)]),
    parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 20, 'UN', 5000, 100000])));
  comprobar('uno sano no', false, pmpEditable(sano.r));
  comprobar('y no propone nada', null, costoPropuestoSinValor(sano.r));
});

escenario('El paso 2a está en el orden recomendado', () => {
  // Sin esto el panel sólo lleva a los costos raros, y los 204 productos con
  // unidades sin valor —$37.293.260— quedan fuera del orden que se sigue.
  plan(COMPRADO, parseArticulos(INV(['AAA', 'PROD AAA', 'BODEGA CENTRAL', 12, 'UN', 0, 0])));
  state.filter = state.filter || {};
  renderStepsPanel(true);
  const html = porId.get('stepsPanel').innerHTML || '';
  comprobar('el panel trae el paso 2a', true, /2a<\/span>/.test(html));
  comprobar('con su título', true, /Cargar el costo de lo que no vale nada/.test(html));
  comprobar('y cuenta el producto', true, /data-go="sinvalor"/.test(html));
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
