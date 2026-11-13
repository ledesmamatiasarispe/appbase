// Extraído de UltraMantenimiento frontend/app.js: hoja para imprimir con casilleros.

/** La lista del mes para llevar al taller: en pantalla no se ve, y al imprimir reemplaza a todo lo demás.
 *  Las columnas de la derecha quedan en blanco para completarlas a mano y registrarlas después. */
function hojaListaDelMes(p, hoy) {
  const blancos = '<td class="casilla">☐</td><td></td><td></td><td></td>';
  const fila = (codigo, equipo, seccion, cuando, responsable) => `<tr><td><b>${esc(codigo)}</b></td><td>${esc(equipo)}</td>
    <td>${esc(seccion)}</td><td>${esc(cuando)}</td><td>${esc(responsable || '')}</td>${blancos}</tr>`;
  const filas = [
    ...p.atrasados.map(t => fila(t.codigo, t.equipo, t.seccion, `${t.frecuencia} · atrasada de ${MESES_LARGOS[t.mes - 1].toLowerCase()}`, t.responsable)),
    ...p.este_mes.map(t => fila(t.codigo, t.equipo, t.seccion, t.frecuencia + (t.faltan > 1 ? ` · ${t.faltan} veces` : ''), t.responsable)),
    ...p.por_horas.filter(s => s.estado === 'vencido' || s.estado === 'proximo').map(s => fila(s.codigo, s.equipo, s.seccion,
      `c/ ${miles(s.cada_horas)} h · ${s.estado === 'vencido' ? 'vencido' : 'a las ' + miles(s.proximo) + ' h'}`, s.responsable)),
  ];
  return `<div class="hoja-lista">
    <h2>Tareas de mantenimiento · ${MESES_LARGOS[hoy.getMonth()]} ${hoy.getFullYear()}</h2>
    <p class="sutil">Impreso el ${hoy.toLocaleDateString('es-AR')}. Marcar lo hecho y registrarlo después en la app.</p>
    <table><thead><tr><th>Tarea</th><th>Equipo</th><th>Mantenimiento</th><th>Frecuencia</th><th>Responsable</th>
      <th>Hecho</th><th class="fecha">Fecha</th><th class="realizo">Realizó</th><th class="obs">Observaciones</th></tr></thead>
    <tbody>${filas.join('') || '<tr><td colspan="9" class="vacio">No hay tareas pendientes este mes.</td></tr>'}</tbody></table></div>`;
}

function imprimirListaDelMes() {
  document.body.classList.add('imprimiendo-lista');
  addEventListener('afterprint', () => document.body.classList.remove('imprimiendo-lista'), { once: true });
  print();
}

