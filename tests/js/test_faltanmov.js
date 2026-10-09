/* Cuando al informe le faltan movimientos de un producto.

   "Lo que debería tener hoy" se calcula sumando el conteo y los movimientos
   posteriores. Si el informe no trae todos, esa cuenta sale mal y el ajuste
   que se propone es un fantasma: con sus archivos, 23083-012 pedía aumentar 4
   unidades que no faltaban, y el diagnóstico las atribuía a una salida de 8
   del 2025.

   Se nota porque el propio informe se contradice: el Saldo Inventario de una
   fila no es el de la anterior más lo que esa fila movió. Son 4 productos de
   1.737 en su informe, pero son justo los que hacen dudar de todo lo demás. */
const {porId} = require('./entorno.js');
const {compute, buildPlan, docSteps, state} = require('../../app/static/js/regularizacion.js');

let fallas = 0, hechas = 0;
function escenario(t, fn){ console.log('\n' + t); try { fn(); } catch(e){ fallas++; hechas++; console.log(`  ✘ reventó: ${e.message}`); } }
function comprobar(t, esp, obt){ hechas++; if (esp === obt){ console.log(`  ✔ ${t}`); return; } fallas++; console.log(`  ✘ ${t}\n      esperaba ${esp}, obtuvo ${obt}`); }

const DIA = (a, m, d) => new Date(a, m - 1, d);

// Los saldos van puestos a mano: es lo que trae el informe, y es justo donde
// aparece la contradicción.
function docs(filas){
  return filas.map((f, i) => ({
    art: f.art || 'AAA', key: 'AAA', nameKey: 'NAAA', tipo: f.tipo || 'ENVÍO A PRODUCCIÓN',
    folio: String(f.folio ?? 100 + i), fecha: f.fecha, kind: f.kind, qty: f.qty,
    valor: f.valor ?? f.qty * 1000, saldo: f.saldo, valorInv: f.valorInv ?? f.saldo * 1000,
    um: '', orig: f.kind === 'out' ? 'C' : '', dest: f.kind === 'in' ? 'C' : '',
    estado: 'Aprobado', motivo: '', desc: 'PROD AAA', traspaso: !!f.traspaso,
  }));
}

function pantalla(filas, contado){
  state.stock = contado ? [{key: 'AAA', code: 'AAA', name: 'PROD AAA', stock: contado.stock,
    fecha: contado.fecha, linea: '', um: '', por: '', estado: '', variants: ['AAA'], nCounted: 1}] : [];
  state.recount = new Map(); state.manual = new Set(); state.hechos = new Map();
  state.pmpEdit = new Map(); state.ajustes = []; state.articulos = null;
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  const mov = docs(filas);
  state.mov = mov;
  const out = compute(mov);
  state.rows = out.rows; state.zero = out.zero;
  return {r: out.rows[0], plan: buildPlan()};
}

// 100 unidades, salen 2 y salen 2: el saldo baja de 2 en 2 y todo cuadra.
const SANO = [
  {kind: 'in', qty: 100, saldo: 100, fecha: DIA(2026, 8, 1), tipo: 'PARTE DE ENTRADA'},
  {kind: 'out', qty: 2, saldo: 98, fecha: DIA(2026, 9, 1)},
  {kind: 'out', qty: 2, saldo: 96, fecha: DIA(2026, 9, 2)},
];

escenario('Un producto cuyo saldo sigue a sus movimientos no se marca', () => {
  const {r} = pantalla(SANO);
  comprobar('sin aviso', null, r.faltanMov);
});

