/* La unidad de medida, a la vista en la hoja "Productos".

   La pantalla dice cuánto ajustar, pero no en qué. Con el mismo producto
   llevado en unidades en un lado y en metros en otro —que es el caso que ya
   detecta la causa "Posible otra unidad de medida"— un "+4" no se puede
   escribir en Defontana sin saber si son cuatro piezas o cuatro metros.

   La unidad que manda es la de Defontana: es el sistema donde se hace el
   ajuste, así que es la unidad en la que hay que escribirlo. */
const {porId} = require('./entorno.js');
const {compute, parseStock, REG_COLS, regRow, state} = require('../../app/static/js/regularizacion.js');

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

// Un movimiento del Informe de Documentos, con su unidad.
function doc(art, um, dia, qty, saldo) {
  return {art, key: art.replace(/[^A-Z0-9]/g, ''), nameKey: 'NOMBRE' + art, tipo: 'FACTURA',
          folio: '100', fecha: DIA(2026, 8, dia), kind: 'in', qty, saldo, valor: qty * 1000,
          valorInv: saldo * 1000, orig: 'CENTRAL', dest: 'CENTRAL', estado: 'Aprobado',
          motivo: '', desc: 'PRODUCTO ' + art, um};
}

// El conteo de bodega, con la unidad en que se contó.
function conteo(code, stock, um, dia) {
  return parseStock([
    ['Código', 'Nombre', 'Stock físico', 'Fecha', 'Unidad', 'Línea de negocio'],
    [code, 'PRODUCTO ' + code, stock, `0${dia}-08-2026`, um, 'PRENSAS'],
  ]);
}

function pantalla(movs, stock) {
  state.stock = stock || []; state.recount = new Map(); state.manual = new Set();
  state.hechos = new Map(); state.pmpEdit = new Map(); state.ajustes = []; state.articulos = null;
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  state.mov = movs;
  const out = compute(movs);
  state.rows = out.rows; state.zero = out.zero;
  return out.rows;
}

escenario('La unidad que manda es la de Defontana', () => {
  // Es el sistema donde se escribe el ajuste: de nada sirve saber que el
  // conteo estaba en cajas si el ajuste hay que escribirlo en unidades.
  const rows = pantalla([doc('AAA', 'UN', 1, 10, 10)], conteo('AAA', 10, 'UN', 2));
  comprobar('la fila la lleva', 'UN', rows[0].um);
});

escenario('Sin documentos queda la del conteo', () => {
  // Un producto contado que no aparece en el informe: la única unidad que
  // existe es la que escribió bodega, y dejarla fuera sería esconder el único
  // dato que hay.
  const rows = pantalla([], conteo('BBB', 5, 'MT', 2));
  comprobar('la fila la lleva', 'MT', rows[0].um);
});

escenario('Contado en otra unidad: la columna dice la de Defontana', () => {
  // Defontana lo lleva en metros y bodega contó en unidades. La columna no
  // puede decir "UN" —el ajuste se escribe en metros— pero tampoco puede
  // callar que lo contado está en otra, o el número de al lado engaña.
  const rows = pantalla([doc('CCC', 'MT', 1, 100, 100)], conteo('CCC', 4, 'UN', 2));
  const r = rows[0];
  comprobar('la columna lleva la de Defontana', 'MT', r.um);
  comprobar('y queda registrado en qué se contó', 'UN', r.umInfo && r.umInfo.de);
  const fila = regRow(r);
  comprobar('la celda muestra la de Defontana', true, />MT</.test(fila));
  comprobar('y dice en qué se contó', true, /contado en UN/.test(fila));
});

escenario('La columna va donde se lee junto al producto', () => {
  // Al final de la tabla hay que desplazarla a lo ancho para leerla, y es un
  // dato que se mira junto a la cantidad, no después de todo.
  const claves = REG_COLS.map(c => c[0]);
  comprobar('existe la columna', true, claves.includes('um'));
  comprobar('se llama Unidad', 'Unidad', (REG_COLS.find(c => c[0] === 'um') || [])[1]);
  comprobar('va después de la línea', true, claves.indexOf('um') > claves.indexOf('linea'));
  comprobar('y antes de lo contado', true, claves.indexOf('um') < claves.indexOf('contado'));
});

escenario('Sin unidad en ninguna parte, queda el guion', () => {
  // Una celda en blanco se lee como un error de carga.
  const rows = pantalla([doc('DDD', '', 1, 10, 10)], conteo('DDD', 10, '', 2));
  comprobar('la fila no inventa una', '', rows[0].um);
  // Se mira la celda de la unidad y no la fila entera: el guion sale en varias
  // columnas, así que buscarlo suelto pasaría con la celda vacía.
  const fila = regRow(rows[0]);
  const celda = fila.slice(fila.indexOf('class="linea um"'));
  comprobar('la celda queda con el guion', true, /^[^<]*<span class="mut">—<\/span><\/td>/.test(
    celda.slice(celda.indexOf('>') + 1)));
});

escenario('La columna se puede ordenar y exportar como las demás', () => {
  // El tercer elemento de cada columna es cómo se lee el valor: sin eso la
  // columna se dibuja pero no ordena ni sale en el Excel.
  const col = REG_COLS.find(c => c[0] === 'um');
  const rows = pantalla([doc('EEE', 'KG', 1, 10, 10)], conteo('EEE', 10, 'KG', 2));
  comprobar('sabe leer su valor', 'KG', col[3](rows[0]));
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
