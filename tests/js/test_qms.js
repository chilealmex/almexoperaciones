/* El cruce con QMS: los dos sistemas lado a lado.

   QMS es el otro sistema. Acá no entra en ningún cálculo —lo que se ajusta en
   Defontana se sigue decidiendo con el conteo físico—: es para mirar código,
   unidad, cantidad y valor unitario de los dos lados y ver dónde no coinciden
   o qué existe en uno y no en el otro. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {parseQms, computeQms, cruceQms, qmsRow, regExport, compute, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const DIA = (a, m, d) => new Date(a, m - 1, d);

/* Arma los dos lados: el de Defontana como lo deja el cruce normal (conteo +
   documentos + stock valorizado) y el de QMS como lo deja su archivo. */
function cruce({qms = [], docs = [], conteo = [], articulos = null}){
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optSame', Object.assign(porId.get('optSame') || {}, {value: 'before'}));
  state.stock = conteo.map(c => ({code: c.code, key: R.parseStock([['Código', 'Stock físico'], [c.code, 0]])[0].key,
                                  name: c.name || '', stock: c.stock ?? null, fecha: c.fecha || DIA(2026, 9, 1),
                                  por: '', estado: '', um: c.um || '', linea: c.linea || '',
                                  ubicacion: c.ubicacion || ''}));
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map(); state.movCuando = new Map();
  state.articulos = articulos;
  const mov = docs.map((d, i) => ({art: d.art, key: null, nameKey: '', tipo: 'PARTE DE ENTRADA', folio: String(100 + i),
    fecha: d.fecha || DIA(2026, 1, 10), kind: d.kind || 'in', qty: d.qty, saldo: d.saldo != null ? d.saldo : d.qty,
    valor: d.valor || 0, valorInv: d.valorInv != null ? d.valorInv : (d.valor || 0), costo: 0,
    orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', um: d.um || '', desc: d.desc || '', _aj: false}));
  for (const m of mov){ m.key = R.parseStock([['Código', 'Stock físico'], [m.art, 0]])[0].key; }
  state.mov = mov;
  state.qms = qms.length ? parseQms([['Código Único', 'Stock', 'Unidad', 'Valor unitario', 'Descripción', 'Linea Negocio', 'Categoria', 'ubicacion_bodega'],
    ...qms.map(q => [q.code, q.stock, q.um || '', q.unit == null ? '' : q.unit, q.name || '', q.linea || '', q.cat || '', q.ubicacion || ''])]) : null;
  state.rows = compute(mov).rows;
  computeQms();
  return state.qmsRows;
}

const de = (filas, codigo) => filas.find(r => r.code === codigo || (r.q && r.q.code === codigo) || (r.d && r.d.code === codigo));


console.log('\nSin el archivo de QMS no hay cruce, y no se rompe nada');
{
  const filas = cruce({docs: [{art: 'INS-001', qty: 10}]});
  comprobar('no hay filas', 0, filas.length);
}

console.log('\nUn producto que está en los dos y cuadra');
{
  const filas = cruce({
    qms: [{code: 'INS-001', stock: 10, um: 'UN', unit: 1000}],
    docs: [{art: 'INS-001', qty: 10, valor: 10000, valorInv: 10000, saldo: 10, um: 'UN'}],
  });
  const r = de(filas, 'INS-001');
  comprobar('está en los dos', true, !!(r.q && r.d));
  comprobar('y se marca que coinciden', 'igual', r.st);
  comprobar('con el stock de cada lado', '10 / 10', `${r.q.stock} / ${r.d.stock}`);
}

console.log('\nLo que ella quiere ver: está en uno y no en el otro');
{
  const filas = cruce({
    qms: [{code: 'SOLO-QMS', stock: 5, um: 'UN', unit: 100}],
    docs: [{art: 'SOLO-DEF', qty: 7, valor: 700, saldo: 7, um: 'UN'}],
  });
  comprobar('el de QMS sale como que Defontana no lo tiene', 'falta', de(filas, 'SOLO-QMS').st);
  comprobar('el de Defontana sale como que QMS no lo tiene', 'sobra', de(filas, 'SOLO-DEF').st);
  comprobar('y son dos filas, no cuatro', 2, filas.length);
}

console.log('\nContado pero sin nada en Defontana: no es "está en Defontana"');
{
  // Un producto del conteo físico que Defontana no tiene no aparece en ningún
  // documento ni en su stock. Darlo por existente escondería justo el caso.
  const filas = cruce({
    qms: [{code: 'INS-001', stock: 5, um: 'UN', unit: 100}],
    conteo: [{code: 'INS-001', stock: 5}],
  });
  comprobar('sigue saliendo como que Defontana no lo tiene', 'falta', de(filas, 'INS-001').st);
}

console.log('\nUnidades de medida');
{
  const filas = cruce({
    qms: [{code: 'A-1', stock: 9, um: 'RL', unit: 100}, {code: 'A-2', stock: 9, um: 'UNIDAD', unit: 100}],
    docs: [{art: 'A-1', qty: 9, valor: 900, saldo: 9, um: 'UN'}, {art: 'A-2', qty: 9, valor: 900, saldo: 9, um: 'UN'}],
  });
  comprobar('RL contra UN se avisa', 'unidad', de(filas, 'A-1').st);
  comprobar('UNIDAD contra UN es la misma unidad', 'igual', de(filas, 'A-2').st);
}

console.log('\nCantidades y valor unitario');
{
  const filas = cruce({
    qms: [{code: 'A-1', stock: 12, um: 'UN', unit: 100}, {code: 'A-2', stock: 9, um: 'UN', unit: 150}],
    docs: [{art: 'A-1', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'},
           {art: 'A-2', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
  });
  const dif = de(filas, 'A-1');
  comprobar('la cantidad distinta se marca', 'cantidad', dif.st);
  comprobar('y se dice cuánto', 3, dif.difStock);
  comprobar('el valor unitario distinto se marca', 'valor', de(filas, 'A-2').st);
  comprobar('y se dice cuánto', 50, de(filas, 'A-2').difUnit);
}

console.log('\nUnos pesos de redondeo no son una diferencia de valor');
{
  // Cada sistema calcula su valor unitario por su cuenta. Marcar $100,4 contra
  // $100 llenaría la pantalla de diferencias que no son tales.
  const filas = cruce({
    qms: [{code: 'A-1', stock: 9, um: 'UN', unit: 100.4}],
    docs: [{art: 'A-1', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
  });
  comprobar('$100,4 contra $100 pasa como igual', 'igual', de(filas, 'A-1').st);
}

console.log('\nEl mismo código en varias líneas de QMS se suma');
{
  const filas = cruce({
    qms: [{code: 'A-1', stock: 4, um: 'UN', unit: 100, linea: 'FUSION'},
          {code: 'A-1', stock: 5, um: 'UN', unit: 100, linea: 'PRENSAS'}],
    docs: [{art: 'A-1', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
  });
  comprobar('las dos líneas suman 9', 9, de(filas, 'A-1').q.stock);
  comprobar('y cuadra con Defontana', 'igual', de(filas, 'A-1').st);
}

console.log('\nLos códigos se cruzan como en el resto del módulo');
{
  // Guiones, ceros a la izquierda y mayúsculas no hacen dos productos.
  const filas = cruce({
    qms: [{code: '0ins-001', stock: 9, um: 'UN', unit: 100}],
    docs: [{art: 'INS-001', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
  });
  comprobar('es un solo producto', 1, filas.length);
  comprobar('y muestra los dos códigos tal como los escribe cada sistema',
            '0ins-001 / INS-001', `${filas[0].q.code} / ${filas[0].d.code}`);
}

console.log('\nEl stock valorizado de Defontana también entra al cruce');
{
  // Un producto que está en el Informe de Inventario pero no tiene documentos
  // en el informe cargado: igual lo tiene Defontana.
  // En dos bodegas: el stock del producto es la suma. Quedándose con una, el
  // cruce diría que a Defontana le faltan las de la otra.
  const articulos = R.parseArticulos([
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
    ['SOLO-INV', 'Sólo en el inventario', 'BODEGA CENTRAL', 3, 'UN', 250, 750],
    ['SOLO-INV', 'Sólo en el inventario', 'BODEGA INSUMOS', 1, 'UN', 250, 250]]);
  const filas = cruce({qms: [{code: 'OTRO', stock: 1, um: 'UN', unit: 1}], articulos,
                       docs: [{art: 'OTRO2', qty: 1, valor: 1, saldo: 1}]});
  const r = de(filas, 'SOLO-INV');
  comprobar('aparece en el cruce', true, !!r);
  comprobar('como que QMS no lo tiene', 'sobra', r.st);
  comprobar('con el stock de sus dos bodegas sumado', 4, r.d.stock);
  comprobar('y su valor unitario', 250, r.d.unit);
}

console.log('\nLa fila de la pantalla muestra las dos columnas de cada cosa');
{
  const filas = cruce({
    qms: [{code: 'A-1', stock: 12, um: 'RL', unit: 100, name: 'Producto de prueba'}],
    docs: [{art: 'A-1', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
  });
  const html = qmsRow(de(filas, 'A-1'));
  comprobar('el código de QMS', true, html.includes('A-1'));
  comprobar('las dos unidades', true, html.includes('>RL<') && html.includes('>UN<'));
  comprobar('las dos cantidades', true, html.includes('>12<') && html.includes('>9<'));
  comprobar('y el aviso de la unidad', true, html.includes('Unidad distinta'));
}

console.log('\nUn lado vacío se dice, no se inventa un cero');
{
  const filas = cruce({qms: [{code: 'SOLO-QMS', stock: 5, um: 'UN', unit: 100}]});
  const html = qmsRow(de(filas, 'SOLO-QMS'));
  comprobar('dice que no está', true, html.includes('no está'));
  comprobar('y no muestra un stock de Defontana', false, html.includes('>0<'));
}

console.log('\nDónde está cada producto: QMS, Defontana, los dos o ninguno');
{
  // Lo pedido: nada más que eso. "En ninguno" es el caso raro —está en la
  // lista del conteo y ningún sistema lo tiene— y por eso se separa.
  const articulos = R.parseArticulos([
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
    ['SOLO-DEF', 'Sólo en Defontana', 'BODEGA CENTRAL', 2, 'UN', 100, 200],
    ['EN-CERO', 'Sin stock', 'BODEGA CENTRAL', 0, 'UN', 0, 0]]);
  cruce({
    qms: [{code: 'EN-LOS-DOS', stock: 9, um: 'UN', unit: 100},
          {code: 'SOLO-QMS', stock: 3, um: 'UN', unit: 100}],
    docs: [{art: 'EN-LOS-DOS', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
    conteo: [{code: 'EN-LOS-DOS', stock: 9}, {code: 'SOLO-QMS', stock: 3},
             {code: 'SOLO-DEF', stock: 2}, {code: 'EN-NINGUNO', stock: 1}],
    articulos,
  });
  const donde = c => R.regExport(state.rows.find(r => r.code === c))['Está en'];
  comprobar('el que está en los dos', 'QMS y Defontana', donde('EN-LOS-DOS'));
  comprobar('el que sólo tiene QMS', 'Sólo QMS', donde('SOLO-QMS'));
  comprobar('el que sólo tiene Defontana', 'Sólo Defontana', donde('SOLO-DEF'));
  comprobar('y el raro, que no está en ninguno', 'En ninguno', donde('EN-NINGUNO'));
  comprobar('en la tabla se ve igual', true,
            R.regRow(state.rows.find(r => r.code === 'EN-NINGUNO')).includes('En ninguno'));
}

console.log('\nSin archivo de QMS no se afirma dónde está');
{
  cruce({docs: [{art: 'A-1', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
         conteo: [{code: 'A-1', stock: 9}]});
  comprobar('la columna queda vacía', '', R.regExport(state.rows.find(r => r.code === 'A-1'))['Está en']);
  // Y en la tabla tampoco se inventa: sin el archivo no hay nada que decir
  // sobre QMS, y decir "Sólo Defontana" sería afirmarlo sin haberlo mirado.
  const fila = R.regRow(state.rows.find(r => r.code === 'A-1'));
  comprobar('y en la tabla no aparece ninguna etiqueta', false,
            ['QMS y Defontana', 'Sólo QMS', 'Sólo Defontana', 'En ninguno'].some(x => fila.includes(x)));
}

console.log('\nEl Excel de Productos también trae el cruce con QMS');
{
  // Es donde ella mira el detalle producto por producto. Las dos unidades van
  // de donde están actualizadas: la de QMS de su planilla y la de Defontana
  // del Informe de Inventario, no la del documento más nuevo —que puede traer
  // la unidad que el artículo tenía antes de que se la cambiaran—.
  const articulos = R.parseArticulos([
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
    ['A-1', 'Producto', 'BODEGA CENTRAL', 9, 'KG', 100, 900]]);
  const filas = cruce({
    qms: [{code: 'A-1', stock: 12, um: 'RL', unit: 150}],
    docs: [{art: 'A-1', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
    articulos,
  });
  const fila = regExport(state.rows.find(r => r.code === 'A-1'));

  comprobar('y la pestaña del cruce usa la misma unidad actualizada', 'KG', de(filas, 'A-1').d.um);
  comprobar('el código de QMS', 'A-1', fila['Código QMS']);
  comprobar('la unidad de QMS, de su planilla', 'RL', fila['Unidad QMS']);
  comprobar('la de Defontana, del Informe de Inventario y no la del documento',
            'KG', fila['Unidad Defontana (Informe de Inventario)']);
  comprobar('el stock de QMS', 12, fila['Stock QMS']);
  comprobar('su valor unitario', 150, fila['Valor unitario QMS']);
  comprobar('y cómo cruza', 'Unidad distinta', fila['Cruce con QMS']);
  comprobar('sin perder lo que ya traía', 'A-1', fila['Código']);
}

console.log('\nY si un producto no está en QMS, lo dice');
{
  const filas = cruce({
    qms: [{code: 'OTRO', stock: 1, um: 'UN', unit: 1}],
    docs: [{art: 'A-1', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}],
  });
  const fila = regExport(state.rows.find(r => r.code === 'A-1'));
  comprobar('lo dice en la columna del cruce', 'No está en QMS', fila['Cruce con QMS']);
  comprobar('y no inventa un código de QMS', '', fila['Código QMS']);
}

console.log('\nSin archivo de QMS las columnas quedan vacías, no con un cruce falso');
{
  cruce({docs: [{art: 'A-1', qty: 9, valor: 900, valorInv: 900, saldo: 9, um: 'UN'}]});
  const fila = regExport(state.rows.find(r => r.code === 'A-1'));
  comprobar('la columna del cruce queda vacía', '', fila['Cruce con QMS']);
}

/* ---- Las dos líneas de negocio ----

   Viene de dos lados y pueden decir cosas distintas: la del conteo es la que
   quedó guardada cuando se armó la toma, y la de QMS la que ese sistema tiene
   ahora. El Informe de Inventario no trae línea, así que no hay una tercera. */

console.log('\nLa línea del conteo y la de QMS, cada una por su lado');
{
  cruce({
    qms: [{code: 'INS-001', stock: 10, um: 'UN', unit: 1000, linea: 'PRENSAS'}],
    conteo: [{code: 'INS-001', stock: 10, linea: 'INSUMOS PRODUCCION'}],
    docs: [{art: 'INS-001', qty: 10, saldo: 10, valor: 10000, valorInv: 10000}],
  });
  const r = state.rows.find(x => x.code === 'INS-001');
  const x = R.regExport(r);
  comprobar('la del conteo', 'INSUMOS PRODUCCION', x['Línea']);
  comprobar('la de QMS', 'PRENSAS', x['Línea QMS']);
  comprobar('y las dos salen en la tabla', true,
    R.regRow(r).includes('INSUMOS PRODUCCION') && R.regRow(r).includes('PRENSAS'));
  // La columna de la tabla se usa además para ordenar y para copiar: tiene
  // que traer la de QMS, no repetir la del conteo.
  const col = clave => R.REG_COLS.find(c => c[0] === clave)[3](r);
  comprobar('la columna "Línea QMS" trae la de QMS', 'PRENSAS', col('lineaqms'));
  comprobar('y la de al lado sigue siendo la del conteo', 'INSUMOS PRODUCCION', col('linea'));
}

console.log('\nSin archivo de QMS, esa columna queda vacía');
{
  cruce({
    conteo: [{code: 'INS-001', stock: 10, linea: 'INSUMOS PRODUCCION'}],
    docs: [{art: 'INS-001', qty: 10, saldo: 10, valor: 10000, valorInv: 10000}],
  });
  const x = R.regExport(state.rows.find(r => r.code === 'INS-001'));
  comprobar('sin línea de QMS', '', x['Línea QMS']);
  comprobar('pero la del conteo sigue', 'INSUMOS PRODUCCION', x['Línea']);
}

console.log('\nUn producto que no está en QMS tampoco la inventa');
{
  cruce({
    qms: [{code: 'OTRO', stock: 1, um: 'UN', unit: 100, linea: 'PRENSAS'}],
    conteo: [{code: 'INS-001', stock: 10, linea: 'INSUMOS PRODUCCION'}],
    docs: [{art: 'INS-001', qty: 10, saldo: 10, valor: 10000, valorInv: 10000}],
  });
  const r = state.rows.find(x => x.code === 'INS-001');
  comprobar('vacía en el Excel', '', R.regExport(r)['Línea QMS']);
  // Y tampoco se le pega la línea de otro producto que sí está en QMS.
  comprobar('vacía en la tabla', null, R.REG_COLS.find(c => c[0] === 'lineaqms')[3](r));
  comprobar('la tabla no muestra la línea ajena', false, R.regRow(r).includes('PRENSAS'));
}

/* ---- La ubicación, desde QMS ----

   Defontana dice en qué bodega está el artículo; en qué parte de la bodega
   —"Sala Fría", "R3-E1/R3-F1"— sólo lo sabe QMS, que es donde se anota. En su
   archivo son 1.227 de 2.004 filas con ubicación. */

console.log('\nLa ubicación sale del archivo de QMS');
{
  cruce({
    qms: [{code: 'INS-001', stock: 10, um: 'UN', unit: 1000, ubicacion: 'Sala Fría'}],
    conteo: [{code: 'INS-001', stock: 10}],
    docs: [{art: 'INS-001', qty: 10, saldo: 10, valor: 10000, valorInv: 10000}],
  });
  const x = R.regExport(state.rows.find(r => r.code === 'INS-001'));
  comprobar('la ubicación de QMS', 'Sala Fría', x['Ubicación']);
}

console.log('\nLa de QMS manda sobre la que traiga el conteo');
{
  cruce({
    qms: [{code: 'INS-001', stock: 10, um: 'UN', unit: 1000, ubicacion: 'Sala Fría'}],
    conteo: [{code: 'INS-001', stock: 10, ubicacion: 'ESTANTE VIEJO'}],
    docs: [{art: 'INS-001', qty: 10, saldo: 10, valor: 10000, valorInv: 10000}],
  });
  const x = R.regExport(state.rows.find(r => r.code === 'INS-001'));
  comprobar('manda la de QMS', 'Sala Fría', x['Ubicación']);
}

console.log('\nSi QMS no la trae, queda la del conteo');
{
  cruce({
    qms: [{code: 'INS-001', stock: 10, um: 'UN', unit: 1000}],
    conteo: [{code: 'INS-001', stock: 10, ubicacion: 'ESTANTE A3'}],
    docs: [{art: 'INS-001', qty: 10, saldo: 10, valor: 10000, valorInv: 10000}],
  });
  const x = R.regExport(state.rows.find(r => r.code === 'INS-001'));
  comprobar('la del conteo, de respaldo', 'ESTANTE A3', x['Ubicación']);
}

/* ---- Cómo se escribe el código en cada sistema ----

   Los códigos cruzan por la clave —sin signos, espacios ni ceros de adelante—,
   así que un artículo puede cruzar con el código escrito distinto en cada
   sistema: "ROP-BCAN-M" en QMS y "ROP- BCAN-M" en Defontana. Para saber
   cuáles hay que emparejar a mano hay que poder verlo de una pasada, y
   bajarlo. */

console.log('\nDice si los dos sistemas escriben igual el código');
{
  const articulos = R.parseArticulos([
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
    ['ROP- BCAN-M', 'BUZO', 'BODEGA CENTRAL', 3, 'UN', 100, 300]]);
  cruce({
    qms: [{code: 'ROP-BCAN-M', stock: 3, um: 'UN', unit: 100}],
    docs: [{art: 'ROP- BCAN-M', qty: 3, saldo: 3, valor: 300, valorInv: 300, um: 'UN'}],
    articulos,
  });
  const fila = state.qmsRows.find(r => (r.q && r.q.code) === 'ROP-BCAN-M');
  comprobar('cruzan como el mismo artículo', true, !!(fila && fila.q && fila.d));
  comprobar('pero el código está escrito distinto', 'distinto', fila.codigos);
  comprobar('y se dice en la tabla', true, R.qmsRow(fila).includes('Escrito distinto'));
  comprobar('y en el Excel', 'Escrito distinto', R.qmsExport(fila)['¿Se escriben igual?']);
  comprobar('con los dos códigos al lado', 'ROP-BCAN-M', R.qmsExport(fila)['Código QMS']);
  comprobar('cada uno como lo escribe su sistema', 'ROP- BCAN-M', R.qmsExport(fila)['Código Defontana']);
}

console.log('\nY cuando lo escriben igual, también');
{
  cruce({
    qms: [{code: 'A-1', stock: 3, um: 'UN', unit: 100}],
    docs: [{art: 'A-1', qty: 3, saldo: 3, valor: 300, valorInv: 300, um: 'UN'}],
  });
  const fila = state.qmsRows.find(r => r.code === 'A-1');
  comprobar('lo dice', 'igual', fila.codigos);
  comprobar('en el Excel', 'Igual', R.qmsExport(fila)['¿Se escriben igual?']);
}

console.log('\nSi está en un solo sistema no hay dos códigos que comparar');
{
  cruce({
    qms: [{code: 'SOLO-QMS', stock: 1, um: 'UN', unit: 1}],
    docs: [{art: 'SOLO-DEF', qty: 1, saldo: 1, valor: 1, valorInv: 1, um: 'UN'}],
  });
  const soloQms = state.qmsRows.find(r => r.code === 'SOLO-QMS');
  const soloDef = state.qmsRows.find(r => r.code === 'SOLO-DEF');
  comprobar('el que sólo está en QMS queda vacío', '', soloQms.codigos);
  comprobar('y en el Excel también', '', R.qmsExport(soloQms)['¿Se escriben igual?']);
  comprobar('lo mismo el que sólo está en Defontana', '', soloDef.codigos);
  comprobar('y no se inventa el código que falta', '', R.qmsExport(soloQms)['Código Defontana']);
}

console.log('\nY sale también en el Excel de Productos');
{
  const articulos = R.parseArticulos([
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
    ['ROP- BCAN-M', 'BUZO', 'BODEGA CENTRAL', 3, 'UN', 100, 300]]);
  cruce({
    qms: [{code: 'ROP-BCAN-M', stock: 3, um: 'UN', unit: 100}],
    docs: [{art: 'ROP- BCAN-M', qty: 3, saldo: 3, valor: 300, valorInv: 300, um: 'UN'}],
    articulos,
  });
  const x = R.regExport(state.rows.find(r => r.code === 'ROP- BCAN-M'));
  comprobar('con su código de QMS', 'ROP-BCAN-M', x['Código QMS']);
  comprobar('y diciendo que está escrito distinto', 'Escrito distinto', x['¿Se escriben igual?']);
}

console.log('\nSe pueden filtrar los que están escritos distinto');
{
  const articulos = R.parseArticulos([
    ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'],
    ['ROP- BCAN-M', 'BUZO', 'BODEGA CENTRAL', 3, 'UN', 100, 300],
    ['A-1', 'OTRO', 'BODEGA CENTRAL', 3, 'UN', 100, 300]]);
  cruce({
    qms: [{code: 'ROP-BCAN-M', stock: 3, um: 'UN', unit: 100}, {code: 'A-1', stock: 3, um: 'UN', unit: 100}],
    docs: [{art: 'ROP- BCAN-M', qty: 3, saldo: 3, valor: 300, valorInv: 300, um: 'UN'},
           {art: 'A-1', qty: 3, saldo: 3, valor: 300, valorInv: 300, um: 'UN'}],
    articulos,
  });
  const filtro = R.QMS_FILTERS.find(f => f[0] === 'codigo');
  comprobar('hay un filtro', true, !!filtro);
  const pasan = state.qmsRows.filter(filtro[2]);
  comprobar('deja pasar sólo el escrito distinto', 1, pasan.length);
  comprobar('y es el que es', 'ROP-BCAN-M', pasan[0].code);
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
