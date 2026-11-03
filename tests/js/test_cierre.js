/* El saldo de inventario al cierre de un mes, para consultar.

   Sale SÓLO del Informe de Documentos de Defontana: ni el conteo, ni QMS, ni
   el stock valorizado entran acá. Es lo que Defontana puede explicar con sus
   propios movimientos al último día del mes que se elija.

   El saldo de cada fila del informe depende del orden en que Defontana
   procesó los documentos, que puede no ser el de las filas cuando hay varios
   el mismo día; por eso el saldo inicial se vota y el del cierre se calcula
   sumando los documentos. */
const {porId} = require('./entorno.js');
const R = require('../../app/static/js/regularizacion.js');
const {parseMov, saldosAlCierre, mesesDelInforme, state} = R;

let fallas = 0, hechas = 0;
function comprobar(titulo, esperado, obtenido) {
  hechas++;
  if (esperado === obtenido) { console.log(`  ✔ ${titulo}`); return; }
  fallas++;
  console.log(`  ✘ ${titulo}\n      esperaba ${esperado}, obtuvo ${obtenido}`);
}

const CAB = ['Tipo Documento', 'Estado', 'Folio', 'Fecha', 'Bod. Origen', 'Bod. Destino', 'Motivo',
             'Movimiento', 'Artículo', 'Descripción', 'Cant. Movimiento', 'U. Medida',
             'Valor Movimiento', 'Saldo Inventario', 'Valor Inventario'];

// Una línea del Informe de Documentos.
const doc = ({tipo = 'PARTE DE ENTRADA', folio = '1', fecha, art = 'A-1', qty, kind = 'in',
              saldo = '', valorInv = '', um = 'UN', orig = '', dest = ''}) =>
  [tipo, 'Aprobado', folio, fecha, orig || (kind === 'out' ? 'BODEGA CENTRAL' : ''),
   dest || (kind === 'in' ? 'BODEGA CENTRAL' : ''),
   kind === 'out' ? 'SALIDA' : 'COMPRA', kind === 'in' ? 'Ingreso' : 'Egreso',
   art, 'PRODUCTO ' + art, qty, um, qty * 1000, saldo, valorInv];

function cargar(filas) {
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  state.mov = parseMov([CAB, ...filas]);
  return state.mov;
}

const de = (filas, code) => filas.find(f => f.code === code) || {};

console.log('\nEl saldo al cierre es lo que había el último día del mes');
{
  cargar([
    doc({fecha: '2026-08-10', qty: 10, saldo: 10, valorInv: 10000}),
    doc({fecha: '2026-09-05', qty: 4, kind: 'out', folio: '2', saldo: 6, valorInv: 6000}),
    doc({fecha: '2026-10-03', qty: 3, kind: 'out', folio: '3', saldo: 3, valorInv: 3000}),
  ]);

  comprobar('a fin de agosto', 10, de(saldosAlCierre('2026-08'), 'A-1').saldo);
  comprobar('a fin de septiembre', 6, de(saldosAlCierre('2026-09'), 'A-1').saldo);
  comprobar('a fin de octubre', 3, de(saldosAlCierre('2026-10'), 'A-1').saldo);
}

console.log('\nLo que pasó después del corte no cuenta');
{
  // Es la pregunta entera: el saldo de ese mes no puede moverse porque
  // después se haya hecho un documento.
  cargar([
    doc({fecha: '2026-09-28', qty: 5, saldo: 5, valorInv: 5000}),
    doc({fecha: '2026-10-01', qty: 5, folio: '2', saldo: 10, valorInv: 10000}),
  ]);

  comprobar('el de octubre no entra en septiembre', 5, de(saldosAlCierre('2026-09'), 'A-1').saldo);
  comprobar('y en octubre sí', 10, de(saldosAlCierre('2026-10'), 'A-1').saldo);
}

console.log('\nEl saldo inicial no se lee de una fila: se vota');
{
  // Dos documentos el mismo día, procesados por Defontana en otro orden que
  // el de las filas: creyéndole a la última fila, el saldo sale mal.
  cargar([
    doc({fecha: '2026-09-10', qty: 10, saldo: 30, valorInv: 30000}),
    doc({fecha: '2026-09-10', qty: 5, kind: 'out', folio: '2', saldo: 25, valorInv: 25000}),
  ]);
  // (saldo − acumulado) da 20 en las dos filas: el inicial es 20.
  comprobar('el inicial manda', 25, de(saldosAlCierre('2026-09'), 'A-1').saldo);
}

