// Extraído de UltraMantenimiento frontend/app.js: gráfico de líneas o barras en SVG, sin librerías.

function graficoSVG(d) {
  const filas = d.filas, u = d.unidad ? ' ' + d.unidad : '';
  const num = v => Number(v).toLocaleString('es-AR', { maximumFractionDigits: 2 });
  if (d.forma === 'torta') {
    const total = filas.reduce((t, [, v]) => t + v, 0) || 1;
    const cx = 120, cy = 120, r = 105;
    let ang = -Math.PI / 2;
    const porciones = filas.map(([, v], i) => {
      const a2 = ang + 2 * Math.PI * v / total, color = COLORES[i % COLORES.length];
      const p = v >= total ? `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}"/>`
        : `<path d="M${cx},${cy} L${cx + r * Math.cos(ang)},${cy + r * Math.sin(ang)} A${r},${r} 0 ${a2 - ang > Math.PI ? 1 : 0} 1 ${cx + r * Math.cos(a2)},${cy + r * Math.sin(a2)} Z" fill="${color}"/>`;
      ang = a2;
      return p;
    }).join('');
    const leyenda = filas.map(([et, v], i) => `<g transform="translate(260,${20 + i * 22})"><rect width="14" height="14" rx="2" fill="${COLORES[i % COLORES.length]}"/>
      <text x="20" y="12">${esc(et)}: ${num(v)}${esc(u)} (${Math.round(100 * v / total)} %)</text></g>`).join('');
    return `<svg viewBox="0 0 640 ${Math.max(240, 30 + filas.length * 22)}" class="svg-grafico" role="img">${porciones}${leyenda}</svg>`;
  }
  const W = 640, H = 260, m = { l: 52, r: 12, t: 22, b: 40 };
  const vals = filas.map(f => f[1]);
  let max = Math.max(0, ...vals), min = Math.min(0, ...vals);
  if (max === min) max = min + 1;
  const y = v => m.t + (H - m.t - m.b) * (max - v) / (max - min);
  const paso = (W - m.l - m.r) / filas.length, x = i => m.l + paso * (i + 0.5);
  const guias = [min, (min + max) / 2, max].map(v => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}" class="g-guia"/>
    <text x="${m.l - 6}" y="${y(v) + 4}" text-anchor="end">${num(v)}</text>`).join('');
  const etiquetas = filas.map(([et], i) => `<text x="${x(i)}" y="${H - m.b + 16}" text-anchor="middle">${esc(et.length > 12 ? et.slice(0, 11) + '…' : et)}</text>`).join('');
  let marcas;
  if (d.forma === 'linea') {
    marcas = `<polyline fill="none" stroke="${COLORES[0]}" stroke-width="2.5" points="${filas.map(([, v], i) => `${x(i)},${y(v)}`).join(' ')}"/>`
      + filas.map(([, v], i) => `<circle cx="${x(i)}" cy="${y(v)}" r="3.5" fill="${COLORES[0]}"/><text x="${x(i)}" y="${y(v) - 8}" text-anchor="middle">${num(v)}</text>`).join('');
  } else {
    const bw = Math.min(48, paso * 0.6);
    marcas = filas.map(([, v], i) => `<rect x="${x(i) - bw / 2}" y="${Math.min(y(v), y(0))}" width="${bw}" height="${Math.max(1, Math.abs(y(v) - y(0)))}" rx="2" fill="${COLORES[0]}"/>
      <text x="${x(i)}" y="${v >= 0 ? y(v) - 5 : y(v) + 14}" text-anchor="middle">${num(v)}</text>`).join('');
  }
  return `<svg viewBox="0 0 ${W} ${H}" class="svg-grafico" role="img">${guias}${marcas}${etiquetas}${u ? `<text x="${m.l}" y="12" class="g-unidad">${esc(d.unidad)}</text>` : ''}</svg>`;
}

