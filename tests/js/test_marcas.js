/* "Ya regularizado", paso por paso.

   Marcar el producto entero servía para la unidad de medida: se corrige en
   Defontana y no hay ajuste que hacer. Pero se llevaba por delante la cantidad
   y el costo, que sí había que ajustar y dejaban de pedirse: el producto
   desaparecía de los pasos 2, 3 y 4 y no quedaba forma de regularizarlo paso a
   paso. Ahora cada paso se marca por su cuenta. */
const {porId} = require('./entorno.js');
const {compute, buildPlan, docSteps, tipoAjCosto, state} = require('../../app/static/js/regularizacion.js');

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
const ing = (q, cu, d) => ({kind: 'in', qty: q, cu, fecha: DIA(2026, 8, d)});

function docsDe(lista, um) {
  let s = 0, v = 0;
  return lista.map((d, i) => {
    let valor = d.cu * d.qty;
    if (d.kind === 'in') { s += d.qty; v += valor; }
    else { const p = s > 0 ? v / s : 0; valor = p * d.qty; s -= d.qty; v -= valor; }
    return {art: 'AAA', key: 'AAA', nameKey: 'NAAA', tipo: 'FACTURA', folio: String(100 + i),
            fecha: d.fecha, kind: d.kind, qty: d.qty, saldo: s, valor, valorInv: v, um: um || '',
            orig: 'C', dest: 'C', estado: 'Aprobado', motivo: '', desc: 'PROD AAA'};
  });
}

// Tres compras a $1.000 y una entrada a $20.000 (el costo malo), 13 unidades.
// Se cuentan 20 el día 5 y el día 7 entra un ingreso de 7, justo la diferencia:
// Defontana no sabe si ya estaban en bodega al contar, así que lo deja "a
// confirmar". Tiene las tres cosas a la vez: confirmar, costo y cantidad.
const MOV = [ing(1, 1000, 1), ing(1, 1000, 2), ing(1, 1000, 3), ing(10, 20000, 4), ing(7, 1000, 7)];
const CONTEO = [{key: 'AAA', code: 'AAA', name: 'PROD AAA', stock: 20, fecha: DIA(2026, 8, 5),
                 linea: '', um: '', por: '', estado: ''}];

function pantalla(marca, caso, costoAMano = 1000) {
  const c = caso || {mov: MOV, conteo: CONTEO};
  state.stock = c.conteo; state.recount = new Map(); state.manual = new Set();
  // El monto del ajuste de costo sale del costo escrito a mano: sin eso sólo
  // se muestran las cifras. Estas pruebas lo escriben para comprobar el monto.
  state.pmpEdit = costoAMano == null ? new Map() : new Map([['AAA', costoAMano]]); state.ajustes = [];
  state.hechos = marca === undefined ? new Map() : new Map([['AAA', marca]]);
  porId.set('optBodega', Object.assign(porId.get('optBodega') || {}, {value: '*'}));
  porId.set('optAprob', Object.assign(porId.get('optAprob') || {}, {checked: false}));
  porId.set('optLinea', Object.assign(porId.get('optLinea') || {}, {value: ''}));
  const mov = docsDe(c.mov, c.um);
  state.mov = mov;
  const out = compute(mov);
  state.rows = out.rows; state.zero = out.zero;
  return {r: out.rows[0], plan: buildPlan()};
}

const pasos = p => docSteps(p.r).map(x => x.k);
const marcado = (...ps) => ({sug: 7, fecha: +DIA(2026, 8, 5), pasos: ps});
// La marca guarda la diferencia que ella vio al marcar; con otra, no vale.
const marcadoSug = (sug, ...ps) => ({sug, fecha: +DIA(2026, 8, 5), pasos: ps});

escenario('Sin marcar nada: están los tres pasos', () => {
  const p = pantalla();
  comprobar('el producto queda a confirmar', 'check', p.r.st);
  comprobar('pide confirmar', true, pasos(p).includes('verify'));
  comprobar('y pide corregir el costo', true, pasos(p).includes('cost'));
  comprobar('todavía no pide la cantidad: primero hay que confirmar', false, pasos(p).includes('in'));
});

