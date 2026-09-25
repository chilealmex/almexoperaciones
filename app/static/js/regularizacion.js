/* Regularización de inventario: cruza el conteo físico con el Informe de Documentos
   de Defontana, propone los ajustes a PMP, lista los documentos a costo $0 y
   verifica los ajustes con el informe descargado de nuevo. Todo corre en el
   navegador: los archivos de Defontana no se suben al servidor. */
(function(){
  const $ = s => document.getElementById(s);
  const EPS = 1e-9;
  const norm = v => String(v ?? '').trim().toUpperCase();
  // Clave para cruzar códigos: sin tildes, sin espacios, puntos, guiones, guiones bajos ni ceros a la izquierda
  const keyOf = v => String(v ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/[^A-Z0-9]/g, '').replace(/^0+(?=.)/, '');
  const strip = s => norm(s).normalize('NFD').replace(/[̀-ͯ]/g,'');
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const fmt = n => n == null || n === '' || isNaN(n) ? '—' : Number(n).toLocaleString('es-CL', {maximumFractionDigits: 3});
  const sgn = n => n == null ? '—' : (n > EPS ? '+' : n < -EPS ? '−' : '') + fmt(Math.abs(n));
  const money = n => n == null || isNaN(n) ? '—' : (n < -0.5 ? '−$' : '$') + Math.abs(Math.round(n)).toLocaleString('es-CL');
  const dayKey = d => d ? d.getFullYear()*10000 + (d.getMonth()+1)*100 + d.getDate() : null;
  const fmtDate = (d, t) => !d ? '' : String(d.getDate()).padStart(2,'0') + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + d.getFullYear() +
    (t ? ' ' + String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0') : '');

  // ---------- Lectura de archivos ----------
  function parseDate(v){
    if (v == null || v === '') return null;
    if (v instanceof Date) return isNaN(v) ? null : v;
    if (typeof v === 'number'){ const p = XLSX.SSF.parse_date_code(v); return p ? new Date(p.y, p.m-1, p.d, p.H, p.M) : null; }
    const s = String(v).trim();
    let m = s.match(/^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{2,4})(?:[ T,]+(\d{1,2}):(\d{2}))?/);
    if (m){ let y = +m[3]; if (y < 100) y += 2000; return new Date(y, +m[2]-1, +m[1], +(m[4]||0), +(m[5]||0)); }
    m = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
    return m ? new Date(+m[1], +m[2]-1, +m[3], +(m[4]||0), +(m[5]||0)) : null;
  }
  function num(v){
    if (typeof v === 'number') return v;
    if (v == null || v === '') return null;
    let s = String(v).trim().replace(/[\s$]/g,'');
    if (/,\d+$/.test(s)) s = s.replace(/\./g,'').replace(',', '.'); else s = s.replace(/,/g,'');
    const n = Number(s); return isNaN(n) ? null : n;
  }
  function readTable(rows, required){
    for (let i = 0; i < Math.min(rows.length, 30); i++){
      const h = rows[i].map(strip);
      if (required.every(r => h.includes(r))){
        const idx = {}; h.forEach((x, j) => { if (x && !(x in idx)) idx[x] = j; });
        const col = (...names) => { for (const n of names){ const k = strip(n); if (k in idx) return idx[k]; } return -1; };
        return {col, rows: rows.slice(i+1)};
      }
    }
    return null;
  }
  function parseStock(rows){
    const t = readTable(rows, ['CODIGO', 'STOCK FISICO']);
    if (!t) throw new Error('No encontré las columnas “Código” y “Stock físico”. ¿Es el archivo de Stock y conteo?');
    const c = {code:t.col('Código'), name:t.col('Nombre'), stock:t.col('Stock físico'), estado:t.col('Estado del conteo'),
      por:t.col('Contado por'), fecha:t.col('Fecha y hora del conteo','Fecha del conteo','Fecha'),
      um:t.col('Unidad', 'Unidad Medida', 'Unidad de medida', 'Unidad QMS', 'U. Medida', 'UM', 'Unidad Defontana'),
      linea:t.col('Línea de negocio', 'Linea de negocio', 'Linea Negocio', 'Línea', 'Linea')};
    const out = [];
    for (const r of t.rows){
      const code = String(r[c.code] ?? '').trim(); if (!code) continue;
      out.push({code, key:keyOf(code), name:r[c.name] ?? '', stock:num(r[c.stock]), estado:c.estado >= 0 ? r[c.estado] ?? '' : '',
        por:c.por >= 0 ? r[c.por] ?? '' : '', fecha:c.fecha >= 0 ? parseDate(r[c.fecha]) : null, um:c.um >= 0 ? String(r[c.um] ?? '').trim() : '', linea:c.linea >= 0 ? String(r[c.linea] ?? '').trim() : ''});
    }
    return out;
  }

  // ---------- Unidades de medida ----------
  // Mismos grupos que app/utils/unidades.py (M = MT = MTS…), más las de conversión conocida.
  const UM_GRUPOS = {
    metro:['M','MT','MTS','METRO','METROS'], pie:['FT','PIE','PIES','FEET'], pulgada:['IN','PULG','PULGADA','PULGADAS'],
    centimetro:['CM','CMS'], milimetro:['MM'], litro:['L','LT','LTS','LITRO','LITROS'], galon:['GL','GAL','GALON','GALONES'],
    kilo:['KG','KGS','KILO','KILOS','KILOGRAMO','KILOGRAMOS'], libra:['LB','LBS','LIBRA','LIBRAS'], gramo:['G','GR','GRS','GRAMO','GRAMOS'],
    unidad:['UN','UND','UNI','UD','UNIDAD','UNIDADES','CU'], par:['PAR','PARES','PR'], docena:['DOC','DOCENA','DOCENAS','DZ'], pack:['PK','PACK','PACKS'], rollo:['RL','ROLLO','ROLLOS'], caja:['CJ','CAJA','CAJAS']
  };
  const UM_NOMBRE = {metro:'metros', pie:'pies', pulgada:'pulgadas', centimetro:'centímetros', milimetro:'milímetros', litro:'litros', galon:'galones', kilo:'kilos', libra:'libras', gramo:'gramos', unidad:'unidades', par:'pares', docena:'docenas', pack:'packs', rollo:'rollos', caja:'cajas'};
  const UM_POR_FORMA = {};
  for (const [g, formas] of Object.entries(UM_GRUPOS)) for (const f of formas) UM_POR_FORMA[f] = g;
  const umGrupo = u => { const l = String(u || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase().replace(/[^A-Z0-9]/g, ''); return UM_POR_FORMA[l] || l; };
  // Factor para pasar una cantidad de la unidad "de" a la unidad "a" (1 de = factor a)
  const UM_BASE = {metro:['L', 1], pie:['L', 0.3048], pulgada:['L', 0.0254], centimetro:['L', 0.01], milimetro:['L', 0.001],
    litro:['V', 1], galon:['V', 3.78541], kilo:['P', 1], libra:['P', 0.453592], gramo:['P', 0.001],
    unidad:['C', 1], par:['C', 2], docena:['C', 12]};
  function umFactor(de, a){
    const x = UM_BASE[de], y = UM_BASE[a];
    return x && y && x[0] === y[0] ? x[1] / y[1] : null;
  }

  function parseMov(rows){
    const t = readTable(rows, ['ARTICULO', 'MOVIMIENTO']);
    if (!t) throw new Error('No encontré las columnas “Artículo” y “Movimiento”. ¿Es el Informe de Documentos de Defontana?');
    const g = t.col;
    const c = {tipo:g('Tipo Documento'), estado:g('Estado'), folio:g('Folio'), fecha:g('Fecha'), orig:g('Bod. Origen','Bodega Origen'),
      dest:g('Bod. Destino','Bodega Destino'), mov:g('Movimiento'), ref:g('Referencia'), prov:g('Proveedor'), cli:g('Cliente'),
      art:g('Artículo'), desc:g('Descripción'), cant:g('Cant. Movimiento','Cantidad'), um:g('U. Medida'), valor:g('Valor Movimiento'),
      saldo:g('Saldo Inventario'), valorInv:g('Valor Inventario')};
    if (c.cant < 0 || c.fecha < 0) throw new Error('No encontré las columnas “Fecha” y “Cant. Movimiento”.');
    const at = (r, k) => c[k] >= 0 ? (r[c[k]] ?? '') : '';
    const out = [];
    t.rows.forEach((r, i) => {
      const art = String(at(r,'art')).trim(); if (!art) return;
      const mv = strip(at(r,'mov'));
      const kind = mv.startsWith('ING') ? 'in' : mv.startsWith('EGR') ? 'out' : null;
      if (!kind) return;
      out.push({i, art, key:keyOf(art), kind, qty:Math.abs(num(at(r,'cant')) || 0), fecha:parseDate(at(r,'fecha')),
        tipo:at(r,'tipo'), estado:at(r,'estado'), folio:at(r,'folio'), orig:String(at(r,'orig')).trim(), dest:String(at(r,'dest')).trim(),
        ref:at(r,'ref') || at(r,'cli') || at(r,'prov'), desc:at(r,'desc'), nameKey:keyOf(at(r,'desc')), um:at(r,'um'),
        valor:c.valor >= 0 ? num(at(r,'valor')) : null, saldo:num(at(r,'saldo')), valorInv:c.valorInv >= 0 ? num(at(r,'valorInv')) : null});
    });
    out.sort((a,b) => (a.fecha||0) - (b.fecha||0) || a.i - b.i);
    return out;
  }

  // ---------- Recuentos hechos hoy (se guardan en este navegador) ----------
  function leerRecuentos(){
    try {
      const raw = JSON.parse(localStorage.getItem('regx-recuentos') || '{}');
      return new Map(Object.entries(raw).map(([k, v]) => [k, {qty: v.qty, fecha: new Date(v.fecha)}]));
    } catch(_){ return new Map(); }
  }
  function guardarRecuentos(){
    try { localStorage.setItem('regx-recuentos', JSON.stringify(Object.fromEntries([...state.recount].map(([k, v]) => [k, {qty: v.qty, fecha: +v.fecha}])))); } catch(_){}
  }

  // Excel de recuentos: una fila por producto con el código y la cantidad contada hoy
  function parseRecount(rows){
    for (let i = 0; i < Math.min(rows.length, 30); i++){
      const h = rows[i].map(strip);
      const ci = h.findIndex(x => ['CODIGO', 'ARTICULO', 'COD ARTICULO', 'CODIGO ARTICULO'].includes(x));
      const qi = h.findIndex(x => ['FISICO', 'STOCK FISICO', 'CANTIDAD', 'RECUENTO', 'CONTADO', 'CANTIDAD FISICA'].includes(x));
      if (ci < 0 || qi < 0) continue;
      const fi = h.findIndex(x => ['FECHA', 'FECHA Y HORA DEL CONTEO', 'FECHA DEL CONTEO'].includes(x));
      const out = [];
      for (const r of rows.slice(i + 1)){
        const code = String(r[ci] ?? '').trim(), q = num(r[qi]);
        if (!code || q == null) continue;
        out.push({key: keyOf(code), qty: q, fecha: (fi >= 0 && parseDate(r[fi])) || new Date()});
      }
      return out;
    }
    throw new Error('No encontré las columnas del código (Código o Artículo) y de la cantidad (Físico o Cantidad).');
  }

  // ---------- Conteo del sistema ----------
  // La página trae el conteo de "Stock y conteo" como JSON: [código, nombre, stock físico, estado, contado por, fecha y hora]
  function conteoDelSistema(){
    const el = document.getElementById('regx-conteo');
    let data = [];
    try { data = JSON.parse(el ? el.textContent : '[]'); } catch(_){ data = []; }
    return data.map(([code, name, stock, estado, por, fecha, um, linea]) => ({code, key:keyOf(code), name, stock, estado, por, fecha:parseDate(fecha), um: um || '', linea: linea || ''}));
  }

  // ---------- Estado ----------
  const state = {stock:conteoDelSistema(), mov:[], view:'reg', filter:{reg:'all', zero:'all', check:'all'}, mov2:null, ajSel:null, checkRows:[], docGroups:[],
    sort:{reg:{k:'code', d:1}, zero:{k:'fecha', d:1}, check:{k:'code', d:1}}, open:new Set(), pmpEdit:new Map(), recount:leerRecuentos(), rows:[], zero:[]};

  function fillBodegas(){
    const sel = $('optBodega'), prev = sel.value, count = new Map();
    for (const m of state.mov){ const b = m.kind === 'in' ? m.dest : m.orig; if (b) count.set(b, (count.get(b)||0) + 1); }
    const list = [...count.entries()].sort((a,b) => b[1]-a[1]).map(x => x[0]);
    sel.innerHTML = '<option value="*">Todas las bodegas</option>' + list.map(b => `<option value="${esc(b)}">${esc(b)}</option>`).join('');
    sel.value = list.includes(prev) ? prev : (list.find(b => /CENTRAL/i.test(b)) || '*');
  }

  // PMP: último Valor Inventario / Saldo Inventario con ambos > 0; si no hay, costo unitario del último documento con valor.
  function pmpOf(list, upto){
    const lim = upto == null ? list.length - 1 : upto;
    for (let j = lim; j >= 0; j--){ const m = list[j]; if (m.saldo > EPS && m.valorInv > EPS) return {v:m.valorInv / m.saldo, src:'PMP Defontana al ' + fmtDate(m.fecha)}; }
    for (let j = lim; j >= 0; j--){ const m = list[j]; if (m.qty > EPS && m.valor > EPS) return {v:m.valor / m.qty, src:'Costo doc. del ' + fmtDate(m.fecha)}; }
    for (let j = lim + 1; j < list.length; j++){
      const m = list[j];
      if (m.saldo > EPS && m.valorInv > EPS) return {v:m.valorInv / m.saldo, src:'PMP Defontana al ' + fmtDate(m.fecha)};
      if (m.qty > EPS && m.valor > EPS) return {v:m.valor / m.qty, src:'Costo doc. del ' + fmtDate(m.fecha)};
    }
    return null;
  }

  // ---------- Causa probable del descuadre ----------
  const CAUSES = {
    late:      'Documento registrado después del conteo',
    sameday:   'Movimiento del mismo día del conteo',
    dupin:     'Posible ingreso duplicado',
    notfound:  'No se encontró en bodega',
    ingnorec:  'Ingreso registrado que no está en bodega',
    neg:       'Salidas sin ingreso previo',
    egrnodesp: 'Salida registrada que sigue en bodega',
    um:        'Posible otra unidad de medida',
    noin:      'Falta registrar un ingreso',
    noout:     'Falta registrar una salida'
  };
  const near = (a, b) => Math.abs(a - b) < 1e-6;
  const docTxt = m => `${m.tipo} #${m.folio} del ${fmtDate(m.fecha)} por ${fmt(m.qty)}`;
  function diagnose(s, docs, after, diff, sys, sameNet, zeros){
    if (diff == null || Math.abs(diff) <= EPS) return {cause:null, obs:[]};
    const ad = Math.abs(diff), obs = [];
    const pre = docs.filter(m => m.fecha && !after(m)), post = docs.filter(m => m.fecha && after(m));
    let cause = null;
    // 1. La diferencia la explica un documento registrado después del conteo
    const kindPost = diff > 0 ? 'in' : 'out';
    const postK = post.filter(m => m.kind === kindPost);
    const one = postK.find(m => near(m.qty, ad)), postSum = postK.reduce((a, m) => a + m.qty, 0);
    if (one){
      cause = 'late';
      obs.push(diff > 0 ? `El ingreso ${docTxt(one)} se registró después del conteo, pero la mercadería ya estaba en bodega al contar. Si fue así, no hay que ajustar: Defontana ya quedó bien.`
                        : `La salida ${docTxt(one)} se registró después del conteo, pero la mercadería ya había salido al contar. Si fue así, no hay que ajustar: Defontana ya quedó bien.`);
    } else if (postK.length > 1 && near(postSum, ad)){
      cause = 'late';
      obs.push(`Los ${diff > 0 ? 'ingresos' : 'egresos'} registrados después del conteo suman ${fmt(postSum)}, igual a la diferencia: probablemente ya ${diff > 0 ? 'estaban en bodega' : 'habían salido'} al contar. Si fue así, no hay que ajustar.`);
    } else if (Math.abs(sameNet) > EPS && near(diff, -sameNet)){
      // 2. La explican los documentos del mismo día
      cause = 'sameday';
      obs.push(`La diferencia es igual a los documentos del mismo día del conteo (${sgn(sameNet)}): probablemente se contó antes de ese movimiento. Si fue así, no hay que ajustar.`);
    } else if (diff < 0){
      const ins = pre.filter(m => m.kind === 'in');
      const dup = ins.find(m => near(m.qty, ad) && ins.some(o => o !== m && near(o.qty, m.qty) && dayKey(o.fecha) === dayKey(m.fecha)));
      const ing = ins.filter(m => near(m.qty, ad));
      if (dup){ cause = 'dupin'; obs.push(`Hay dos ingresos del ${fmtDate(dup.fecha)} por ${fmt(dup.qty)} cada uno, y eso es justo lo que falta: posible ingreso registrado dos veces.`); }
      else if (Math.abs(s.stock) <= EPS && sys > EPS){ cause = 'notfound'; obs.push(`No se encontró nada en bodega y Defontana tenía ${fmt(sys)}. Revisar otras ubicaciones, préstamos a obra o salidas sin documento.`); }
      else if (ing.length){ const m = ing[ing.length - 1]; cause = 'ingnorec'; obs.push(`Lo que falta es igual al ingreso ${docTxt(m)}: puede que no haya llegado completo, esté guardado en otra ubicación o se haya ingresado de más.`); }
    } else {
      if (sys < -EPS){ cause = 'neg'; obs.push(`Defontana tenía saldo negativo (${fmt(sys)}) al contar: se registraron salidas sin haber ingresado el producto. Falta registrar el ingreso (compra, importación o devolución).`); }
      else {
        const eg = pre.filter(m => m.kind === 'out' && near(m.qty, ad));
        if (eg.length){ const m = eg[eg.length - 1]; cause = 'egrnodesp'; obs.push(`Lo que sobra es igual a la salida ${docTxt(m)}: puede que no se haya despachado o que haya vuelto sin registrar la devolución.`); }
      }
    }
    // 3. Unidad de medida: múltiplos exactos (caja, paquete) o conversiones conocidas (pies, pulgadas, libras).
    // Una conversión que calza pesa más que las demás explicaciones, salvo las de fecha de documento.
    // Si el conteo trae su unidad y es la misma de Defontana, no se supone ninguna conversión.
    // Si el conteo declara su unidad, las diferencias de unidad ya se trataron (conversión explícita).
    if (!s.um && cause !== 'late' && cause !== 'sameday' && s.stock > EPS && sys > EPS){
      const um = docs.length ? String(docs[docs.length - 1].um || '').toUpperCase() : '';
      const r = s.stock / sys;
      // Solo se prueba la conversión que corresponde a la unidad del producto en Defontana
      const en = (...u) => u.map(umGrupo).includes(umGrupo(um));
      const conv = [
        {f:1 / 3.2808, ok: en('FT', 'PIE', 'PIES'), txt:'metros y Defontana lo tiene en pies'},
        {f:3.2808, ok: en('M', 'MT', 'MTS', 'METRO', 'METROS'), txt:'pies y Defontana lo tiene en metros'},
        {f:2.54, ok: en('IN', 'PULG', 'PULGADA', 'PULGADAS'), txt:'centímetros y Defontana lo tiene en pulgadas'},
        {f:1 / 2.54, ok: en('CM'), txt:'pulgadas y Defontana lo tiene en centímetros'},
        {f:0.4536, ok: en('LB', 'LBS', 'LIBRA', 'LIBRAS'), txt:'kilos y Defontana lo tiene en libras'},
        {f:1 / 0.4536, ok: en('KG', 'KGS', 'KILO', 'KILOS'), txt:'libras y Defontana lo tiene en kilos'}
      ].find(c => c.ok && Math.abs(r / c.f - 1) <= 0.03);
      const f = [10, 12, 20, 24, 25, 50, 100, 1000].find(x => near(r, x) || near(1 / r, x));
      if (conv){
        cause = 'um'; obs.length = 0;
        const factor = sys / s.stock;
        obs.push(`Parece que se contó en ${conv.txt}${um ? ' (' + esc(um) + ')' : ''}: ${fmt(s.stock)} equivale a unos ${fmt(Math.round(s.stock * factor * 10) / 10)} en la unidad de Defontana, casi lo mismo que tiene (${fmt(sys)}). Convierte antes de ajustar.`);
      } else if (f && !cause){
        cause = 'um';
        obs.push(`Lo contado es ${near(r, f) ? f + ' veces' : '1/' + f + ' de'} lo que tiene Defontana${um ? ' (en ' + esc(um) + ')' : ''}: posible conteo en otra unidad (caja, paquete, rollo, metro).`);
      }
    }
    // 4. Genérico
    if (!cause){
      if (diff > 0){ cause = 'noin'; obs.push(`Hay ${fmt(ad)} más en bodega que en Defontana: falta registrar un ingreso (compra, devolución de OT o de cliente) o se registró una salida de más.`); }
      else {
        cause = 'noout';
        const outs = pre.filter(m => m.kind === 'out'), freq = new Map();
        outs.forEach(m => freq.set(m.tipo, (freq.get(m.tipo) || 0) + 1));
        const top = [...freq.entries()].sort((a, b) => b[1] - a[1])[0];
        obs.push(`Faltan ${fmt(ad)} en bodega: falta registrar una salida (consumo en OT, venta, merma) o se registró un ingreso de más.` + (top ? ` Sus salidas suelen ser “${top[0]}”.` : ''));
      }
    }
    // Notas de apoyo
    const lastIn = [...pre].reverse().find(m => m.kind === 'in'), lastOut = [...pre].reverse().find(m => m.kind === 'out');
    if (lastIn) obs.push('Último ingreso antes del conteo: ' + docTxt(lastIn) + '.');
    if (lastOut) obs.push('Última salida antes del conteo: ' + docTxt(lastOut) + '.');
    if (!pre.length && docs.length) obs.push('No tenía documentos antes del conteo; el saldo al conteo se calculó hacia atrás desde el primer documento.');
    if (zeros) obs.push(zeros + (zeros === 1 ? ' documento' : ' documentos') + ' a costo $0.');
    if (s.nCounted > 1) obs.push('Se contó en ' + s.nCounted + ' códigos distintos y se sumaron.');
    return {cause, obs};
  }

  function compute(movList){
    const bod = $('optBodega').value, sameAfter = $('optSame').value === 'after', onlyAprob = $('optAprob').checked;
    // El mismo código puede venir escrito de varias formas: se agrupa por la clave normalizada
    const groups = new Map();
    for (const s of state.stock){ if (!groups.has(s.key)) groups.set(s.key, []); groups.get(s.key).push(s); }
    // Si un artículo de Defontana no cruza por código, se intenta por nombre (solo si el nombre es único)
    const byName = new Map();
    for (const s of state.stock){ const nk = keyOf(s.name); if (nk.length < 6) continue; byName.set(nk, byName.has(nk) && byName.get(nk) !== s.key ? null : s.key); }
    const byKey = new Map();
    for (const m of movList){
      if (onlyAprob && m.estado && !/aprob/i.test(m.estado)) continue;
      m._k = m.key; m._byName = false;
      if (!groups.has(m.key) && byName.get(m.nameKey)){ m._k = byName.get(m.nameKey); m._byName = true; }
      if (!byKey.has(m._k)) byKey.set(m._k, []);
      byKey.get(m._k).push(m);
    }
    const mergeGroup = list => {
      const done = list.filter(x => x.stock != null && x.fecha != null);
      const main = done[0] || list[0];
      const g = {code:main.code, key:main.key, name:main.name, por:main.por, estado:main.estado, um:main.um || '', linea:(list.find(x => x.linea) || main).linea || '',
        stock: done.length ? done.reduce((a, x) => a + x.stock, 0) : null,
        fecha: done.length ? new Date(Math.max(...done.map(x => +x.fecha))) : null,
        variants: list.map(x => x.code), nCounted: done.length};
      // Un recuento ingresado en la tabla reemplaza al conteo original
      const rc = state.recount.get(main.key);
      if (rc){ g.original = {stock: g.stock, fecha: g.fecha}; g.stock = rc.qty; g.fecha = rc.fecha; g.por = 'Recuento'; g.recontado = true; g.nCounted = Math.max(1, g.nCounted); }
      return g;
    };
    const inBod = m => bod === '*' || (m.kind === 'in' ? m.dest : m.orig) === bod;
    const build = (s, docs) => {
      // Si el conteo está en otra unidad que Defontana, se convierte cuando la conversión es conocida
      // Lo contado (y su unidad) es la referencia. Si Defontana lleva el producto en otra unidad,
      // antes de cruzar se pasan sus cantidades (saldos y movimientos) a la unidad del conteo.
      let umInfo = null;
      const umDef = docs.length ? umGrupo(docs[docs.length - 1].um) : '';
      if (s && s.stock != null && s.um && umDef && umGrupo(s.um) !== umDef){
        const f = umFactor(umDef, umGrupo(s.um));   // 1 unidad de Defontana = f unidades del conteo
        umInfo = {de: s.um, a: docs[docs.length - 1].um, f};
        if (f) docs = docs.map(m => ({...m, qty: m.qty * f, saldo: m.saldo != null ? m.saldo * f : null}));
      }
      const counted = !!s && s.stock != null && s.fecha != null;
      const ck = counted ? dayKey(s.fecha) : null;
      const after = m => { const dk = dayKey(m.fecha); return dk > ck || (dk === ck && sameAfter); };
      let ins = 0, outs = 0, sameDay = 0, sameNet = 0, idx = null, aj = 0, ajVal = 0;
      const ajDocs = docs.filter(m => m._aj);
      for (const m of ajDocs){ aj += m.kind === 'in' ? m.qty : -m.qty; ajVal += (m.kind === 'in' ? 1 : -1) * (m.valor || 0); }
      docs.forEach((m, j) => {
        if (!counted || !m.fecha) return;
        if (after(m)){ if (!m._aj && inBod(m)){ if (m.kind === 'in') ins += m.qty; else outs += m.qty; } }
        else { idx = j; if (dayKey(m.fecha) === ck){ sameDay++; sameNet += m.kind === 'in' ? m.qty : -m.qty; } }
      });
      // Defontana lleva un saldo por cada artículo: si el código existe escrito de varias formas, se suman
      const byArt = new Map();
      for (const m of docs){ const a = norm(m.art); if (!byArt.has(a)) byArt.set(a, []); byArt.get(a).push(m); }
      // El saldo de cada fila del informe depende del orden en que Defontana procesó los documentos, que
      // puede no ser el orden de las filas cuando hay varios el mismo día. Por eso se toma como saldo
      // inicial el valor que más se repite de (saldo de la fila − movimientos acumulados hasta ella) y
      // los saldos al conteo y final se calculan sumando los documentos.
      const signed = m => m.kind === 'in' ? m.qty : -m.qty;
      let sysNow = null, sysAtCount = null, sysCalc = null, toOther = 0;
      for (const list of byArt.values()){
        let cum = 0; const votes = new Map();
        for (const m of list){ cum += signed(m); if (m.saldo != null){ const v = Math.round((m.saldo - cum) * 1e6) / 1e6; votes.set(v, (votes.get(v) || 0) + 1); } }
        if (!votes.size) continue;
        let init = null, best = 0;
        for (const [v, n] of votes) if (n > best){ init = v; best = n; }
        const last = list[list.length - 1];
        if (last.saldo != null) sysNow = (sysNow || 0) + last.saldo;
        sysCalc = (sysCalc || 0) + init + cum;
        if (counted) sysAtCount = (sysAtCount || 0) + init + list.filter(m => m.fecha && !after(m)).reduce((a, m) => a + signed(m), 0);
      }
      if (counted) for (const m of docs) if (m.fecha && after(m) && !m._aj && !inBod(m) && m.kind === 'in') toOther += m.qty;
      const own = s ? new Set(s.variants.map(norm)) : new Set();
      const alias = [...(s ? s.variants.filter(v => norm(v) !== norm(s.code)) : []), ...[...byArt.keys()].filter(a => !own.has(a) && (s || a !== norm(docs[0].art)))];
      const viaName = docs.some(m => m._byName);
      const realNow = counted ? s.stock + ins - outs : null;
      const diff = counted && sysAtCount != null ? s.stock - sysAtCount : null;
      const key = s ? s.key : docs[0].key;
      const pm = docs.length ? pmpOf(docs, idx) : null;
      const edited = state.pmpEdit.has(key);
      const pmp = edited ? state.pmpEdit.get(key) : pm ? pm.v : null;
      let st;
      if (!s) st = 'nofile';
      else if (!counted) st = 'nocount';
      else if (diff == null) st = 'nodata';
      else st = diff > EPS ? 'up' : diff < -EPS ? 'down' : 'ok';
      const zeros = docs.filter(m => m.valor != null && Math.abs(m.valor) < EPS && m.qty > EPS).length;
      const cost = costReview(docs, sysCalc);
      const dx = counted ? diagnose(s, docs.filter(m => !m._aj), after, diff, sysAtCount, sameNet, zeros) : {cause:null, obs:[]};
      if (counted && umInfo && sysAtCount != null){
        const de = esc(umInfo.de), a = esc(umInfo.a), hoy = sysCalc ?? sysNow;
        if (umInfo.f){
          umInfo.hoyDef = hoy != null ? Math.round(hoy / umInfo.f * 1000) / 1000 : null;
          umInfo.hoyConv = hoy != null ? Math.round(hoy * 1000) / 1000 : null;
          dx.obs.push(`Defontana lleva este producto en ${a} y se contó en ${de}: sus cantidades se pasaron a ${de} (1 ${a} = ${fmt(Math.round(umInfo.f * 10000) / 10000)} ${de}) antes de cruzar. Primero cambia la unidad en Defontana: su saldo de ${fmt(umInfo.hoyDef)} ${a} queda en ${fmt(umInfo.hoyConv)} ${de}.`);
        } else {
          dx.cause = 'um'; dx.umMaster = true;
          dx.obs.unshift(`Se contó en ${de}, pero en Defontana el producto está en ${a} y no hay una conversión conocida entre esas unidades: se compararon las cifras tal cual. Corrige la unidad en el maestro de Defontana y confirma en qué unidad se registraron sus movimientos antes de ajustar.`);
        }
      }
      if (dx.cause === 'late' || dx.cause === 'sameday' || dx.cause === 'um') st = 'check';
      return {cause:dx.cause, obs:dx.obs, umRound: !!dx.umRound, umMaster: !!dx.umMaster, linea: s ? s.linea || '' : '', alias, viaName, nCounted: s ? s.nCounted : 0, key, code: s ? s.code : docs[0].art, name: s ? s.name : docs[0].desc, s, umInfo, counted, docs, ins, outs, sameDay, aj, ajVal, ajDocs, sysCalc, toOther,
        sysAtCount, sysNow, realNow, diff, st, pmp, edited, pmpSrc: edited ? 'Ingresado a mano' : pm ? pm.src : 'Sin costo en Defontana',
        valor: diff != null && Math.abs(diff) > EPS && pmp != null ? diff * pmp : (st === 'ok' ? 0 : null), zeros, cost};
    };
    const seen = new Set();
    const rows = [...groups.values()].map(list => { const s = mergeGroup(list); seen.add(s.key); return build(s, byKey.get(s.key) || []); });
    for (const [k, docs] of byKey) if (!seen.has(k) && docs.some(inBod)) rows.push(build(null, docs));

    const names = new Map(rows.map(r => [r.key, r.name])), lineas = new Map(rows.map(r => [r.key, r.linea]));
    const zero = [];
    for (const [k, docs] of byKey) docs.forEach((m, j) => {
      if (!inBod(m) || m.valor == null || Math.abs(m.valor) > EPS || m.qty <= EPS) return;
      const pm = pmpOf(docs, j - 1 >= 0 ? j - 1 : null);
      const edited = state.pmpEdit.has(k);
      const pmp = edited ? state.pmpEdit.get(k) : pm ? pm.v : null;
      zero.push({key:k, m, code:m.art, name:m.desc || names.get(k) || '', linea: lineas.get(k) || '', pmp, edited,
        pmpSrc: edited ? 'Ingresado a mano' : pm ? pm.src : 'Sin costo en Defontana', valor: pmp != null ? pmp * m.qty : null,
        rev: zeroReview(m, docs, j, pmp)});
    });
    return {rows, zero, orphan: [...byKey.keys()].filter(k => !seen.has(k)).length};
  }

  // ---------- Costo: productos que entraron o salieron a $0 ----------
  const pmpAt = m => m && m.saldo > EPS && m.valorInv != null ? m.valorInv / m.saldo : null;
  // Costo unitario para corregir un documento a $0: el de la compra con costo más cercana (la última
  // anterior; si no hay, la primera posterior); si no hay compras con costo, el PMP que tenía antes.
  function refCost(docs, j){
    const costed = [];
    docs.forEach((m, i) => { if (m.kind === 'in' && m.valor > EPS && m.qty > EPS) costed.push([m, i]); });
    const src = (m, extra) => `costo de ${m.tipo} #${m.folio} del ${fmtDate(m.fecha)}${extra}`;
    let prev = null;
    for (const c of costed) if (c[1] < j) prev = c;
    if (prev) return {v: prev[0].valor / prev[0].qty, src: src(prev[0], '')};
    const next = costed.find(c => c[1] > j);
    if (next) return {v: next[0].valor / next[0].qty, src: src(next[0], ' (posterior)')};
    const p = pmpAt(docs[j - 1]);
    return p > EPS ? {v: p, src: 'PMP que tenía antes'} : null;
  }
  // Valor y PMP que tendría hoy el producto si los ingresos a $0 se hubieran registrado con su costo.
  // Se recalcula el promedio ponderado documento por documento, con las salidas al PMP de cada momento.
  function correctedToday(docs){
    const f = docs[0];
    if (!f || f.saldo == null || f.valorInv == null) return null;
    let cambio = false;
    const run = corregir => {
      let saldo = f.saldo - (f.kind === 'in' ? f.qty : -f.qty);
      let valor = f.valorInv - (f.kind === 'in' ? 1 : -1) * (f.valor || 0);
      docs.forEach((m, j) => {
        if (m.kind === 'in'){
          let v = m.valor || 0;
          if (corregir && Math.abs(v) < EPS && m.qty > EPS){ const r = refCost(docs, j); if (r){ v = r.v * m.qty; cambio = true; } }
          valor += v; saldo += m.qty;
        } else {
          valor -= (saldo > EPS ? valor / saldo : 0) * m.qty; saldo -= m.qty;
        }
      });
      return {saldo, valor};
    };
    const bien = run(true), asi = run(false);
    if (!cambio || bien.saldo <= EPS) return null;
    // el ajuste es lo que le falta al valor del inventario de hoy por haber entrado a $0
    return {pmp: bien.valor / bien.saldo, ajuste: bien.valor - asi.valor};
  }

  // ¿Hay que revisar el costo de este producto? Mira sus documentos a $0 y cómo está hoy.
  function costReview(docs, saldoHoy){
    const zeros = docs.filter(m => m.valor != null && Math.abs(m.valor) < EPS && m.qty > EPS);
    const last = docs[docs.length - 1];
    const pmpHoy = pmpAt(last);
    const sinCostoHoy = saldoHoy > EPS && last && last.valorInv != null && last.valorInv <= EPS;
    const ins0 = zeros.filter(m => m.kind === 'in');
    const outsSinStock = zeros.filter(m => m.kind === 'out' && m.saldo != null && m.saldo + m.qty <= EPS);
    if (!zeros.length && !sinCostoHoy) return null;
    const txt = [], hacer = [];
    if (sinCostoHoy){ txt.push(`Hoy tiene ${fmt(saldoHoy)} sin costo en Defontana (PMP $0).`); hacer.push({k:'cost', txt:`Ajuste de valor: cargar el costo a las ${fmt(saldoHoy)} unidades`}); }
    const costos = [];
    for (const m of ins0){
      const i = docs.indexOf(m), antes = pmpAt(docs[i - 1]), despues = pmpAt(m), r = refCost(docs, i);
      txt.push(`Entró ${fmt(m.qty)} a $0 con ${m.tipo} #${m.folio} del ${fmtDate(m.fecha)}` + (antes > EPS && despues != null ? `: el PMP bajó de ${money(antes)} a ${money(despues)}.` : '.'));
      costos.push({doc: `${m.tipo} #${m.folio}`, qty: m.qty, v: r ? r.v : null, src: r ? r.src : 'no hay compras con costo en el informe: usa el costo de la factura'});
      hacer.push({k:'cost', txt: r ? `Corregir el costo de ${m.tipo} #${m.folio}: ${fmt(m.qty)} a ${money(r.v)} c/u` : `Corregir el costo de ${m.tipo} #${m.folio} con el valor de la factura`});
    }
    for (const m of outsSinStock){
      const i = docs.indexOf(m), r = refCost(docs, i);
      costos.push({doc: `entrada por ${m.tipo} #${m.folio}`, qty: m.qty, v: r ? r.v : null, src: r ? r.src : 'no hay compras con costo en el informe: usa el costo de la factura'});
    }
    if (outsSinStock.length){ const r = refCost(docs, docs.indexOf(outsSinStock[0])); txt.push(`Salió ${fmt(outsSinStock.reduce((a, m) => a + m.qty, 0))} sin tener stock (${outsSinStock.map(m => m.tipo + ' #' + m.folio).join(', ')}): faltó registrar el ingreso con su costo.`); hacer.push({k:'in', txt:`Parte de Entrada por ${fmt(outsSinStock.reduce((a, m) => a + m.qty, 0))} (lo que salió sin stock)` + (r ? ` a ${money(r.v)} c/u` : ' con el costo de la factura')}); }
    const corr = ins0.length ? correctedToday(docs) : null;
    if (corr && Math.abs(corr.ajuste) > 0.5) hacer.push({k:'cost', txt:`Si no se puede corregir el ingreso: ajuste de valor por ${money(corr.ajuste)} (el PMP queda en ${money(corr.pmp)})`});
    if (sinCostoHoy && !ins0.length){ const r = refCost(docs, docs.length); costos.push({doc: 'stock actual', qty: saldoHoy, v: r ? r.v : null, src: r ? r.src : 'no hay compras con costo en el informe: usa el costo de la factura'}); }
    const need = sinCostoHoy || ins0.length > 0 || outsSinStock.length > 0;
    if (!need) txt.push(`Tuvo salidas a $0, pero hoy ya tiene costo (PMP ${money(pmpHoy)}). No hace falta corregir.`);
    return {need, txt, hacer, costos, corr};
  }
  function zeroReview(m, docs, j, pmp){
    const antes = pmpAt(docs[j - 1]), r = refCost(docs, j);
    const costo = r ? {v: r.v, src: r.src} : null;
    if (m.kind === 'in'){
      const corr = correctedToday(docs);
      const extra = corr && Math.abs(corr.ajuste) > 0.5 ? ` Si no se puede corregir: ajuste de valor por ${money(corr.ajuste)} (PMP queda en ${money(corr.pmp)})` : '';
      return antes > EPS
        ? {need:true, costo, corr, txt:`Sí. Entró a $0 y el PMP bajó de ${money(antes)} a ${money(pmpAt(m))}.`, hacer: (r ? `Corregir el costo del ingreso a ${money(r.v)} c/u (${money(r.v * m.qty)} en total).` : 'Corregir el costo del ingreso con la factura.') + extra}
        : {need:true, costo, corr, txt:'Sí. El producto entró sin costo y no tenía costo antes.', hacer: (r ? `Corregir el costo del ingreso a ${money(r.v)} c/u (${money(r.v * m.qty)} en total).` : 'Cargar el costo real (factura o importación).') + extra};
    }
    if (m.saldo != null && m.saldo + m.qty <= EPS) return {need:true, costo, txt:'Sí. Salió sin tener stock en Defontana: faltó registrar el ingreso.', hacer: r ? `Parte de Entrada por ${fmt(m.qty)} a ${money(r.v)} c/u` : 'Parte de Entrada con el costo de la factura'};
    const hoy = pmpAt(docs[docs.length - 1]);
    return hoy > EPS
      ? {need:false, txt:`No. Salió a $0 porque en ese momento no tenía costo, pero hoy su PMP es ${money(hoy)}.`, hacer:'Nada (solo la salida quedó sin costo)'}
      : {need:true, costo, txt:'Sí. Salió a $0 porque el producto no tiene costo (PMP $0).', hacer: r ? `Ajuste de valor: cargar el costo del producto a ${money(r.v)} c/u` : 'Ajuste de valor: cargar el costo del producto con la factura'};
  }

  // ---------- Qué hacer, en orden ----------
  // Orden recomendado: 1) confirmar lo dudoso, 2) corregir costos, 3) entradas, 4) salidas.
  // Los costos van primero porque Defontana valoriza cada entrada y salida al PMP del momento:
  // si se hace la salida con el PMP malo, la merma queda mal valorizada. Las entradas van antes
  // que las salidas para que el saldo nunca quede negativo y las salidas salgan con costo.
  const STEP = {
    verify:{n:1, label:'Confirmar', cls:'k-verify'}, unit:{n:1.5, label:'Unidad', cls:'k-verify'}, cost:{n:2, label:'Costo', cls:'k-cost'},
    in:{n:3, label:'Entrada', cls:'k-in'}, out:{n:4, label:'Salida', cls:'k-out'}, none:{n:9, label:'—', cls:'k-none'}
  };
  function docSteps(r){
    if (r._steps) return r._steps;
    const d = r.diff, q = d != null ? fmt(Math.abs(d)) : '', steps = [];
    const add = (k, txt) => steps.push({k, txt});
    if (r.umInfo && r.umInfo.f && r.counted) add('unit', `Cambiar la unidad en Defontana de ${r.umInfo.a} a ${r.umInfo.de}: el saldo de ${fmt(r.umInfo.hoyDef)} ${r.umInfo.a} queda en ${fmt(r.umInfo.hoyConv)} ${r.umInfo.de}`);
    if (r.umMaster) add('verify', `Corregir la unidad en el maestro de Defontana (${r.umInfo.a} → ${r.umInfo.de}) y confirmar en qué unidad están sus cantidades antes de ajustar`);
    else if (r.umRound) add('none', 'Nada: la diferencia es solo el redondeo al convertir la unidad del conteo');
    else if (r.cause === 'um') add('verify', 'Revisar la unidad de medida: el conteo parece estar en otra unidad. Convertir y recién después ajustar');
    else if (r.st === 'check') add('verify', 'Volver a contar: la diferencia puede deberse a un documento registrado después del conteo. Si se confirma, no ajustar');
    if (r.st === 'nodata') add('verify', 'Ver el saldo del producto en Defontana (no hay documentos en el informe)');
    if (r.st === 'nocount') add('verify', 'Contar el producto');
    if (r.st === 'nofile') add('verify', 'Revisar por qué no está en el conteo');
    if (r.cost && r.cost.need) r.cost.hacer.forEach(h => add(h.k, h.txt));
    if (r.st === 'up' && r.cause !== 'um'){
      if (r.cause === 'egrnodesp') add('in', `Parte de Entrada por ${q} (devolución), o anular la salida que no se despachó`);
      else add('in', `Parte de Entrada por ${q}` + (r.pmp > 0 ? ` a ${money(r.pmp)} c/u` : ' (poner costo)'));
    }
    if (r.st === 'down' && r.cause !== 'um'){
      if (r.cause === 'dupin') add('out', `Anular el ingreso duplicado, o Parte de Salida por ${q}`);
      else add('out', `Parte de Salida por ${q} (ajuste / merma)`);
    }
    if (!steps.length) add('none', 'Nada que hacer');
    steps.sort((x, y) => STEP[x.k].n - STEP[y.k].n);
    r._steps = steps;
    return steps;
  }
  const docToMake = r => docSteps(r).map(x => x.txt);
  const stepsCell = steps => `<ol class="steps">${steps.map(x => `<li><span class="stepk ${STEP[x.k].cls}">${STEP[x.k].label}</span> ${esc(x.txt)}</li>`).join('')}</ol>`;
  const stepsText = r => docSteps(r).map((x, i) => `${i + 1}. ${STEP[x.k].label}: ${x.txt}`).join(' · ');
  function checkToMake(r){
    const g = r.gap, q = g != null ? fmt(Math.abs(g)) : '';
    if (r.ck === 'ok') return ['Ninguno'];
    if (r.ck === 'double') return [`Volver a contar; si hay ${fmt(Math.abs(r.diff))} más, Parte de ${r.diff < 0 ? 'Entrada' : 'Salida'} por ${fmt(Math.abs(r.diff))} para reversar`];
    if (r.ck === 'review') return ['Volver a contar para decidir'];
    if (r.ck === 'other') return ['Revisar el ajuste'];
    return [g > 0 ? `Parte de Salida por ${q}` : `Parte de Entrada por ${q}`];
  }
  function costCell(r){
    if (!r.cost || !r.cost.need || !r.cost.costos.length) return '<span class="mut">—</span>';
    const items = r.cost.costos.map(c => `<div>${c.v != null ? '<b>' + money(c.v) + '</b> <span class="small">c/u</span>' : '<span class="small">costo de la factura</span>'}<div class="small wrapsmall">${esc(c.doc)} · ${esc(c.src)}</div></div>`).join('');
    const corr = r.cost.corr ? `<div class="small wrapsmall">PMP correcto hoy: <b>${money(r.cost.corr.pmp)}</b></div>` : '';
    return items + corr;
  }
  // Saldo de Defontana hoy (todos los documentos del informe) y lo que falta para llegar al stock real
  const hoyDe = r => r.sysCalc ?? r.sysNow;
  const ajusteHoy = r => r.counted && r.realNow != null && hoyDe(r) != null ? r.realNow - hoyDe(r) : null;
  const makeCell = list => list.length ? `<ul class="make">${list.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '';

  // ---------- Verificar ajustes ----------
  const docId = m => [strip(m.tipo), m.folio, dayKey(m.fecha)].join('|');
  function computeCheck(){
    state.checkRows = []; state.docGroups = [];
    if (!state.mov2) return;
    state.mov2.forEach(m => { m._aj = false; });
    const pre = compute(state.mov2).rows;
    // Documentos posteriores al conteo; se proponen como ajuste los que calzan con las diferencias
    const groups = new Map();
    for (const r of pre){
      if (!r.counted) continue;
      const ck = dayKey(r.s.fecha);
      for (const m of r.docs){
        if (!m.fecha || dayKey(m.fecha) <= ck) continue;
        const id = docId(m);
        let g = groups.get(id);
        if (!g){ g = {id, tipo:m.tipo, folio:m.folio, fecha:m.fecha, lines:0, match:0, valor:0}; groups.set(id, g); }
        g.lines++; g.valor += (m.kind === 'in' ? 1 : -1) * (m.valor || 0);
        if (r.diff != null && near(m.qty, Math.abs(r.diff)) && ((r.diff < 0 && m.kind === 'out') || (r.diff > 0 && m.kind === 'in'))) g.match++;
      }
    }
    const list = [...groups.values()];
    const tot = new Map();
    for (const m of state.mov2){ const t = tot.get(docId(m)) || {lines:0, valor:0}; t.lines++; t.valor += (m.kind === 'in' ? 1 : -1) * (m.valor || 0); tot.set(docId(m), t); }
    list.forEach(g => { const t = tot.get(g.id); if (t){ g.lines = t.lines; g.valor = t.valor; } g.auto = g.lines >= 5 && g.match / g.lines >= 0.6; });
    list.sort((a, b) => (b.auto - a.auto) || (b.fecha - a.fecha));
    state.docGroups = list;
    if (!state.ajSel) state.ajSel = new Set(list.filter(g => g.auto).map(g => g.id));
    state.mov2.forEach(m => { m._aj = state.ajSel.has(docId(m)); });
    const res = compute(state.mov2).rows;
    for (const r of res){
      const hasAj = Math.abs(r.aj) > EPS;
      if (!r.counted || r.diff == null){ if (hasAj) state.checkRows.push({...r, ck:'other', expected:null, gap:null, cobs:[!r.counted ? 'Se ajustó, pero este producto no está contado.' : 'Se ajustó, pero no hay saldo de Defontana al momento del conteo para comparar.']}); continue; }
      const expected = r.realNow, actual = r.sysCalc != null ? r.sysCalc : r.sysNow, gap = actual - expected;
      const late = r.cause === 'late' || r.cause === 'sameday';   // la causa se calcula sin los documentos de ajuste
      const need = r.diff, cobs = [];
      const dirTxt = g => g > 0 ? `Defontana tiene ${fmt(g)} de más: falta una salida de ${fmt(g)}.` : `Defontana tiene ${fmt(-g)} de menos: falta una entrada de ${fmt(-g)}.`;
      const ajTxt = hasAj ? r.ajDocs.map(m => `${m.tipo} #${m.folio} (${m.kind === 'in' ? '+' : '−'}${fmt(m.qty)})`).join(', ') : '';
      let ck;
      if (Math.abs(gap) <= EPS){
        if (late && hasAj){
          ck = 'double';
          const lateDoc = r.docs.filter(m => !m._aj && m.fecha && dayKey(m.fecha) > dayKey(r.s.fecha) && near(m.qty, Math.abs(need)))[0];
          cobs.push(`Cuadra en el cálculo, pero antes del ajuste ya se había registrado ${lateDoc ? lateDoc.tipo + ' #' + lateDoc.folio + ' del ' + fmtDate(lateDoc.fecha) : 'un documento'} por la misma cantidad. Si esa mercadería salió o entró antes del conteo, el ajuste la contó dos veces. Cuenta de nuevo: si en bodega hay ${fmt(actual - need)}, reversa el ajuste.`);
        } else { ck = 'ok'; cobs.push(hasAj ? `Quedó cuadrado con ${ajTxt}. Defontana tiene ${fmt(actual)}, igual al stock real.` : Math.abs(need) <= EPS ? 'Ya estaba cuadrado y sigue cuadrado.' : `Quedó cuadrado sin ajuste: los movimientos posteriores lo corrigieron. Defontana tiene ${fmt(actual)}.`); }
      } else if (!hasAj){
        if (late){ ck = 'review'; cobs.push(`No se ajustó. Probablemente no hacía falta: la diferencia la explica un documento registrado después del conteo. Si al contar ya había salido o entrado esa mercadería, está bien así. Si no, ${dirTxt(gap).toLowerCase()}`); }
        else { ck = 'pending'; cobs.push(`No se ajustó. ${dirTxt(gap)}`); }
      } else {
        ck = 'wrong';
        cobs.push(`Se ajustó ${sgn(r.aj)} con ${ajTxt}, pero había que ajustar ${sgn(need)}. ${dirTxt(gap)}`);
      }
      if (r.sysNow != null && Math.abs(r.sysNow - actual) > EPS) cobs.push(`Ojo: la última fila del informe muestra saldo ${fmt(r.sysNow)}, pero sumando los documentos da ${fmt(actual)}. Pasa cuando el informe trae documentos del mismo día en otro orden, o documentos no aprobados. Confirma el saldo del producto en Defontana.`);
      if (r.toOther > EPS) cobs.push(`${fmt(r.toOther)} se traspasaron a otra bodega después del conteo: siguen en el saldo de Defontana, pero no en esta bodega.`);
      if (r.ins || r.outs) cobs.push(`Movimientos después del conteo (sin contar ajustes): ${r.ins ? '+' + fmt(r.ins) : ''}${r.ins && r.outs ? ' ' : ''}${r.outs ? '−' + fmt(r.outs) : ''}.`);
      const aj0 = r.ajDocs.filter(m => m.valor != null && Math.abs(m.valor) < EPS && m.qty > EPS);
      if (aj0.length) cobs.push('El ajuste quedó a costo $0: el producto no tenía costo en Defontana.');
      if (!hasAj && Math.abs(need) <= EPS && Math.abs(gap) <= EPS) continue;   // cuadrado desde antes, sin ajuste: no se lista
      state.checkRows.push({...r, ck, expected, gap, cobs});
    }
  }

  // ---------- Configuración de las vistas ----------
  const ACTION = {
    up:['a-up','Aumentar'], down:['a-down','Disminuir'], ok:['a-ok','Cuadrado'], check:['a-warn','Revisar antes de ajustar'],
    nodata:['a-warn','Sin saldo en Defontana'], nocount:['a-ok','Sin contar'], nofile:['a-warn','No está en el conteo']
  };
  const REG_FILTERS = [
    ['all', 'Todos', r => true, null],
    ['bad', 'Descuadrados', r => r.st === 'up' || r.st === 'down' || r.st === 'check', 'var(--warn)'],
    ['up', 'Aumentar', r => r.st === 'up', 'var(--in)'],
    ['down', 'Disminuir', r => r.st === 'down', 'var(--out)'],
    ['check', 'Revisar antes de ajustar', r => r.st === 'check', 'var(--warn)'],
    ['ok', 'Cuadrados', r => r.st === 'ok', 'var(--muted)'],
    ['nopmp', 'Falta PMP', r => (r.st === 'up' || r.st === 'down') && !(r.pmp > 0), 'var(--warn)'],
    ['nodata', 'Sin saldo en Defontana', r => r.st === 'nodata', 'var(--warn)'],
    ['nocount', 'Sin contar', r => r.st === 'nocount', 'var(--muted)'],
    ['nofile', 'No están en el conteo', r => r.st === 'nofile', 'var(--warn)'],
    ['alias', 'Código escrito distinto', r => r.alias.length > 0 || r.viaName || r.nCounted > 1, 'var(--accent)'],
    ['cost', 'Revisar costo ($0)', r => !!(r.cost && r.cost.need), 'var(--warn)'],
    ['recount', 'Recontados', r => !!(r.s && r.s.recontado), 'var(--accent)'],
    ['p-verify', 'Paso 1: confirmar', r => !r.umRound && r.st === 'check' || (r.cause === 'um' && (r.st === 'up' || r.st === 'down')), 'var(--warn)', true],
    ['p-cost', 'Paso 2: corregir costos', r => docSteps(r).some(x => x.k === 'cost'), 'var(--warn)', true],
    ['p-in', 'Paso 3: entradas', r => docSteps(r).some(x => x.k === 'in'), 'var(--in)', true],
    ['p-out', 'Paso 4: salidas', r => docSteps(r).some(x => x.k === 'out'), 'var(--out)', true]
  ];
  const ZERO_FILTERS = [
    ['all', 'Todos', z => true, null],
    ['in', 'Ingresos a $0', z => z.m.kind === 'in', 'var(--in)'],
    ['out', 'Egresos a $0', z => z.m.kind === 'out', 'var(--out)'],
    ['need', 'Revisar costo', z => z.rev.need, 'var(--warn)'],
    ['noneed', 'No hace falta', z => !z.rev.need, 'var(--muted)'],
    ['nopmp', 'Sin PMP', z => !(z.pmp > 0), 'var(--warn)']
  ];
  const CHECK = {
    ok:['a-good','Quedó bien','good'], double:['a-warn','Cuadra, revisar doble ajuste','warn'], pending:['a-down','Falta ajustar','bad'],
    wrong:['a-down','Ajuste con diferencia','bad'], review:['a-warn','Revisar si hace falta ajuste','warn'], other:['a-warn','Ajustado sin datos del conteo','warn']
  };
  const CHECK_FILTERS = [
    ['all', 'Todos', r => true, null],
    ['ok', 'Quedó bien', r => r.ck === 'ok', 'var(--in)'],
    ['bad', 'Con problema', r => r.ck !== 'ok', 'var(--out)'],
    ['wrong', 'Ajuste con diferencia', r => r.ck === 'wrong', 'var(--out)'],
    ['pending', 'Falta ajustar', r => r.ck === 'pending', 'var(--out)'],
    ['double', 'Posible doble ajuste', r => r.ck === 'double', 'var(--warn)'],
    ['review', 'Revisar si hace falta', r => r.ck === 'review', 'var(--warn)'],
    ['other', 'Ajustados sin conteo', r => r.ck === 'other', 'var(--warn)']
  ];
  const CHECK_COLS = [
    ['code', 'Producto', '', r => r.code],
    ['linea', 'Línea', '', r => r.linea || null],
    ['contado', 'Contado', 'num', r => r.s ? r.s.stock : null],
    ['need', 'Había que ajustar', 'num', r => r.diff],
    ['aj', 'Se ajustó', 'num', r => r.aj],
    ['ck', 'Resultado', '', r => r.ck],
    ['obs', 'Detalle', '', r => r.ck],
    ['make', 'Documento a generar', '', r => checkToMake(r)[0]],
    ['exp', 'Debería tener Defontana', 'num', r => r.expected],
    ['now', 'Tiene Defontana', 'num', r => r.sysCalc ?? r.sysNow],
    ['gap', 'Diferencia que queda', 'num', r => r.gap]
  ];
  function checkRow(r){
    const [cls, label, stripe] = CHECK[r.ck];
    return `<tr class="rx-row s-${stripe}${state.open.has(r.key) ? ' open' : ''}" data-key="${esc(r.key)}" tabindex="0">
      <td><div class="code">${esc(r.code)}</div><div class="pname">${esc(r.name)}</div>${aliasNote(r)}</td>
      ${lineaCell(r.linea)}
      <td class="num">${r.counted ? fmt(r.s.stock) + '<div class="small">' + fmtDate(r.s.fecha) + '</div>' : '—'}</td>
      <td class="num diff ${r.diff > EPS ? 'plus' : r.diff < -EPS ? 'minus' : 'mut'}">${r.diff == null ? '—' : sgn(r.diff)}</td>
      <td class="num diff ${r.aj > EPS ? 'plus' : r.aj < -EPS ? 'minus' : 'mut'}">${Math.abs(r.aj) > EPS ? sgn(r.aj) + '<div class="small">' + money(r.ajVal) + '</div>' : '—'}</td>
      <td><span class="pill ${cls}">${label}</span></td>
      <td class="obs"><div class="why">${r.cobs[0]}</div>${r.cobs.length > 1 ? '<div class="more-obs">' + r.cobs.slice(1).join('<br>') + '</div>' : ''}</td>
      <td class="tomake">${makeCell(checkToMake(r))}</td>
      <td class="num">${fmt(r.expected)}</td>
      <td class="num">${fmt(r.sysCalc ?? r.sysNow)}${r.sysCalc != null && r.sysNow != null && Math.abs(r.sysCalc - r.sysNow) > EPS ? '<div class="small">informe: ' + fmt(r.sysNow) + '</div>' : ''}</td>
      <td class="num diff ${r.gap == null || Math.abs(r.gap) <= EPS ? 'mut' : 'minus'}">${r.gap == null ? '—' : Math.abs(r.gap) <= EPS ? '0' : sgn(r.gap)}</td></tr>`;
  }

  const lineaCell = l => `<td class="linea">${l ? esc(l) : '<span class="mut">—</span>'}</td>`;
  const REG_COLS = [
    ['code', 'Producto', '', r => r.code],
    ['linea', 'Línea', '', r => r.linea || null],
    ['contado', 'Contado', 'num', r => r.s ? r.s.stock : null],
    ['movs', 'Movimientos desde el conteo', 'num', r => r.counted ? r.ins - r.outs : null],
    ['real', 'Debería tener Defontana hoy', 'num', r => r.realNow],
    ['now', 'Tiene Defontana hoy', 'num', r => hoyDe(r)],
    ['diff', 'Ajuste a hacer hoy', 'num', r => ajusteHoy(r)],
    ['st', 'Qué hacer', '', r => r.st],
    ['obs', 'Por qué está descuadrado', '', r => r.cause ? CAUSES[r.cause] : null],
    ['make', 'Qué hacer, en orden', '', r => STEP[docSteps(r)[0].k].n],
    ['costo', 'Costo a usar ($0)', 'num', r => r.cost && r.cost.need && r.cost.costos.length && r.cost.costos[0].v != null ? r.cost.costos[0].v : null],
    ['pmp', 'PMP', 'num', r => r.pmp],
    ['valor', 'Valor ajuste', 'num', r => r.valor]
  ];
  const ZERO_COLS = [
    ['fecha', 'Fecha', '', z => z.m.fecha],
    ['doc', 'Documento', '', z => z.m.tipo],
    ['code', 'Producto', '', z => z.code],
    ['linea', 'Línea', '', z => z.linea || null],
    ['kind', 'Tipo', '', z => z.m.kind],
    ['qty', 'Cantidad', 'num', z => z.m.qty],
    ['pmp', 'PMP', 'num', z => z.pmp],
    ['valor', 'Valor que debió tener', 'num', z => z.valor],
    ['rev', '¿Revisar costo?', '', z => z.rev.need ? 0 : 1],
    ['costo', 'Costo a usar', 'num', z => z.rev.costo && z.rev.need ? z.rev.costo.v : null],
    ['make', 'Documento a generar', '', z => z.rev.hacer]
  ];

  const pmpInput = (key, v, edited, code) =>
    `<input class="pmp${edited ? ' edited' : v > 0 ? '' : ' missing'}" type="number" min="0" step="any" inputmode="decimal" data-key="${esc(key)}" value="${v != null ? Math.round(v*100)/100 : ''}" placeholder="Poner costo" aria-label="PMP de ${esc(code)}">`;

  function aliasNote(r){
    const bits = [];
    if (r.alias.length) bits.push('También escrito: ' + r.alias.map(esc).join(', '));
    if (r.viaName) bits.push('Cruzado por nombre');
    if (r.nCounted > 1) bits.push('Contado en ' + r.nCounted + ' códigos (se sumaron)');
    return bits.length ? `<div class="alias">${bits.join(' · ')}</div>` : '';
  }
  function regRow(r){
    const [cls, label] = ACTION[r.st], aj = ajusteHoy(r);
    const d = r.diff;
    const qty = (r.st === 'up' || r.st === 'down') ? ' ' + fmt(Math.abs(d)) : '';
    const obsCell = r => {
      const costo = r.cost ? `<div class="costrev${r.cost.need ? '' : ' ok'}"><b>${r.cost.need ? 'Revisar costo:' : 'Costo:'}</b> ${esc(r.cost.txt.join(' '))}</div>` : '';
      if (!r.cause){
        if (r.st === 'nodata') return '<span class="mut">Sin documentos en el informe: no se conoce el saldo de Defontana.</span>' + costo;
        if (r.st === 'nofile') return '<span class="mut">Tiene documentos en Defontana pero no está en el archivo de conteo.</span>' + costo;
        return costo;
      }
      const [main, ...rest] = r.obs;
      return `<div class="cause">${CAUSES[r.cause]}</div><div class="why">${main}</div>${rest.length ? '<div class="more-obs">' + rest.join('<br>') + '</div>' : ''}${costo}`;
    };
    return `<tr class="rx-row s-${r.st}${state.open.has(r.key) ? ' open' : ''}" data-key="${esc(r.key)}" tabindex="0">
      <td><div class="code">${esc(r.code)}</div><div class="pname">${esc(r.name)}</div>${aliasNote(r)}</td>
      ${lineaCell(r.linea)}
      <td class="num">${r.counted ? fmt(r.s.stock) + '<div class="small">' + fmtDate(r.s.fecha) + (r.s.recontado ? ' · recuento' : '') + '</div>' + (r.umInfo ? '<div class="small alias">en ' + esc(r.umInfo.de) + ' · Defontana en ' + esc(r.umInfo.a) + (r.umInfo.f ? ' (convertido)' : '') + '</div>' : '') : '<span class="mut">—</span>'}${r.s && r.s.recontado && r.s.original && r.s.original.stock != null ? '<div class="small">antes: ' + fmt(r.s.original.stock) + ' el ' + fmtDate(r.s.original.fecha) + '</div>' : ''}${r.s ? `<input class="recount" type="number" step="any" min="0" inputmode="decimal" data-key="${esc(r.key)}" value="${r.s.recontado ? r.s.stock : ''}" placeholder="Recuento hoy" aria-label="Recuento de hoy de ${esc(r.code)}">` : ''}</td>
      <td class="num">${r.counted ? (r.ins || r.outs ? (r.ins ? '<span class="plus">+' + fmt(r.ins) + '</span> ' : '') + (r.outs ? '<span class="minus">−' + fmt(r.outs) + '</span>' : '') : '<span class="mut">sin movimientos</span>') : '<span class="mut">—</span>'}</td>
      <td class="num"><b>${fmt(r.realNow)}</b></td>
      <td class="num">${fmt(hoyDe(r))}${r.sysAtCount != null && r.counted ? '<div class="small">al conteo: ' + fmt(r.sysAtCount) + '</div>' : ''}${r.sysCalc != null && r.sysNow != null && Math.abs(r.sysCalc - r.sysNow) > EPS ? '<div class="small">última fila del informe: ' + fmt(r.sysNow) + '</div>' : ''}</td>
      <td class="num diff ${aj > EPS ? 'plus' : aj < -EPS ? 'minus' : 'mut'}">${aj == null ? '—' : Math.abs(aj) <= EPS ? '0' : sgn(aj)}</td>
      <td><span class="pill ${cls}">${label}${qty}</span>${r.sameDay && r.counted ? '<span class="flag" title="Hay documentos el mismo día del conteo">· mismo día</span>' : ''}</td>
      <td class="obs">${obsCell(r)}</td>
      <td class="tomake">${stepsCell(docSteps(r))}</td>
      <td class="num">${costCell(r)}</td>
      <td class="num">${r.st === 'up' || r.st === 'down' || r.st === 'check' ? pmpInput(r.key, r.pmp, r.edited, r.code) : '<span class="mut">' + (r.pmp != null ? money(r.pmp) : '—') + '</span>'}</td>
      <td class="num diff ${r.valor > 0.5 ? 'plus' : r.valor < -0.5 ? 'minus' : 'mut'}">${r.st === 'up' || r.st === 'down' || r.st === 'check' ? money(r.valor) : '—'}</td></tr>`;
  }
  function zeroRow(z){
    return `<tr>
      <td class="num" style="text-align:left">${fmtDate(z.m.fecha)}</td>
      <td>${esc(z.m.tipo)}<div class="small">Folio ${esc(z.m.folio)}${z.m.ref ? ' · ' + esc(z.m.ref) : ''}</div></td>
      <td><div class="code">${esc(z.code)}</div><div class="pname">${esc(z.name)}</div></td>
      ${lineaCell(z.linea)}
      <td><span class="pill ${z.m.kind === 'in' ? 'a-up' : 'a-down'}">${z.m.kind === 'in' ? 'Ingreso' : 'Egreso'}</span></td>
      <td class="num">${fmt(z.m.qty)} <span class="small">${esc(z.m.um)}</span></td>
      <td class="num">${pmpInput(z.key, z.pmp, z.edited, z.code)}<div class="small">${esc(z.pmpSrc)}</div></td>
      <td class="num diff">${money(z.valor)}</td>
      <td class="num">${z.rev.need && z.rev.costo ? '<b>' + money(z.rev.costo.v) + '</b> <span class="small">c/u</span><div class="small wrapsmall">' + esc(z.rev.costo.src) + '</div>' : z.rev.need ? '<span class="small">Usa el costo de la factura</span>' : '—'}</td>
      <td class="obs"><span class="pill ${z.rev.need ? 'a-warn' : 'a-ok'}">${z.rev.need ? 'Sí' : 'No'}</span> <span class="why">${esc(z.rev.txt.replace(/^(Sí|No)\. /, ''))}</span></td>
      <td class="tomake">${makeCell([z.rev.hacer])}</td></tr>`;
  }

  function detail(r){
    const span = (state.view === 'check' ? CHECK_COLS : REG_COLS).length;
    if (!r.docs.length) return `<tr class="detail"><td colspan="${span}"><span class="note">Este código no tiene documentos en el informe de Defontana, así que no se conoce su saldo en el sistema. Revisa su stock directamente en Defontana.</span></td></tr>`;
    const ck = r.counted ? dayKey(r.s.fecha) : null, sameAfter = $('optSame').value === 'after';
    const when = m => { if (m._aj) return 'Ajuste'; if (ck == null) return ''; const dk = dayKey(m.fecha); return dk < ck ? 'Antes' : dk > ck ? 'Después' : sameAfter ? 'Mismo día (después)' : 'Mismo día (antes)'; };
    const rows = r.docs.map(m => {
      const w = when(m), zero = m.valor != null && Math.abs(m.valor) < EPS && m.qty > EPS;
      return `<tr class="${zero ? 'zero' : w.startsWith('Antes') || w === 'Mismo día (antes)' ? 'pre' : 'after'}">
        <td>${fmtDate(m.fecha)}</td><td>${esc(m.tipo)} <span class="small">#${esc(m.folio)}${(m.kind === 'in' ? m.dest : m.orig) && !/CENTRAL/i.test(m.kind === 'in' ? m.dest : m.orig) ? ' · ' + esc(m.kind === 'in' ? m.dest : m.orig) : ''}${norm(m.art) !== norm(r.code) ? ' · ' + esc(m.art) : ''}</span></td><td>${esc(m.ref)}</td>
        <td class="num ${m.kind === 'in' ? 'plus' : 'minus'}">${m.kind === 'in' ? '+' : '−'}${fmt(m.qty)}</td>
        <td class="num">${money(m.valor)}${zero ? ' <span class="flag">$0</span>' : ''}</td>
        <td class="num">${fmt(m.saldo)}</td>
        <td class="num">${m.saldo > EPS && m.valorInv != null ? money(m.valorInv / m.saldo) : '—'}</td>
        <td>${w}</td></tr>`;
    }).join('');
    const head = r.counted ? `<div class="dethead">
      <span>Contado el <b>${fmtDate(r.s.fecha, true)}</b>${r.s.por ? ' por ' + esc(r.s.por) : ''}: <b>${fmt(r.s.stock)}</b></span>
      <span>Defontana tenía: <b>${fmt(r.sysAtCount)}</b></span>
      <span>Origen del PMP: <b>${esc(r.pmpSrc)}</b></span></div>` : '';
    return `<tr class="detail"><td colspan="${span}">${head}<table class="det"><thead><tr><th>Fecha</th><th>Documento</th><th>Referencia</th><th class="num">Cantidad</th><th class="num">Valor</th><th class="num">Saldo</th><th class="num">PMP</th><th>Respecto al conteo</th></tr></thead><tbody>${rows}</tbody></table></td></tr>`;
  }

  // ---------- Pintar ----------
  function sorted(list, cols){
    const {k, d} = state.sort[state.view];
    const get = (cols.find(c => c[0] === k) || cols[0])[3];
    return list.slice().sort((a, b) => {
      let x = get(a), y = get(b);
      if (x instanceof Date) x = +x; if (y instanceof Date) y = +y;
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'es', {numeric:true})) * d;
    });
  }

  function renderAjDocs(){
    const box = $('ajDocs');
    if (!state.mov2){ box.innerHTML = ''; return; }
    const G = state.docGroups, auto = G.filter(g => g.auto), rest = G.filter(g => !g.auto);
    const item = g => `<label class="ajdoc"><input type="checkbox" data-doc="${esc(g.id)}"${state.ajSel.has(g.id) ? ' checked' : ''}> <span>${esc(g.tipo)} <b>#${esc(g.folio)}</b> del ${fmtDate(g.fecha)} · ${fmt(g.lines)} ${g.lines === 1 ? 'línea' : 'líneas'} · ${money(g.valor)}${g.auto ? ' · ' + fmt(g.match) + ' calzan con las diferencias' : ''}</span></label>`;
    const nSel = G.filter(g => state.ajSel.has(g.id)).length;
    box.innerHTML = `<div class="ajbox"><div class="ajhead"><h3>Documentos de ajuste <span class="note">(${fmt(nSel)} de ${fmt(G.length)} marcados)</span></h3>
      <span class="ajbtns"><button type="button" class="rx-btn ghost sm" data-all="1">Marcar todos</button><button type="button" class="rx-btn ghost sm" data-all="0">Quitar todos</button><button type="button" class="rx-btn ghost sm" data-all="auto">Solo los sugeridos</button></span></div>
      <p class="note">${auto.length ? 'Encontré estos documentos que calzan con las diferencias del conteo. Marca o desmarca los que corresponden a ajustes de inventario.' : 'No encontré documentos que calcen con las diferencias. Marca abajo los documentos de ajuste.'}</p>
      ${auto.map(item).join('')}
      ${nSel > auto.length + 5 ? '<p class="note warnline">Ojo: marcaste documentos que no son ajustes. Los movimientos normales (ventas, envíos a producción, compras) no deben marcarse, porque el programa los tomaría como ajustes y el resultado no sería correcto.</p>' : ''}
      ${rest.length ? `<details${auto.length && !state.ajOpen ? '' : ' open'}><summary>Otros documentos posteriores al conteo (${fmt(rest.length)})</summary><div class="ajlist">${rest.map(item).join('')}</div></details>` : ''}</div>`;
  }

  // ---------- Plan de ajustes: listado por paso ----------
  function buildPlan(){
    const R = state.rows, plan = {verify:[], cost:[], in:[], out:[]};
    const dudoso = r => !r.umRound && (r.st === 'check' || (r.cause === 'um' && (r.st === 'up' || r.st === 'down')));
    const lin = $('optLinea').value;
    for (const r of R){
      if (lin && (r.linea || '') !== lin) continue;
      if (dudoso(r)){ plan.verify.push({r, qty:r.diff, txt: (r.obs[0] || docSteps(r).find(x => x.k === 'verify').txt).replace(/<[^>]+>/g, ''), motivo: r.cause ? CAUSES[r.cause] : ''}); continue; }
      if (r.cost && r.cost.need){
        for (const c of r.cost.costos){
          if (/^entrada por /.test(c.doc)) plan.in.push({r, qty:c.qty, v:c.v, src:c.src, motivo:'Salió sin stock (' + c.doc.replace(/^entrada por /, '') + ')'});
          else plan.cost.push({r, doc:c.doc, qty:c.qty, v:c.v, src:c.src, corr:r.cost.corr});
        }
      }
      if (r.st === 'up') plan.in.push({r, qty:r.diff, v:r.pmp > 0 ? r.pmp : null, src:r.pmpSrc, motivo:r.cause ? CAUSES[r.cause] : 'Sobra en bodega'});
      if (r.st === 'down') plan.out.push({r, qty:-r.diff, v:r.pmp > 0 ? r.pmp : null, src:r.pmpSrc, motivo:r.cause ? CAUSES[r.cause] : 'Falta en bodega'});
    }
    plan.um = R.filter(r => r.umInfo && (!lin || (r.linea || '') === lin)).map(r => ({r}));
    const byCode = (a, b) => String(a.r.code).localeCompare(String(b.r.code), 'es', {numeric:true});
    Object.values(plan).forEach(L => L.sort(byCode));
    return plan;
  }
  function renderPlan(){
    const box = $('planBox');
    if (!state.mov.length){ box.innerHTML = '<p class="empty">Sube el Informe de Documentos de Defontana (archivo 2) para armar el plan.</p>'; return; }
    const P = state.plan = buildPlan();
    const prod = x => `<td><div class="code">${esc(x.r.code)}</div><div class="pname">${esc(x.r.name)}</div></td>${lineaCell(x.r.linea)}`;
    const tot = L => L.reduce((a, x) => a + (x.v != null ? x.v * x.qty : 0), 0);
    const sec = (num, titulo, porque, L, head, row, foot) => `<section class="plansec">
      <div class="planhead"><span class="pnum">${num}</span><div><h3>${titulo} <span class="pcount">${fmt(L.length)} ${L.length === 1 ? 'línea' : 'líneas'}</span></h3><p class="pwhy">${porque}</p></div></div>
      ${L.length ? `<div class="tablebox"><table class="plantable"><thead><tr><th class="n">#</th>${head}</tr></thead><tbody>${L.map((x, i) => `<tr><td class="n">${i + 1}</td>${row(x)}</tr>`).join('')}</tbody>${foot ? `<tfoot><tr>${foot}</tr></tfoot>` : ''}</table></div>` : '<p class="note">Nada en este paso.</p>'}
    </section>`;
    const hoyCells = x => /^Salió sin stock/.test(x.motivo) ? '<td class="num mut">—</td><td class="num mut">—</td>' : `<td class="num"><b>${fmt(x.r.realNow)}</b></td><td class="num">${fmt(hoyDe(x.r))}</td>`;
    const costo = x => x.v != null ? `<b>${money(x.v)}</b><div class="small wrapsmall">${esc(x.src || '')}</div>` : '<span class="small">Poner costo (factura)</span>';
    box.innerHTML = `
      <div class="planintro"><b>Hazlo en este orden.</b> Defontana valoriza cada entrada y salida al PMP del momento: si se corrige el costo después, las salidas ya quedaron mal valorizadas. Las entradas van antes que las salidas para que el saldo nunca quede negativo.
      <button type="button" class="rx-btn" id="btnPlanXlsx">Descargar plan en Excel</button></div>
      ${sec(1, 'Confirmar antes de ajustar', 'Recontar o revisar. No hagas ajustes de estos productos hasta confirmarlos.', P.verify,
        '<th>Producto</th><th>Línea</th><th class="num">Diferencia</th><th>Motivo</th><th>Qué revisar</th>',
        x => `${prod(x)}<td class="num diff ${x.qty > 0 ? 'plus' : 'minus'}">${sgn(x.qty)}</td><td>${esc(x.motivo)}</td><td class="wide">${esc(x.txt)}</td>`)}
      ${P.um.length ? `<section class="plansec"><div class="planhead"><span class="pnum">1b</span><div><h3>Cambiar la unidad en Defontana <span class="pcount">${fmt(P.um.length)} productos</span></h3><p class="pwhy">Se contaron en otra unidad que la del maestro de Defontana. Lo contado es la referencia: primero cambia la unidad del producto en Defontana (con su saldo convertido) y después haz las entradas y salidas del plan, que ya están en la unidad del conteo.</p></div></div>
        <div class="tablebox"><table class="plantable"><thead><tr><th class="n">#</th><th>Producto</th><th>Línea</th><th>Unidad en Defontana</th><th>Cambiar a</th><th class="num">Saldo Defontana</th><th class="num">Saldo convertido</th><th class="num">Contado</th><th class="num">Ajuste después</th></tr></thead>
        <tbody>${P.um.map((x, i) => { const u = x.r.umInfo; return `<tr><td class="n">${i + 1}</td>${prod(x)}<td>${esc(u.a)}</td><td><b>${esc(u.de)}</b></td><td class="num">${u.f ? fmt(u.hoyDef) + ' ' + esc(u.a) : fmt(hoyDe(x.r)) + ' ' + esc(u.a)}</td><td class="num">${u.f ? '<b>' + fmt(u.hoyConv) + ' ' + esc(u.de) + '</b>' : '<span class="small">sin conversión conocida</span>'}</td><td class="num">${fmt(x.r.s.stock)} ${esc(u.de)}</td><td class="num">${x.r.diff == null ? '—' : (Math.abs(x.r.diff) <= EPS ? '0' : sgn(Math.round(x.r.diff * 1000) / 1000)) + ' ' + esc(u.de)}</td></tr>`; }).join('')}</tbody></table></div></section>` : ''}
      ${sec(2, 'Corregir costos', 'Corrige el costo del documento indicado. Si Defontana no deja modificarlo, haz el ajuste de valor.', P.cost,
        '<th>Producto</th><th>Línea</th><th>Qué corregir</th><th class="num">Cantidad</th><th class="num">Costo a usar c/u</th><th class="num">Total</th><th class="num">Si no se puede: ajuste de valor</th>',
        x => `${prod(x)}<td>${esc(x.doc)}</td><td class="num">${fmt(x.qty)}</td><td class="num">${costo(x)}</td><td class="num">${x.v != null ? money(x.v * x.qty) : '—'}</td><td class="num">${x.corr && Math.abs(x.corr.ajuste) > 0.5 ? money(x.corr.ajuste) + '<div class="small">PMP queda en ' + money(x.corr.pmp) + '</div>' : '—'}</td>`,
        `<td></td><td colspan="6"><b>Total</b></td><td class="num"><b>${money(tot(P.cost))}</b></td><td></td>`)}
      ${sec(3, 'Entradas (Parte de Entrada)', 'Una Parte de Entrada por ajuste de inventario con estas líneas.', P.in,
        '<th>Producto</th><th>Línea</th><th class="num">Debería tener hoy</th><th class="num">Tiene Defontana hoy</th><th class="num">Cantidad</th><th class="num">Costo c/u</th><th class="num">Total</th><th>Motivo</th>',
        x => `${prod(x)}${hoyCells(x)}<td class="num diff plus">${fmt(x.qty)}</td><td class="num">${costo(x)}</td><td class="num">${x.v != null ? money(x.v * x.qty) : '—'}</td><td>${esc(x.motivo)}</td>`,
        `<td></td><td colspan="6"><b>Total</b></td><td class="num"><b>${money(tot(P.in))}</b></td><td></td>`)}
      ${sec(4, 'Salidas (Parte de Salida)', 'Una Parte de Salida por ajuste de inventario / merma con estas líneas. Defontana pondrá el PMP del día; el valor es referencial.', P.out,
        '<th>Producto</th><th>Línea</th><th class="num">Debería tener hoy</th><th class="num">Tiene Defontana hoy</th><th class="num">Cantidad</th><th class="num">PMP c/u</th><th class="num">Total</th><th>Motivo</th>',
        x => `${prod(x)}${hoyCells(x)}<td class="num diff minus">${fmt(x.qty)}</td><td class="num">${costo(x)}</td><td class="num">${x.v != null ? money(x.v * x.qty) : '—'}</td><td>${esc(x.motivo)}</td>`,
        `<td></td><td colspan="6"><b>Total</b></td><td class="num"><b>${money(tot(P.out))}</b></td><td></td>`)}
      <section class="plansec"><div class="planhead"><span class="pnum">5</span><div><h3>Verificar</h3><p class="pwhy">Cuando termines, descarga de nuevo el Informe de Documentos de Defontana y revísalo en la vista “Verificar ajustes”.</p></div></div></section>`;
  }
  function planExcel(){
    const P = state.plan || buildPlan(), wb = XLSX.utils.book_new();
    const r2 = v => v != null ? Math.round(v * 100) / 100 : '';
    const hoja = (nombre, filas) => XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(filas.length ? filas : [{'': 'Nada en este paso'}]), nombre);
    hoja('1 Confirmar', P.verify.map((x, i) => ({'#': i + 1, 'Código': x.r.code, 'Nombre': x.r.name, 'Línea': x.r.linea || '', 'Diferencia': x.qty, 'Motivo': x.motivo, 'Qué revisar': x.txt})));
    if (P.um.length) hoja('1b Unidades', P.um.map((x, i) => { const u = x.r.umInfo; return {'#': i + 1, 'Código': x.r.code, 'Nombre': x.r.name, 'Línea': x.r.linea || '', 'Unidad en Defontana': u.a, 'Cambiar a': u.de, 'Saldo Defontana (su unidad)': u.f ? u.hoyDef : hoyDe(x.r) ?? '', 'Saldo convertido': u.f ? u.hoyConv : 'sin conversión conocida', 'Contado': x.r.s.stock, 'Ajuste después': x.r.diff ?? ''}; }));
    hoja('2 Costos', P.cost.map((x, i) => ({'#': i + 1, 'Código': x.r.code, 'Nombre': x.r.name, 'Línea': x.r.linea || '', 'Qué corregir': x.doc, 'Cantidad': x.qty, 'Costo a usar c/u': r2(x.v), 'Total': x.v != null ? Math.round(x.v * x.qty) : '', 'Origen del costo': x.src, 'Ajuste de valor (si no se puede corregir)': x.corr ? Math.round(x.corr.ajuste) : '', 'PMP correcto hoy': x.corr ? r2(x.corr.pmp) : ''})));
    hoja('3 Entradas', P.in.map((x, i) => ({'#': i + 1, 'Código': x.r.code, 'Nombre': x.r.name, 'Línea': x.r.linea || '', 'Debería tener hoy': x.r.realNow ?? '', 'Tiene Defontana hoy': hoyDe(x.r) ?? '', 'Cantidad': x.qty, 'Costo c/u': r2(x.v), 'Total': x.v != null ? Math.round(x.v * x.qty) : '', 'Origen del costo': x.src, 'Motivo': x.motivo})));
    hoja('4 Salidas', P.out.map((x, i) => ({'#': i + 1, 'Código': x.r.code, 'Nombre': x.r.name, 'Línea': x.r.linea || '', 'Debería tener hoy': x.r.realNow ?? '', 'Tiene Defontana hoy': hoyDe(x.r) ?? '', 'Cantidad': x.qty, 'PMP c/u (referencial)': r2(x.v), 'Total': x.v != null ? Math.round(x.v * x.qty) : '', 'Motivo': x.motivo})));
    XLSX.writeFile(wb, 'plan-de-ajustes-' + fmtDate(new Date()) + '.xlsx');
  }

  // Panel con el orden recomendado; cada paso filtra la tabla
  function renderStepsPanel(show){
    const box = $('stepsPanel');
    box.hidden = !show || !state.mov.length;
    if (box.hidden) return;
    const F = k => REG_FILTERS.find(x => x[0] === k)[2];
    const n = k => state.rows.filter(F(k)).length, cur = state.filter.reg;
    const paso = (k, num, titulo, porque) => `<button type="button" class="paso${cur === k ? ' on' : ''}" data-go="${k}">
      <span class="pnum">${num}</span><span class="ptxt"><b>${titulo}</b> <span class="pcount">${fmt(n(k))} productos</span><span class="pwhy">${porque}</span></span></button>`;
    box.innerHTML = `<div class="ajhead"><h3>Orden recomendado</h3><button type="button" class="rx-btn sm" data-view-go="plan">Ver el plan completo por paso →</button></div><div class="pasos">
      ${paso('p-verify', 1, 'Confirmar lo dudoso', 'Recontar o revisar antes de tocar Defontana: diferencias por fechas de documentos o por unidad de medida.')}
      ${paso('p-cost', 2, 'Corregir costos', 'Primero los costos: Defontana valoriza cada entrada y salida al PMP del momento.')}
      ${paso('p-in', 3, 'Entradas', 'Parte de Entrada por lo que sobra en bodega, antes de las salidas, para que el saldo no quede negativo.')}
      ${paso('p-out', 4, 'Salidas', 'Parte de Salida por lo que falta en bodega, ya con el costo correcto.')}
      <button type="button" class="paso" data-view-go="check"><span class="pnum">5</span><span class="ptxt"><b>Verificar</b> <span class="pwhy">Bajar de nuevo el informe de Defontana y revisarlo en “Verificar ajustes”.</span></span></button>
    </div>`;
  }

  function fillLineas(){
    const sel = $('optLinea'), prev = sel.value;
    const cnt = new Map();
    for (const s of state.stock) if (s.linea) cnt.set(s.linea, (cnt.get(s.linea) || 0) + 1);
    const list = [...cnt.keys()].sort((a, b) => a.localeCompare(b, 'es'));
    sel.hidden = !list.length;
    sel.innerHTML = '<option value="">Todas las líneas</option>' + list.map(l => `<option value="${esc(l)}">${esc(l)}</option>`).join('');
    sel.value = list.includes(prev) ? prev : '';
  }

  function render(){
    const base = compute(state.mov);
    state.rows = base.rows; state.zero = base.zero; state.orphan = base.orphan;
    computeCheck();
    const reg = state.view === 'reg', chk = state.view === 'check';
    document.querySelectorAll('.view').forEach(b => b.setAttribute('aria-selected', b.dataset.view === state.view));
    $('checkPanel').hidden = !chk;
    renderStepsPanel(reg);
    const plan = state.view === 'plan';
    $('planBox').hidden = !plan; $('filtersBar').hidden = plan; $('tablebox').hidden = plan; $('summary').hidden = plan; $('copyNote').hidden = plan;
    if (plan){ renderPlan(); $('foot').innerHTML = ''; return; }
    if (chk) renderAjDocs();
    const all = reg ? state.rows : chk ? state.checkRows : state.zero, F = reg ? REG_FILTERS : chk ? CHECK_FILTERS : ZERO_FILTERS, cols = reg ? REG_COLS : chk ? CHECK_COLS : ZERO_COLS;

    // Resumen
    if (chk){
      if (!state.mov2) $('summary').innerHTML = '';
      else {
        const n = k => all.filter(r => r.ck === k).length;
        const ajDocs = state.docGroups.filter(g => state.ajSel.has(g.id));
        $('summary').innerHTML = `
        <button class="rx-card up" type="button" data-go="ok"><span class="lbl">Quedaron bien</span><span class="big">${fmt(n('ok'))}</span><span class="note">de ${fmt(all.length)} productos revisados</span></button>
        <button class="rx-card down" type="button" data-go="wrong"><span class="lbl">Ajuste con diferencia</span><span class="big">${fmt(n('wrong'))}</span><span class="note">se ajustó una cantidad distinta</span></button>
        <button class="rx-card down" type="button" data-go="pending"><span class="lbl">Falta ajustar</span><span class="big">${fmt(n('pending'))}</span><span class="note">siguen descuadrados</span></button>
        <button class="rx-card bad" type="button" data-go="double"><span class="lbl">Posible doble ajuste</span><span class="big">${fmt(n('double'))}</span><span class="note">contar de nuevo para confirmar</span></button>
        <div class="rx-card"><span class="lbl">Ajustes en Defontana</span><span class="big">${money(ajDocs.reduce((a, g) => a + g.valor, 0))}</span><span class="note">${fmt(ajDocs.length)} ${ajDocs.length === 1 ? 'documento' : 'documentos'}</span></div>`;
      }
    } else if (reg){
      const bad = all.filter(r => r.st === 'up' || r.st === 'down' || r.st === 'check'), up = bad.filter(r => r.st === 'up'), down = bad.filter(r => r.st === 'down'), chk = bad.filter(r => r.st === 'check');
      const sum = L => L.reduce((a, r) => a + (r.valor || 0), 0);
      const counted = all.filter(r => r.counted).length;
      $('summary').innerHTML = `
        <button class="rx-card bad" type="button" data-go="bad"><span class="lbl">Descuadrados</span><span class="big">${fmt(bad.length)}</span><span class="note">de ${fmt(counted)} productos contados</span></button>
        <button class="rx-card up" type="button" data-go="up"><span class="lbl">Aumentar en Defontana</span><span class="big">${fmt(up.length)}</span><span class="val">${money(sum(up))}</span></button>
        <button class="rx-card down" type="button" data-go="down"><span class="lbl">Disminuir en Defontana</span><span class="big">${fmt(down.length)}</span><span class="val">${money(sum(down))}</span></button>
        <div class="rx-card"><span class="lbl">Efecto neto del ajuste</span><span class="big">${money(sum(up) + sum(down))}</span><span class="note">${fmt(bad.filter(r => !(r.pmp > 0)).length)} sin PMP (poner costo)</span></div>
        <button class="rx-card bad" type="button" data-go="check"><span class="lbl">Revisar antes de ajustar</span><span class="big">${fmt(chk.length)}</span><span class="note">la diferencia se explica por la fecha de un documento</span></button>`;
    } else {
      const ins = all.filter(z => z.m.kind === 'in'), outs = all.filter(z => z.m.kind === 'out');
      const sum = L => L.reduce((a, z) => a + (z.valor || 0), 0);
      $('summary').innerHTML = `
        <div class="rx-card"><span class="lbl">Documentos a $0</span><span class="big">${fmt(all.length)}</span><span class="note">${fmt(new Set(all.map(z => z.key)).size)} productos distintos</span></div>
        <button class="rx-card up" type="button" data-go="in"><span class="lbl">Ingresos sin costo</span><span class="big">${fmt(ins.length)}</span><span class="val">${money(sum(ins))} a PMP</span></button>
        <button class="rx-card down" type="button" data-go="out"><span class="lbl">Egresos sin costo</span><span class="big">${fmt(outs.length)}</span><span class="val">${money(sum(outs))} a PMP</span></button>
        <button class="rx-card bad" type="button" data-go="nopmp"><span class="lbl">Sin PMP para proponer</span><span class="big">${fmt(all.filter(z => !(z.pmp > 0)).length)}</span><span class="note">el producto nunca tuvo costo</span></button>`;
    }

    // Filtros
    const cur = state.filter[state.view];
    $('chips').innerHTML = F.map(([k, label, f, color, hidden]) => {
      if (hidden && k !== cur) return '';
      const n = all.filter(f).length;
      if (!n && k !== 'all' && k !== cur) return '';
      return `<button type="button" class="chip" data-f="${k}" aria-pressed="${cur === k}">${color ? `<span class="dot" style="background:${color}"></span>` : ''}${label}<span class="c">${fmt(n)}</span></button>`;
    }).join('');

    // Tabla
    const {k: sk, d: sd} = state.sort[state.view];
    $('thead').innerHTML = '<tr>' + cols.map(([k, label, cls]) => `<th class="sort ${cls}" data-sort="${k}">${label}${sk === k ? ' <span class="arr">' + (sd > 0 ? '▲' : '▼') + '</span>' : ''}</th>`).join('') + '</tr>';
    let f = (F.find(x => x[0] === cur) || F[0])[2];
    const sel = $('optCause');
    sel.hidden = !reg;
    if (reg){
      const cnt = new Map(); all.forEach(r => { if (r.cause) cnt.set(r.cause, (cnt.get(r.cause) || 0) + 1); });
      const prev = state.cause || '';
      sel.innerHTML = '<option value="">Todas las causas</option>' + Object.keys(CAUSES).filter(k => cnt.has(k)).map(k => `<option value="${k}">${CAUSES[k]} (${fmt(cnt.get(k))})</option>`).join('');
      sel.value = cnt.has(prev) ? prev : '';
      if (sel.value){ const f0 = f, c = sel.value; f = r => f0(r) && r.cause === c; }
    }
    const q = strip($('optSearch').value);
    const zer = state.view === 'zero';
    const lin = $('optLinea').value;
    const rows = sorted(all.filter(r => f(r) && (!lin || (r.linea || '') === lin) && (!q || strip(r.code).includes(q) || strip(r.name).includes(q) || (zer && strip(r.m.tipo + ' ' + r.m.ref + ' ' + r.m.folio).includes(q)))), cols);
    state.visible = rows;
    const tb = $('tbody');
    if (!chk && !state.mov.length){ tb.innerHTML = `<tr><td colspan="${cols.length}" class="empty">Sube arriba el Informe de Documentos de Defontana (archivo 2) para cruzarlo con el conteo.</td></tr>`; }
    else if (chk && !state.mov2){ tb.innerHTML = `<tr><td colspan="${cols.length}" class="empty">Sube arriba el Informe de Documentos de Defontana descargado de nuevo, ya con los ajustes hechos. El programa buscará los documentos de ajuste y revisará producto por producto si quedó cuadrado.</td></tr>`; }
    else if (!rows.length){ tb.innerHTML = `<tr><td colspan="${cols.length}" class="empty">No hay productos en esta vista.</td></tr>`; }
    else {
      const parts = [];
      for (const r of rows){ parts.push(reg ? regRow(r) : chk ? checkRow(r) : zeroRow(r)); if (!zer && state.open.has(r.key)) parts.push(detail(r)); }
      tb.innerHTML = parts.join('');
    }

    $('foot').innerHTML = chk
      ? '<b>Cómo se verifica.</b> “Debería tener Defontana” = Contado + ingresos − egresos registrados después del conteo, sin contar los documentos de ajuste. “Tiene Defontana” es el saldo de Defontana al conteo más todos los documentos posteriores, incluidos los ajustes (se calcula con los documentos para no depender del orden de las filas; si la última fila del informe muestra otro saldo, se avisa). Si son iguales, quedó bien. “Posible doble ajuste” significa que cuadra en el cálculo, pero la diferencia del conteo calzaba con un documento registrado después del conteo: si esa mercadería ya había salido o entrado al contar, el ajuste la contó dos veces. Solo se listan los productos que estaban descuadrados o que tuvieron ajuste.'
      : reg
      ? '<b>Cómo se calcula.</b> “Debería tener Defontana hoy” = lo contado + las entradas − las salidas registradas después del conteo: es lo que tendría Defontana si el ajuste se hubiera hecho al contar. “Tiene Defontana hoy” es el saldo con todos los documentos del informe (debajo, el saldo que tenía al momento del conteo). “Ajuste a hacer hoy” = Debería tener − Tiene: si es positivo, Parte de Entrada; si es negativo, Parte de Salida. El saldo de Defontana es el del producto en todas las bodegas. El PMP es Valor Inventario / Saldo Inventario del último documento con saldo; puedes corregirlo en la tabla. Los códigos se cruzan sin considerar mayúsculas, tildes, espacios, puntos, comas, guiones, guiones bajos ni ceros a la izquierda; si un artículo de Defontana no cruza por código, se cruza por nombre. Haz clic en un producto para ver sus documentos.'
      : '<b>Cómo se calcula.</b> Son los documentos cuyo “Valor Movimiento” es $0. El valor que debió tener = cantidad × PMP del producto antes del documento (si no hay, el primero que aparece después). Un egreso a $0 suele ocurrir cuando el producto no tenía saldo o su PMP era $0.';
  }

  // ---------- Exportar ----------
  const regExport = r => ({
    'Código': r.code, 'Nombre': r.name, 'Línea': r.linea || '', 'Otras formas del código': r.alias.join(', ') + (r.viaName ? (r.alias.length ? ' · ' : '') + 'cruzado por nombre' : ''), 'Qué hacer': ACTION[r.st][1], 'Causa probable': r.cause ? CAUSES[r.cause] : '',
    'Observaciones': r.obs.map(x => x.replace(/<[^>]+>/g, '')).join(' '),
    'Qué hacer, en orden': stepsText(r), 'Revisar costo': r.cost ? (r.cost.need ? 'Sí' : 'No') : '', 'Detalle costo': r.cost ? r.cost.txt.join(' ') : '',
    'Costo a usar (c/u)': r.cost && r.cost.need ? r.cost.costos.map(c => (c.v != null ? Math.round(c.v * 100) / 100 : 'factura') + ' (' + c.doc + ')').join(' · ') : '',
    'PMP correcto hoy': r.cost && r.cost.corr ? Math.round(r.cost.corr.pmp * 100) / 100 : '',
    'Ajuste de valor': r.cost && r.cost.corr ? Math.round(r.cost.corr.ajuste) : '',
    'Cantidad a ajustar': r.diff != null && Math.abs(r.diff) > EPS ? Math.abs(r.diff) : '',
    'Contado': r.s ? r.s.stock : '', 'Fecha conteo': r.counted ? fmtDate(r.s.fecha, true) : '', 'Recuento': r.s && r.s.recontado ? 'Sí' : '',
    'Movimientos desde el conteo': r.counted ? r.ins - r.outs : '', 'Debería tener Defontana hoy': r.realNow ?? '', 'Tiene Defontana hoy': hoyDe(r) ?? '',
    'Ajuste a hacer hoy': ajusteHoy(r) ?? '', 'Defontana al conteo': r.sysAtCount ?? '', 'Diferencia al conteo': r.diff ?? '',
    'PMP': r.pmp != null ? Math.round(r.pmp * 100) / 100 : '', 'Origen PMP': r.pmpSrc,
    'Valor ajuste': r.valor != null ? Math.round(r.valor) : '',
    'Saldo última fila del informe': r.sysNow ?? ''
  });
  const zeroExport = z => ({
    'Fecha': fmtDate(z.m.fecha), 'Documento': z.m.tipo, 'Folio': z.m.folio, 'Referencia': z.m.ref,
    'Código': z.code, 'Nombre': z.name, 'Línea': z.linea || '', 'Tipo': z.m.kind === 'in' ? 'Ingreso' : 'Egreso', 'Cantidad': z.m.qty,
    'PMP': z.pmp != null ? Math.round(z.pmp * 100) / 100 : '', 'Origen PMP': z.pmpSrc, 'Valor que debió tener': z.valor != null ? Math.round(z.valor) : '',
    '¿Revisar costo?': z.rev.need ? 'Sí' : 'No', 'Motivo': z.rev.txt,
    'Costo a usar (c/u)': z.rev.need && z.rev.costo ? Math.round(z.rev.costo.v * 100) / 100 : '', 'Origen del costo': z.rev.need && z.rev.costo ? z.rev.costo.src : '',
    'PMP correcto hoy': z.rev.corr ? Math.round(z.rev.corr.pmp * 100) / 100 : '', 'Ajuste de valor': z.rev.corr ? Math.round(z.rev.corr.ajuste) : '', 'Documento a generar': z.rev.hacer
  });
  const checkExport = r => ({
    'Código': r.code, 'Nombre': r.name, 'Línea': r.linea || '', 'Resultado': CHECK[r.ck][1], 'Detalle': r.cobs.map(x => x.replace(/<[^>]+>/g, '')).join(' '),
    'Documento a generar': checkToMake(r).join(' · '),
    'Contado': r.s ? r.s.stock : '', 'Fecha conteo': r.counted ? fmtDate(r.s.fecha, true) : '',
    'Había que ajustar': r.diff ?? '', 'Se ajustó': r.aj, 'Valor ajuste': Math.round(r.ajVal),
    'Documentos de ajuste': r.ajDocs.map(m => m.tipo + ' #' + m.folio).join(', '),
    'Debería tener Defontana': r.expected ?? '', 'Tiene Defontana': r.sysCalc ?? r.sysNow ?? '', 'Saldo última fila del informe': r.sysNow ?? '', 'Diferencia que queda': r.gap ?? ''
  });
  const exportRows = () => (state.visible || []).map(state.view === 'reg' ? regExport : state.view === 'check' ? checkExport : zeroExport);

  $('btnXlsx').addEventListener('click', () => {
    const rows = exportRows(); if (!rows.length) return;
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), {reg:'Regularización', zero:'Documentos a costo 0', check:'Verificación de ajustes'}[state.view]);
    const name = {reg:'regularizacion-inventario-', zero:'documentos-costo-0-', check:'verificacion-ajustes-'}[state.view] + fmtDate(new Date()) + '.xlsx';
    XLSX.writeFile(wb, name);
  });
  $('btnCopy').addEventListener('click', () => {
    const rows = exportRows(); if (!rows.length) return;
    const keys = Object.keys(rows[0]);
    const tsv = [keys.join('\t'), ...rows.map(r => keys.map(k => String(r[k] ?? '').replace(/[\t\n]/g, ' ')).join('\t'))].join('\n');
    const done = () => { $('copyNote').textContent = fmt(rows.length) + ' filas copiadas. Pégalas en Excel.'; };
    navigator.clipboard.writeText(tsv).then(done).catch(() => {
      const ta = document.createElement('textarea'); ta.value = tsv; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch(_){ $('copyNote').textContent = 'No se pudo copiar.'; }
      ta.remove();
    });
  });

  // ---------- Carga ----------
  function setupLoader(inputId, dropId, statusId, parser, key, label){
    const input = $(inputId), drop = $(dropId), st = $(statusId);
    const handle = file => {
      if (!file) return;
      st.textContent = 'Leyendo ' + file.name + '…';
      file.arrayBuffer().then(buf => {
        const wb = XLSX.read(buf, {type:'array'});
        const data = parser(XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], {header:1, raw:true, defval:null, blankrows:false}));
        if (!data.length) throw new Error('El archivo no tiene filas con datos.');
        state[key] = data;
        drop.classList.remove('err'); drop.classList.add('ok');
        st.textContent = file.name + ' · ' + fmt(data.length) + ' ' + label;
        state.open.clear();
        if (key === 'mov') fillBodegas();
        if (key === 'stock') fillLineas();
        if (key === 'mov2'){ state.ajSel = null; if (!state.mov || !state.mov.length) { state.mov = data; fillBodegas(); } }
        render();
      }).catch(e => { drop.classList.remove('ok'); drop.classList.add('err'); st.textContent = e.message || 'No se pudo leer el archivo.'; });
    };
    input.addEventListener('change', () => { handle(input.files[0]); input.value = ''; });
    ['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave','drop'].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove('over')));
    drop.addEventListener('drop', e => { e.preventDefault(); handle(e.dataTransfer.files[0]); });
  }
  setupLoader('fileStock', 'dropStock', 'stStock', parseStock, 'stock', 'códigos');
  setupLoader('fileMov', 'dropMov', 'stMov', parseMov, 'mov', 'líneas de documentos');
  setupLoader('fileMov2', 'dropMov2', 'stMov2', parseMov, 'mov2', 'líneas de documentos');
  function refreshRecountStatus(){
    const n = state.recount.size;
    $('btnClearRecount').hidden = !n;
    if (n) $('stRecount').textContent = `${fmt(n)} ${n === 1 ? 'producto recontado' : 'productos recontados'}: se usa el recuento en vez del conteo original (filtro “Recontados”).`;
  }
  $('fileRecount').addEventListener('change', () => {
    const file = $('fileRecount').files[0]; $('fileRecount').value = ''; if (!file) return;
    file.arrayBuffer().then(buf => {
      const wb = XLSX.read(buf, {type:'array'});
      const data = parseRecount(XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], {header:1, raw:true, defval:null, blankrows:false}));
      if (!data.length) throw new Error('El archivo no tiene recuentos.');
      for (const d of data) state.recount.set(d.key, {qty: d.qty, fecha: d.fecha});
      guardarRecuentos(); $('dropRecount').classList.remove('err'); $('dropRecount').classList.add('ok');
      render(); refreshRecountStatus();
      $('stRecount').textContent = file.name + ' · ' + $('stRecount').textContent;
    }).catch(e => { $('dropRecount').classList.add('err'); $('stRecount').textContent = e.message || 'No se pudo leer el archivo.'; });
  });
  $('btnClearRecount').addEventListener('click', () => {
    state.recount.clear(); guardarRecuentos(); $('dropRecount').classList.remove('ok');
    $('stRecount').textContent = 'Excel con el código y el físico contado hoy: reemplaza el conteo de esos productos';
    render(); refreshRecountStatus();
  });
  $('ajDocs').addEventListener('click', e => {
    const b = e.target.closest('[data-all]'); if (!b) return;
    const v = b.dataset.all;
    state.ajOpen = true;
    state.ajSel = new Set(v === '1' ? state.docGroups.map(g => g.id) : v === 'auto' ? state.docGroups.filter(g => g.auto).map(g => g.id) : []);
    render();
  });
  $('ajDocs').addEventListener('toggle', e => { if (e.target.tagName === 'DETAILS') state.ajOpen = e.target.open; }, true);
  $('ajDocs').addEventListener('change', e => {
    const c = e.target.closest('input[data-doc]'); if (!c) return;
    if (c.checked) state.ajSel.add(c.dataset.doc); else state.ajSel.delete(c.dataset.doc);
    render();
  });

  // ---------- Eventos ----------
  document.querySelector('.views').addEventListener('click', e => {
    const b = e.target.closest('.view'); if (!b) return;
    state.view = b.dataset.view; state.open.clear(); render();
  });
  $('planBox').addEventListener('click', e => { if (e.target.closest('#btnPlanXlsx')) planExcel(); });
  $('stepsPanel').addEventListener('click', e => {
    const v = e.target.closest('[data-view-go]');
    if (v){ state.view = v.dataset.viewGo; state.open.clear(); render(); return; }
    const b = e.target.closest('[data-go]'); if (!b) return;
    state.filter.reg = state.filter.reg === b.dataset.go ? 'all' : b.dataset.go; render();
  });
  $('summary').addEventListener('click', e => { const b = e.target.closest('[data-go]'); if (!b) return; state.filter[state.view] = b.dataset.go; render(); });
  $('chips').addEventListener('click', e => { const b = e.target.closest('.chip'); if (!b) return; state.filter[state.view] = b.dataset.f; render(); });
  $('thead').addEventListener('click', e => {
    const th = e.target.closest('th[data-sort]'); if (!th) return;
    const s = state.sort[state.view];
    if (s.k === th.dataset.sort) s.d = -s.d; else { s.k = th.dataset.sort; s.d = 1; }
    render();
  });
  ['optBodega','optSame','optAprob','optLinea'].forEach(id => $(id).addEventListener('change', render));
  $('optCause').addEventListener('change', () => { state.cause = $('optCause').value; render(); });
  let t; $('optSearch').addEventListener('input', () => { clearTimeout(t); t = setTimeout(render, 150); });
  const toggle = tr => { const k = tr.dataset.key; state.open.has(k) ? state.open.delete(k) : state.open.add(k); render(); };
  $('tbody').addEventListener('click', e => { if (e.target.closest('input')) return; const tr = e.target.closest('tr.rx-row'); if (tr) toggle(tr); });
  $('tbody').addEventListener('keydown', e => { if (e.target.closest('input')) return; const tr = e.target.closest('tr.rx-row'); if (tr && (e.key === 'Enter' || e.key === ' ')){ e.preventDefault(); toggle(tr); } });
  $('tbody').addEventListener('change', e => {
    const rc = e.target.closest('input.recount');
    if (rc){
      const v = num(rc.value);
      if (v == null) state.recount.delete(rc.dataset.key); else state.recount.set(rc.dataset.key, {qty: v, fecha: new Date()});
      guardarRecuentos(); render(); refreshRecountStatus(); return;
    }
    const inp = e.target.closest('input.pmp'); if (!inp) return;
    const v = num(inp.value);
    if (v == null) state.pmpEdit.delete(inp.dataset.key); else state.pmpEdit.set(inp.dataset.key, v);
    render();
  });

  fillBodegas();
  fillLineas();
  render();
  refreshRecountStatus();
})();
