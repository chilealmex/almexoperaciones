/* Los costos se llenan en el Excel del plan y se suben de vuelta.

   El paso 2 ya no propone un monto: pide el costo. Escribirlos uno por uno en
   la pantalla, para cincuenta y tantos productos, es el tipo de trabajo que se
   abandona a la mitad. El plan se descarga con una columna vacía, se llena de
   una pasada en el Excel y se sube; de ahí salen los mismos costos que si se
   hubieran tecleado. */
const {porId} = require('./entorno.js');
const {compute, buildPlan, parseCostos, state} = require('../../app/static/js/regularizacion.js');

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

const CAB = ['#', 'Código', 'Nombre', 'ESCRIBE AQUÍ el costo a usar', 'Línea', 'Qué corregir'];
const hoja = (...filas) => [CAB, ...filas];

escenario('Lee los costos que se escribieron en la columna', () => {
  const c = parseCostos(hoja([1, 'BRP-003', 'BROCHA 3"', 1283.23, 'PRENSAS', 'NO OCUPAR #2'],
                             [2, '11-STR-ENC-09', 'SELLO', 397, 'PRENSAS', 'NO OCUPAR2 #84']));
  comprobar('dos costos', 2, c.length);
  comprobar('el código', 'BRP-003', c[0].code);
  comprobar('el costo, con decimales', 1283.23, c[0].costo);
  comprobar('y la clave para cruzarlo', 'BRP003', c[0].key);
});

escenario('Las filas sin llenar se saltan, no se ponen en cero', () => {
  const c = parseCostos(hoja([1, 'AAA', 'UNO', '', 'L', 'D'],
                             [2, 'BBB', 'DOS', 1000, 'L', 'D'],
                             [3, 'CCC', 'TRES', 0, 'L', 'D']));
  comprobar('sólo la que tiene costo', 1, c.length);
  comprobar('y es la correcta', 'BBB', c[0].code);
});

escenario('Si no es el archivo que corresponde, lo dice', () => {
  let m1 = '', m2 = '', m3 = '';
  try { parseCostos([['Artículo', 'Movimiento'], ['AAA', 'Ingreso']]); } catch (e) { m1 = e.message; }
  comprobar('sin columna Código', true, /Código/.test(m1));
  try { parseCostos([['Código', 'Nombre'], ['AAA', 'UNO']]); } catch (e) { m2 = e.message; }
  comprobar('sin columna de costo, dice qué hacer', true, /Descarga el plan en Excel/.test(m2));
  try { parseCostos(hoja([1, 'AAA', 'UNO', '', 'L', 'D'])); } catch (e) { m3 = e.message; }
  comprobar('con la columna vacía, avisa en vez de callarse', true, /Ninguna fila trae un costo/.test(m3));
});

// --- El viaje completo: descargar, llenar, subir ---

const DIA = (a, m, d) => new Date(a, m - 1, d);
const ing = (q, cu, d) => ({kind: 'in', qty: q, cu, fecha: DIA(2026, 8, d)});

function docsDe(lista) {
  let s = 0, v = 0;
  return lista.map((d, i) => {
    let valor = d.cu * d.qty;
    if (d.kind === 'in') { s += d.qty; v += valor; }
    else { const p = s > 0 ? v / s : 0; valor = p * d.qty; s -= d.qty; v -= valor; }
    return {art: 'AAA', key: 'AAA', nameKey: 'NAAA', tipo: 'FACTURA', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo: s, valor, valorInv: v, um: '',
            orig: 'C', dest: 'C', estado: 'Aprobado', motivo: '', desc: 'PROD AAA'};
  });
}

function plan(costos) {
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  state.hechos = new Map(); state.ajustes = []; state.articulos = null;
  state.pmpEdit = new Map(costos || []);
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  const mov = docsDe([ing(10, 0, 1), ing(20, 1000, 2)]);
  state.mov = mov;
  const out = compute(mov);
  state.rows = out.rows; state.zero = out.zero;
  return buildPlan();
}

escenario('Sin los costos, el plan pide el costo; con ellos, calcula', () => {
  const sin = plan(null);
  comprobar('hay una línea de costo', 1, sin.cost.length);
  comprobar('y no trae monto', null, sin.cost[0].corr);

  // Lo que vuelve del Excel, leído por el mismo lector
  const leidos = parseCostos(hoja([1, 'AAA', 'PROD AAA', 1000, '', '']));
  const con = plan(leidos.map(c => [c.key, c.costo]));
  comprobar('ahora sí hay monto', true, !!con.cost[0].corr);
  // 30 unidades que deben quedar a $1.000 = $30.000, y hoy valen $20.000
  comprobar('y es el que corresponde', 10000, Math.round(con.cost[0].corr.ajuste));
  comprobar('con el costo escrito como costo a dejar', 1000, Math.round(con.cost[0].corr.pmp));
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