escenario('Marcar sólo lo que había que confirmar deja ver la cantidad', () => {
  // Esto es lo que ella pedía: marcó la unidad de medida y el ajuste de
  // cantidad tiene que aparecer en su paso, no desaparecer el producto.
  const p = pantalla(marcado('confirmar'));
  comprobar('ya no pide confirmar', false, pasos(p).includes('verify'));
  comprobar('ahora sí pide la entrada por la diferencia', true, pasos(p).includes('in'));
  comprobar('y el plan la pide', 1, p.plan.in.length);
  comprobar('por las 7 unidades', 7, p.plan.in[0].qty);
  comprobar('el costo sigue pidiéndose', true, pasos(p).includes('cost'));
  comprobar('y el plan lo pide', 1, p.plan.cost.length);
  comprobar('el producto NO queda como ya regularizado', false, p.r.manual);
  comprobar('dice que la marca fue de la revisión', true, /Marcaste la revisión/.test(p.r.obs.join(' ')));
});

escenario('Marcar el costo no se lleva la cantidad', () => {
  const p = pantalla(marcado('confirmar', 'costo'));
  comprobar('ya no pide el costo', false, pasos(p).includes('cost'));
  comprobar('ni el plan', 0, p.plan.cost.length);
  comprobar('pero la cantidad sigue', true, pasos(p).includes('in'));
  comprobar('y el plan la pide', 1, p.plan.in.length);
});

escenario('Marcar la cantidad no se lleva el costo', () => {
  const p = pantalla(marcado('confirmar', 'cantidad'));
  comprobar('la cantidad queda hecha', 'done', p.r.st);
  comprobar('el plan no pide entrada', 0, p.plan.in.length);
  comprobar('pero el costo sigue pidiéndose', true, pasos(p).includes('cost'));
  comprobar('y el plan lo pide', 1, p.plan.cost.length);
  comprobar('el producto NO queda como ya regularizado', false, p.r.manual);
});

escenario('Con los tres pasos marcados, el producto queda listo', () => {
  const p = pantalla(marcado('confirmar', 'costo', 'cantidad'));
  comprobar('queda marcado como ya regularizado', true, p.r.manual);
  comprobar('y no pide nada', 0, p.plan.cost.length + p.plan.in.length + p.plan.out.length + p.plan.verify.length);
});

escenario('Una marca vieja, sin pasos, sigue valiendo por todo el producto', () => {
  // Las marcas guardadas antes de esto significaban el producto entero: no se
  // pueden reinterpretar como "sólo la unidad de medida" sin ponerle trabajo
  // de vuelta que ella ya había dado por hecho.
  comprobar('guardada como null', true, pantalla(null).r.manual);
  comprobar('guardada sin la lista de pasos', true, pantalla({sug: 7, fecha: +DIA(2026, 8, 5)}).r.manual);
});

// El caso de ella: se contó en M y en Defontana el producto está en UN, sin
// conversión conocida. Hay que corregir la unidad en el maestro de Defontana,
// y recién después ajustar la cantidad.
const UNIDAD = {um: 'UN', mov: [ing(78, 1000, 1)],
                conteo: [{key: 'AAA', code: 'AAA', name: 'PROD AAA', stock: 58, fecha: DIA(2026, 8, 5),
                          linea: '', um: 'M', por: '', estado: ''}]};

escenario('Unidad de medida: marcarla no esconde el ajuste de cantidad', () => {
  const sin = pantalla(undefined, UNIDAD);
  comprobar('sin marcar, hay que confirmar la unidad', 'check', sin.r.st);
  comprobar('y pide corregir el maestro', true, pasos(sin).includes('verify'));
  comprobar('todavía no pide la salida', false, pasos(sin).includes('out'));

  const p = pantalla(marcadoSug(-20, 'confirmar'), UNIDAD);
  comprobar('marcada la unidad, ya no la pide', false, pasos(p).includes('verify'));
  comprobar('ahora pide la salida por la diferencia', true, pasos(p).includes('out'));
  comprobar('el plan la pide', 1, p.plan.out.length);
  comprobar('por las 20 unidades', 20, p.plan.out[0].qty);
  comprobar('y lo explica', true, /unidad de medida como corregida/.test(p.r.obs.join(' ')));
});

// Un ingreso a $0 teniendo compras normales antes: va por el camino de los $0,
// que es otro código que el del costo fuera de lo normal.
const CERO = {mov: [ing(1, 1000, 1), ing(1, 1000, 2), ing(1, 1000, 3), ing(10, 0, 4)],
              conteo: CONTEO};

