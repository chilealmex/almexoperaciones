/* Poner a mano si un movimiento fue antes o después del conteo.

   La fecha de un documento es la del papel, no la hora en que pasó. Un envío a
   producción fechado el día del conteo pudo salir de bodega antes de que se
   contara —y entonces ya está en lo contado— o después —y entonces hay que
   sumarlo aparte—. De eso depende cuánto ajustar, y la fecha sola no lo dice:
   lo sabe quien contó.

   Hasta ahora había una sola perilla para todos los del mismo día. Esto deja
   decidirlo documento por documento, y lo elegido manda sobre la fecha. */
const {porId} = require('./entorno.js');
const {compute, ajusteDelConteo, detail, state} = require('../../app/static/js/regularizacion.js');

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const DIA = (a, m, d) => new Date(a, m - 1, d);

function escenario({contado, fechaConteo, saldoInicial, docs, mismoDia = 'before', cuando = {}}) {
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optSame', Object.assign(porId.get('optSame') || {}, {value: mismoDia}));
  state.stock = [{code: 'ART-1', key: 'ART1', name: 'ARTICULO', stock: contado,
                  fecha: fechaConteo, por: 'Bodega', estado: 'Contado', um: '', linea: ''}];
  state.recount = new Map();
  state.hechos = new Map();
  state.pmpEdit = new Map();
  state.movCuando = new Map(Object.entries(cuando));

  let saldo = saldoInicial;
  const movimientos = docs.map((d, i) => {
    saldo += d.kind === 'in' ? d.qty : -d.qty;
    return {art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: d.tipo || 'ENVIO A PRODUCCION',
            folio: String(d.folio != null ? d.folio : 100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo, valor: 0, costo: 0,
            orig: 'CENTRAL', dest: 'CENTRAL', estado: 'Aprobado', motivo: '', _aj: !!d.ajuste};
  });
  return compute(movimientos).rows[0];
}

/* La clave con que se guarda la elección: tipo, folio y día del documento.
   Es la misma que usa el módulo para reconocer un comprobante. */
const CLAVE = (tipo, folio, a, m, d) => [tipo, folio, a * 10000 + m * 100 + d].join('|');

console.log('\nEl caso de ella: un envío a producción el mismo día del conteo');
{
  // Contó 10. Defontana tenía 20 y ese mismo día salieron 10 a producción.
  // Si el envío salió ANTES de contar, lo contado ya lo descuenta: Defontana
  // debería tener 10 y falta ajustar... nada más que la diferencia al contar.
  const base = {contado: 10, fechaConteo: DIA(2026, 8, 18), saldoInicial: 20,
                docs: [{kind: 'out', qty: 10, folio: 74, fecha: DIA(2026, 8, 18)}]};

  const antes = escenario(base);
  comprobar('tomado como antes, Defontana tenía 10 al conteo', 10, antes.sysAtCount);
  comprobar('y no hay nada que ajustar', 0, ajusteDelConteo(antes));

  // Si salió DESPUÉS de contar, al momento de contar Defontana todavía tenía
  // 20 contra 10 contados: faltan 10 de ajuste.
  const despues = escenario({...base, cuando: {[CLAVE('ENVIO A PRODUCCION', '74', 2026, 8, 18)]: 'despues'}});
  comprobar('puesto como después, Defontana tenía 20 al conteo', 20, despues.sysAtCount);
  comprobar('y hay que ajustar −10', -10, ajusteDelConteo(despues));
}

console.log('\nLo elegido manda sobre la perilla de "todos los del mismo día"');
{
  const base = {contado: 10, fechaConteo: DIA(2026, 8, 18), saldoInicial: 20, mismoDia: 'after',
                docs: [{kind: 'out', qty: 10, folio: 74, fecha: DIA(2026, 8, 18)}]};

  const porLaPerilla = escenario(base);
  comprobar('con la perilla en "después", el ajuste es −10', -10, ajusteDelConteo(porLaPerilla));

  const aMano = escenario({...base, cuando: {[CLAVE('ENVIO A PRODUCCION', '74', 2026, 8, 18)]: 'antes'}});
  comprobar('puesto a mano en "antes", el ajuste vuelve a 0', 0, ajusteDelConteo(aMano));
}

console.log('\nTambién sirve para un movimiento de otro día');
{
  // El documento quedó fechado al día siguiente, pero la mercadería salió
  // antes de que pasaran contando. Por fecha entraría como posterior.
  const base = {contado: 10, fechaConteo: DIA(2026, 8, 18), saldoInicial: 20,
                docs: [{kind: 'out', qty: 10, folio: 74, fecha: DIA(2026, 8, 19)}]};

  const porFecha = escenario(base);
  comprobar('por la fecha, Defontana tenía 20 al conteo', 20, porFecha.sysAtCount);
  comprobar('y el ajuste sale −10', -10, ajusteDelConteo(porFecha));

  const aMano = escenario({...base, cuando: {[CLAVE('ENVIO A PRODUCCION', '74', 2026, 8, 19)]: 'antes'}});
  comprobar('puesto como anterior, Defontana tenía 10', 10, aMano.sysAtCount);
  comprobar('y no hay nada que ajustar', 0, ajusteDelConteo(aMano));
}

console.log('\nUna elección sólo afecta a su documento');
{
  const base = {contado: 10, fechaConteo: DIA(2026, 8, 18), saldoInicial: 30,
                docs: [{kind: 'out', qty: 10, folio: 74, fecha: DIA(2026, 8, 18)},
                       {kind: 'out', qty: 10, folio: 75, fecha: DIA(2026, 8, 18)}]};

  comprobar('los dos como antes: Defontana tenía 10, no falta nada',
            0, ajusteDelConteo(escenario(base)));

  const uno = escenario({...base, cuando: {[CLAVE('ENVIO A PRODUCCION', '75', 2026, 8, 18)]: 'despues'}});
  comprobar('moviendo sólo el 75, Defontana tenía 20 al conteo', 20, uno.sysAtCount);
  comprobar('y el ajuste es −10, no −20', -10, ajusteDelConteo(uno));
}

console.log('\nLo que debería tener hoy también cambia');
{
  // Lo que Defontana debería tener hoy = lo contado ± lo que pasó después.
  const base = {contado: 10, fechaConteo: DIA(2026, 8, 18), saldoInicial: 20,
                docs: [{kind: 'out', qty: 10, folio: 74, fecha: DIA(2026, 8, 18)}]};

  comprobar('como antes: lo contado ya lo descuenta, hoy deberían ser 10',
            10, escenario(base).realNow);
  comprobar('como después: se descuenta de lo contado, hoy deberían ser 0',
            0, escenario({...base, cuando: {[CLAVE('ENVIO A PRODUCCION', '74', 2026, 8, 18)]: 'despues'}}).realNow);
}

console.log('\nEn la pantalla, cada movimiento trae con qué cambiarlo');
{
  const base = {contado: 10, fechaConteo: DIA(2026, 8, 18), saldoInicial: 20,
                docs: [{kind: 'out', qty: 10, folio: 74, fecha: DIA(2026, 8, 18)}]};
  const clave = CLAVE('ENVIO A PRODUCCION', '74', 2026, 8, 18);

  const html = detail(escenario(base));
  comprobar('hay un desplegable en la fila del movimiento', true, html.includes('select class="cuando"'));
  comprobar('apuntando a su documento', true, html.includes(`data-doc="${clave}"`));
  comprobar('con lo que dice la fecha elegido', true, html.includes('<option value="" selected>Mismo día (antes)</option>'));
  comprobar('y las dos opciones para cambiarlo', true,
            html.includes('>Antes del conteo</option>') && html.includes('>Después del conteo</option>'));

  const puesto = detail(escenario({...base, cuando: {[clave]: 'despues'}}));
  comprobar('puesto a mano, queda marcado', true, puesto.includes('class="cuando puesto"'));
  comprobar('con su opción elegida', true, puesto.includes('<option value="despues" selected>'));
  comprobar('y dice qué decía la fecha', true, puesto.includes('por fecha: mismo día (antes)'));
}

console.log('\nUn comprobante de ajuste no se cambia de lado');
{
  // No es un movimiento del día a día: es la corrección que se hizo. Dejarlo
  // mover sólo daría formas de descuadrar la cuenta de lo ya ajustado.
  const html = detail(escenario({
    contado: 10, fechaConteo: DIA(2026, 8, 18), saldoInicial: 20,
    docs: [{kind: 'out', qty: 10, folio: 74, fecha: DIA(2026, 8, 20), tipo: 'PARTE DE SALIDA', ajuste: true}],
  }));
  comprobar('no trae desplegable', false, html.includes('select class="cuando"'));
  comprobar('y sigue diciendo que es un ajuste', true, html.includes('<td>Ajuste</td>'));
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
