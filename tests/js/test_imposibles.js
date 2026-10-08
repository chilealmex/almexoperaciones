/* Valorizaciones que no pueden existir.

   Tres estados en que un artículo no puede quedar y que no se notan mirando
   cantidades: valor negativo, valor sin unidades, y stock negativo. No son "un
   costo distinto del esperado": son cuentas que no cierran, y casi siempre las
   deja un ajuste mal hecho. Importa verlas justo cuando se está ajustando. */
const {porId} = require('./entorno.js');
const {compute, valorizacionImposible, parseArticulos, state} = require('../../app/static/js/regularizacion.js');

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

// El valor sin unidades y el valor negativo se marcan sólo cuando lo dice el
// stock valorizado: el producto listado, con su saldo y su valorizado de
// verdad. Del arrastre del informe de documentos no se puede concluir —es una
// reconstrucción— y proponer un ajuste con eso saca valor que Defontana no
// tiene. Por eso los escenarios traen la foto.
const INV = (saldo, total) => parseArticulos([
  ['Informe de Inventario'], ['Empresa: X'], ['Fecha de generación: 07-10-2026, 10:37 a. m.'], [],
  ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor Unidad', 'Total'],
  ['ART-1', 'ARTICULO', 'BODEGA CENTRAL', saldo, 'UN', 0, total],
]);

function enPantalla(filas, foto) {
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  state.hechos = new Map(); state.pmpEdit = new Map();
  state.articulos = foto || null;
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  return compute(docs(filas)).zero.filter(z => z.imposible);
}

escenario('Valor de inventario negativo', () => {
  const movs = [{kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
                {kind: 'out', qty: 2, valor: 9000, saldo: 3, valorInv: -4000}];
  state.articulos = INV(3, -4000);
  comprobar('se detecta', 'valorNegativo', (valorizacionImposible(docs(movs)) || {}).cual);
  const filas = enPantalla(movs, INV(3, -4000));
  comprobar('aparece en la pantalla', 1, filas.length);
  comprobar('marcada para revisar', true, filas[0].rev.need);
  comprobar('dice que un valor negativo no existe', true, /no existe/.test(filas[0].rev.txt));
});

escenario('Valor sin unidades', () => {
  const filas = enPantalla([{kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
                            {kind: 'out', qty: 5, valor: 1000, saldo: 0, valorInv: 4000}],
                           INV(0, 4000));
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

escenario('Un valor negativo del arrastre tampoco se propone solo', () => {
  // Mismo criterio que el valor sin unidades: si el valorizado dice que el
  // producto está en cero, el negativo que arrastra el informe de documentos
  // es de la reconstrucción y no hay nada que subir en Defontana.
  const movs = [{kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
                {kind: 'out', qty: 2, valor: 9000, saldo: 3, valorInv: -4000}];
  comprobar('el valorizado lo trae en cero: nada que hacer', 0, enPantalla(movs, INV(3, 0)).length);
  comprobar('y si el valorizado lo trae negativo, sí', 1, enPantalla(movs, INV(3, -4000)).length);
  // Sin el Informe de Inventario cargado no hay con qué afirmarlo: lo único
  // que queda es el arrastre, que es de donde salía la propuesta equivocada.
  comprobar('sin informe de inventario, no se concluye', 0, enPantalla(movs, null).length);
});

escenario('Sin que lo diga el valorizado, no se propone sacar valor', () => {
  // El caso de ella: 41015-042 quedó con 0 unidades y el arrastre del informe
  // de documentos le dejaba $1.193.505. El Informe de Inventario lo trae en
  // cero, así que ese valor no está en Defontana y el ajuste de costo que se
  // proponía habría sacado plata que no existe.
  const movs = [{kind: 'in', qty: 5, valor: 5000, saldo: 5, valorInv: 5000},
                {kind: 'out', qty: 5, valor: 1000, saldo: 0, valorInv: 4000}];
  comprobar('el valorizado lo trae en cero: nada que hacer', 0, enPantalla(movs, INV(0, 0)).length);
  comprobar('sin valorizado cargado, tampoco se concluye', 0, enPantalla(movs, null).length);
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
