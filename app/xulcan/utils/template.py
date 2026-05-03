# app/xulcan/utils/template.py
import logging
from jinja2 import Template, TemplateError

logger = logging.getLogger("xulcan.utils.template")

def render_template(texto: str, memory_dict: dict) -> str:
    """
    Motor de inyección transversal (Jinja2).
    Procesa variables {{ }}, condicionales {% %} y comentarios {# #}.
    """
    # 1. Optimización inteligente: Revisamos si hay CUALQUIER sintaxis de Jinja
    if not any(marker in texto for marker in ("{{", "{%", "{#")):
        return texto
        
    try:
        # 2. Renderizamos con el poder absoluto de Jinja2
        plantilla = Template(texto)
        return plantilla.render(**memory_dict)
        
    except TemplateError as e:
        # 3. Defensa contra Blueprints mal escritos
        logger.error(f"⚠️ Error de sintaxis en plantilla Jinja2: {e}. Se devuelve texto crudo.")
        return texto
    except Exception as e:
        logger.error(f"💥 Error inesperado renderizando plantilla: {e}")
        return texto