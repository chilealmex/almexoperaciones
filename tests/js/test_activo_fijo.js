/* Los activos fijos, en Regularización.

   Un activo fijo se compra a una bodega normal y después se traspasa a la
   bodega de activos fijos. Quien recorre la bodega contando no pasa por ahí,
   así que el producto sale contado en 0 aunque esté guardado, y la pantalla
   proponía sacar de Defontana unidades que sí existen: en su informe del
   27-10 son 29 artículos en "BODEGA DE ACTIVOS FIJOS", todos con saldo.

   Marcado como activo fijo, lo que Defontana tenga en esa bodega se suma a lo
   contado: el traspaso es justamente la señal de que quedó bien. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {parseMov, parseStock, parseArticulos, compute, ajusteDelConteo, regExport, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  if (esperado === obtenido) { console.log(`  ✔ ${titulo}`); return; }
  fallas++;
  console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`);
}

const INV = ['Código Artículo', 'Descripción', 'Bodega', 'Saldo', 'Unidad', 'Valor unidad', 'Total'];
const CAB_MOV = ['Tipo Documento', 'Estado', 'Folio', 'Fecha', 'Bod. Origen', 'Bod. Destino', 'Motivo',
                 'Movimiento', 'Artículo', 'Descripción', 'Cant. Movimiento', 'U. Medida',
                 'Valor Movimiento', 'Saldo Inventario', 'Valor Inventario'];

// El caso de ella: entró 4 a la bodega central en mayo, después se traspasó a
// la de activos fijos, y el conteo del 23-10 lo encontró en 0.
function escenario({contado = 0, bodega = 'BODEGA DE ACTIVOS FIJOS', conInventario = true,
                    columnaAf = null, marcados = [], desmarcados = []} = {}) {
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  const cab = ['Código', 'Nombre', 'Stock físico', 'Fecha del conteo'];
  const fila = ['45025-024', 'ELEMENTO CALEFACTOR', contado, '2026-10-23'];
  if (columnaAf != null){ cab.push('Activo fijo'); fila.push(columnaAf); }
  state.stock = parseStock([cab, fila]);
  state.articulos = conInventario ? parseArticulos([INV,
    ['45025-024', 'ELEMENTO CALEFACTOR', bodega, 4, 'UN', 1765625, 7062500]]) : null;
  state.afSi = new Set(marcados); state.afNo = new Set(desmarcados);
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map();
  state.movCuando = new Map(); state.ajSi = new Set(); state.ajNo = new Set();
  state.qms = null; state.ajustes = null;
  const mov = parseMov([CAB_MOV,
    ['PARTE ENTRADA IMPORTACION', 'Aprobado', '43', '2026-05-14', '', 'BODEGA CENTRAL', 'COMPRA',
     'Ingreso', '45025-024', 'ELEMENTO CALEFACTOR', 4, 'UN', 7062500, 4, 7062500]]);
  state.rows = compute(mov).rows;
  return state.rows.find(r => r.code === '45025-024');
}

const clave = () => state.rows[0].key;

console.log('\nSin marcar, el conteo en 0 pide sacar lo que Defontana tiene');
{
  const r = escenario();
  comprobar('queda descuadrado', 'down', r.st);
  comprobar('y se propone disminuir 4', -4, ajusteDelConteo(r));
}

console.log('\nMarcado como activo fijo, lo de esa bodega se suma a lo contado');
{
  let r = escenario();
  r = escenario({marcados: [r.key]});
  comprobar('cuadra', 'ok', r.st);
  comprobar('sin nada que ajustar', 0, ajusteDelConteo(r));
  comprobar('y se dice cuántas están ahí', 4, r.enActivos);
  comprobar('explicando por qué no se propone sacarlas', true,
            r.obs.some(o => /activo fijo/i.test(o) && /no se propone sacarlas/.test(o)));
}

console.log('\nSólo cuenta lo que está en la bodega de activos fijos');
{
  // El mismo producto marcado, pero sus unidades están en la bodega central:
  // ahí el conteo sí pasó, y que no se haya encontrado es una diferencia de
  // verdad.
  let r = escenario({bodega: 'BODEGA CENTRAL'});
  r = escenario({bodega: 'BODEGA CENTRAL', marcados: [r.key]});
  comprobar('sigue descuadrado', 'down', r.st);
  comprobar('con su ajuste', -4, ajusteDelConteo(r));
  comprobar('y sin unidades en activos fijos', 0, r.enActivos);
}

console.log('\nLa marca puede venir en el archivo de conteo');
{
  // El Excel de "Stock y conteo" trae la columna desde que se pueden marcar
  // los activos fijos en el módulo de conteo.
  const r = escenario({columnaAf: 'Sí'});
  comprobar('se toma de la columna', true, r.activoFijo);
  comprobar('y cuadra igual', 'ok', r.st);
}

console.log('\nY lo que se marca en la pantalla manda sobre esa columna');
{
  let r = escenario({columnaAf: 'Sí'});
  r = escenario({columnaAf: 'Sí', desmarcados: [r.key]});
  comprobar('desmarcado, vuelve a pedir el ajuste', 'down', r.st);
  comprobar('sin sumar nada', 0, r.enActivos);

  let x = escenario({columnaAf: ''});
  x = escenario({columnaAf: '', marcados: [x.key]});
  comprobar('y al revés, marcado a mano, cuadra', 'ok', x.st);
}

console.log('\nSin el Informe de Inventario no se sabe en qué bodega está');
{
  // El saldo por bodega sale de ese archivo. Sin él, marcar no puede cambiar
  // la cuenta: no hay con qué saber qué parte está en activos fijos.
  let r = escenario({conInventario: false});
  r = escenario({conInventario: false, marcados: [r.key]});
  comprobar('la marca queda puesta', true, r.activoFijo);
  comprobar('pero no se inventan unidades', 0, r.enActivos);
  comprobar('y el ajuste sigue como estaba', -4, ajusteDelConteo(r));
}

console.log('\nSi se contó parte de lo que hay, se suma lo de la otra bodega');
{
  // Dos en la bodega central (contadas) y cuatro en la de activos fijos: el
  // producto está completo, no falta nada.
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  state.stock = parseStock([['Código', 'Nombre', 'Stock físico', 'Fecha del conteo'],
                            ['AF-005', 'MÁQUINA', 2, '2026-10-23']]);
  state.articulos = parseArticulos([INV,
    ['AF-005', 'MÁQUINA', 'BODEGA CENTRAL', 2, 'UN', 100, 200],
    ['AF-005', 'MÁQUINA', 'BODEGA DE ACTIVOS FIJOS', 4, 'UN', 100, 400]]);
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map();
  state.movCuando = new Map(); state.ajSi = new Set(); state.ajNo = new Set();
  state.afSi = new Set(); state.afNo = new Set(); state.qms = null; state.ajustes = null;
  const mov = parseMov([CAB_MOV,
    ['PARTE DE ENTRADA', 'Aprobado', '1', '2026-05-14', '', 'BODEGA CENTRAL', 'COMPRA',
     'Ingreso', 'AF-005', 'MÁQUINA', 6, 'UN', 600, 6, 600]]);
  state.rows = compute(mov).rows;
  const sinMarcar = state.rows[0];
  comprobar('sin marcar, pide sacar 4', -4, ajusteDelConteo(sinMarcar));
  state.afSi = new Set([sinMarcar.key]);
  state.rows = compute(mov).rows;
  const r = state.rows[0];
  comprobar('marcado, cuadra', 'ok', r.st);
  comprobar('sumando las 4 de activos fijos a las 2 contadas', 4, r.enActivos);
}

console.log('\nEn el Excel queda dicho');
{
  let r = escenario();
  r = escenario({marcados: [r.key]});
  const x = regExport(r);
  comprobar('que es activo fijo', 'Sí', x['Activo fijo']);
  comprobar('y cuántas están en esa bodega', 4, x['En la bodega de activos fijos']);
}

console.log('\nEl botón para marcarlo está en la fila');
{
  let r = escenario();
  comprobar('sin marcar, invita a marcarlo', true, R.regRow(r).includes('☆ Activo fijo'));
  r = escenario({marcados: [r.key]});
  comprobar('marcado, se ve que lo está', true, R.regRow(r).includes('★ Activo fijo'));
  comprobar('y el botón lleva su código', true, R.regRow(r).includes('data-afijo='));
}

console.log('\nY se pueden filtrar');
{
  let r = escenario();
  r = escenario({marcados: [r.key]});
  const filtro = R.REG_FILTERS ? R.REG_FILTERS.find(f => f[0] === 'afijo') : null;
  comprobar('hay un filtro de activos fijos', true, !!filtro);
  if (filtro) comprobar('que deja pasar a los marcados', true, filtro[2](r));
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
