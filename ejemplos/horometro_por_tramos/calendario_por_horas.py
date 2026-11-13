# Extraído de UltraMantenimiento app/calendario.py

def estado_por_horas(cada_horas: int | None, proximo_inicial: int | None, ultima_lectura: int | None,
                     hecho_a: int | None, aviso: int) -> EstadoHoras:
    """Servicio por horas: el próximo es el último hecho + intervalo; si nunca se hizo, el inicial del Plan."""
    if hecho_a is not None and cada_horas:
        proximo = hecho_a + cada_horas
    else:
        proximo = proximo_inicial
    if proximo is None:
        return EstadoHoras(ultima_lectura, hecho_a, None, None, "falta_dato")
    if ultima_lectura is None:
        return EstadoHoras(None, hecho_a, proximo, None, "sin_lectura")
    faltan = proximo - ultima_lectura
    estado = "vencido" if faltan < 0 else "proximo" if faltan <= aviso else "al_dia"
    return EstadoHoras(ultima_lectura, hecho_a, proximo, faltan, estado)


