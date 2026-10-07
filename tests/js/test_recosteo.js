/* El ajuste de costo se mide contra lo que Defontana tiene HOY.

   El valor de cada movimiento es lo que movió el Valor Inventario entre su
   fila y la anterior, no lo que diga la columna "Valor Movimiento": esa
   columna no es fiable —en su informe no coincide en el 13,5% de los
   ingresos—. Con eso, repetir los movimientos reproduce exactamente el valor
   que Defontana tiene, y el ajuste por los ingresos a $0 es la única
   diferencia.

   Lo que antes era "Defontana revalorizó por su cuenta y nadie lo explica" ya
   no existe como concepto: todo salto del Valor Inventario pertenece al
   documento de su fila. Si ese documento movió mucho más de lo que suele
   costar el producto, lo toma el camino del costo fuera de lo normal, que es
   donde corresponde.

   El invariante que se comprueba: si el ajuste promete dejar el PMP en X,
   entonces el valor de hoy más el ajuste tiene que dar X por las unidades que
   hay. */
const {porId} = require('./entorno.js');
const {compute, buildPlan, tipoAjCosto, ajCostoUnit, state} = require('../../app/static/js/regularizacion.js');

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

const DIA = (a, m, d) => new Date(a, m - 1, d);

// Movimientos con el saldo y el valor corriendo fila a fila, como los trae el
// informe. `valorFinal` deja la última fila con el Valor Inventario que diga
// Defontana, que es lo que pasa cuando revaloriza por su cuenta.
function informe(lista, valorFinal) {
  let s = 0, v = 0;
  const docs = lista.map((d, i) => {
    let valor = d.cu * d.qty;
    if (d.kind === 'in') { s += d.qty; v += valor; }
    else { const p = s > 0 ? v / s : 0; valor = p * d.qty; s -= d.qty; v -= valor; }
    return {art: 'AAA', key: 'AAA', nameKey: 'NAAA', tipo: 'FACTURA', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo: s, valor, valorInv: v, um: '',
            orig: 'C', dest: 'C', estado: 'Aprobado', motivo: '', desc: 'PROD AAA'};
  });
  if (valorFinal != null) docs[docs.length - 1].valorInv = valorFinal;
  return docs;
}

const ing = (q, cu, d) => ({kind: 'in', qty: q, cu, fecha: DIA(2026, 8, d)});

// El monto del ajuste sale sólo del costo que ella escriba en la columna PMP:
// sin eso habría que estimarlo, y un comprobante no se hace con una estimación.
// Las pruebas que miran montos escriben ese costo, que acá son los $1.000 que
// cuestan de verdad las compras del artículo.
const COSTO_ESCRITO = 1000;

function pantalla(docs, costoAMano = COSTO_ESCRITO) {
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  state.hechos = new Map(); state.ajustes = []; state.mov = docs;
  state.pmpEdit = costoAMano == null ? new Map() : new Map([['AAA', costoAMano]]);
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  const out = compute(docs);
  return out.rows[0];
}

// Un ingreso a $0 (lo que dispara la propuesta de costo) y compras normales a
// $1.000. Quedan 30 unidades.
const MOVS = [ing(10, 0, 1), ing(10, 1000, 2), ing(10, 1000, 3)];

// El invariante: si promete dejar el PMP en X, el valor de hoy más el ajuste
// tiene que dar X por las unidades que hay.
function cuadra(r) {
  const u = r.docs[r.docs.length - 1], c = r.cost.corr;
  return Math.round((u.valorInv + c.ajuste) - c.pmp * u.saldo);
}

escenario('Cuando Defontana cuadra con sus movimientos, nada cambia', () => {
  const r = pantalla(informe(MOVS));
  const u = r.docs[r.docs.length - 1];
  comprobar('Defontana tiene $20.000 por 30 unidades', 20000, Math.round(u.valorInv));
  comprobar('propone subirlo en $10.000 (las 10 que entraron a $0)', 10000, Math.round(r.cost.corr.ajuste));
  comprobar('para dejar el PMP en $1.000', 1000, Math.round(r.cost.corr.pmp));
  comprobar('y el monto cuadra con ese PMP', 0, cuadra(r));
  comprobar('es un ajuste de entrada', 'Ajuste de costo ENTRADA', tipoAjCosto(r.cost.corr.ajuste));
});

