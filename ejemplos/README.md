# Ejemplos: herramientas que nacieron en cada app

Código de referencia tomado de las apps, **no enchufado** al núcleo. Sirve para reusar una herramienta en otra app sin
reinventarla: se copia, se adapta a un módulo (`nucleo/modulo.py`, con `modulos/notas` como molde) y, si la usan dos o
más apps, se convierte en un módulo de `modulos/` o pasa al núcleo.

| Ejemplo | De qué app | Qué hace |
|---|---|---|
| `mapa_de_planta/` | UltraMantenimiento | Planos dibujados en la app (rectángulos, líneas, textos sobre grilla en metros) con elementos ubicados como puntos de colores según su estado. Editor con arrastrar, imanes a la grilla, propiedades. |
| `horometro_por_tramos/` | UltraMantenimiento | Lecturas de un contador que se cambia (horómetro): tramos, coherencia dentro de cada tramo, y servicios por horas que se corren al contador nuevo. |
| `imprimir_lista/` | UltraMantenimiento | Una hoja apaisada para imprimir con casilleros en blanco (hecho, fecha, quién, observaciones), oculta en pantalla. |
| `grafico_svg/` | UltraMantenimiento | Gráfico de líneas o barras en SVG sin librerías. |
| `icono_sin_librerias.py` | UltraMantenimiento | Genera el .ico del ejecutable dibujando con geometría, sin librerías de imágenes. |
| `importar_otra_instalacion/` | Gestión Automotor | Traer los datos de otra instalación (una versión vieja en otra carpeta o la carpeta data de otra PC): valida, respalda lo de acá y reemplaza. |
| `historial_y_auditoria/` | Gestión Automotor | Historial append-only (triggers que impiden modificarlo o borrarlo) y altas/ediciones/bajas auditadas que dejan solo los campos que cambiaron. |
| `mail_semanal/` | Gestión Automotor | Resumen semanal por mail (SMTP) con programador en segundo plano, reintentos, registro de envíos y la contraseña del mail cifrada (Fernet) con la clave fuera de la base. |
| `alertas_con_ritmo/` | Gestión Automotor | Alertas de vencimiento configurables: "aparece N días antes" y "se pone roja cuando faltan M". |
| `chequeo_de_ayuda/` | Gestión Automotor | Herramienta de desarrollo: recorre cada pantalla y formulario y lista los pasos de la Ayuda que no encuentran su elemento (con Edge headless `--dump-dom`). |
| `importar_desde_excel/` | Gestión Automotor | Importador de una planilla con simulación sin escribir, una transacción por fila e idempotente. |
| `migracion_ultramantenimiento/` | UltraMantenimiento | Los archivos reales de su paso al núcleo (ver `docs/migrar_una_app.md`): migración de usuarios por legajo, módulo, tests que no tocan la base real. |
| `multiplataforma/` | Edificios de Mamá | Lanzadores de doble clic para Windows, Mac y Linux, empaquetado y release para los tres sistemas, y el actualizador que también instala desde el código fuente. |

Lo que ya pasó al núcleo (y no hace falta copiar): sesiones y usuarios, contraseña provisoria con aviso, nombre y logo,
puerto e instancia única, escrituras de a una (`BEGIN IMMEDIATE`), actualizador con copia de la base y vuelta atrás,
`?v=VERSION`, adjuntos validados por firma, validaciones de campo y la Ayuda con su Tour.
