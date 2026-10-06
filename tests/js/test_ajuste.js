/* El ajuste que propone Regularización.

   La regla: se ajusta la diferencia AL MOMENTO DE CONTAR. Los movimientos
   posteriores no entran, porque ya están registrados en Defontana y volver a
   considerarlos pide ajustar dos veces por lo mismo. */
const {porId} = require('./entorno.js');
const {compute, ajusteDelConteo, pendiente, hoyDe, state} = require('../../app/static/js/regularizacion.js');

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  const ok = esperado === obtenido || (esperado == null && obtenido == null);
  if (!ok) { fallas++; console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`); }
  else console.log(`  ✔ ${titulo}`);
}

const DIA = (a, m, d) => new Date(a, m - 1, d);

/* Arma el estado como lo dejaría la lectura de los archivos y corre el cálculo.
   `docs` son las filas del Informe de Documentos, en orden. */
function escenario({contado, fechaConteo, saldoInicial, docs, bodega = '*', soloAprobados = false}) {
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: soloAprobados}));
  // El filtro de bodega de la pantalla: '*' son todas.
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: bodega}));
  state.stock = [{code: 'ART-1', key: 'ART1', name: 'ARTICULO', stock: contado,
                  fecha: fechaConteo, por: 'Bodega', estado: 'Contado', um: '', linea: ''}];
  state.recount = new Map();
  state.manual = new Set();
  state.hechos = new Map();
  state.pmpEdit = state.pmpEdit || new Map();

  let saldo = saldoInicial;
  const movimientos = docs.map((d, i) => {
    saldo += d.kind === 'in' ? d.qty : -d.qty;
    return {art: 'ART-1', key: 'ART1', nameKey: 'ARTICULO', tipo: d.tipo || 'PARTE', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo, valor: 0, costo: 0,
            orig: d.orig || 'CENTRAL', dest: d.dest || 'CENTRAL', estado: d.estado || 'Aprobado', motivo: '',
            _aj: !!d.ajuste};
  });
  return compute(movimientos).rows[0];
}

console.log('\nEl caso de ella: contó 5, Defontana tenía 3, después entraron 10');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)}],
  });
  comprobar('Defontana tenía 3 al conteo', 3, r.sysAtCount);
  comprobar('y tiene 13 hoy', 13, r.sysCalc);
  comprobar('el ajuste es una ENTRADA POR 2, no una salida por 8', 2, ajusteDelConteo(r));
}

console.log('\nLo mismo, pero mirando sólo una bodega y la entrada fue a otra');
{
  // Acá se rompía: el movimiento posterior no entra en la cuenta por el filtro
  // de bodega, pero el saldo de Defontana sí lo trae. Midiendo contra el saldo
  // de hoy salía una salida por 8 —para "llegar a 5"— con 15 en bodega.
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3, bodega: 'CENTRAL',
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15), dest: 'OTRA', orig: 'OTRA'}],
  });
  comprobar('entrada por 2, no salida por 8', 2, ajusteDelConteo(r));
}

console.log('\nLo mismo, con un documento sin aprobar después del conteo');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 10), saldoInicial: 1,
    docs: [{kind: 'in', qty: 2, fecha: DIA(2026, 9, 5)},
           {kind: 'in', qty: 10, fecha: DIA(2026, 9, 15), estado: 'Pendiente'}],
    soloAprobados: true,
  });
  comprobar('entrada por 2', 2, ajusteDelConteo(r));
}

console.log('\nSin movimientos posteriores al conteo');
{
  // Un artículo sin ningún documento no sale en el Informe, así que siempre
  // hay al menos uno: acá, anterior al conteo.
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 10), saldoInicial: 1,
    docs: [{kind: 'in', qty: 2, fecha: DIA(2026, 9, 5)}],
  });
  comprobar('entrada por 2', 2, ajusteDelConteo(r));
}

console.log('\nSobra stock en Defontana: contó 5 y había 8');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 10), saldoInicial: 6,
    docs: [{kind: 'in', qty: 2, fecha: DIA(2026, 9, 5)}],
  });
  comprobar('Defontana tenía 8 al conteo', 8, r.sysAtCount);
  comprobar('salida por 3', -3, ajusteDelConteo(r));
}

console.log('\nYa se hizo el ajuste: no se puede pedir dos veces');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)},
           {kind: 'in', qty: 2, fecha: DIA(2026, 9, 20), tipo: 'PARTE DE ENTRADA', ajuste: true}],
  });
  comprobar('el ajuste sigue siendo 2 en total', 2, ajusteDelConteo(r));
}

console.log('\nCuadrado: contó 5 y había 5, con movimientos después');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 5,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)},
           {kind: 'out', qty: 4, fecha: DIA(2026, 9, 20)}],
  });
  comprobar('no hay nada que ajustar', 0, ajusteDelConteo(r));
}

console.log('\nMovimientos ANTES del conteo: ésos sí cuentan, están en el saldo');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 10), saldoInicial: 1,
    docs: [{kind: 'in', qty: 2, fecha: DIA(2026, 9, 5)}],
  });
  comprobar('Defontana tenía 3 al conteo', 3, r.sysAtCount);
  comprobar('entrada por 2', 2, ajusteDelConteo(r));
}



console.log('\nLas tres columnas de la pantalla tienen que cuadrar entre sí');
{
  // "Debería tener − tiene = ajuste". Si no cuadran, el número correcto se lee
  // como un error y nadie lo aplica.
  const casos = [
    {titulo: 'todas las bodegas', bodega: '*', ajustado: false},
    {titulo: 'una sola bodega', bodega: 'CENTRAL', ajustado: false},
    {titulo: 'con el ajuste ya hecho', bodega: '*', ajustado: true},
  ];
  for (const c of casos) {
    const docs = [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15), dest: 'OTRA', orig: 'OTRA'}];
    if (c.ajustado) docs.push({kind: 'in', qty: 2, fecha: DIA(2026, 9, 20), ajuste: true});
    const r = escenario({contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3, bodega: c.bodega, docs});
    const hoy = hoyDe(r);
    comprobar(`${c.titulo}: debería tener (${r.realNow}) − tiene (${hoy}) = lo que falta`,
              pendiente(r), r.realNow - hoy);
  }
}

console.log('\nCon el informe completo, "debería tener" es lo de siempre');
{
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)}],
  });
  comprobar('contado + lo que entró después = 15', 15, r.realNow);
}


console.log('\nDespués de registrar el ajuste, no se puede volver a pedir');
{
  // Se contaron 5, Defontana tenía 3, entraron 10 y DESPUÉS se hizo la entrada
  // por 2. Ya está: en bodega hay 15 y Defontana dice 15.
  const r = escenario({
    contado: 5, fechaConteo: DIA(2026, 9, 1), saldoInicial: 3,
    docs: [{kind: 'in', qty: 10, fecha: DIA(2026, 9, 15)},
           {kind: 'in', qty: 2, fecha: DIA(2026, 9, 20), tipo: 'PARTE DE ENTRADA', ajuste: true}],
  });
  comprobar('Defontana tiene 15 hoy', 15, hoyDe(r));
  comprobar('lo que falta ajustar es 0', 0, pendiente(r));
  comprobar('y debería tener 15 hoy, no 17', 15, r.realNow);
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
