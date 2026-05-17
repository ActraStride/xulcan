# app/xulcan/__init__.py

"""
Xulcan Agent OS
El Sistema Operativo para la orquestación determinista de Agentes de IA.
"""

# Importamos el motor principal (que renombraremos a continuación)
from xulcan.app import Xulcan

# Importamos las piezas que el usuario SÍ necesita usar en su código
from xulcan.blueprint.schema import AgentBlueprint
from xulcan.protocol.tools import ToolDefinition, FunctionDef

# Declaramos públicamente qué se exporta cuando alguien usa Xulcan
__all__ =[
    "Xulcan",            # El Motor / Facade
    "AgentBlueprint",    # Por si quieren armar agentes en código
    "ToolDefinition",    # Para armar los gafetes de herramientas
    "FunctionDef"
]