escenario('Marcar el costo también vale para los ingresos a $0', () => {
  const sin = pantalla(undefined, CERO);
  comprobar('sin marcar, pide corregir el costo', true, pasos(sin).includes('cost'));
  comprobar('y el plan lo pide', 1, sin.plan.cost.length);

  const p = pantalla(marcado('costo'), CERO);
  comprobar('marcado, ya no lo pide', false, pasos(p).includes('cost'));
  comprobar('ni el plan', 0, p.plan.cost.length);
});

// --- Entrada o salida de costo ---

escenario('El ajuste de costo dice si es entrada o salida', () => {
  // Entró a $20.000 lo que cuesta $1.000: el inventario vale de más, así que
  // el comprobante en Defontana es un ajuste de costo SALIDA.
  const p = pantalla(marcado('confirmar'));
  const x = p.plan.cost[0];
  comprobar('el valor hay que bajarlo', true, x.corr.ajuste < 0);
  comprobar('y lo llama salida', true, /Ajuste de costo SALIDA/.test(x.nota));
  comprobar('sin repetir el signo en el monto', false, /−\$/.test(x.nota));

  // Un ingreso a $0: el inventario vale de menos, hay que subirlo.
  const c = pantalla(undefined, CERO);
  const y = c.plan.cost[0];
  comprobar('acá el valor hay que subirlo', true, y.corr.ajuste > 0);
  comprobar('y lo llama entrada', true, /Ajuste de costo ENTRADA/.test(docSteps(c.r).find(s => s.k === 'cost').txt));
});

escenario('Si el costo no se sabe, no inventa el sentido del comprobante', () => {
  // Todo entró a $1, así que hoy el producto vale $1 la unidad: va al paso 2a
  // —cargarle el costo— y no al 2, que es para lo que tiene valor y lo tiene
  // mal. Sin costo conocido no se dice si el comprobante sube o baja el valor.
  const p = pantalla(undefined, {mov: [ing(2, 1, 1), ing(3, 1, 2)], conteo: CONTEO}, null);
  comprobar('no va al paso 2', 0, p.plan.cost.length);
  const x = p.plan.sinValor[0];
  comprobar('va al 2a', true, !!x);
  comprobar('sin costo propuesto', null, x.v);
  const paso = docSteps(p.r).find(h => h.k === 'sinvalor');
  comprobar('y no dice ni entrada ni salida', false, /SALIDA/.test(paso.txt));
});

escenario('Un producto sin costo en Defontana: cargarlo es una entrada', () => {
  // Todo entró a $0 y quedan unidades: el PMP es $0. Cargarle el costo sube el
  // valor del inventario, así que el comprobante es de entrada.
  const p = pantalla(undefined, {mov: [ing(20, 0, 1)], conteo: CONTEO});
  // Va en su propio paso: "tiene unidades y no vale nada" es distinto de
  // "entró a un costo raro", y se resuelve distinto.
  const paso = docSteps(p.r).find(x => x.k === 'sinvalor');
  comprobar('pide cargar el costo', true, !!paso && /cargar el costo/.test(paso.txt));
  comprobar('y es una entrada', true, !!paso && paso.txt.startsWith('Ajuste de costo ENTRADA'));
});

escenario('Sin monto no se nombra el comprobante', () => {
  comprobar('un ajuste que sube el valor es entrada', 'Ajuste de costo ENTRADA', tipoAjCosto(5000));
  comprobar('uno que lo baja es salida', 'Ajuste de costo SALIDA', tipoAjCosto(-5000));
  comprobar('sin monto, ninguno', null, tipoAjCosto(null));
  comprobar('y por unos pesos tampoco: no hay comprobante que hacer', null, tipoAjCosto(0.2));
});

escenario('Si el conteo cambia, la marca deja de valer', () => {
  // La marca vale para la diferencia que ella vio al marcar. Con un conteo
  // nuevo el producto vuelve a aparecer, como antes.
  const p = pantalla({sug: 7, fecha: +DIA(2026, 8, 1), pasos: ['confirmar']});
  comprobar('vuelve a pedir confirmar', true, pasos(p).includes('verify'));
  comprobar('y lo avisa', true, /la diferencia cambió/.test(p.r.obs.join(' ')));
});

console.log(`\n${hechas - fallas} de ${hechas} comprobaciones pasaron`);
process.exit(fallas ? 1 : 0);
