/* El cruce con QMS: los dos sistemas lado a lado.

   QMS es el otro sistema. Acá no entra en ningún cálculo —lo que se ajusta en
   Defontana se sigue decidiendo con el conteo físico—: es para mirar código,
   unidad, cantidad y valor unitario de los dos lados y ver dónde no coinciden
   o qué existe en uno y no en el otro. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {parseQms, computeQms, cruceQms, qmsRow, compute, state} = R;

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
                                  por: '', estado: '', um: c.um || '', linea: c.linea || ''}));
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map(); state.movCuando = new Map();
  state.articulos = articulos;
  const mov = docs.map((d, i) => ({art: d.art, key: null, nameKey: '', tipo: 'PARTE DE ENTRADA', folio: String(100 + i),
    fecha: d.fecha || DIA(2026, 1, 10), kind: d.kind || 'in', qty: d.qty, saldo: d.saldo != null ? d.saldo : d.qty,
    valor: d.valor || 0, valorInv: d.valorInv != null ? d.valorInv : (d.valor || 0), costo: 0,
    orig: '', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', um: d.um || '', desc: d.desc || '', _aj: false}));
  for (const m of mov){ m.key = R.parseStock([['Código', 'Stock físico'], [m.art, 0]])[0].key; }
  state.mov = mov;
  state.qms = qms.length ? parseQms([['Código Único', 'Stock', 'Unidad', 'Valor unitario', 'Descripción', 'Linea Negocio', 'Categoria'],
    ...qms.map(q => [q.code, q.stock, q.um || '', q.unit == null ? '' : q.unit, q.name || '', q.linea || '', q.cat || ''])]) : null;
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

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
