'use strict';
// ── Módulo de ejemplo: NOTAS (pantalla) ──
// Se carga después de nucleo.js y ayuda.js: usa sus utilidades (api, abrirModal, alEnviar, esc...) y registra lo suyo
// en VISTAS, Nucleo.tarjetasOpciones y Ayuda. Todo lo global de un módulo lleva su nombre (notas...) para que dos
// módulos de apps distintas no choquen si se fusionan.

const PRIORIDADES_NOTA = { alta: ['rojo', 'Alta'], normal: ['azul', 'Normal'], baja: ['', 'Baja'] };

VISTAS.notas = async () => {
  const notas = await api('/api/notas');
  S.notas = notas;
  $('#vista').innerHTML = `
    <div class="encabezado"><h2>Notas</h2><div class="botones"><button class="primario" onclick="modalNota()">Nueva nota</button></div></div>
    <p class="sutil">Módulo de ejemplo: el molde para hacer uno nuevo. Archivar es de administrador y no borra.</p>
    <div class="tarjeta tabla-wrap">${casillaOcultos('notas', notas.filter(n => !n.activa).length)}<table ${tablaOcultos('notas')}>
      <thead><tr><th>Título</th><th>Prioridad</th><th>Vence</th><th>Creada por</th><th></th></tr></thead><tbody>
      ${notas.map(n => `<tr class="${n.activa ? '' : 'baja'}"><td><b>${esc(n.titulo)}</b><div class="sutil nota-texto">${esc(n.texto)}</div></td>
        <td><span class="chip ${PRIORIDADES_NOTA[n.prioridad][0]}">${PRIORIDADES_NOTA[n.prioridad][1]}</span></td>
        <td>${fecha(n.vence) || '—'}</td><td>${esc(n.creado_por || '')}</td>
        <td class="botones">${n.activa ? `<button class="chico" onclick="modalNota(${n.id})">Editar</button>` : ''}
          ${soloAdmin(`<button class="chico ${n.activa ? 'peligro' : ''}" onclick="archivarNota(${n.id}, ${n.activa})">${n.activa ? 'Archivar' : 'Reactivar'}</button>`)}</td></tr>`).join('')
        || '<tr><td colspan="5" class="vacio">Todavía no hay notas.</td></tr>'}
    </tbody></table></div>`;
};

function modalNota(id) {
  const n = id ? S.notas.find(x => x.id === id) : null;
  abrirModal(`<h2>${n ? 'Editar nota' : 'Nueva nota'}</h2>
    <form id="f-nota"><div class="campos">
      <label class="ancho">Título <input name="titulo" value="${esc(n?.titulo || '')}" required maxlength="120"></label>
      <label class="ancho">Texto <textarea name="texto">${esc(n?.texto || '')}</textarea></label>
      <label>Prioridad <select name="prioridad">${opcionesSelect(Object.entries(PRIORIDADES_NOTA).map(([k, [, t]]) => [k, t]), n?.prioridad || 'normal', null)}</select></label>
      <label>Vence <input name="vence" type="date" value="${esc(n?.vence || '')}"></label>
    </div><p class="error"></p>
    <div class="botones"><button class="primario" type="submit">Guardar</button><button type="button" onclick="cerrarModal()">Cancelar</button></div></form>`);
  alEnviar($('#f-nota'), async d => {
    await api(n ? '/api/notas/' + id : '/api/notas', { metodo: n ? 'PUT' : 'POST', datos: d });
    cerrarModal(); avisar('Nota guardada.'); irA('notas');
  });
}

async function archivarNota(id, activa) {
  if (activa && !confirm('¿Archivar esta nota? Sale del listado (se ve con "Ver ocultos").')) return;
  try { await api(`/api/notas/${id}/${activa ? 'archivar' : 'reactivar'}`, { metodo: 'POST' }); irA('notas'); }
  catch (e) { avisar(e.message, true); }
}

// Una tarjeta del módulo en Opciones (orden: dónde va entre las del núcleo y las de otros módulos).
Nucleo.tarjetasOpciones.push({
  orden: 40,
  html: async () => `<div class="tarjeta" id="op-notas"><h3>Notas</h3>
    <p class="sutil">Ejemplo de tarjeta de un módulo en Opciones: acá iría su configuración.</p></div>`,
});

// La ayuda de la pantalla y de su formulario, y un paso en el Tour completo.
Ayuda.pasos.notas = () => [
  { titulo: 'Notas', texto: 'Un módulo de ejemplo: muestra cómo se arma una pantalla sobre el núcleo.' },
  { el: () => Ayuda.h.boton('Nueva nota'), titulo: 'Nueva nota', texto: 'Título, texto, prioridad y vencimiento. El servidor valida todo y su mensaje aparece en el formulario.' },
  { el: () => Ayuda.h.enVista('.ver-ocultos'), titulo: 'Ver ocultos', texto: 'Las notas archivadas no se borran: aparecen tachadas al marcar esta casilla.' },
];
Ayuda.pasos['f-nota'] = () => [
  { el: () => Ayuda.h.campo('titulo'), titulo: 'Título', texto: 'Obligatorio, hasta 120 caracteres.' },
  { el: () => Ayuda.h.campo('prioridad'), titulo: 'Prioridad', texto: 'Ordena el listado: primero las de prioridad alta.' },
];
Ayuda.tour.push({ ir: 'notas', el: () => Ayuda.h.menu('notas'), titulo: 'Notas', texto: 'La pantalla del módulo de ejemplo.' });
