/* Poner a mano si un movimiento fue antes o después del conteo.

   La fecha de un documento es la del papel, no la hora en que pasó. Un envío a
   producción fechado el día del conteo pudo salir de bodega antes de que se
   contara —y entonces ya está en lo contado— o después —y entonces hay que
   sumarlo aparte—. De eso depende cuánto ajustar, y la fecha sola no lo dice:
   lo sabe quien contó.

   Hasta ahora había una sola perilla para todos los del mismo día. Esto deja
   decidirlo documento por documento, y lo elegido manda sobre la fecha. */
const {porId} = require('./entorno.js');
const {compute, ajusteDelConteo, pendiente, detail, state} = require('../../app/static/js/regularizacion.js');

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
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo, valor: d.valor || 0, costo: 0,
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
  // Con valor: sin él la fila se pinta como "valorizada en $0", que es otro
  // aviso y tapa el color de antes/después.
  const base = {contado: 10, fechaConteo: DIA(2026, 8, 18), saldoInicial: 20,
                docs: [{kind: 'out', qty: 10, folio: 74, fecha: DIA(2026, 8, 18), valor: 35000}]};
  const clave = CLAVE('ENVIO A PRODUCCION', '74', 2026, 8, 18);

  const html = detail(escenario(base));
  comprobar('hay un desplegable en la fila del movimiento', true, html.includes('select class="cuando"'));
  comprobar('apuntando a su documento', true, html.includes(`data-doc="${clave}"`));
  comprobar('con lo que dice la fecha elegido', true, html.includes('<option value="" selected>Mismo día (antes)</option>'));
  comprobar('y las dos opciones para cambiarlo', true,
            html.includes('>Antes del conteo</option>') && html.includes('>Después del conteo</option>'));

  // Los posteriores al conteo van resaltados y los anteriores en gris: es
  // cómo se ve de un vistazo qué entra en la cuenta del ajuste y qué no.
  comprobar('la fila del anterior va en gris', true, html.includes('<tr class="pre">'));

  const puesto = detail(escenario({...base, cuando: {[clave]: 'despues'}}));
  comprobar('movido a después, la fila cambia de lado', true, puesto.includes('<tr class="after">'));
  comprobar('puesto a mano, queda marcado', true, puesto.includes('class="cuando puesto"'));
  comprobar('con su opción elegida', true, puesto.includes('<option value="despues" selected>'));
  comprobar('y dice qué decía la fecha', true, puesto.includes('por fecha: mismo día (antes)'));
}

console.log('\nEl ajuste del mismo día va DESPUÉS del conteo, aunque la perilla diga antes');
{
  /* El caso de A2000ETQ-CATNOINFLAMABL, con sus archivos:
       - PARTE DE ENTRADA #40 del 29-01-2026: +310 (Defontana queda en 310)
       - contó 0 el 13-10-2026
       - PARTE DE SALIDA #316 del mismo 13-10: −310, y está en el archivo de
         ajustes, o sea es la corrección de ese conteo.

     El ajuste es correcto y no falta nada. Tomándolo como anterior al conteo,
     Defontana aparecía en 0 al momento de contar, cuadrada con lo contado, y
     el sistema concluía que el ajuste no hacía falta: pedía "aumentar 310",
     o sea volver a meter 310 unidades que no existen. */
  const r = escenario({
    contado: 0, fechaConteo: DIA(2026, 10, 13), saldoInicial: 0,
    docs: [{kind: 'in', qty: 310, folio: 40, fecha: DIA(2026, 1, 29), tipo: 'PARTE DE ENTRADA'},
           {kind: 'out', qty: 310, folio: 316, fecha: DIA(2026, 10, 13), tipo: 'PARTE DE SALIDA', ajuste: true}],
  });
  comprobar('Defontana tenía 310 al momento de contar', 310, r.sysAtCount);
  comprobar('la diferencia al contar era −310', -310, ajusteDelConteo(r));
  comprobar('ya está ajustada', -310, r.aj);
  comprobar('no falta nada por ajustar', 0, pendiente(r));
  comprobar('y hoy Defontana debería tener 0, no 310', 0, r.realNow);
}

console.log('\nUn ajuste de otro día anterior sigue siendo historia');
{
  // Ajustado en agosto, contado en octubre: ese ajuste ya estaba hecho cuando
  // se contó, así que forma parte del saldo que Defontana tenía al contar.
  const r = escenario({
    contado: 10, fechaConteo: DIA(2026, 10, 13), saldoInicial: 30,
    docs: [{kind: 'out', qty: 10, folio: 300, fecha: DIA(2026, 8, 1), tipo: 'PARTE DE SALIDA', ajuste: true}],
  });
  comprobar('Defontana tenía 20 al contar', 20, r.sysAtCount);
}

console.log('\nUn comprobante de ajuste también se puede mover a mano');
{
  // Pasa cuando el ajuste se hizo en la mañana, por otra cosa, y el conteo fue
  // en la tarde: entonces sí estaba hecho antes de contar.
  const base = {contado: 0, fechaConteo: DIA(2026, 10, 13), saldoInicial: 0,
                docs: [{kind: 'in', qty: 310, folio: 40, fecha: DIA(2026, 1, 29), tipo: 'PARTE DE ENTRADA'},
                       {kind: 'out', qty: 310, folio: 316, fecha: DIA(2026, 10, 13), tipo: 'PARTE DE SALIDA', ajuste: true}]};
  const clave = CLAVE('PARTE DE SALIDA', '316', 2026, 10, 13);

  const aMano = escenario({...base, cuando: {[clave]: 'antes'}});
  comprobar('puesto como anterior, Defontana tenía 0 al contar', 0, aMano.sysAtCount);

  const html = detail(escenario(base));
  comprobar('el ajuste trae su desplegable', true, html.includes(`data-doc="${clave}"`));
  comprobar('y dice de qué lado quedó', true, html.includes('>Ajuste (después)</option>'));
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
