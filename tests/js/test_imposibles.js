/* Valorizaciones que no pueden existir.

   Tres estados en que un artículo no puede quedar y que no se notan mirando
   cantidades: valor negativo, valor sin unidades, y stock negativo. No son "un
   costo distinto del esperado": son cuentas que no cierran, y casi siempre las
   deja un ajuste mal hecho. Importa verlas justo cuando se está ajustando. */
const {porId} = require('./entorno.js');
const {compute, valorizacionImposible, state} = require('../../app/static/js/regularizacion.js');

let fallas = 0, hechas = 0;
function escenario(titulo, fn) {
  console.log('\n' + titulo);
  try { fn(); } catch (e) { fallas++; hechas++; console.log(`  ✘ reventó: ${e.message}`); }
}
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  if (esperado === obtenido) { console.log(`  ✔ ${titulo}`); return; }
  fallas++;
  console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`);
}

const DIA = (a, m, d) => new Date(a, m - 1, d);

// Se arman los documentos con el saldo y el valor puestos a mano: es lo que
// trae el informe, y es justamente donde aparecen las cuentas que no cierran.
function docs(filas) {
  return filas.map((f, i) => ({
    art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: 'PARTE', folio: String(i),
    fecha: DIA(2026, 8, i + 1), kind: f.kind, qty: f.qty, valor: f.valor ?? 0,
    saldo: f.saldo, valorInv: f.valorInv, orig: 'CENTRAL', dest: 'CENTRAL',
    estado: 'Aprobado', motivo: '', desc: 'ARTICULO',
  }));
}

function enPantalla(filas) {
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  state.hechos = new Map(); state.pmpEdit = new Map();
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  return compute(docs(filas)).zero.filter(z => z.imposible);
}

escenario('Valor de inventario negativo', () => {
  const d = docs([{kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
                  {kind: 'out', qty: 2, valor: 9000, saldo: 3, valorInv: -4000}]);
  comprobar('se detecta', 'valorNegativo', (valorizacionImposible(d) || {}).cual);
  const filas = enPantalla([{kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
                            {kind: 'out', qty: 2, valor: 9000, saldo: 3, valorInv: -4000}]);
  comprobar('aparece en la pantalla', 1, filas.length);
  comprobar('marcada para revisar', true, filas[0].rev.need);
  comprobar('dice que un valor negativo no existe', true, /no existe/.test(filas[0].rev.txt));
});

escenario('Valor sin unidades', () => {
  const filas = enPantalla([{kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
                            {kind: 'out', qty: 5, valor: 1000, saldo: 0, valorInv: 4000}]);
  comprobar('aparece', 1, filas.length);
  comprobar('es el caso de valor sin stock', 'valorSinStock', filas[0].imposible);
  comprobar('propone dejar el valor en $0', true, /en \$0/.test(filas[0].rev.hacer));
});

escenario('Stock negativo', () => {
  const filas = enPantalla([{kind: 'in', qty: 2, valor: 2000, saldo: 2, valorInv: 2000},
                            {kind: 'out', qty: 5, valor: 2000, saldo: -3, valorInv: 0}]);
  comprobar('aparece', 1, filas.length);
  comprobar('es el caso de stock negativo', 'stockNegativo', filas[0].imposible);
  comprobar('manda a arreglar primero la cantidad', true, /Primero la cantidad/.test(filas[0].rev.hacer));
});

escenario('Un artículo sano no aparece', () => {
  comprobar('ninguna fila', 0, enPantalla([
    {kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
    {kind: 'out', qty: 2, valor: 2000, saldo: 3, valorInv: 3000},
  ]).length);
});

escenario('Stock en cero y valor en cero es normal, no un problema', () => {
  // Un producto que se agotó limpiamente: no hay nada que arreglar
  comprobar('ninguna fila', 0, enPantalla([
    {kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
    {kind: 'out', qty: 5, valor: 5000, saldo: 0, valorInv: 0},
  ]).length);
});

escenario('Stock con valor $0 no cuenta acá: ya lo detecta "sin costo"', () => {
  // Se avisa en otra parte; duplicarlo haría revisar dos veces lo mismo
  comprobar('ninguna fila de valorización imposible', 0, enPantalla([
    {kind: 'in', qty: 5, valor: 0, saldo: 5, valorInv: 0},
  ]).length);
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
