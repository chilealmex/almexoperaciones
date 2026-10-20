/* Un navegador de mentira, lo justo para que regularizacion.js cargue fuera de
   la pantalla. No dibuja nada: sólo deja llamar al cálculo, que es lo que hay
   que poder comprobar. */
function elemento(valor = '') {
  const el = {
    value: valor, checked: false, textContent: '', innerHTML: '', hidden: false,
    style: {}, dataset: {}, files: [], options: [],
    classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
    addEventListener(){}, removeEventListener(){}, appendChild(){}, remove(){},
    setAttribute(){}, removeAttribute(){}, getAttribute(){ return null; },
    querySelector(){ return elemento(); }, querySelectorAll(){ return []; },
    closest(){ return null; }, focus(){}, click(){}, scrollIntoView(){},
    insertAdjacentHTML(){},
  };
  return el;
}

const porId = new Map();
global.document = {
  getElementById(id){
    if (!porId.has(id)) porId.set(id, elemento(id === 'optBodega' ? '*' : ''));
    return porId.get(id);
  },
  querySelector(){ return elemento(); },
  querySelectorAll(){ return []; },
  createElement(){ return elemento(); },
  addEventListener(){},
  body: elemento(),
};
global.window = {addEventListener(){}, location: {href: ''}, localStorage: {getItem(){ return null; }, setItem(){}}};
global.navigator = {clipboard: {writeText(){ return Promise.resolve(); }}};
global.fetch = () => Promise.resolve({ok: true, json: () => Promise.resolve({})});
// Lo mínimo de SheetJS que usa el módulo fuera de leer archivos: convertir el
// número de serie con que Excel guarda las fechas. Hace falta para probar lo
// que pasa cuando esa celda viene en 0, que es como llegan las filas de los
// productos que no se contaron.
global.XLSX = {
  read(){ return {SheetNames: [], Sheets: {}}; },
  utils: {},
  SSF: {
    parse_date_code(v){
      if (v == null || isNaN(v)) return null;
      const d = new Date(Math.round((Number(v) - 25569) * 86400 * 1000));
      return {y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate(), H: d.getUTCHours(), M: d.getUTCMinutes()};
    },
  },
};

module.exports = {elemento, porId};
