/* De dónde sale el PMP con que se valoriza el ajuste.

   El Informe de Documentos son movimientos: el PMP se saca de la última fila
   que traiga saldo y valor, y esa fila puede ser de hace meses. El Informe de
   Inventario es el costo que Defontana tiene hoy, y es ése el que vale.

   Con sus archivos, 48 de los 296 productos con ajuste pendiente se estaban
   valorizando con un costo viejo —de marzo o de julio—: $2.003.507 de
   diferencia en el ajuste valorizado.

   Un código sin stock no tiene costo que sacar de ahí, y ahí siguen mandando
   los documentos. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {compute, parseArticulos, parseStock, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const DIA = (a, m, d) => new Date(a, m - 1, d);
const claveDe = code => parseStock([['Código', 'Stock físico'], [code, 0]])[0].key;

// El Informe de Inventario, con la columna del valorizado: el PMP es Total
// dividido por Saldo, que es lo que Defontana tiene de verdad.
const INV = ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'];
const inventario = (...filas) => parseArticulos([
  ['Informe de Inventario'], ['Empresa: Shaw Almex Chile SpA'],
  ['Fecha de generación: 20-10-2026, 09:20 a. m.'], [], INV, ...filas]);
const fila = (code, saldo, total) => [code, 'PROD ' + code, saldo > 0 ? 'BODEGA CENTRAL' : 'SIN STOCK-SIN BODEGA',
                                      saldo, 'UN', 0, total];
// El Informe de Artículos, el otro que da Defontana: no trae el valorizado,
// sólo "Costo Vigente", que llega en 0 aunque el producto esté valorizado.
const sinValorizado = (code, stock, costo) => parseArticulos([
  ['Artículo', 'Descripción', 'Stock Disponible', 'Costo Vigente'], [code, 'PROD ' + code, stock, costo]]);

/* Un producto contado, con un movimiento que deja PMP 5.000 en los documentos
   (saldo 10, Valor Inventario 50.000). */
function caso({articulos = null, contado = 8, aMano = null, conDocs = true} = {}){
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optSame', Object.assign(porId.get('optSame') || {}, {value: 'before'}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  const key = claveDe('AAA');
  state.stock = [{code: 'AAA', key, name: 'PROD AAA', stock: contado, fecha: DIA(2026, 10, 8),
                  por: '', estado: '', um: '', linea: ''}];
  state.recount = new Map(); state.hechos = new Map(); state.movCuando = new Map();
  state.pmpEdit = aMano == null ? new Map() : new Map([[key, aMano]]);
  state.ajustes = null; state.mov2 = null; state.qms = null;
  state.articulos = articulos;
  const docs = conDocs ? [{art: 'AAA', key, nameKey: '', tipo: 'PARTE DE ENTRADA', folio: '100',
    fecha: DIA(2026, 3, 2), kind: 'in', qty: 10, saldo: 10, valor: 50000, valorInv: 50000, costo: 0,
    orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', um: '', desc: 'PROD AAA', i: 0, _aj: false}] : [];
  state.mov = docs;
  return compute(docs).rows.find(r => r.code === 'AAA');
}

console.log('\nCon stock en el Informe de Inventario, el PMP es el del archivo');
{
  const r = caso({articulos: inventario(fila('AAA', 10, 70000))});
  comprobar('el PMP es Total/Saldo, no el del documento', 7000, r.pmp);
  comprobar('y lo dice, con la fecha del archivo',
    'PMP del Informe de Inventario del 20-10-2026, 09:20 a. m.', r.pmpSrc);
  comprobar('hay que disminuir 2', 'down', r.st);
  comprobar('y el ajuste se valoriza con ese costo', -14000, Math.round(r.valor));
}

console.log('\nSin el archivo, el PMP sigue saliendo de los documentos');
{
  const r = caso();
  comprobar('el PMP del documento', 5000, r.pmp);
  comprobar('y el origen es el de antes', 'PMP Defontana al 02-03-2026', r.pmpSrc);
  comprobar('el ajuste se valoriza con ése', -10000, Math.round(r.valor));
}

console.log('\nUn producto que no está en el archivo no cambia');
{
  const r = caso({articulos: inventario(fila('OTRO', 5, 25000))});
  comprobar('sigue el PMP del documento', 5000, r.pmp);
}

console.log('\nSin stock en el archivo no hay costo que sacar de ahí');
{
  // Es la regla de ella: el que tiene stock tiene costo, el que no, no.
  const r = caso({articulos: inventario(fila('AAA', 0, 0))});
  comprobar('mandan los documentos', 5000, r.pmp);
  comprobar('y el origen lo dice', 'PMP Defontana al 02-03-2026', r.pmpSrc);
}

console.log('\nSin stock, aunque el archivo traiga un valor unitario, no se usa');
{
  // Saldo 0 y "Valor unidad" 1.234: el producto no tiene unidades, así que ese
  // número no es el costo de nada que Defontana tenga hoy.
  const r = caso({articulos: inventario(['AAA', 'PROD AAA', 'SIN STOCK-SIN BODEGA', 0, 'UN', 1234, 0])});
  comprobar('mandan los documentos', 5000, r.pmp);
}

console.log('\nCon stock pero sin valorizar, tampoco');
{
  // Saldo 10 y Total 0: Defontana tiene unidades sin valor. Valorizar el
  // ajuste en $0 lo haría desaparecer; el costo hay que sacarlo de otra parte.
  const r = caso({articulos: inventario(fila('AAA', 10, 0))});
  comprobar('mandan los documentos', 5000, r.pmp);
  comprobar('y el ajuste vale lo que valía', -10000, Math.round(r.valor));
}

console.log('\nSin la columna del valorizado no se usa "Costo Vigente"');
{
  // Esa columna llega en 0 aunque el producto esté valorizado —en su informe,
  // 533 de 1.108 productos con stock—, así que no sirve como PMP.
  const r = caso({articulos: sinValorizado('AAA', 10, 9999)});
  comprobar('mandan los documentos', 5000, r.pmp);
}

console.log('\nEl costo escrito a mano le gana a los dos');
{
  const r = caso({articulos: inventario(fila('AAA', 10, 70000)), aMano: 1234});
  comprobar('el PMP es el escrito', 1234, r.pmp);
  comprobar('y el origen lo dice', 'Ingresado a mano', r.pmpSrc);
}

console.log('\nUn producto con stock en el archivo y sin un solo movimiento');
{
  const r = caso({articulos: inventario(fila('AAA', 10, 70000)), conDocs: false, contado: 12});
  comprobar('toma el PMP del archivo igual', 7000, r.pmp);
  comprobar('y lo dice', 'PMP del Informe de Inventario del 20-10-2026, 09:20 a. m.', r.pmpSrc);
}

console.log(`\n${hechas - fallas}/${hechas} comprobaciones`);
if (fallas) process.exit(1);
