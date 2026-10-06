/* Verificar los ajustes con el Informe actualizado.

   Después de ajustar se vuelve a bajar el Informe de Defontana y se comprueba
   si quedó cuadrado. El caso que importa acá: movimientos registrados el mismo
   día del ajuste. La cantidad queda bien igual —sumar o restar no depende del
   orden— pero el PMP no, porque Defontana valoriza cada movimiento al costo
   que había en ese momento. */
const {porId} = require('./entorno.js');
const {computeCheck, state} = require('../../app/static/js/regularizacion.js');

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

function verificar(docs, contado, fechaConteo) {
  let saldo = 0, valorInv = 0;
  const movs = docs.map((d, i) => {
    let valor = d.cu != null ? d.cu * d.qty : 0;
    if (d.kind === 'in') { saldo += d.qty; valorInv += valor; }
    else { const pmp = saldo > 0 ? valorInv / saldo : 0; valor = pmp * d.qty; saldo -= d.qty; valorInv -= valor; }
    return {art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: d.tipo || 'PARTE', folio: String(i + 1),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo, valor, valorInv,
            orig: 'CENTRAL', dest: 'CENTRAL', estado: 'Aprobado', motivo: d.ajuste ? 'AJUSTE' : '',
            desc: 'ARTICULO', _aj: !!d.ajuste};
  });
  state.stock = [{code: 'ART-1', key: 'ART1', name: 'ARTICULO', stock: contado, fecha: fechaConteo,
                  por: 'B', estado: 'Contado', um: '', linea: ''}];
  state.recount = new Map(); state.manual = new Set(); state.hechos = new Map(); state.pmpEdit = new Map();
  state.mov2 = movs; state.ajSi = new Set(); state.ajNo = new Set();
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  computeCheck();
  return movs;
}

// Contado 5 el 01-09; Defontana tenía 3 -> hay que ingresar 2
const BASE = [
  {kind: 'in', qty: 3, cu: 1000, fecha: DIA(2026, 8, 20)},
];

escenario('Con un movimiento el mismo día del ajuste, avisa', () => {
  const movs = verificar([
    ...BASE,
    {kind: 'in', qty: 2, cu: 1000, fecha: DIA(2026, 10, 6), ajuste: true, tipo: 'PARTE DE ENTRADA'},
    {kind: 'in', qty: 10, cu: 5000, fecha: DIA(2026, 10, 6), tipo: 'PARTE DE ENTRADA'},
  ], 5, DIA(2026, 9, 1));

  const fila = state.checkRows[0];
  comprobar('la fila aparece en Verificar ajustes', true, !!fila);
  const aviso = (fila.cobs || []).find(t => /mismo día del ajuste/.test(t));
  comprobar('avisa del movimiento del mismo día', true, !!aviso);
  comprobar('explica que la cantidad igual queda bien', true, /cantidad queda bien/.test(aviso || ''));
  comprobar('y que el costo puede quedar distinto', true, /PMP del momento/.test(aviso || ''));
});

escenario('Sin movimientos ese día, no avisa de más', () => {
  verificar([
    ...BASE,
    {kind: 'in', qty: 2, cu: 1000, fecha: DIA(2026, 10, 6), ajuste: true, tipo: 'PARTE DE ENTRADA'},
    {kind: 'in', qty: 10, cu: 5000, fecha: DIA(2026, 10, 9), tipo: 'PARTE DE ENTRADA'},
  ], 5, DIA(2026, 9, 1));

  const fila = state.checkRows[0];
  comprobar('no hay aviso del mismo día', false,
            (fila.cobs || []).some(t => /mismo día del ajuste/.test(t)));
});

escenario('El ajuste bien hecho se marca como cuadrado', () => {
  verificar([
    ...BASE,
    {kind: 'in', qty: 2, cu: 1000, fecha: DIA(2026, 10, 6), ajuste: true, tipo: 'PARTE DE ENTRADA'},
  ], 5, DIA(2026, 9, 1));

  comprobar('quedó bien', 'ok', state.checkRows[0].ck);
});

escenario('Un ajuste por la cantidad equivocada se marca', () => {
  verificar([
    ...BASE,
    {kind: 'in', qty: 7, cu: 1000, fecha: DIA(2026, 10, 6), ajuste: true, tipo: 'PARTE DE ENTRADA'},
  ], 5, DIA(2026, 9, 1));

  comprobar('se marca con diferencia', 'wrong', state.checkRows[0].ck);
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