console.log('\nUn traspaso entre bodegas no cambia el inventario');
{
  cargar([
    doc({fecha: '2026-09-01', qty: 10, saldo: 10, valorInv: 10000}),
    doc({tipo: 'TRASPASO ENTRE BODEGAS', folio: '5', fecha: '2026-09-15', qty: 4, kind: 'in',
         orig: 'BODEGA CENTRAL', dest: 'BODEGA INSUMOS', saldo: 10, valorInv: 10000}),
  ]);
  const fila = de(saldosAlCierre('2026-09'), 'A-1');

  comprobar('el saldo no se mueve', 10, fila.saldo);
  // La entrada de 10 sí es del mes; las 4 del traspaso no se suman a ella.
  comprobar('ni se cuenta entre las entradas del mes', 10, fila.entradas);
}

console.log('\nLas entradas y salidas son las del mes elegido');
{
  cargar([
    doc({fecha: '2026-08-20', qty: 10, saldo: 10, valorInv: 10000}),
    doc({fecha: '2026-09-05', qty: 6, folio: '2', saldo: 16, valorInv: 16000}),
    doc({fecha: '2026-09-20', qty: 4, kind: 'out', folio: '3', saldo: 12, valorInv: 12000}),
  ]);
  const fila = de(saldosAlCierre('2026-09'), 'A-1');

  comprobar('entradas del mes', 6, fila.entradas);
  comprobar('salidas del mes', 4, fila.salidas);
  comprobar('y el saldo al cierre', 12, fila.saldo);
  // Lo de agosto no se cuenta como movimiento de septiembre.
  comprobar('los movimientos del mes', 2, fila.movimientos);
}

console.log('\nEl valorizado es el del informe, no uno reconstruido');
{
  cargar([
    doc({fecha: '2026-09-05', qty: 8, saldo: 8, valorInv: 72000}),
    doc({fecha: '2026-10-05', qty: 2, kind: 'out', folio: '2', saldo: 6, valorInv: 54000}),
  ]);
  const sep = de(saldosAlCierre('2026-09'), 'A-1');

  comprobar('el valor al cierre de septiembre', 72000, sep.valor);
  comprobar('y el costo unitario sale de dividirlo', 9000, sep.costo);
  comprobar('en octubre, el de octubre', 54000, de(saldosAlCierre('2026-10'), 'A-1').valor);
}

console.log('\nUn producto sin documentos a esa fecha no aparece');
{
  cargar([
    doc({fecha: '2026-10-05', art: 'NUEVO', qty: 3, saldo: 3, valorInv: 3000}),
    doc({fecha: '2026-08-05', art: 'VIEJO', qty: 1, folio: '2', saldo: 1, valorInv: 1000}),
  ]);
  const ago = saldosAlCierre('2026-08');

  comprobar('en agosto está el que ya existía', 1, de(ago, 'VIEJO').saldo);
  comprobar('y no el que todavía no', true, !ago.some(f => f.code === 'NUEVO'));
  comprobar('en octubre están los dos', 2, saldosAlCierre('2026-10').length);
}

console.log('\nEl mismo producto con dos códigos se suma');
{
  cargar([
    doc({fecha: '2026-09-01', art: 'A-1', qty: 4, saldo: 4, valorInv: 4000}),
    doc({fecha: '2026-09-02', art: 'A1', qty: 6, folio: '2', saldo: 6, valorInv: 6000}),
  ]);
  const filas = saldosAlCierre('2026-09');

  comprobar('es una sola fila', 1, filas.length);
  comprobar('con los dos saldos sumados', 10, filas[0].saldo);
  comprobar('y los dos valores', 10000, filas[0].valor);
  comprobar('diciendo con qué códigos', 2, filas[0].arts.length);
}

console.log('\nEl saldo se calcula, no se copia de la última fila');
{
  // El informe deja el Saldo Inventario en blanco en algunas filas. Copiando
  // el de la última, el producto queda en cero aunque tenga stock.
  cargar([
    doc({fecha: '2026-09-02', qty: 10, saldo: 10, valorInv: 10000}),
    doc({fecha: '2026-09-20', qty: 3, kind: 'out', folio: '2', saldo: '', valorInv: ''}),
  ]);

  comprobar('quedan 7', 7, de(saldosAlCierre('2026-09'), 'A-1').saldo);
}

