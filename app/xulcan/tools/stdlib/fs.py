# app/xulcan/tools/stdlib/fs.py

import os
import ast
import logging
from pathlib import Path
from typing import List, Dict, Union

logger = logging.getLogger("xulcan.tools.stdlib.fs")

# ============================================================================
# IMPLEMENTACIONES DEL SISTEMA DE ARCHIVOS (STATELESS)
# ============================================================================

def list_directory(directory_path: str) -> Union[List[Dict[str, Union[str, int]]], str]:
    """Lista los archivos y carpetas de un directorio local."""
    logger.info(f"📂 [FS] Listing directory: {directory_path}")
    path = Path(directory_path)
    
    if not path.exists():
        return f"Error: El directorio '{directory_path}' no existe."
    if not path.is_dir():
        return f"Error: '{directory_path}' no es un directorio."
        
    try:
        items =[]
        for item in path.iterdir():
            items.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size_bytes": item.stat().st_size if item.is_file() else 0
            })
        return items
    except PermissionError:
        return f"Error: Permiso denegado para leer '{directory_path}'."
    except Exception as e:
        logger.error(f"❌ Error listing directory {directory_path}: {e}")
        return f"Error al listar el directorio: {str(e)}"


def read_file_content(file_path: str) -> str:
    """Lee el contenido en texto de un archivo local."""
    logger.info(f"📄 [FS] Reading file: {file_path}")
    path = Path(file_path)
    
    if not path.exists():
        return f"Error: El archivo '{file_path}' no existe."
    if not path.is_file():
        return f"Error: '{file_path}' no es un archivo válido."
        
    try:
        # Límite de seguridad para no explotar la memoria RAM del LLM (ej. 15,000 chars)
        content = path.read_text(encoding='utf-8')
        if len(content) > 15000:
            return content[:15000] + "\n\n...[CONTENIDO TRUNCADO POR LÍMITE DE TAMAÑO]"
        return content
    except UnicodeDecodeError:
        return f"Error: El archivo '{file_path}' parece ser binario o no tiene codificación UTF-8."
    except PermissionError:
        return f"Error: Permiso denegado para leer el archivo."
    except Exception as e:
        logger.error(f"❌ Error reading file {file_path}: {e}")
        return f"Error al leer el archivo: {str(e)}"


def read_file_ast(file_path: str) -> str:
    """Lee un archivo Python y devuelve su Árbol de Sintaxis Abstracta (AST)."""
    logger.info(f"🌳[FS] Reading AST for file: {file_path}")
    path = Path(file_path)
    
    if not path.exists():
        return f"Error: El archivo '{file_path}' no existe."
    if path.suffix != '.py':
        return f"Error: El archivo '{file_path}' no es un script de Python (.py)."
        
    try:
        content = path.read_text(encoding='utf-8')
        parsed_ast = ast.parse(content, filename=path.name)
        
        # ast.dump devuelve un string con la estructura jerárquica del código
        # (Ideal para que el LLM entienda la estructura de un código muy grande sin leerlo todo)
        return ast.dump(parsed_ast, indent=2)
    except SyntaxError as se:
        return f"Error de sintaxis en el código Python: {se}"
    except Exception as e:
        logger.error(f"❌ Error parsing AST for {file_path}: {e}")
        return f"Error al parsear el AST: {str(e)}"