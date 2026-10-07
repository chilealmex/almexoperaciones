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
const {compute, buildPlan, docSteps, parseArticulos, costoDeSuCompra, state} =
  require('../../app/static/js/regularizacion.js');

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

function plan(docs, inventario) {
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  state.hechos = new Map(); state.pmpEdit = new Map(); state.ajustes = [];
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

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
