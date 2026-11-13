"""Rutas delgadas: leen el pedido, llaman al caso de uso y devuelven el resultado. Sin reglas ni try/except (los
errores de negocio los traduce el núcleo a 400/404). Todas bajo /api/notas para no chocar con otros módulos."""
from fastapi import APIRouter, Body

from nucleo.auth import Admin, Usuario

from . import servicios

router = APIRouter(prefix="/api/notas")
CAMPOS = ("titulo", "texto", "prioridad", "vence")


@router.get("")
def listar(u: dict = Usuario):
    return servicios.listar()


@router.post("")
def crear(body: dict = Body(...), u: dict = Usuario):
    return servicios.crear(u, **{k: body.get(k) for k in CAMPOS})


@router.put("/{nota_id}")
def actualizar(nota_id: int, body: dict = Body(...), u: dict = Usuario):
    return servicios.actualizar(u, nota_id, **{k: body.get(k) for k in CAMPOS})


@router.post("/{nota_id}/archivar")
def archivar(nota_id: int, u: dict = Admin):   # archivar es de administrador: así se ve cómo se restringe una acción
    return servicios.cambiar_alta(u, nota_id, activa=False)


@router.post("/{nota_id}/reactivar")
def reactivar(nota_id: int, u: dict = Admin):
    return servicios.cambiar_alta(u, nota_id, activa=True)
