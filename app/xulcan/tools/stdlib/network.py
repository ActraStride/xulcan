# app/xulcan/tools/stdlib/network.py

import json
import re
import urllib.request
import urllib.parse
import asyncio
import logging
from typing import Dict, Optional, Any

# from xulcan.protocol.tools import ToolDefinition, FunctionDef

logger = logging.getLogger("xulcan.tools.stdlib.network")

# ============================================================================
# 2. IMPLEMENTACIONES DE LAS FUNCIONES (STATELESS)
# ============================================================================

def _clean_html(raw_html: str) -> str:
    """Función auxiliar para limpiar HTML y extraer texto legible."""
    # Remover scripts y estilos completamente
    cleanr = re.compile(r'<(script|style).*?>.*?</\1>', re.IGNORECASE | re.DOTALL)
    text = re.sub(cleanr, '', raw_html)
    # Remover el resto de etiquetas HTML
    cleanr = re.compile(r'<.*?>')
    text = re.sub(cleanr, ' ', text)
    # Limpiar espacios en blanco excesivos
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def network_fetch_webpage(url: str) -> str:
    """Implementación asíncrona para descargar y limpiar páginas web."""
    logger.info(f"🌐 [Network] Fetching webpage: {url}")
    
    def _fetch():
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'XulcanAgent/1.0 (Autonomous OS)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8')
            
    try:
        html_content = await asyncio.to_thread(_fetch)
        clean_text = _clean_html(html_content)
        
        # Límite de seguridad: 10,000 caracteres (~2,500 tokens)
        if len(clean_text) > 10000:
            return clean_text[:10000] + "\n\n...[CONTENIDO TRUNCADO POR LÍMITE DE MEMORIA]"
        return clean_text
        
    except Exception as e:
        logger.error(f"❌ Error fetching {url}: {str(e)}")
        return f"Error al acceder a la página: {str(e)}"

async def network_api_get(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    """Implementación asíncrona para consumir APIs REST (GET)."""
    logger.info(f"🌐 [Network] API GET: {url}")
    
    def _fetch_api():
        req_headers = {'User-Agent': 'XulcanAgent/1.0'}
        if headers:
            req_headers.update(headers)
            
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.read().decode('utf-8')

    try:
        raw_response = await asyncio.to_thread(_fetch_api)
        # Intentamos parsearlo a JSON nativo para que el LLM lo entienda mejor
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError:
            return raw_response # Si no es JSON, devolvemos el string crudo
            
    except Exception as e:
        logger.error(f"❌ API GET Error en {url}: {str(e)}")
        return {"error": f"La petición a la API falló: {str(e)}"}

# ============================================================================
# EXPORTACIÓN
# ============================================================================
