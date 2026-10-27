/* La línea de negocio de Defontana, y el informe que vino descuadrado.

   Desde el 27-10 el Informe de Inventario se saca con la columna "Línea de
   Negocio". Es la tercera: la del conteo quedó guardada al armar la toma y la
   de QMS la tiene ese sistema, y las tres pueden decir cosas distintas.

   Ese mismo informe —el primero sacado con la columna nueva— vino con la
   columna "Total" corrida: sus montos son de otras filas. Ahí multiplicar no
   sirve para decidir cuál columna es el valorizado, y con dos filas que
   cuadraban de casualidad se decidía el PMP de las 1.616. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {parseArticulos, parseStock, parseMov, compute, regExport, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  if (esperado === obtenido) { console.log(`  ✔ ${titulo}`); return; }
  fallas++;
  console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`);
}

const CAB = ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total', 'Línea de Negocio'];
const cabecera = (...titulos) => ['Informe de Inventario'] && [
  ['Informe de Inventario'], ['Empresa: Shaw Almex Chile SpA'],
  ['Fecha de generación: 27-10-2026, 10:42 a. m.'], [], titulos];

const inventario = (titulos, ...filas) => parseArticulos([...cabecera(...titulos), ...filas]);

const DIA = (a, m, d) => new Date(a, m - 1, d);
const CAB_MOV = ['Tipo Documento', 'Estado', 'Folio', 'Fecha', 'Bod. Origen', 'Bod. Destino', 'Motivo',
                 'Movimiento', 'Artículo', 'Descripción', 'Cant. Movimiento', 'U. Medida',
                 'Valor Movimiento', 'Saldo Inventario', 'Valor Inventario'];

// Un producto contado, con su movimiento, para poder mirar la fila del Excel.
function fila(articulos, {lineaConteo = '', lineaQms = ''} = {}){
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  state.articulos = articulos;
  state.stock = parseStock([['Código', 'Nombre', 'Stock físico', 'Fecha del conteo', 'Línea de negocio'],
                            ['A-1', 'TUERCAS', 13, '2026-10-20', lineaConteo]]);
  state.qms = lineaQms ? R.parseQms([['Código Único', 'Descripción', 'Stock', 'Unidad', 'Valor unitario', 'Linea Negocio'],
                                     ['A-1', 'TUERCAS', 13, 'UN', 100, lineaQms]]) : null;
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map();
  state.movCuando = new Map(); state.ajSi = new Set(); state.ajNo = new Set(); state.ajustes = null;
  const mov = parseMov([CAB_MOV,
    ['PARTE DE ENTRADA', 'Aprobado', '1', '2026-07-01', '', 'CENTRAL', '', 'Ingreso', 'A-1',
     'TUERCAS', 13, 'UN', 72751.25, 13, 72751.25]]);
  state.rows = compute(mov).rows;
  R.computeQms();
  return regExport(state.rows.find(r => r.code === 'A-1'));
}

console.log('\nLa línea de negocio del informe sale en el Excel');
{
  const art = inventario(CAB, ['A-1', 'TUERCAS', 'BODEGA CENTRAL', 13, 'UN', 5596.25, 72751.25, 'REPUESTOS']);
  comprobar('el lector la guarda', 'REPUESTOS', art[0].linea);
  const x = fila(art);
  comprobar('y llega a la columna del Excel', 'REPUESTOS', x['Línea Defontana (Informe de Inventario)']);
  comprobar('en la tabla también', 'REPUESTOS', R.REG_COLS.find(c => c[0] === 'lineainv')[3](state.rows[0]));
}

console.log('\nLas tres líneas conviven, cada una con la suya');
{
  const art = inventario(CAB, ['A-1', 'TUERCAS', 'BODEGA CENTRAL', 13, 'UN', 5596.25, 72751.25, 'REPUESTOS']);
  const x = fila(art, {lineaConteo: 'INSUMOS PRODUCCION', lineaQms: 'PRENSAS'});
  comprobar('la del conteo', 'INSUMOS PRODUCCION', x['Línea']);
  comprobar('la de QMS', 'PRENSAS', x['Línea QMS']);
  comprobar('y la de Defontana', 'REPUESTOS', x['Línea Defontana (Informe de Inventario)']);
}

console.log('\nUn producto en dos bodegas trae la línea una sola vez');
{
  // El informe lista una fila por bodega y la línea puede venir en una sola:
  // mirando nada más la primera, el producto queda sin línea.
  const art = inventario(CAB,
    ['A-1', 'TUERCAS', 'BODEGA CENTRAL', 8, 'UN', 5596.25, 44770, ''],
    ['A-1', 'TUERCAS', 'BODEGA INSUMOS', 5, 'UN', 5596.25, 27981.25, 'REPUESTOS']);
  const x = fila(art);

  comprobar('la línea sale igual', 'REPUESTOS', x['Línea Defontana (Informe de Inventario)']);
}

console.log('\nSin esa columna no se inventa ninguna');
{
  // Los informes de antes del 27-10 no la traen, y siguen leyéndose igual.
  const viejo = ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'];
  const art = inventario(viejo, ['A-1', 'TUERCAS', 'BODEGA CENTRAL', 13, 'UN', 5596.25, 72751.25]);
  const x = fila(art, {lineaConteo: 'INSUMOS PRODUCCION'});
  comprobar('queda vacía', '', x['Línea Defontana (Informe de Inventario)']);
  comprobar('y la del conteo sigue', 'INSUMOS PRODUCCION', x['Línea']);
  comprobar('el valorizado se lee como siempre', 5596.25, art[0].costo);
}

/* ---- El informe con la columna de valor corrida ---- */