escenario('Un saldo que salta se detecta y se dice cuánto', () => {
  // Entre la primera y la segunda salida el saldo sube 14 sin que haya nada
  // que lo explique: es el caso de 23083-012.
  const {r} = pantalla([
    {kind: 'in', qty: 100, saldo: 100, fecha: DIA(2026, 8, 1), tipo: 'PARTE DE ENTRADA'},
    {kind: 'out', qty: 2, saldo: 98, fecha: DIA(2026, 9, 1)},
    {kind: 'out', qty: 2, saldo: 110, fecha: DIA(2026, 9, 2), folio: 148},
  ]);
  comprobar('se detecta', true, !!r.faltanMov);
  comprobar('un solo salto', 1, r.faltanMov.saltos);
  // 98 − 2 = 96, pero el informe dice 110: 14 unidades sin explicar
  comprobar('y las unidades que no explica', 14, r.faltanMov.unidades);
  comprobar('dice en qué documento empieza', '148', r.faltanMov.desde.folio);
});

escenario('Va al paso 1, no a entradas ni salidas', () => {
  // Contado 100 el 01-09. El saldo salta, así que la cuenta de "debería tener
  // hoy" no sirve y lo que corresponde es mirarlo, no ajustar por ella.
  const {r, plan} = pantalla([
    {kind: 'in', qty: 100, saldo: 100, fecha: DIA(2026, 8, 1), tipo: 'PARTE DE ENTRADA'},
    {kind: 'out', qty: 2, saldo: 98, fecha: DIA(2026, 9, 2)},
    {kind: 'out', qty: 2, saldo: 110, fecha: DIA(2026, 9, 3)},
  ], {stock: 100, fecha: DIA(2026, 9, 1)});
  comprobar('está en el paso 1', 1, plan.verify.length);
  comprobar('y no en entradas', 0, plan.in.length);
  comprobar('ni en salidas', 0, plan.out.length);
  const v = plan.verify[0];
  comprobar('con su motivo', 'Al informe le faltan movimientos de este producto', v.motivo);
  comprobar('y el aviso explica el salto', true, /Saldo Inventario salta/.test(v.txt));
  comprobar('diciendo que no se ajuste por la diferencia', true, /No ajustes por la diferencia calculada/.test(v.txt));
  comprobar('el paso del producto también lo dice', true,
            docSteps(r).some(x => x.k === 'verify' && /le faltan movimientos/.test(x.txt)));
});

escenario('El aviso gana sobre el diagnóstico de la diferencia', () => {
  // El diagnóstico ("faltan 10 en Defontana, falta registrar un ingreso")
  // está hecho sobre la misma historia incompleta, así que explicaría un
  // fantasma. En 23083-012 decía que lo que sobra calza con una salida de 8
  // del 2025, cuando lo que pasa es que faltan 56 unidades en el informe.
  const {r, plan} = pantalla([
    {kind: 'in', qty: 90, saldo: 90, fecha: DIA(2026, 8, 1), tipo: 'PARTE DE ENTRADA'},
    {kind: 'out', qty: 10, saldo: 80, fecha: DIA(2026, 9, 5)},
    {kind: 'out', qty: 2, saldo: 92, fecha: DIA(2026, 9, 6), folio: 148},
  ], {stock: 100, fecha: DIA(2026, 9, 1)});
  comprobar('el producto trae un diagnóstico', true, /falta registrar un ingreso/.test(r.obs[0]));
  comprobar('pero el plan muestra el aviso', true, /le faltan movimientos/.test(plan.verify[0].txt));
  comprobar('y no el diagnóstico', false, /falta registrar un ingreso/.test(plan.verify[0].txt));
});

escenario('El traspaso entre bodegas no cuenta como salto', () => {
  // Un traspaso no mueve el saldo del artículo: viene marcado "Ingreso" pero
  // el Saldo Inventario queda igual. Eso es correcto, no una contradicción.
  const {r} = pantalla([
    {kind: 'in', qty: 100, saldo: 100, fecha: DIA(2026, 8, 1), tipo: 'PARTE DE ENTRADA'},
    {kind: 'in', qty: 50, saldo: 100, fecha: DIA(2026, 9, 1), tipo: 'TRASPASO ENTRE BODEGAS', traspaso: true},
    {kind: 'out', qty: 2, saldo: 98, fecha: DIA(2026, 9, 2)},
  ]);
  comprobar('sin aviso', null, r.faltanMov);
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