escenario('Un ingreso que movió mucho más valor lo toma el camino del costo raro', () => {
  // La última entrada movió $120.000 por 20 unidades —$6.000 c/u— cuando las
  // compras del producto son de $1.000. Antes eso era "una revalorización que
  // nadie explica"; ahora es lo que es: un ingreso a un costo fuera de lo
  // normal, atribuido a su documento.
  const r = pantalla(informe(MOVS, 120000), null);
  const u = r.docs[r.docs.length - 1];
  // La última fila pasa de $10.000 a $120.000: movió $110.000 por 10 unidades
  comprobar('el valor del movimiento sale del salto del inventario', 110000, Math.round(u._v));
  comprobar('o sea $11.000 por unidad, no los $1.000 que dice la columna', 11000, Math.round(u._v / u.qty));
  comprobar('Defontana tiene $120.000', 120000, Math.round(u.valorInv));
});

escenario('Repetir los movimientos reproduce el valor de Defontana', () => {
  // Con el valor fiable, la repetición ya no es una versión paralela: da
  // exactamente lo que Defontana tiene. Por eso el ajuste que se propone es
  // sólo lo que falta por los ingresos a $0, no una diferencia de modelos.
  for (const valorDefontana of [null, 120000, 5000, 60000]) {
    const r = pantalla(informe(MOVS, valorDefontana));
    const u = r.docs[r.docs.length - 1], c = r.cost.corr;
    // 10 unidades entraron a $0 y el costo escrito es $1.000
    comprobar(`con Defontana en ${valorDefontana == null ? 'lo que cuadra' : '$' + valorDefontana}, el ajuste es por las 10 a $0`,
              10000, Math.round(c.ajuste));
    comprobar('   y el monto cuadra con el PMP que promete', 0, cuadra(r));
  }
});

escenario('El ajuste nunca deja el PMP más lejos de lo que debería', () => {
  // Lo que pasaba antes: con el inventario inflado se proponía SUMAR valor.
  for (const valorDefontana of [null, 120000, 5000, 60000, 1000]) {
    const r = pantalla(informe(MOVS, valorDefontana));
    const u = r.docs[r.docs.length - 1], c = r.cost.corr;
    const antes = Math.abs(u.valorInv / u.saldo - c.pmp);
    const despues = Math.abs((u.valorInv + c.ajuste) / u.saldo - c.pmp);
    comprobar(`con Defontana en ${valorDefontana == null ? 'lo que cuadra' : '$' + valorDefontana}, acerca el PMP`,
              true, despues <= antes + 0.001);
  }
});

// --- Qué se teclea en Defontana ---
//
// El comprobante se carga por unidad, y el campo "Costo Unitario" de Defontana
// es el costo con que debe QUEDAR el artículo, no el monto a sacarle: Defontana
// multiplica por el stock y arma el total sola.
//
// Decirle el monto por unidad la hizo teclear $3.230,87 para 209 brochas que
// debían quedar en $1.283,23: Defontana entendió "déjalas a $3.230,87" y movió
// $268.196 en vez de $675.252, dejando el inventario al triple de lo que vale.

