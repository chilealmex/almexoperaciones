/* La hoja "Ajustes vs sugerido" del Excel del Resumen.

   Compara lo que el sistema proponía con lo que se ajustó de verdad. Para
   poder revisar una diferencia hace falta saber de dónde salió: qué se contó,
   dónde está guardado, qué tenía Defontana en ese momento, y qué dice QMS.
   Sin eso hay que ir a buscar cada producto a otra hoja. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {compute, computeQms, parseStock, parseQms, parseArticulos, cmpExport, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const DIA = (a, m, d) => new Date(a, m - 1, d);
const INV = ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'];

/* Un producto contado el 08-10, con 10 unidades en Defontana desde agosto y
   una salida de ajuste de 5 el 09-10. */
function escenario({conQms = false, conInventario = false} = {}){
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optSame', Object.assign(porId.get('optSame') || {}, {value: 'before'}));
  state.stock = parseStock([['Código', 'Stock físico'], ['AAA', 5]]).map(
    s => Object.assign(s, {fecha: DIA(2026, 10, 8), name: 'PROD AAA'}));
  state.recount = new Map(); state.manual = new Set(); state.hechos = new Map();
  state.pmpEdit = new Map(); state.movCuando = new Map(); state.ajustes = null;
  state.articulos = conInventario ? parseArticulos([INV,
    ['AAA', 'PROD AAA', 'BODEGA CENTRAL', 5, 'UN', 1000, 5000]]) : null;
  state.qms = conQms ? parseQms([['Código Único', 'Stock', 'Unidad', 'Valor unitario'],
    ['AAA', 7, 'UN', 1100]]) : null;
  const base = {art: 'AAA', key: 'AAA', nameKey: 'PROD AAA', orig: '', dest: 'CENTRAL',
                estado: 'Aprobado', motivo: '', desc: 'PROD AAA', costo: 0};
  const movs = [
    {...base, tipo: 'PARTE DE ENTRADA', folio: '1', fecha: DIA(2026, 8, 1), kind: 'in',
     qty: 10, saldo: 10, valor: 10000, valorInv: 10000, i: 0, _aj: false},
    {...base, tipo: 'PARTE DE SALIDA', folio: '311', fecha: DIA(2026, 10, 9), kind: 'out',
     qty: 5, saldo: 5, valor: 5000, valorInv: 5000, i: 1, _aj: true},
  ];
  state.mov = movs;
  // Marcar el comprobante como ajuste es lo que en la pantalla hace el archivo
  // de ajustes o la casilla de "Comprobantes de ajuste ya hechos": sin eso, la
  // salida es un movimiento normal y no una regularización.
  state.ajSi = new Set(R.detectarAjustes(movs).map(g => g.id));
  state.ajNo = new Set();
  state.docGroupsMain = R.detectarAjustes(movs);
  state.rows = compute(movs).rows;
  computeQms();
  const r = state.rows.find(x => x.code === 'AAA');
  return cmpExport({r, sug: -5, aj: r.aj, dif: 0, vSug: -5000, vAj: r.ajVal || 0, estado: 'ok', costo: null});
}

console.log('\nLa hoja dice de dónde salió la diferencia');
{
  const x = escenario({conInventario: true});
  comprobar('lo contado', 5, x['Contado']);
  comprobar('cuándo se contó', true, String(x['Fecha conteo']).startsWith('08-10-2026'));
  comprobar('lo que Defontana tenía en ese momento', 10, x['Defontana al conteo']);
  comprobar('y dónde está guardado', 'BODEGA CENTRAL', x['Bodega']);
}

console.log('\nY trae el cruce con QMS, igual que el Excel de Productos');
{
  const x = escenario({conQms: true, conInventario: true});
  comprobar('el stock de QMS', 7, x['Stock QMS']);
  comprobar('su valor unitario', 1100, x['Valor unitario QMS']);
  comprobar('en qué sistemas está', 'QMS y Defontana', x['Está en']);
  comprobar('y cómo cruza', true, !!x['Cruce con QMS']);
}

console.log('\nSin esos archivos, las celdas quedan vacías y no se inventa nada');
{
  const x = escenario();
  comprobar('sin bodega', '', x['Bodega']);
  comprobar('sin stock de QMS', '', x['Stock QMS']);
  comprobar('sin cruce', '', x['Cruce con QMS']);
  // Lo que sí se sabe sin ningún archivo opcional: el conteo y el saldo.
  comprobar('pero el contado sigue', 5, x['Contado']);
  comprobar('y el saldo al conteo también', 10, x['Defontana al conteo']);
}

console.log('\nLo que ya traía la hoja no se perdió');
{
  const x = escenario({conInventario: true});
  comprobar('lo sugerido', -5, x['Sugerido']);
  comprobar('lo ajustado', -5, x['Ajustado']);
  comprobar('el comprobante', 'PARTE DE SALIDA #311', x['Comprobantes']);
  comprobar('y el estado', true, !!x['Estado']);
}

console.log(`\n${hechas - fallas}/${hechas} comprobaciones`);
if (fallas) process.exit(1);
