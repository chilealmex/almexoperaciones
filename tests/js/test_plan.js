/* El paso 2 del plan: "Corregir costos".

   El cálculo de costos malos vive en la vista "Costos a revisar", que es por
   documento. El plan y el contador del panel "Orden recomendado" se arman
   desde las filas de productos. Si el producto no lleva colgado su costo malo,
   se ve en esa vista y no entra nunca al plan, que es lo que ella sigue para
   regularizar: con su informe real el paso 2 decía 1 producto cuando había 53. */
const {porId} = require('./entorno.js');
const {compute, buildPlan, docSteps, parseArticulos, state} = require('../../app/static/js/regularizacion.js');

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
const ingreso = (art, qty, cu, dia) => ({art, kind: 'in', qty, cu, fecha: DIA(2026, 8, dia)});
const egreso = (art, qty, dia) => ({art, kind: 'out', qty, cu: 0, fecha: DIA(2026, 8, dia)});

// El informe trae el saldo y el valor corriendo fila a fila, por artículo: las
// salidas se valorizan al PMP del momento.
function docsDe(lista) {
  const saldo = new Map(), valorInv = new Map();
  return lista.map((d, i) => {
    const a = d.art;
    let s = saldo.get(a) || 0, v = valorInv.get(a) || 0, valor = d.cu * d.qty;
    if (d.kind === 'in') { s += d.qty; v += valor; }
    else { const pmp = s > 0 ? v / s : 0; valor = pmp * d.qty; s -= d.qty; v -= valor; }
    saldo.set(a, s); valorInv.set(a, v);
    return {art: a, key: a.replace(/[^A-Z0-9]/g, ''), nameKey: 'NOMBRE' + a, tipo: 'FACTURA',
            folio: String(100 + i), fecha: d.fecha, kind: d.kind, qty: d.qty, saldo: s, valor,
            valorInv: v, orig: 'CENTRAL', dest: 'CENTRAL', estado: 'Aprobado', motivo: '',
            desc: 'PRODUCTO ' + a};
  });
}

// Arma la pantalla completa: las filas, la vista de costos y el plan.
function pantalla(lista, conteo, hechos, costoAMano = 1000) {
  state.stock = conteo || []; state.recount = new Map(); state.manual = new Set();
  // El monto del ajuste de costo sale del costo escrito a mano: sin eso sólo
  // se muestran las cifras. Estas pruebas lo escriben para comprobar el monto.
  state.hechos = hechos || new Map(); state.pmpEdit = costoAMano == null ? new Map() : new Map([['AAA', costoAMano], ['BBB', costoAMano]]); state.ajustes = [];
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  const mov = docsDe(lista);
  state.mov = mov;
  const out = compute(mov);
  state.rows = out.rows; state.zero = out.zero;
  return {rows: out.rows, zero: out.zero, plan: buildPlan()};
}

const enPaso2 = p => new Set(p.plan.cost.map(x => x.r.code));
// El contador del panel "Orden recomendado" usa este mismo criterio
const cuentaDelPanel = p => p.rows.filter(r => docSteps(r).some(x => x.k === 'cost')).length;

// Tres compras normales a $1.000 y una entrada a $20.000 que quedó en bodega.
const MALO = a => [ingreso(a, 1, 1000, 1), ingreso(a, 1, 1000, 2), ingreso(a, 1, 1000, 3), ingreso(a, 10, 20000, 4)];

escenario('Un costo fuera de lo normal entra al paso 2 del plan', () => {
  const p = pantalla(MALO('AAA'));
  comprobar('la vista de costos lo pide', true, p.zero.some(z => z.raro && z.rev.need));
  comprobar('y el plan también', true, enPaso2(p).has('AAA'));
  comprobar('una sola línea', 1, p.plan.cost.length);
  comprobar('el panel cuenta 1 producto', 1, cuentaDelPanel(p));
  const x = p.plan.cost[0];
  comprobar('dice qué documento lo dejó así', true, /entró a .*20\.000/.test(x.doc));
  comprobar('el costo a usar es el habitual', 1000, x.v);
  comprobar('la cantidad es lo que queda en bodega', 13, x.qty);
  // 13 unidades que deberían valer 13.000 y hoy valen 203.000
  comprobar('y el ajuste de valor', -190000, Math.round(x.corr.ajuste));
  comprobar('con el detalle de qué hacer', true, /Ajuste de costo/.test(x.nota));
});

escenario('Sin stock hoy no entra: ese costo ya salió con las salidas', () => {
  const p = pantalla([...MALO('AAA'), egreso('AAA', 13, 5)]);
  comprobar('no se muestra en la vista de costos', false, p.zero.some(z => z.raro));
  comprobar('y el plan no lo pide', 0, p.plan.cost.length);
  comprobar('y el panel tampoco', 0, cuentaDelPanel(p));
});

escenario('Si el PMP de hoy ya se acomodó, tampoco', () => {
  // Después del ingreso malo entran 200 a $1.000: el PMP vuelve a lo normal
  const p = pantalla([...MALO('AAA'), ingreso('AAA', 200, 1000, 5)]);
  comprobar('el plan no lo pide', 0, p.plan.cost.length);
});

