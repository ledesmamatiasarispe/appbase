'use strict';
// ── Chequeo de pasos huérfanos de la Ayuda (herramienta de desarrollo; index.html NO lo carga) ──
// Recorre cada pantalla y cada formulario del modal, y para cada uno cuenta los pasos de PASOS (ayuda.js) que
// corresponden (según su `si`) y no encuentran su elemento: esos son los "huérfanos", que en la app desaparecen sin
// avisar. Después hace lo mismo con el Tour completo, navegando como lo hace el tour. Deja el resultado como JSON en
// <pre id="chequeo-resultado"> (y en la consola), para leerlo con Edge headless --dump-dom.
// Cómo se corre: CLAUDEREADME.txt, punto 8.H. Usa los datos que haya en la base: con la semilla de prueba tiene que dar
// cero huérfanos; con la base vacía, solo los que dependen de datos (y las fichas no se pueden abrir).
(async function () {
  const esperar = ms => new Promise(r => setTimeout(r, ms));
  const salida = { escenarios: [], sinCubrir: [], tour: null, errores: [] };

  async function cargada() {
    for (let i = 0; i < 100; i++) {
      const v = document.getElementById('vista');
      if (S.usuario && v && v.textContent.trim() && !v.textContent.includes('Cargando…')) break;
      await esperar(100);
    }
    await esperar(500);   // los listados pintan la tabla en un segundo tiempo
  }
  async function abrir(ruta) {
    if (document.getElementById('modal').open) cerrarModal();
    irA(ruta);
    await cargada();
  }
  async function conModal(fn) {
    await fn();
    for (let i = 0; i < 50 && !document.querySelector('#modal[open] form[id]'); i++) await esperar(100);
    await esperar(300);
  }

  for (let i = 0; i < 100 && !S.usuario; i++) await esperar(100);
  if (!S.usuario) { salida.errores.push('Sin sesión: revisar el token del ?token='); return terminar(); }
  const admin = !!S.usuario.es_admin;

  // ── ejemplos para abrir fichas y formularios (con la base vacía quedan en null y esos escenarios se saltean) ──
  const ok = p => p.catch(() => []);
  const [pols, vehs, clis, flos, coms, docs, alertas, usuarios] = await Promise.all([
    ok(api('/api/polizas?incluir_anuladas=true')), ok(api('/api/vehiculos?incluir_baja=true')), ok(api('/api/clientes?incluir_baja=true')),
    ok(api('/api/flotas?incluir_baja=true')), ok(api('/api/companias?incluir_baja=true')), ok(api('/api/documentos')), ok(api('/api/alertas')),
    admin ? ok(api('/api/usuarios')) : []]);
  const id = x => x ? x.id : null;
  const E = {
    // la póliza más completa: no anulada ni renovada, con cuotas por pagar y con pagos
    poliza: id(pols.find(p => !p.anulada && p.estado !== 'renovada' && p.vencimiento_cuota && p.cuota_texto && !/^cuota 1 /i.test(p.cuota_texto)) || pols.find(p => !p.anulada && p.estado !== 'renovada')),
    polizaAnulada: id(pols.find(p => p.anulada)),
    polizaRenovada: id(pols.find(p => p.estado === 'renovada')),
    polizaPersonal: id(pols.find(p => !p.anulada && p.tipo === 'personal')),
    polizaBien: id(pols.find(p => !p.anulada && ['celular', 'hogar', 'consorcio'].includes(p.tipo))),
    vehiculo: id(vehs.find(v => v.activo && v.asegurado_por && !v.flota_id) || vehs.find(v => v.activo)),
    vehiculoBaja: id(vehs.find(v => !v.activo)),
    cliente: id(clis.filter(c => c.activo).sort((a, b) => b.vehiculos - a.vehiculos)[0]),
    flota: id(flos.find(f => f.activa && f.vehiculos)),
    compania: id(coms.find(c => c.activa && c.polizas) || coms[0]),
    documento: id(docs.find(d => d.estado !== 'renovado' && d.estado !== 'baja')),
    documentoConFoto: id(docs.find(d => d.foto && d.estado !== 'baja')),
    alertaCuota: alertas.find(a => a.tipo === 'cuota')?.poliza_id ?? null,
    alertaVigencia: alertas.find(a => a.tipo === 'vigencia')?.poliza_id ?? null,
    otroUsuario: usuarios.find(u => u.legajo !== S.usuario.legajo)?.legajo ?? null,
  };
  salida.ejemplos = E;

  // [nombre, ruta, clave esperada, abrir el modal (opcional), necesita]
  const ESC = [
    ['Inicio', 'inicio', 'inicio'],
    ['Alertas', 'alertas', 'alertas'],
    ['Cronograma (mes)', 'cronograma', 'cronograma', null, true, () => { S.crono.vista = 'mes'; }],
    ['Cronograma (año)', 'cronograma', 'cronograma-anio', null, true, () => { S.crono.vista = 'anio'; }],
    ['Clientes', 'clientes', 'clientes'],
    ['Ficha de cliente', `clientes/${E.cliente}`, 'clientes-ficha', null, E.cliente],
    ['Vehículos', 'vehiculos', 'vehiculos'],
    ['Ficha de vehículo', `vehiculos/${E.vehiculo}`, 'vehiculos-ficha', null, E.vehiculo],
    ['Ficha de vehículo de baja', `vehiculos/${E.vehiculoBaja}`, 'vehiculos-ficha', null, E.vehiculoBaja],
    ['Flotas', 'flotas', 'flotas'],
    ['Ficha de flota', `flotas/${E.flota}`, 'flotas-ficha', null, E.flota],
    ['Pólizas', 'polizas', 'polizas'],
    ['Ficha de póliza', `polizas/${E.poliza}`, 'polizas-ficha', null, E.poliza],
    ['Ficha de póliza anulada', `polizas/${E.polizaAnulada}`, 'polizas-ficha', null, E.polizaAnulada],
    ['Ficha de póliza renovada', `polizas/${E.polizaRenovada}`, 'polizas-ficha', null, E.polizaRenovada],
    ['Ficha de póliza personal', `polizas/${E.polizaPersonal}`, 'polizas-ficha', null, E.polizaPersonal],
    ['Ficha de póliza de un bien', `polizas/${E.polizaBien}`, 'polizas-ficha', null, E.polizaBien],
    ['Compañías', 'companias', 'companias'],
    ['Ficha de compañía', `companias/${E.compania}`, 'companias-ficha', null, E.compania],
    ['Documentación', 'documentacion', 'documentacion'],
    ['Usuarios', 'usuarios', admin ? 'usuarios' : 'inicio'],
    ['Opciones', 'opciones', 'opciones'],
    // formularios
    ['Modal: cliente (alta)', 'clientes', 'f-cliente', () => modalCliente()],
    ['Modal: cliente (edición)', `clientes/${E.cliente}`, 'f-cliente', () => modalCliente(S.actual), E.cliente],
    ['Modal: vehículo (alta)', 'vehiculos', 'f-vehiculo', () => modalVehiculo()],
    ['Modal: vehículo (alta en flota)', `flotas/${E.flota}`, 'f-vehiculo', () => modalVehiculo(null, { flota_id: S.actual.id, flota: S.actual.nombre }), E.flota],
    ['Modal: vehículo (edición)', `vehiculos/${E.vehiculo}`, 'f-vehiculo', () => modalVehiculo(S.actual), E.vehiculo],
    ['Modal: venta', `vehiculos/${E.vehiculo}`, 'f-venta', () => modalVenta(S.actual), E.vehiculo],
    ['Modal: foto extra', `vehiculos/${E.vehiculo}`, 'f-foto', () => modalFotoExtra(S.actual.id), E.vehiculo],
    ['Modal: flota (alta)', 'flotas', 'f-flota', () => modalFlota()],
    ['Modal: flota (edición)', `flotas/${E.flota}`, 'f-flota', () => modalFlota(S.actual), E.flota],
    ['Modal: vincular vehículo', `flotas/${E.flota}`, 'f-vincular', () => modalVincular(S.actual), E.flota],
    ['Modal: sacar de la flota', `flotas/${E.flota}`, 'f-quitar', () => { const v = S.actual.vehiculos.find(x => x.pertenece); modalQuitar(S.actual.id, v.vehiculo_id, v.dominio); }, E.flota],
    ['Modal: póliza (alta)', 'polizas', 'f-poliza', () => modalPoliza()],
    ['Modal: póliza (edición)', `polizas/${E.poliza}`, 'f-poliza', () => modalPoliza(S.actual), E.poliza],
    ['Modal: póliza personal (edición)', `polizas/${E.polizaPersonal}`, 'f-poliza', () => modalPoliza(S.actual), E.polizaPersonal],
    ['Modal: póliza de un bien (edición)', `polizas/${E.polizaBien}`, 'f-poliza', () => modalPoliza(S.actual), E.polizaBien],
    ['Modal: póliza (renovación)', `polizas/${E.poliza}`, 'f-poliza', () => modalPoliza(S.actual, { renovar: true }), E.poliza],
    ['Modal: renovar desde la alerta', 'alertas', 'f-poliza', () => renovarDesdeAlerta(E.alertaVigencia), E.alertaVigencia],
    ['Modal: anular', `polizas/${E.poliza}`, 'f-anular', () => modalAnular(S.actual), E.poliza],
    ['Modal: pago', `polizas/${E.poliza}`, 'f-pago', () => modalPago(S.actual), E.poliza],
    ['Modal: pago desde la alerta', 'alertas', 'f-pago', () => pagarDesdeAlerta(E.alertaCuota), E.alertaCuota],
    ['Modal: documento (alta)', `vehiculos/${E.vehiculo}`, 'f-documento', () => nuevoDocumento({ vehiculo_id: S.actual.id }), E.vehiculo],
    ['Modal: documento (corrección)', 'documentacion', 'f-documento', () => editarDocumento(E.documento), E.documento],
    ['Modal: documento (renovación)', 'documentacion', 'f-doc-renovar', () => renovarDocumento(E.documento), E.documento],
    ['Modal: detalle del documento', 'documentacion', 'f-doc-foto', () => verDocumento(E.documento), E.documento],
    ['Modal: detalle del documento (con foto)', 'documentacion', 'f-doc-foto', () => verDocumento(E.documentoConFoto), E.documentoConFoto],
    ['Modal: tipo de documentación', 'opciones', 'f-doc-tipo', () => modalTipoDocumento(), admin || null],
    ['Modal: compañía (alta)', 'companias', 'f-compania', () => modalCompania(), admin || null],
    ['Modal: compañía (edición)', `companias/${E.compania}`, 'f-compania', () => modalCompania(S.actual), admin && E.compania],
    ['Modal: usuario (alta)', 'usuarios', 'f-usuario', () => modalUsuario(), admin || null],
    ['Modal: usuario (edición)', 'usuarios', 'f-usuario', () => modalUsuario(E.otroUsuario), admin && E.otroUsuario],
    ['Modal: restablecer contraseña', 'usuarios', 'f-restablecer', () => modalRestablecer(E.otroUsuario), admin && E.otroUsuario],
    ['Modal: cambiar contraseña', 'inicio', 'f-password', () => modalPassword(false)],
  ];

  const cubiertas = new Set();
  for (const [nombre, ruta, clave, fn, necesita, antes] of ESC) {
    if (necesita === null || necesita === false) { salida.escenarios.push({ nombre, salteado: 'sin datos o sin permiso' }); continue; }
    try {
      if (antes) antes();
      await abrir(ruta);
      if (fn) await conModal(fn);
      const r = Ayuda.revisar();
      if (r.clave !== clave) r.error = `se esperaba la clave ${clave}`;
      if (fn && !document.querySelector('#modal .ayuda-boton-modal')) r.error = (r.error ? r.error + '; ' : '') + 'el formulario no tiene su botón Ayuda';
      if (r.huerfanos.length) r.pantalla = `${location.hash} · ${document.getElementById('vista').textContent.replace(/\s+/g, ' ').trim().slice(0, 160)}`;
      cubiertas.add(r.clave);
      salida.escenarios.push({ nombre, ...r });
    } catch (e) { salida.escenarios.push({ nombre, error: String(e && e.message || e) }); }
  }
  if (document.getElementById('modal').open) cerrarModal();
  S.crono.vista = 'mes';
  salida.sinCubrir = Ayuda.claves().filter(k => !cubiertas.has(k));

  // ── el tour completo, paso por paso, navegando como el tour ──
  const tour = { total: 0, huerfanos: [] };
  for (const p of Ayuda.pasosTour().filter(Ayuda.corresponde)) {
    tour.total++;
    let destino = typeof p.ir === 'function' ? await p.ir() : p.ir;
    if (destino && (location.hash.slice(1) || 'inicio') !== destino) await abrir(destino);
    else await esperar(200);
    if (p.el && !Ayuda.elementos(p).length) tour.huerfanos.push(`${p.titulo} (${destino})`);
  }
  salida.tour = tour;
  terminar();

  function terminar() {
    const total = salida.escenarios.reduce((n, e) => n + (e.huerfanos?.length || 0), 0);
    salida.resumen = { escenarios: salida.escenarios.length, huerfanos: total, tourHuerfanos: salida.tour?.huerfanos.length ?? null,
      sinCubrir: salida.sinCubrir.length, conError: salida.escenarios.filter(e => e.error).length };
    const pre = document.createElement('pre');
    pre.id = 'chequeo-resultado';
    pre.textContent = JSON.stringify(salida, null, 1);
    document.body.appendChild(pre);
    console.log('CHEQUEO_AYUDA', JSON.stringify(salida.resumen));
  }
})();