console.log('\nY los meses no dependen del conteo ni del ajuste');
{
  // "Movimientos del mes" sólo ofrece desde el mes del ajuste, porque antes
  // los documentos no se hacían todos. Acá la pregunta es otra: cuánto había
  // a fin de un mes cualquiera, también de antes del ajuste.
  cargar([
    doc({fecha: '2026-05-02', art: 'INS-500', qty: 10, saldo: 10, valorInv: 10000}),
    doc({fecha: '2026-10-01', art: 'INS-500', qty: 10, folio: '400', saldo: 20, valorInv: 20000}),
    doc({tipo: 'PARTE DE SALIDA', folio: '311', fecha: '2026-10-09', art: 'INS-500',
         qty: 4, kind: 'out', saldo: 16, valorInv: 16000}),
  ]);
  state.stock = R.parseStock([['Código', 'Nombre', 'Stock físico', 'Fecha del conteo'],
                              ['INS-500', 'PRODUCTO INS-500', 16, '2026-10-08']]);
  state.recount = new Map(); state.hechos = new Map(); state.pmpEdit = new Map();
  state.ajNo = new Set(); state.ajustes = null;
  // Marcar los comprobantes como ajuste es lo que en la pantalla hace el
  // archivo de ajustes o la casilla de "Comprobantes de ajuste ya hechos".
  state.ajSi = new Set(R.detectarAjustes(state.mov).map(g => g.id));
  R.detectarAjustes(state.mov);

  comprobar('mayo sigue estando', true, mesesDelInforme().includes('2026-05'));
  comprobar('y su saldo es el de mayo', 10, de(saldosAlCierre('2026-05'), 'INS-500').saldo);
}

console.log('\nSe ofrecen todos los meses del informe');
{
  // No se cortan en el mes del ajuste como en "Movimientos del mes": acá la
  // pregunta es el saldo de un mes cualquiera, también de antes.
  cargar([
    doc({fecha: '2025-12-01', qty: 1, saldo: 1, valorInv: 1000}),
    doc({fecha: '2026-09-01', qty: 1, folio: '2', saldo: 2, valorInv: 2000}),
    doc({fecha: '2026-10-01', qty: 1, folio: '3', saldo: 3, valorInv: 3000}),
  ]);

  comprobar('del más nuevo al más viejo', '2026-10, 2026-09, 2025-12', mesesDelInforme().join(', '));
}

console.log('\nUn saldo negativo se puede filtrar');
{
  cargar([
    doc({fecha: '2026-09-10', qty: 5, kind: 'out', saldo: -5, valorInv: 0}),
  ]);
  const filas = saldosAlCierre('2026-09');
  const filtro = R.CIERRE_FILTERS.find(f => f[0] === 'negativo');

  comprobar('el saldo queda en negativo', -5, filas[0].saldo);
  comprobar('y el filtro lo encuentra', 1, filas.filter(filtro[2]).length);
  comprobar('el de "con saldo" también', 1,
            filas.filter(R.CIERRE_FILTERS.find(f => f[0] === 'consaldo')[2]).length);
}

console.log('\nLo que se ve en la tabla y en el Excel');
{
  cargar([
    doc({fecha: '2026-09-05', qty: 8, saldo: 8, valorInv: 72000}),
    doc({fecha: '2026-09-20', qty: 2, kind: 'out', folio: '2', saldo: 6, valorInv: 54000}),
  ]);
  state.cierre = '2026-09';
  const fila = saldosAlCierre('2026-09')[0];
  const x = R.cierreExport(fila);

  comprobar('el mes', 'septiembre 2026', x['Mes']);
  comprobar('el saldo', 6, x['Saldo al cierre']);
  comprobar('el valorizado', 54000, x['Valorizado']);
  comprobar('las entradas', 8, x['Entradas del mes']);
  comprobar('las salidas', 2, x['Salidas del mes']);
  comprobar('y el último movimiento', '20-09-2026', x['Último movimiento']);
  const html = R.cierreRow(fila);
  comprobar('la tabla muestra el producto', true, html.includes('A-1'));
  comprobar('y su saldo', true, html.includes('<b>6</b>'));
}

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
