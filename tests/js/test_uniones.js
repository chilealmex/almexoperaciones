/* Regularización respeta las parejas confirmadas en Unificar códigos.

   Esta pantalla trabaja con los archivos que se suben en ella, no con el
   maestro, así que cruza los códigos por su cuenta: ignora signos, acentos y
   ceros de adelante. Eso alcanza para "011-CON-OTH-01" y "11-CON-OTH-01", pero
   no para dos códigos que no se parecen y que alguien decidió que son el mismo
   artículo. Sin esto, ese artículo queda partido en dos y aparece descuadrado
   por los dos lados: faltando por un código y sobrando por el otro. */
const {elemento, porId} = require('./entorno.js');

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

function conUniones(pares) {
  porId.set('regx-config', Object.assign(elemento(), {
    textContent: JSON.stringify({uniones: pares}),
  }));
  delete require.cache[require.resolve('../../app/static/js/regularizacion.js')];
  return require('../../app/static/js/regularizacion.js');
}

const DIA = (a, m, d) => new Date(a, m - 1, d);

function cruzar(mod, uniones, contado, docsDe) {
  const {compute, state} = mod;
  let saldo = 0, valorInv = 0;
  const movs = docsDe.map((d, i) => {
    const valor = d.cu * d.qty;
    if (d.kind === 'in') { saldo += d.qty; valorInv += valor; }
    else { const pmp = saldo > 0 ? valorInv / saldo : 0; saldo -= d.qty; valorInv -= pmp * d.qty; }
    return {art: d.art, key: mod.parseMov ? undefined : undefined, nameKey: '', tipo: 'PARTE', folio: String(i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo, valor, valorInv,
            orig: 'CENTRAL', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', desc: 'ARTICULO'};
  });
  // La clave la pone el lector, igual que al leer el archivo de verdad
  const filas = [['Tipo Documento','Estado','Folio','Fecha','Bod. Origen','Bod. Destino','Motivo',
                  'Movimiento','Artículo','Descripción','Cant. Movimiento','U. Medida',
                  'Valor Movimiento','Saldo Inventario','Valor Inventario']];
  for (const m of movs) filas.push(['PARTE','Aprobado',m.folio,
    m.fecha.getFullYear()+'-'+String(m.fecha.getMonth()+1).padStart(2,'0')+'-'+String(m.fecha.getDate()).padStart(2,'0'),
    '','CENTRAL','', m.kind === 'in' ? 'Ingreso' : 'Egreso', m.art, 'DESCRIPCION DE ' + m.art, m.qty, 'UN', m.valor, m.saldo, m.valorInv]);
  const leidos = mod.parseMov(filas);

  state.stock = contado.map(c => ({code: c.art, key: '', name: 'ARTICULO', stock: c.qty, fecha: c.fecha,
                                   por: 'B', estado: 'Contado', um: '', linea: ''}));
  // La clave del conteo también la pone el lector
  const filasStock = [['Código', 'Nombre', 'Stock físico', 'Fecha del conteo']];
  for (const c of contado) filasStock.push([c.art, 'DESCRIPCION DE ' + c.art, c.qty,
    c.fecha.getFullYear()+'-'+String(c.fecha.getMonth()+1).padStart(2,'0')+'-'+String(c.fecha.getDate()).padStart(2,'0')]);
  state.stock = mod.parseStock(filasStock);
  state.recount = new Map(); state.manual = new Set(); state.hechos = new Map(); state.pmpEdit = new Map();
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  return compute(leidos).rows;
}

// Dos códigos que NO se parecen en nada: la pantalla no puede adivinar que son
// el mismo artículo, sólo puede saberlo porque alguien lo confirmó.
const CONTEO = [{art: 'ABC-100', qty: 10, fecha: DIA(2026, 9, 1)}];
const MOVS = [{art: 'XYZ-7', kind: 'in', qty: 12, cu: 1000, fecha: DIA(2026, 8, 1)}];

escenario('Sin la unión confirmada, el artículo queda partido en dos', () => {
  // Es lo que pasaba: el conteo por un código y los movimientos por el otro
  const mod = conUniones([]);
  const filas = cruzar(mod, [], CONTEO, MOVS);
  comprobar('salen dos filas', 2, filas.length);
});

escenario('Con la unión confirmada, es un solo artículo', () => {
  const mod = conUniones([['XYZ-7', 'ABC-100']]);
  const filas = cruzar(mod, [], CONTEO, MOVS);
  comprobar('sale una sola fila', 1, filas.length);
  const r = filas[0];
  comprobar('con el conteo puesto', 10, r.s && r.s.stock);
  comprobar('y los movimientos del otro código', 12, r.sysAtCount);
  comprobar('el ajuste sale bien: sobran 2', -2, mod.ajusteDelConteo(r));
});

escenario('La unión vale en cualquier sentido que venga el par', () => {
  const mod = conUniones([['ABC-100', 'XYZ-7']]);
  comprobar('igual queda un solo artículo', 1, cruzar(mod, [], CONTEO, MOVS).length);
});

escenario('Una cadena de uniones se sigue hasta el final', () => {
  // A se unió con B, y B después con C: A tiene que llegar a C
  const mod = conUniones([['AAA-1', 'BBB-2'], ['BBB-2', 'CCC-3']]);
  const filas = cruzar(mod, [], [{art: 'AAA-1', qty: 5, fecha: DIA(2026, 9, 1)}],
                       [{art: 'CCC-3', kind: 'in', qty: 5, cu: 100, fecha: DIA(2026, 8, 1)}]);
  comprobar('queda un solo artículo', 1, filas.length);
});

escenario('Una unión circular no cuelga el cálculo', () => {
  // No debería pasar, pero un dato malo no puede dejar la pantalla congelada
  const mod = conUniones([['AAA-1', 'BBB-2'], ['BBB-2', 'AAA-1']]);
  const filas = cruzar(mod, [], [{art: 'AAA-1', qty: 5, fecha: DIA(2026, 9, 1)}],
                       [{art: 'AAA-1', kind: 'in', qty: 5, cu: 100, fecha: DIA(2026, 8, 1)}]);
  comprobar('responde igual', 1, filas.length);
});

escenario('Sin uniones configuradas, todo sigue como antes', () => {
  const mod = conUniones([]);
  const filas = cruzar(mod, [], [{art: 'X-1', qty: 5, fecha: DIA(2026, 9, 1)}],
                       [{art: 'X-1', kind: 'in', qty: 5, cu: 100, fecha: DIA(2026, 8, 1)}]);
  comprobar('un artículo, cuadrado', 1, filas.length);
  comprobar('sin ajuste', 0, mod.ajusteDelConteo(filas[0]));
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