escenario('Dice qué poner en "Costo Unitario", no cuánto sacar por unidad', () => {
  const r = pantalla(informe(MOVS, 120000));
  const txt = r.cost.hacer.map(h => h.txt).join(' ');
  // Defontana tiene $120.000 y faltan los $10.000 de las 10 que entraron a $0:
  // el inventario debe quedar en $130.000 por 30 unidades, o sea $4.333 c/u
  comprobar('el ajuste es por las 10 unidades que entraron a $0', 10000, Math.round(r.cost.corr.ajuste));
  comprobar('el costo con que debe quedar', 4333, Math.round(r.cost.corr.pmp));
  comprobar('eso es lo que manda teclear', true, /"Costo Unitario" de Defontana pon \$4\.333/.test(txt));
  comprobar('y dice sobre cuántas unidades', true, /por las 30 unidades/.test(txt));
  // El monto por unidad ($3.000) es justamente el número equivocado: tecleado
  // en ese campo Defontana lo toma como el costo a dejar.
  comprobar('NO manda teclear el monto por unidad', false, /Costo Unitario" de Defontana pon \$3\.000/.test(txt));
});

escenario('Lo que Defontana va a calcular cuadra con el ajuste', () => {
  // Defontana hace: valor de hoy − costo tecleado × stock. Eso tiene que dar
  // exactamente el ajuste propuesto, o el inventario no queda donde debe.
  for (const valorDefontana of [120000, 60000]) {
    const r = pantalla(informe(MOVS, valorDefontana));
    const u = r.docs[r.docs.length - 1], c = r.cost.corr;
    const loQueMueveDefontana = u.valorInv - c.pmp * u.saldo;
    comprobar(`con Defontana en $${valorDefontana}, mueve lo propuesto`,
              Math.round(-c.ajuste), Math.round(loQueMueveDefontana));
  }
});

escenario('El costo a teclear lleva decimales', () => {
  // 130.000 entre 30 no es redondo. Si el costo unitario se redondea a peso,
  // el total que arma Defontana se corre.
  const r = pantalla(informe(MOVS, 120000));
  const c = r.cost.corr;
  comprobar('son 30 unidades', 30, Math.round(c.unidades));
  comprobar('el costo a dejar no es redondo', true, Math.abs(c.pmp - Math.round(c.pmp)) > 0.001);
  comprobar('y se muestra con sus decimales', true,
            /pon \$4\.333,33 —/.test(r.cost.hacer.map(h => h.txt).join(' ')));
  comprobar('redondear a peso correría el total', true, Math.abs((4333 - c.pmp) * 30) > 9);
});

escenario('El plan lleva el costo a teclear y las unidades', () => {
  const docs = informe(MOVS, 120000);
  const out = compute(docs);
  state.rows = out.rows; state.zero = out.zero;
  const x = buildPlan().cost.find(y => y.corr);
  comprobar('las unidades', 30, Math.round(x.corr.unidades));
  comprobar('y el costo con que debe quedar', 4333, Math.round(x.corr.pmp));
});

escenario('Un costo fuera de lo normal también manda el costo a dejar', () => {
  // Otro camino distinto del de los $0: acá el objetivo es lo que suele costar.
  const malo = [ing(1, 1000, 1), ing(1, 1000, 2), ing(1, 1000, 3), ing(10, 20000, 4)];
  const r = pantalla(informe(malo));
  const out = compute(informe(malo));
  state.rows = out.rows; state.zero = out.zero;
  const x = buildPlan().cost.find(y => y.corr);
  comprobar('hay una línea con ajuste', true, !!x);
  if (!x) return;
  comprobar('las unidades son las 13 que quedan', 13, Math.round(x.corr.unidades));
  comprobar('el costo a dejar es el habitual', 1000, Math.round(x.corr.pmp));
  comprobar('y el paso lo dice', true,
            /"Costo Unitario" de Defontana pon \$1\.000/.test(out.rows[0].costExtra[0].rev.hacer));
});

escenario('Sin un costo escrito no se propone ningún monto', () => {
  // Lo que ella pidió: mostrar, no estimar. El sistema enseña las cifras
  // exactas —cuánto entró a $0, qué tiene Defontana hoy— y pide el costo.
  const r = pantalla(informe(MOVS, 120000), null);
  comprobar('sigue pidiendo revisar el costo', true, !!(r.cost && r.cost.need));
  comprobar('pero sin monto', null, r.cost.corr);
  const txt = r.cost.hacer.map(h => h.txt).join(' ');
  comprobar('dice qué entró a $0', true, /entró 10 a \$0 con FACTURA #100/.test(txt));
  comprobar('y pide escribir el costo', true, /Escribe el costo en la columna PMP/.test(txt));
  comprobar('sin nombrar entrada ni salida, que no se sabe', false, /ENTRADA|SALIDA/.test(txt));
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
