/* El ajuste de costo se mide contra lo que Defontana tiene HOY.

   El ajuste se calculaba repitiendo los movimientos del producto y comparando
   esa repetición consigo misma. Casi siempre da igual. Deja de darlo cuando
   Defontana revaloriza por su cuenta —un recosteo, la factura que llega
   después con otro costo—: ahí el valor acumulado se mueve sin que ningún
   documento del producto se vea mal, y el ajuste calculado contra la
   repetición propone mover un valor que el sistema no tiene.

   El caso real: BRP-003, 209 brochas. Repitiendo los movimientos da $259.719,
   pero Defontana tenía $943.426 (PMP $4.514 para una brocha de $1.271). Se
   proponía un ajuste de ENTRADA por $2.943 —subirle valor a un inventario que
   ya estaba inflado— cuando lo que sobraban eran ~$675.000.

   El invariante que lo deja al descubierto: si el ajuste promete dejar el PMP
   en X, entonces el valor de hoy más el ajuste tiene que dar X por las
   unidades que hay. Antes no daba. */
const {porId} = require('./entorno.js');
const {compute, tipoAjCosto, state} = require('../../app/static/js/regularizacion.js');

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

// Movimientos con el saldo y el valor corriendo fila a fila, como los trae el
// informe. `valorFinal` deja la última fila con el Valor Inventario que diga
// Defontana, que es lo que pasa cuando revaloriza por su cuenta.
function informe(lista, valorFinal) {
  let s = 0, v = 0;
  const docs = lista.map((d, i) => {
    let valor = d.cu * d.qty;
    if (d.kind === 'in') { s += d.qty; v += valor; }
    else { const p = s > 0 ? v / s : 0; valor = p * d.qty; s -= d.qty; v -= valor; }
    return {art: 'AAA', key: 'AAA', nameKey: 'NAAA', tipo: 'FACTURA', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo: s, valor, valorInv: v, um: '',
            orig: 'C', dest: 'C', estado: 'Aprobado', motivo: '', desc: 'PROD AAA'};
  });
  if (valorFinal != null) docs[docs.length - 1].valorInv = valorFinal;
  return docs;
}

const ing = (q, cu, d) => ({kind: 'in', qty: q, cu, fecha: DIA(2026, 8, d)});

function pantalla(docs) {
  state.stock = []; state.recount = new Map(); state.manual = new Set();
  state.hechos = new Map(); state.pmpEdit = new Map(); state.ajustes = []; state.mov = docs;
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  const out = compute(docs);
  return out.rows[0];
}

// Un ingreso a $0 (lo que dispara la propuesta de costo) y compras normales a
// $1.000. Quedan 30 unidades.
const MOVS = [ing(10, 0, 1), ing(10, 1000, 2), ing(10, 1000, 3)];

// El invariante: si promete dejar el PMP en X, el valor de hoy más el ajuste
// tiene que dar X por las unidades que hay.
function cuadra(r) {
  const u = r.docs[r.docs.length - 1], c = r.cost.corr;
  return Math.round((u.valorInv + c.ajuste) - c.pmp * u.saldo);
}

escenario('Cuando Defontana cuadra con sus movimientos, nada cambia', () => {
  const r = pantalla(informe(MOVS));
  const u = r.docs[r.docs.length - 1];
  comprobar('Defontana tiene $20.000 por 30 unidades', 20000, Math.round(u.valorInv));
  comprobar('propone subirlo en $10.000 (las 10 que entraron a $0)', 10000, Math.round(r.cost.corr.ajuste));
  comprobar('para dejar el PMP en $1.000', 1000, Math.round(r.cost.corr.pmp));
  comprobar('y el monto cuadra con ese PMP', 0, cuadra(r));
  comprobar('es un ajuste de entrada', 'Ajuste de costo ENTRADA', tipoAjCosto(r.cost.corr.ajuste));
});

escenario('El caso de BRP-003: Defontana revalorizó para arriba', () => {
  // Mismos movimientos, pero Defontana dice que las 30 valen $120.000
  // ($4.000 c/u para un producto de $1.000). Ningún documento se ve mal.
  const r = pantalla(informe(MOVS, 120000));
  comprobar('hay que BAJAR el valor, no subirlo', true, r.cost.corr.ajuste < 0);
  comprobar('por $90.000: de $120.000 a los $30.000 que corresponden', -90000, Math.round(r.cost.corr.ajuste));
  comprobar('el PMP sigue siendo $1.000', 1000, Math.round(r.cost.corr.pmp));
  comprobar('y el monto cuadra con ese PMP', 0, cuadra(r));
  comprobar('es un ajuste de salida', 'Ajuste de costo SALIDA', tipoAjCosto(r.cost.corr.ajuste));
  comprobar('y lo dice en el paso', true, /Ajuste de costo SALIDA por \$90\.000/.test(r.cost.hacer.map(h => h.txt).join(' ')));
});

escenario('Y si revalorizó para abajo, es una entrada más grande', () => {
  const r = pantalla(informe(MOVS, 5000));
  comprobar('hay que subir el valor', true, r.cost.corr.ajuste > 0);
  comprobar('por $25.000: de $5.000 a $30.000', 25000, Math.round(r.cost.corr.ajuste));
  comprobar('el monto cuadra con el PMP que promete', 0, cuadra(r));
  comprobar('es un ajuste de entrada', 'Ajuste de costo ENTRADA', tipoAjCosto(r.cost.corr.ajuste));
});

escenario('El ajuste nunca deja el PMP más lejos de lo que debería', () => {
  // Lo que pasaba antes: con el inventario inflado se proponía SUMAR valor.
  for (const valorDefontana of [null, 120000, 5000, 60000, 1000]) {
    const r = pantalla(informe(MOVS, valorDefontana));
    const u = r.docs[r.docs.length - 1], c = r.cost.corr;
    const antes = Math.abs(u.valorInv / u.saldo - c.pmp);
    const despues = Math.abs((u.valorInv + c.ajuste) / u.saldo - c.pmp);
    comprobar(`con Defontana en ${valorDefontana == null ? 'lo que cuadra' : '$' + valorDefontana}, acerca el PMP`,
              true, despues <= antes + 0.001);
  }
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