// Como vino el del 27-10: la columna titulada "Valor unidad" trae el TOTAL de
// la fila, y la titulada "Total" trae montos de otras filas. Las que no tienen
// saldo llevan 0 en la primera y monto en la segunda, que es lo que delata
// cuál está alineada.
const DESCUADRADO = [
  ['A-1', 'TUERCAS', 'BODEGA CENTRAL', 13, 'UN', 72751.25, 5000, 'REPUESTOS'],
  ['A-2', 'SCREWS', 'BODEGA CENTRAL', 50, 'UN', 5000, 2691.46, 'REPUESTOS'],
  ['A-3', 'TORNILLOS', 'BODEGA CENTRAL', 20, 'UN', 8540, 10111.32, 'REPUESTOS'],
  ['A-4', 'PERNOS', 'BODEGA CENTRAL', 32, 'UN', 2691.46, 35109.5, 'TOOLS'],
  ['B-1', 'SIN STOCK UNO', 'SIN STOCK-SIN BODEGA', 0, 'UN', 0, 15482.5, 'TOOLS'],
  ['B-2', 'SIN STOCK DOS', 'SIN STOCK-SIN BODEGA', 0, 'UN', 0, 66770, 'TOOLS'],
];

console.log('\nCon la columna del valor corrida, el valorizado sale de la que cuadra con los saldos');
{
  const art = inventario(CAB, ...DESCUADRADO);
  const de = c => art.find(a => a.art === c);
  comprobar('se avisa que vino descuadrado', true, art.columnasDescuadradas);
  comprobar('el valorizado es el de la fila', 72751.25, de('A-1').valor);
  comprobar('y el PMP sale de dividirlo por el saldo', 5596.25, de('A-1').costo);
  comprobar('otro producto igual', 100, de('A-2').costo);
  // Lo de la otra columna son montos de otras filas: no es el costo de nadie.
  comprobar('el de la fila sin saldo no toma el monto ajeno', 0, de('B-1').valor);
  comprobar('ni un costo inventado', 0, de('B-1').costo);
  comprobar('la línea se lee igual', 'TOOLS', de('B-1').linea);
}

console.log('\nUn informe sano no se toca');
{
  const art = inventario(CAB,
    ['A-1', 'TUERCAS', 'BODEGA CENTRAL', 13, 'UN', 5596.25, 72751.25, 'REPUESTOS'],
    ['A-2', 'SCREWS', 'BODEGA CENTRAL', 50, 'UN', 100, 5000, 'REPUESTOS'],
    ['B-1', 'SIN STOCK', 'SIN STOCK-SIN BODEGA', 0, 'UN', 0, 0, 'TOOLS']);

  comprobar('no se avisa nada', undefined, art.columnasDescuadradas || undefined);
  comprobar('el valorizado es el que dice', 72751.25, art[0].valor);
  comprobar('y el PMP también', 5596.25, art[0].costo);
}

console.log('\nUn informe de puros productos con una unidad no se declara descuadrado');
{
  // Con saldo 1 el valor unitario y el total son el mismo número, así que la
  // fila cuadra leída de las dos maneras y no dice nada. Si contaran, un
  // informe así podría declararse descuadrado y cambiar columnas sin motivo.
  const art = inventario(CAB,
    ['A-1', 'UNO', 'BODEGA CENTRAL', 1, 'UN', 9500, 9500, 'REPUESTOS'],
    ['A-2', 'OTRO', 'BODEGA CENTRAL', 1, 'UN', 300, 300, 'TOOLS']);

  comprobar('no se avisa nada', undefined, art.columnasDescuadradas || undefined);
  comprobar('y el costo es el que dice', 9500, art[0].costo);
}

console.log('\nY el informe con los títulos cambiados de lugar sigue arreglándose');
{
  // El del 21-10: "Valorización | Valor Unidad", con los datos al revés de lo
  // que dicen los títulos. Ahí las dos columnas SÍ multiplican, leídas al
  // revés, y eso es otra cosa que venir descuadrado.
  const titulos = ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valorización', 'Valor Unidad'];
  const art = inventario(titulos,
    ['A-1', 'TUERCAS', 'BODEGA CENTRAL', 13, 'UN', 5596.25, 72751.25],
    ['A-2', 'SCREWS', 'BODEGA CENTRAL', 50, 'UN', 100, 5000]);

  comprobar('se arregla por los datos', 5596.25, art[0].costo);
  comprobar('y se dice que venían cambiadas', true, art.columnasCambiadas);
  comprobar('no es el caso de descuadrado', undefined, art.columnasDescuadradas || undefined);
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
