/* Costos a regularizar.

   Lo que importa no es qué documento estuvo mal, sino qué producto tiene HOY
   el costo malo y todavía tiene stock. Un ingreso mal costeado de hace un año,
   cuyas unidades ya salieron, no deja nada que revalorizar: proponer un ajuste
   ahí sería inventar un movimiento sin motivo. */
const {porId} = require('./entorno.js');
const {compute, costoHabitual, costoAtipico, comoEstaHoy, state} =
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

const DIA = (a, m, d) => new Date(a, m - 1, d);
const ingreso = (qty, cu, dia) => ({kind: 'in', qty, cu, fecha: DIA(2026, 8, dia)});
const egreso = (qty, dia) => ({kind: 'out', qty, cu: 0, fecha: DIA(2026, 8, dia)});

function docsDe(lista) {
  // El informe de verdad trae el saldo y el valor del inventario corriendo
  // fila a fila: las salidas se valorizan al PMP del momento.
  let saldo = 0, valorInv = 0;
  return lista.map((d, i) => {
    let valor = d.cu * d.qty;
    if (d.kind === 'in') { saldo += d.qty; valorInv += valor; }
    else {
      const pmp = saldo > 0 ? valorInv / saldo : 0;
      valor = pmp * d.qty; saldo -= d.qty; valorInv -= valor;
    }
    return {art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: 'FACTURA', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo, valor, valorInv,
            orig: 'CENTRAL', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', desc: 'ARTICULO'};
  });
}

function enPantalla(lista, costoAMano) {
  state.stock = []; state.recount = new Map(); state.manual = new Set(); state.hechos = new Map();
  state.pmpEdit = new Map();
  if (costoAMano != null) state.pmpEdit.set('ART1', costoAMano);
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  return compute(docsDe(lista)).zero;
}

// --- Reconocer el ingreso raro ---

escenario('Lo que suele costar: la mediana, no el promedio', () => {
  // El promedio se lo lleva justamente el ingreso raro que se busca
  const docs = docsDe([ingreso(10, 1000, 1), ingreso(10, 1000, 2), ingreso(10, 1000, 3), ingreso(1, 20000, 4)]);
  comprobar('el costo habitual es 1.000, no 5.750', 1000, costoHabitual(docs));
});

escenario('El caso de ella: se compra a 1.000 y hubo una entrada a 20.000', () => {
  const docs = docsDe([ingreso(10, 1000, 1), ingreso(10, 1000, 2), ingreso(10, 1000, 3), ingreso(1, 20000, 4)]);
  const habitual = costoHabitual(docs);
  comprobar('los ingresos normales no se marcan', null, costoAtipico(docs[0], habitual));
  const raro = costoAtipico(docs[3], habitual);
  comprobar('el de 20.000 sí se marca', true, !!raro);
  comprobar('y dice que es 20 veces lo normal', 20, raro && raro.veces);
});

escenario('Un ingreso a $1 se marca aunque no haya con qué compararlo', () => {
  const docs = docsDe([ingreso(5, 1, 1)]);
  comprobar('sin costo habitual no se sabe qué es normal', null, costoHabitual(docs));
  const raro = costoAtipico(docs[0], null);
  comprobar('pero $1 no es un costo: se marca igual', true, !!(raro && raro.irrisorio));
});

escenario('Un ingreso mucho más barato de lo normal también', () => {
  const docs = docsDe([ingreso(10, 1000, 1), ingreso(10, 1000, 2), ingreso(10, 1000, 3), ingreso(5, 100, 4)]);
  const raro = costoAtipico(docs[3], costoHabitual(docs));
  comprobar('se marca', true, !!raro);
  comprobar('y dice que es más barato', true, raro && raro.barato);
});

escenario('Lo que NO se marca, para no llenar de avisos falsos', () => {
  const subeDeAPoco = docsDe([ingreso(10, 1000, 1), ingreso(10, 1200, 2), ingreso(10, 1400, 3), ingreso(10, 1800, 4)]);
  comprobar('un alza normal de precios no es un error',
            null, costoAtipico(subeDeAPoco[3], costoHabitual(subeDeAPoco)));
  const dosIngresos = docsDe([ingreso(10, 1000, 1), ingreso(10, 20000, 2)]);
  comprobar('con dos ingresos no se sabe cuál es el raro', null, costoHabitual(dosIngresos));
});

// --- Qué se propone regularizar: sólo lo que hoy está mal Y tiene stock ---

const MALO_HOY = [ingreso(1, 1000, 1), ingreso(1, 1000, 2), ingreso(1, 1000, 3), ingreso(10, 20000, 4)];

escenario('Con stock y el PMP de hoy malo: se propone el ajuste de costo', () => {
  const z = enPantalla(MALO_HOY);
  comprobar('aparece una fila', 1, z.length);
  const rev = z[0].rev;
  comprobar('hay que regularizar', true, rev.need);
  comprobar('el costo a usar es el habitual', 1000, rev.costo.v);
  comprobar('propone un ajuste de costo', true, /Ajuste de costo/.test(rev.hacer));
  // 13 unidades que deberían valer 13.000 y hoy valen 203.000
  comprobar('por la diferencia de valor de lo que queda', -190000, Math.round(rev.ajusteCosto));
  comprobar('dice el PMP de hoy y lo que queda en bodega', true, /PMP de hoy/.test(rev.txt));
});

escenario('Sin stock hoy: no se propone nada', () => {
  // Las 13 unidades salieron: ese costo ya se fue con las salidas y no queda
  // nada que revalorizar. Proponer un ajuste acá es inventar un movimiento.
  const z = enPantalla([...MALO_HOY, egreso(13, 5)]);
  comprobar('la fila sigue apareciendo, para poder verla', 1, z.length);
  comprobar('pero no hay que ajustar', false, z[0].rev.need);
  comprobar('y dice por qué', true, /no quedan unidades/.test(z[0].rev.txt));
});

escenario('Con stock pero el PMP ya se acomodó: tampoco', () => {
  // Después del ingreso malo entraron muchas a precio normal: el PMP volvió
  const z = enPantalla([...MALO_HOY, ingreso(400, 1000, 5)]);
  comprobar('no hay que ajustar', false, z[0].rev.need);
  comprobar('y dice que el PMP de hoy ya está bien', true, /ya está en lo normal/.test(z[0].rev.txt));
});

// --- Cuando no se sabe cuánto cuesta ---

const SIN_REFERENCIA = [ingreso(5, 1, 1)];

escenario('Sin con qué compararlo, se pide el costo en vez de inventarlo', () => {
  const z = enPantalla(SIN_REFERENCIA);
  comprobar('hay que regularizar', true, z[0].rev.need);
  comprobar('pide escribir el costo', true, /Escríbelo en la columna PMP/.test(z[0].rev.hacer));
  comprobar('y no inventa un ajuste', null, z[0].rev.ajusteCosto);
});

escenario('Con el costo escrito a mano, se calcula el ajuste', () => {
  const z = enPantalla(SIN_REFERENCIA, 3000);
  const rev = z[0].rev;
  comprobar('usa el costo escrito', 3000, rev.costo.v);
  comprobar('dice que lo pusiste tú', 'Ingresado a mano', rev.costo.src);
  // 5 unidades que deberían valer 15.000 y hoy valen 5
  comprobar('y propone el ajuste', 14995, Math.round(rev.ajusteCosto));
});

escenario('Un producto con varios ingresos raros: el ajuste va una sola vez', () => {
  // El ajuste deja el valor de lo que queda en bodega en lo que corresponde:
  // es uno solo para el producto. Proponerlo en cada fila lleva a aplicarlo
  // tantas veces como filas, y a descuadrar por el doble o el triple.
  const z = enPantalla([ingreso(1, 1000, 1), ingreso(1, 1000, 2), ingreso(1, 1000, 3),
                        ingreso(10, 20000, 4), ingreso(10, 50000, 5)]);
  comprobar('las dos filas raras se muestran', 2, z.length);
  comprobar('pero sólo una pide el ajuste', 1, z.filter(x => x.rev.need).length);
  const secundaria = z.find(x => !x.rev.need);
  comprobar('la otra dice dónde está el ajuste', true, /una sola vez/.test(secundaria.rev.hacer));
  comprobar('y no trae un monto que se pueda aplicar de nuevo', null, secundaria.rev.ajusteCosto);
  comprobar('el ajuste que queda es el de la desviación mayor', true,
            /50/.test(String(Math.round(z.find(x => x.rev.need).raro.cu / 1000))));
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
