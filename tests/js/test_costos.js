/* Ingresos mal valorizados que no son $0.

   Un ingreso puede estar mal costeado sin entrar a cero: a $1, o a $20.000
   cuando el producto se compra a $1.000. Defontana valoriza cada salida al PMP
   del momento, así que uno de ésos ensucia la valorización de todo lo que
   salga después, y no se nota mirando cantidades. */
const {porId} = require('./entorno.js');
const {compute, costoHabitual, costoAtipico, state} = require('../../app/static/js/regularizacion.js');

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const DIA = (a, m, d) => new Date(a, m - 1, d);
const ingreso = (qty, cu, dia) => ({kind: 'in', qty, cu, fecha: DIA(2026, 8, dia)});

function docsDe(lista) {
  let saldo = 0;
  return lista.map((d, i) => {
    saldo += d.kind === 'in' ? d.qty : -d.qty;
    return {art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: 'FACTURA', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo, valor: d.cu * d.qty, valorInv: null,
            orig: 'CENTRAL', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', desc: 'ARTICULO'};
  });
}

console.log('\nLo que suele costar: la mediana, no el promedio');
{
  // El promedio se lo lleva justamente el ingreso raro que se busca
  const docs = docsDe([ingreso(10, 1000, 1), ingreso(10, 1000, 2), ingreso(10, 1000, 3), ingreso(1, 20000, 4)]);
  comprobar('el costo habitual es 1.000, no 5.750', 1000, costoHabitual(docs));
}

console.log('\nEl caso de ella: se compra a 1.000 y hubo una entrada a 20.000');
{
  const docs = docsDe([ingreso(10, 1000, 1), ingreso(10, 1000, 2), ingreso(10, 1000, 3), ingreso(1, 20000, 4)]);
  const habitual = costoHabitual(docs);
  comprobar('los ingresos normales no se marcan', null, costoAtipico(docs[0], habitual));
  const raro = costoAtipico(docs[3], habitual);
  comprobar('el de 20.000 sí se marca', true, !!raro);
  comprobar('y dice que es 20 veces lo normal', 20, raro && raro.veces);
}

console.log('\nUn ingreso a $1 se marca aunque no haya con qué compararlo');
{
  const docs = docsDe([ingreso(5, 1, 1)]);
  comprobar('sin costo habitual no se sabe qué es normal', null, costoHabitual(docs));
  const raro = costoAtipico(docs[0], null);
  comprobar('pero $1 no es un costo: se marca igual', true, !!(raro && raro.irrisorio));
}

console.log('\nUn ingreso mucho más barato de lo normal también');
{
  const docs = docsDe([ingreso(10, 1000, 1), ingreso(10, 1000, 2), ingreso(10, 1000, 3), ingreso(5, 100, 4)]);
  const raro = costoAtipico(docs[3], costoHabitual(docs));
  comprobar('se marca', true, !!raro);
  comprobar('y dice que es más barato', true, raro && raro.barato);
}

console.log('\nLo que NO se puede marcar, para no llenar de avisos falsos');
{
  const subeDeAPoco = docsDe([ingreso(10, 1000, 1), ingreso(10, 1200, 2), ingreso(10, 1400, 3), ingreso(10, 1800, 4)]);
  comprobar('un alza normal de precios no es un error',
            null, costoAtipico(subeDeAPoco[3], costoHabitual(subeDeAPoco)));

  const dosIngresos = docsDe([ingreso(10, 1000, 1), ingreso(10, 20000, 2)]);
  comprobar('con dos ingresos no se sabe cuál es el raro', null, costoHabitual(dosIngresos));
}

console.log('\nEn la pantalla sale como algo a revisar, con qué hacer');
{
  state.stock = [];
  state.recount = new Map(); state.manual = new Set(); state.hechos = new Map();
  state.pmpEdit = state.pmpEdit || new Map();
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));

  const docs = docsDe([ingreso(10, 1000, 1), ingreso(10, 1000, 2), ingreso(10, 1000, 3), ingreso(1, 20000, 4)]);
  const z = compute(docs).zero;
  comprobar('aparece una sola fila, la del ingreso raro', 1, z.length);
  const fila = z[0];
  comprobar('marcada para revisar', true, fila.rev.need);
  comprobar('propone corregir al costo habitual', 1000, fila.rev.costo.v);
  comprobar('y dice cuántas veces se fue', true, /20 veces más caro/.test(fila.rev.txt));
  comprobar('explica que ensucia lo que salió después', true, /mal valorizado/.test(fila.rev.txt));
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
