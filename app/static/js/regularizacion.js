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
      por:t.col('Contado por'), fecha:t.col('Fecha y hora del conteo','Fecha del conteo','Fecha')};
    const out = [];
    for (const r of t.rows){
      const code = String(r[c.code] ?? '').trim(); if (!code) continue;
      out.push({code, key:keyOf(code), name:r[c.name] ?? '', stock:num(r[c.stock]), estado:c.estado >= 0 ? r[c.estado] ?? '' : '',
        por:c.por >= 0 ? r[c.por] ?? '' : '', fecha:c.fecha >= 0 ? parseDate(r[c.fecha]) : null});
    }
    return out;
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

  // ---------- Conteo del sistema ----------
  // La página trae el conteo de "Stock y conteo" como JSON: [código, nombre, stock físico, estado, contado por, fecha y hora]
  function conteoDelSistema(){
    const el = document.getElementById('regx-conteo');
    let data = [];
    try { data = JSON.parse(el ? el.textContent : '[]'); } catch(_){ data = []; }
    return data.map(([code, name, stock, estado, por, fecha]) => ({code, key:keyOf(code), name, stock, estado, por, fecha:parseDate(fecha)}));
  }

  // ---------- Estado ----------
  const state = {stock:conteoDelSistema(), mov:[], view:'reg', filter:{reg:'all', zero:'all', check:'all'}, mov2:null, ajSel:null, checkRows:[], docGroups:[],
    sort:{reg:{k:'code', d:1}, zero:{k:'fecha', d:1}, check:{k:'code', d:1}}, open:new Set(), pmpEdit:new Map(), rows:[], zero:[]};

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
    // 3. Unidad de medida
    if (!cause && s.stock > EPS && sys > EPS){
      const r = s.stock / sys, f = [10, 12, 20, 24, 25, 50, 100, 1000].find(x => near(r, x) || near(1 / r, x));
      if (f){ const um = docs.length ? docs[docs.length - 1].um : ''; cause = 'um';
        obs.push(`Lo contado es ${near(r, f) ? f + ' veces' : '1/' + f + ' de'} lo que tiene Defontana${um ? ' (en ' + esc(um) + ')' : ''}: posible conteo en otra unidad (caja, paquete, rollo, metro).`); }
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
      return {code:main.code, key:main.key, name:main.name, por:main.por, estado:main.estado,
        stock: done.length ? done.reduce((a, x) => a + x.stock, 0) : null,
        fecha: done.length ? new Date(Math.max(...done.map(x => +x.fecha))) : null,
        variants: list.map(x => x.code), nCounted: done.length};
    };
    const inBod = m => bod === '*' || (m.kind === 'in' ? m.dest : m.orig) === bod;
    const build = (s, docs) => {
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
      let sysNow = null, sysAtCount = null;
      for (const list of byArt.values()){
        const last = list[list.length - 1];
        if (last.saldo != null) sysNow = (sysNow || 0) + last.saldo;
        if (!counted) continue;
        let li = null; list.forEach((m, j) => { if (m.fecha && !after(m)) li = j; });
        let v = null;
        if (li != null) v = list[li].saldo;
        else { const f = list[0]; if (f.saldo != null) v = f.saldo - (f.kind === 'in' ? f.qty : -f.qty); }
        if (v != null) sysAtCount = (sysAtCount || 0) + v;
      }
      // Saldo final calculado con los documentos (no depende del orden de las filas del informe)
      let sysCalc = null, toOther = 0;
      if (counted && sysAtCount != null){
        sysCalc = sysAtCount;
        for (const m of docs) if (m.fecha && after(m)){
          sysCalc += m.kind === 'in' ? m.qty : -m.qty;
          if (!m._aj && !inBod(m) && m.kind === 'in') toOther += m.qty;
        }
      }
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
      const dx = counted ? diagnose(s, docs.filter(m => !m._aj), after, diff, sysAtCount, sameNet, zeros) : {cause:null, obs:[]};
      if (dx.cause === 'late' || dx.cause === 'sameday') st = 'check';
      return {cause:dx.cause, obs:dx.obs, alias, viaName, nCounted: s ? s.nCounted : 0, key, code: s ? s.code : docs[0].art, name: s ? s.name : docs[0].desc, s, counted, docs, ins, outs, sameDay, aj, ajVal, ajDocs, sysCalc, toOther,
        sysAtCount, sysNow, realNow, diff, st, pmp, edited, pmpSrc: edited ? 'Ingresado a mano' : pm ? pm.src : 'Sin costo en Defontana',
        valor: diff != null && Math.abs(diff) > EPS && pmp != null ? diff * pmp : (st === 'ok' ? 0 : null), zeros};
    };
    const seen = new Set();
    const rows = [...groups.values()].map(list => { const s = mergeGroup(list); seen.add(s.key); return build(s, byKey.get(s.key) || []); });
    for (const [k, docs] of byKey) if (!seen.has(k) && docs.some(inBod)) rows.push(build(null, docs));

    const names = new Map(rows.map(r => [r.key, r.name]));
    const zero = [];
    for (const [k, docs] of byKey) docs.forEach((m, j) => {
      if (!inBod(m) || m.valor == null || Math.abs(m.valor) > EPS || m.qty <= EPS) return;
      const pm = pmpOf(docs, j - 1 >= 0 ? j - 1 : null);
      const edited = state.pmpEdit.has(k);
      const pmp = edited ? state.pmpEdit.get(k) : pm ? pm.v : null;
      zero.push({key:k, m, code:m.art, name:m.desc || names.get(k) || '', pmp, edited,
        pmpSrc: edited ? 'Ingresado a mano' : pm ? pm.src : 'Sin costo en Defontana', valor: pmp != null ? pmp * m.qty : null});
    });
    return {rows, zero, orphan: [...byKey.keys()].filter(k => !seen.has(k)).length};
  }

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
    ['alias', 'Código escrito distinto', r => r.alias.length > 0 || r.viaName || r.nCounted > 1, 'var(--accent)']
  ];
  const ZERO_FILTERS = [
    ['all', 'Todos', z => true, null],
    ['in', 'Ingresos a $0', z => z.m.kind === 'in', 'var(--in)'],
    ['out', 'Egresos a $0', z => z.m.kind === 'out', 'var(--out)'],
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
    ['contado', 'Contado', 'num', r => r.s ? r.s.stock : null],
    ['need', 'Había que ajustar', 'num', r => r.diff],
    ['aj', 'Se ajustó', 'num', r => r.aj],
    ['ck', 'Resultado', '', r => r.ck],
    ['obs', 'Detalle', '', r => r.ck],
    ['exp', 'Debería tener Defontana', 'num', r => r.expected],
    ['now', 'Tiene Defontana', 'num', r => r.sysCalc ?? r.sysNow],
    ['gap', 'Diferencia que queda', 'num', r => r.gap]
  ];
  function checkRow(r){
    const [cls, label, stripe] = CHECK[r.ck];
    return `<tr class="rx-row s-${stripe}${state.open.has(r.key) ? ' open' : ''}" data-key="${esc(r.key)}" tabindex="0">
      <td><div class="code">${esc(r.code)}</div><div class="pname">${esc(r.name)}</div>${aliasNote(r)}</td>
      <td class="num">${r.counted ? fmt(r.s.stock) + '<div class="small">' + fmtDate(r.s.fecha) + '</div>' : '—'}</td>
      <td class="num diff ${r.diff > EPS ? 'plus' : r.diff < -EPS ? 'minus' : 'mut'}">${r.diff == null ? '—' : sgn(r.diff)}</td>
      <td class="num diff ${r.aj > EPS ? 'plus' : r.aj < -EPS ? 'minus' : 'mut'}">${Math.abs(r.aj) > EPS ? sgn(r.aj) + '<div class="small">' + money(r.ajVal) + '</div>' : '—'}</td>
      <td><span class="pill ${cls}">${label}</span></td>
      <td class="obs"><div class="why">${r.cobs[0]}</div>${r.cobs.length > 1 ? '<div class="more-obs">' + r.cobs.slice(1).join('<br>') + '</div>' : ''}</td>
      <td class="num">${fmt(r.expected)}</td>
      <td class="num">${fmt(r.sysCalc ?? r.sysNow)}${r.sysCalc != null && r.sysNow != null && Math.abs(r.sysCalc - r.sysNow) > EPS ? '<div class="small">informe: ' + fmt(r.sysNow) + '</div>' : ''}</td>
      <td class="num diff ${r.gap == null || Math.abs(r.gap) <= EPS ? 'mut' : 'minus'}">${r.gap == null ? '—' : Math.abs(r.gap) <= EPS ? '0' : sgn(r.gap)}</td></tr>`;
  }

  const REG_COLS = [
    ['code', 'Producto', '', r => r.code],
    ['contado', 'Contado', 'num', r => r.s ? r.s.stock : null],
    ['sys', 'Defontana al conteo', 'num', r => r.sysAtCount],
    ['diff', 'Diferencia', 'num', r => r.diff],
    ['st', 'Qué hacer', '', r => r.st],
    ['obs', 'Por qué está descuadrado', '', r => r.cause ? CAUSES[r.cause] : null],
    ['pmp', 'PMP', 'num', r => r.pmp],
    ['valor', 'Valor ajuste', 'num', r => r.valor],
    ['real', 'Stock real hoy', 'num', r => r.realNow],
    ['now', 'Defontana hoy', 'num', r => r.sysNow]
  ];
  const ZERO_COLS = [
    ['fecha', 'Fecha', '', z => z.m.fecha],
    ['doc', 'Documento', '', z => z.m.tipo],
    ['code', 'Producto', '', z => z.code],
    ['kind', 'Tipo', '', z => z.m.kind],
    ['qty', 'Cantidad', 'num', z => z.m.qty],
    ['pmp', 'PMP', 'num', z => z.pmp],
    ['valor', 'Valor que debió tener', 'num', z => z.valor]
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
    const [cls, label] = ACTION[r.st];
    const d = r.diff;
    const qty = (r.st === 'up' || r.st === 'down') ? ' ' + fmt(Math.abs(d)) : '';
    const obsCell = r => {
      if (!r.cause){
        if (r.st === 'nodata') return '<span class="mut">Sin documentos en el informe: no se conoce el saldo de Defontana.</span>';
        if (r.st === 'nofile') return '<span class="mut">Tiene documentos en Defontana pero no está en el archivo de conteo.</span>';
        return '';
      }
      const [main, ...rest] = r.obs;
      return `<div class="cause">${CAUSES[r.cause]}</div><div class="why">${main}</div>${rest.length ? '<div class="more-obs">' + rest.join('<br>') + '</div>' : ''}`;
    };
    return `<tr class="rx-row s-${r.st}${state.open.has(r.key) ? ' open' : ''}" data-key="${esc(r.key)}" tabindex="0">
      <td><div class="code">${esc(r.code)}</div><div class="pname">${esc(r.name)}</div>${aliasNote(r)}</td>
      <td class="num">${r.counted ? fmt(r.s.stock) + '<div class="small">' + fmtDate(r.s.fecha) + '</div>' : '<span class="mut">—</span>'}</td>
      <td class="num">${fmt(r.sysAtCount)}</td>
      <td class="num diff ${d > EPS ? 'plus' : d < -EPS ? 'minus' : 'mut'}">${d == null ? '—' : sgn(d)}</td>
      <td><span class="pill ${cls}">${label}${qty}</span>${r.sameDay && r.counted ? '<span class="flag" title="Hay documentos el mismo día del conteo">· mismo día</span>' : ''}</td>
      <td class="obs">${obsCell(r)}</td>
      <td class="num">${r.st === 'up' || r.st === 'down' || r.st === 'check' ? pmpInput(r.key, r.pmp, r.edited, r.code) : '<span class="mut">' + (r.pmp != null ? money(r.pmp) : '—') + '</span>'}</td>
      <td class="num diff ${r.valor > 0.5 ? 'plus' : r.valor < -0.5 ? 'minus' : 'mut'}">${r.st === 'up' || r.st === 'down' || r.st === 'check' ? money(r.valor) : '—'}</td>
      <td class="num">${fmt(r.realNow)}${r.ins || r.outs ? '<div class="small">' + (r.ins ? '<span class="plus">+' + fmt(r.ins) + '</span> ' : '') + (r.outs ? '<span class="minus">−' + fmt(r.outs) + '</span>' : '') + ' desde el conteo</div>' : ''}</td>
      <td class="num">${fmt(r.sysNow)}</td></tr>`;
  }
  function zeroRow(z){
    return `<tr>
      <td class="num" style="text-align:left">${fmtDate(z.m.fecha)}</td>
      <td>${esc(z.m.tipo)}<div class="small">Folio ${esc(z.m.folio)}${z.m.ref ? ' · ' + esc(z.m.ref) : ''}</div></td>
      <td><div class="code">${esc(z.code)}</div><div class="pname">${esc(z.name)}</div></td>
      <td><span class="pill ${z.m.kind === 'in' ? 'a-up' : 'a-down'}">${z.m.kind === 'in' ? 'Ingreso' : 'Egreso'}</span></td>
      <td class="num">${fmt(z.m.qty)} <span class="small">${esc(z.m.um)}</span></td>
      <td class="num">${pmpInput(z.key, z.pmp, z.edited, z.code)}<div class="small">${esc(z.pmpSrc)}</div></td>
      <td class="num diff">${money(z.valor)}</td></tr>`;
  }

  function detail(r){
    if (!r.docs.length) return `<tr class="detail"><td colspan="9"><span class="note">Este código no tiene documentos en el informe de Defontana, así que no se conoce su saldo en el sistema. Revisa su stock directamente en Defontana.</span></td></tr>`;
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
    return `<tr class="detail"><td colspan="9">${head}<table class="det"><thead><tr><th>Fecha</th><th>Documento</th><th>Referencia</th><th class="num">Cantidad</th><th class="num">Valor</th><th class="num">Saldo</th><th class="num">PMP</th><th>Respecto al conteo</th></tr></thead><tbody>${rows}</tbody></table></td></tr>`;
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
    box.innerHTML = `<div class="ajbox"><h3>Documentos de ajuste</h3>
      <p class="note">${auto.length ? 'Encontré estos documentos que calzan con las diferencias del conteo. Marca o desmarca los que corresponden a ajustes de inventario.' : 'No encontré documentos que calcen con las diferencias. Marca abajo los documentos de ajuste.'}</p>
      ${auto.map(item).join('')}
      ${rest.length ? `<details${auto.length ? '' : ' open'}><summary>Otros documentos posteriores al conteo (${fmt(rest.length)})</summary><div class="ajlist">${rest.map(item).join('')}</div></details>` : ''}</div>`;
  }

  function render(){
    const base = compute(state.mov);
    state.rows = base.rows; state.zero = base.zero; state.orphan = base.orphan;
    computeCheck();
    const reg = state.view === 'reg', chk = state.view === 'check';
    document.querySelectorAll('.view').forEach(b => b.setAttribute('aria-selected', b.dataset.view === state.view));
    $('checkPanel').hidden = !chk;
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
    $('chips').innerHTML = F.map(([k, label, f, color]) => {
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
    const rows = sorted(all.filter(r => f(r) && (!q || strip(r.code).includes(q) || strip(r.name).includes(q) || (zer && strip(r.m.tipo + ' ' + r.m.ref + ' ' + r.m.folio).includes(q)))), cols);
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
      ? '<b>Cómo se calcula.</b> Diferencia = Contado − Defontana al conteo. “Defontana al conteo” es el Saldo Inventario del último documento anterior al conteo (es el saldo del producto en todas las bodegas). Si es positiva hay que <b>aumentar</b> (entrada por ajuste); si es negativa, <b>disminuir</b> (salida por ajuste). Como el ajuste se hace hoy, la cantidad también es igual a Stock real hoy − Defontana hoy. El PMP es Valor Inventario / Saldo Inventario del último documento con saldo; puedes corregirlo en la tabla. Los códigos se cruzan sin considerar mayúsculas, tildes, espacios, puntos, comas, guiones, guiones bajos ni ceros a la izquierda; si un artículo de Defontana no cruza por código, se cruza por nombre. Haz clic en un producto para ver sus documentos.'
      : '<b>Cómo se calcula.</b> Son los documentos cuyo “Valor Movimiento” es $0. El valor que debió tener = cantidad × PMP del producto antes del documento (si no hay, el primero que aparece después). Un egreso a $0 suele ocurrir cuando el producto no tenía saldo o su PMP era $0.';
  }

  // ---------- Exportar ----------
  const regExport = r => ({
    'Código': r.code, 'Nombre': r.name, 'Otras formas del código': r.alias.join(', ') + (r.viaName ? (r.alias.length ? ' · ' : '') + 'cruzado por nombre' : ''), 'Qué hacer': ACTION[r.st][1], 'Causa probable': r.cause ? CAUSES[r.cause] : '',
    'Observaciones': r.obs.map(x => x.replace(/<[^>]+>/g, '')).join(' '),
    'Cantidad a ajustar': r.diff != null && Math.abs(r.diff) > EPS ? Math.abs(r.diff) : '',
    'Contado': r.s ? r.s.stock : '', 'Fecha conteo': r.counted ? fmtDate(r.s.fecha, true) : '',
    'Defontana al conteo': r.sysAtCount ?? '', 'Diferencia': r.diff ?? '',
    'PMP': r.pmp != null ? Math.round(r.pmp * 100) / 100 : '', 'Origen PMP': r.pmpSrc,
    'Valor ajuste': r.valor != null ? Math.round(r.valor) : '',
    'Stock real hoy': r.realNow ?? '', 'Defontana hoy': r.sysNow ?? ''
  });
  const zeroExport = z => ({
    'Fecha': fmtDate(z.m.fecha), 'Documento': z.m.tipo, 'Folio': z.m.folio, 'Referencia': z.m.ref,
    'Código': z.code, 'Nombre': z.name, 'Tipo': z.m.kind === 'in' ? 'Ingreso' : 'Egreso', 'Cantidad': z.m.qty,
    'PMP': z.pmp != null ? Math.round(z.pmp * 100) / 100 : '', 'Origen PMP': z.pmpSrc, 'Valor que debió tener': z.valor != null ? Math.round(z.valor) : ''
  });
  const checkExport = r => ({
    'Código': r.code, 'Nombre': r.name, 'Resultado': CHECK[r.ck][1], 'Detalle': r.cobs.map(x => x.replace(/<[^>]+>/g, '')).join(' '),
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
  $('summary').addEventListener('click', e => { const b = e.target.closest('[data-go]'); if (!b) return; state.filter[state.view] = b.dataset.go; render(); });
  $('chips').addEventListener('click', e => { const b = e.target.closest('.chip'); if (!b) return; state.filter[state.view] = b.dataset.f; render(); });
  $('thead').addEventListener('click', e => {
    const th = e.target.closest('th[data-sort]'); if (!th) return;
    const s = state.sort[state.view];
    if (s.k === th.dataset.sort) s.d = -s.d; else { s.k = th.dataset.sort; s.d = 1; }
    render();
  });
  ['optBodega','optSame','optAprob'].forEach(id => $(id).addEventListener('change', render));
  $('optCause').addEventListener('change', () => { state.cause = $('optCause').value; render(); });
  let t; $('optSearch').addEventListener('input', () => { clearTimeout(t); t = setTimeout(render, 150); });
  const toggle = tr => { const k = tr.dataset.key; state.open.has(k) ? state.open.delete(k) : state.open.add(k); render(); };
  $('tbody').addEventListener('click', e => { if (e.target.closest('input')) return; const tr = e.target.closest('tr.rx-row'); if (tr) toggle(tr); });
  $('tbody').addEventListener('keydown', e => { if (e.target.closest('input')) return; const tr = e.target.closest('tr.rx-row'); if (tr && (e.key === 'Enter' || e.key === ' ')){ e.preventDefault(); toggle(tr); } });
  $('tbody').addEventListener('change', e => {
    const inp = e.target.closest('input.pmp'); if (!inp) return;
    const v = num(inp.value);
    if (v == null) state.pmpEdit.delete(inp.dataset.key); else state.pmpEdit.set(inp.dataset.key, v);
    render();
  });

  fillBodegas();
  render();
})();