escenario('Varios productos malos: uno por producto, no uno por documento', () => {
  // BBB tiene DOS ingresos raros; el ajuste de costo es del producto, no del
  // documento: pedirlo dos veces lo descuadraría por el doble.
  const p = pantalla([...MALO('AAA'),
    ingreso('BBB', 1, 1000, 1), ingreso('BBB', 1, 1000, 2), ingreso('BBB', 1, 1000, 3),
    ingreso('BBB', 10, 20000, 4), ingreso('BBB', 10, 30000, 5)]);
  comprobar('dos productos en el paso 2', 2, enPaso2(p).size);
  comprobar('y dos líneas, no tres', 2, p.plan.cost.length);
  comprobar('el panel cuenta 2 productos', 2, cuentaDelPanel(p));
});

escenario('Un producto a $0 no se pide dos veces', () => {
  // Entró a $0 teniendo compras normales antes: lo toma el camino de los $0.
  const p = pantalla([ingreso('AAA', 1, 1000, 1), ingreso('AAA', 1, 1000, 2),
                      ingreso('AAA', 1, 1000, 3), ingreso('AAA', 10, 0, 4)]);
  comprobar('aparece en el paso 2', true, enPaso2(p).has('AAA'));
  comprobar('una sola línea', 1, p.plan.cost.length);
  comprobar('el panel cuenta 1 producto', 1, cuentaDelPanel(p));
});

escenario('Una valorización imposible también entra al paso 2', () => {
  // Valor sin unidades: salió todo y el inventario sigue valiendo $5.000. No
  // sale de una cuenta bien hecha —se arma a mano— porque justamente es un
  // estado en que Defontana no debería poder quedar.
  //
  // Lo tiene que decir el stock valorizado: el producto listado, con 0
  // unidades y un Total que no es cero. Del arrastre del informe de documentos
  // no alcanza, porque es una reconstrucción y el ajuste sacaría valor que
  // Defontana no tiene.
  const mov = docsDe([ingreso('AAA', 10, 1000, 1), ingreso('AAA', 10, 0, 2)]);
  mov.push({...mov[1], folio: '200', fecha: DIA(2026, 8, 3), kind: 'out', qty: 20,
            valor: 5000, saldo: 0, valorInv: 5000});
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  state.articulos = parseArticulos([
    ['Informe de Inventario'], ['Empresa: X'], ['Fecha de generación: 07-10-2026, 10:37 a. m.'], [],
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor Unidad', 'Total'],
    ['AAA', 'PRODUCTO AAA', 'BODEGA CENTRAL', 0, 'UN', 0, 5000]]);
  state.hechos = new Map(); state.pmpEdit = new Map([['AAA', 1000]]); state.ajustes = []; state.mov = mov;
  const out = compute(mov);
  state.rows = out.rows; state.zero = out.zero;
  const p = {rows: out.rows, zero: out.zero, plan: buildPlan()};
  comprobar('la vista lo detecta', true, p.zero.some(z => z.imposible === 'valorSinStock'));
  comprobar('y el plan lo pide', true, enPaso2(p).has('AAA'));
  const x = p.plan.cost.find(y => y.doc === 'Valor sin unidades');
  comprobar('con su nombre', true, !!x);
  comprobar('y el ajuste deja el valor en $0', -5000, x && Math.round(x.corr.ajuste));
  comprobar('el panel lo cuenta', 1, cuentaDelPanel(p));
  state.articulos = null;
});

escenario('Si no se sabe el costo, no se inventa uno malo', () => {
  // Las dos entradas son a $1: no hay ninguna compra de verdad con qué
  // comparar. La compra anterior más cercana al segundo ingreso es el primero,
  // que es el mismo dato de relleno que está mal; apoyarse en él es corregir
  // un $1 con otro $1. Y como son sólo dos, tampoco hay mediana.
  const p = pantalla([ingreso('AAA', 2, 1, 1), ingreso('AAA', 3, 1, 2)], undefined, undefined, null);
  comprobar('entra al paso 2', true, enPaso2(p).has('AAA'));
  comprobar('una línea por producto', 1, p.plan.cost.length);
  const x = p.plan.cost[0];
  comprobar('no propone un costo', null, x.v);
  comprobar('y pide escribirlo a mano', true, /Escribe el costo en la columna PMP/.test(x.nota));
  comprobar('sin inventar un ajuste de valor', null, x.corr);
});

escenario('Un producto marcado como ya regularizado no entra', () => {
  // La marca "Ya regularizado" cuelga del conteo, así que hace falta uno.
  const conteo = [{key: 'AAA', code: 'AAA', name: 'PRODUCTO AAA', stock: 13,
                   fecha: DIA(2026, 8, 6), linea: '', um: '', por: '', estado: ''}];
  const sinMarca = pantalla(MALO('AAA'), conteo);
  comprobar('contado y sin marcar, el plan lo pide', 1, sinMarca.plan.cost.length);

  const marcado = pantalla(MALO('AAA'), conteo, new Map([['AAA', null]]));
  comprobar('marcado como ya regularizado, no', 0, marcado.plan.cost.length);
  comprobar('y el panel tampoco lo cuenta', 0, cuentaDelPanel(marcado));
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
