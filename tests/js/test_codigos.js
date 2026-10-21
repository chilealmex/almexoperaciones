/* Los códigos creados en Defontana que no tienen stock.

   El Informe de Inventario puede traerlos: la fila viene con el código y la
   descripción, la bodega en "SIN STOCK-SIN BODEGA" —no está en ninguna— y
   Saldo, Valor unidad y Total vacíos. Son los que hacen falta para cruzar con
   QMS qué códigos existen en cada sistema, y tienen que entrar con stock 0,
   que es lo que efectivamente tienen.

   También distingue los dos informes que Defontana da: el que trae todo el
   maestro y el que viene filtrado a lo que tiene stock. En el primero, que un
   código no esté significa que no existe; en el segundo no significa nada. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {parseArticulos, parseQms, parseStock, compute, computeQms, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const CAB = ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'];
const inv = (...filas) => parseArticulos([
  ['Informe de Inventario'], ['Empresa: Shaw Almex Chile SpA'],
  ['Fecha de generación: 20-10-2026, 09:20 a. m.'], [], CAB, ...filas]);
// Una fila como la que manda Defontana para un código sin stock.
const sinStock = (code, name = 'ARTICULO') => [code, name, 'SIN STOCK-SIN BODEGA', '', '', '', ''];
const conStock = (code, saldo, unidad = 100) =>
  [code, 'ARTICULO', 'BODEGA CENTRAL', saldo, 'UN', unidad, saldo * unidad];
const de = (arts, code) => arts.find(a => a.art === code);

console.log('\nUn código sin stock entra igual, con saldo 0');
{
  const a = inv(conStock('INS-001', 12), sinStock('INS-002'));
  comprobar('entran los dos', 2, a.length);
  comprobar('el que no tiene stock está', true, !!de(a, 'INS-002'));
  comprobar('entra con stock 0', 0, de(a, 'INS-002').stock);
  comprobar('y sin valor', 0, de(a, 'INS-002').valor);
  comprobar('conserva el nombre', 'ARTICULO', de(a, 'INS-002').name);
  comprobar('el que sí tiene stock no cambia', 12, de(a, 'INS-001').stock);
}

console.log('\n"SIN STOCK-SIN BODEGA" no es una bodega');
{
  const a = inv(sinStock('INS-002'));
  comprobar('queda sin bodega', '', de(a, 'INS-002').bodega);
}

console.log('\nLa marca puesta en una fila que sí tiene stock no se cree');
{
  // En uno de sus intentos la marca quedó en todas las filas, incluidas las
  // de 13 y 50 unidades. Ahí no dice que no haya stock: el saldo manda.
  const a = parseArticulos([CAB, ['INS-001', 'ARTICULO', 'SIN STOCK-SIN BODEGA', 13, 'UN', 100, 1300]]);
  comprobar('mantiene el saldo', 13, de(a, 'INS-001').stock);
  comprobar('no cuenta como código sin stock', 0, a.sinStock);
  comprobar('y el informe no se da por completo', false, a.completo);
  comprobar('la bodega se respeta', 'SIN STOCK-SIN BODEGA', de(a, 'INS-001').bodega);
}

console.log('\nCuántos códigos sin stock declara el informe');
{
  const a = inv(conStock('INS-001', 12), sinStock('INS-002'), sinStock('INS-003'));
  comprobar('los cuenta', 2, a.sinStock);
  comprobar('trae todo el maestro', true, a.completo);
}
{
  // La otra manera de decirlo: el saldo escrito en 0.
  const a = inv(conStock('INS-001', 12), conStock('INS-002', 0));
  comprobar('un saldo 0 escrito también cuenta', 1, a.sinStock);
  comprobar('y el informe es el completo', true, a.completo);
}
{
  const a = inv(conStock('INS-001', 12), conStock('INS-002', 7));
  comprobar('sin ninguno, no declara nada', 0, a.sinStock);
  comprobar('es el informe filtrado a lo que tiene stock', false, a.completo);
}

console.log('\nUna celda de saldo vacía no es lo mismo que un 0 escrito');
{
  // En su informe del 20-10 12:03 hay 5 filas así y ese informe trae sólo los
  // artículos con stock: tomarlas como prueba de que están todos los códigos
  // es apoyar la conclusión en 5 celdas en blanco.
  const a = parseArticulos([CAB, ['INS-001', 'ARTICULO', 'BODEGA CENTRAL', 12, 'UN', 100, 1200],
    ['15060', 'NIPLE TUERCA', 'BODEGA CENTRAL', '', 'UN', 0, '']]);
  comprobar('la fila entra igual', 2, a.length);
  comprobar('con stock 0', 0, de(a, '15060').stock);
  comprobar('pero no cuenta como código declarado sin stock', 0, a.sinStock);
  comprobar('y el informe no se da por completo', false, a.completo);
}

console.log('\nEl pie del informe no es un artículo');
{
  const a = parseArticulos([CAB, ['INS-001', 'ARTICULO', 'BODEGA CENTRAL', 12, 'UN', 100, 1200],
    ['Total general', '', '', '', '', '', '']]);
  comprobar('sólo entra el artículo', 1, a.length);
  comprobar('y es el que corresponde', 'INS-001', a[0].art);
}

console.log('\nUn código sin stock se cruza con QMS igual que cualquier otro');
{
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optSame', Object.assign(porId.get('optSame') || {}, {value: 'before'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  state.stock = []; state.mov = []; state.ajustes = null; state.mov2 = null;
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map(); state.movCuando = new Map();
  state.articulos = inv(sinStock('INS-002'));
  state.qms = parseQms([['Código Único', 'Stock', 'Unidad', 'Valor unitario', 'Descripción'],
    ['INS-002', 5, 'UN', 1000, 'ARTICULO'], ['SOLO-QMS', 3, 'UN', 500, 'OTRO']]);
  state.rows = compute([]).rows;
  computeQms();
  const fila = state.qmsRows.find(f => (f.q && f.q.code === 'INS-002') || (f.d && f.d.code === 'INS-002'));
  comprobar('el código sin stock aparece en el cruce', true, !!fila);
  comprobar('con su lado de Defontana', true, !!(fila && fila.d));
  comprobar('en 0', 0, fila && fila.d ? fila.d.stock : null);
  comprobar('y con su lado de QMS', 5, fila && fila.q ? fila.q.stock : null);
  comprobar('la diferencia es lo que QMS tiene de más', 5, fila ? fila.difStock : null);
  comprobar('el que sólo está en QMS sigue saliendo así', 'falta',
    (state.qmsRows.find(f => f.q && f.q.code === 'SOLO-QMS') || {}).st);
}

console.log(`\n${hechas - fallas}/${hechas} comprobaciones`);
if (fallas) process.exit(1);
