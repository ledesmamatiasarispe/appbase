// Extraído de Gestión Automotor frontend/app.js

/** Traer los datos de otra instalación (una versión vieja en otra carpeta, o la carpeta data de otra PC). Primero
 *  "Revisar" muestra qué se trae y qué hay acá; "Importar" REEMPLAZA lo de acá (antes lo respalda). Solo administrador. */
const tarjetaImportarVersion = () => `<div class="tarjeta" id="op-importar"><h3>Traer datos de otra instalación</h3>
  <p class="sutil">Para pasar a esta versión los datos de una instalación anterior: la carpeta donde estaba la versión vieja,
    o la carpeta <b>data</b> copiada de otra PC. Es una ruta de <b>esta PC servidor</b>, por ejemplo <code>C:\\GestionAutomotorAPB-viejo</code>.</p>
  <form id="f-importar" onsubmit="event.preventDefault(); revisarImportacion()"><div class="campos">
    <label class="ancho">Carpeta de la otra instalación <input name="ruta" required placeholder="C:\\...\\GestionAutomotorAPB" autocomplete="off"></label></div>
    <p class="error"></p><div class="botones"><button type="submit">Revisar</button></div></form>
  <div id="op-importar-resultado"></div></div>`;

async function revisarImportacion() {
  const f = $('#f-importar'), ruta = f.elements.ruta.value, caja = $('#op-importar-resultado');
  $('.error', f).textContent = ''; caja.innerHTML = '';
  try {
    const r = await api('/api/importar-version/revisar', { metodo: 'POST', datos: { ruta } });
    const filas = Object.keys(r.importar).map(k => `<tr><td>${esc(k)}</td><td><b>${miles(r.importar[k])}</b></td><td>${miles(r.actual[k])}</td></tr>`).join('');
    caja.innerHTML = `<p>Base encontrada: <code>${esc(r.ruta_base)}</code></p>
      <div class="tabla-wrap"><table><thead><tr><th></th><th>Se trae</th><th>Hay acá ahora</th></tr></thead><tbody>${filas}
        <tr><td>archivos adjuntos</td><td><b>${miles(r.adjuntos)}</b></td><td></td></tr></tbody></table></div>
      ${r.clave ? '' : '<p class="sutil">No trae la clave de secretos: la contraseña del mail habrá que escribirla de nuevo en Opciones.</p>'}
      <div class="recuadro aviso-rojo"><b>Importar reemplaza todo lo de acá</b> (no lo suma). Lo de acá queda respaldado en la carpeta data.
        Después se entra con los <b>usuarios y contraseñas de la base importada</b>.</div>
      <div class="botones"><button class="primario peligro" onclick="importarVersion(${esc(JSON.stringify(ruta))})">Importar y reemplazar</button></div>`;
  } catch (e) { $('.error', f).textContent = e.message; }
}

async function importarVersion(ruta) {
  if (!confirm('¿Reemplazar todos los datos de acá por los de la otra instalación? Lo de acá queda respaldado.')) return;
  try {
    const r = await api('/api/importar-version', { metodo: 'POST', datos: { ruta } });
    alert(`Datos importados. Lo que había antes quedó respaldado en:\n${r.respaldo}\n\nAhora entrá con un usuario de la base importada.`);
    salir();
  } catch (e) { avisar(e.message, true); }
}

