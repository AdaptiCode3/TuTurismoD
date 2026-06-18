"""
core/repositories/categories.py
===============================
Repositorio para la colección de categorías usando PyMongo nativo.
"""
from typing import Any
from dataclasses import dataclass

from core.repositories.base import BaseRepository

@dataclass
class CategoryDocument:
    id: str
    nombre: str
    icono: str = ""
    descripcion: str = ""

class CategoryRepository(BaseRepository[CategoryDocument]):
    def __init__(self) -> None:
        super().__init__("categorias")

    def _map_document(self, document: dict[str, Any]) -> CategoryDocument:
        return CategoryDocument(
            id=document.get("id", ""),
            nombre=document.get("nombre", ""),
            icono=document.get("icono", ""),
            descripcion=document.get("descripcion", "")
        )
