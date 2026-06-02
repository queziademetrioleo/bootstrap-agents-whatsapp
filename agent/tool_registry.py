"""Auto-discovery de tools.

Importa todos os modulos de `tools/`, coleta cada variavel `TOOL` e monta o
registro. O colaborador nunca edita arquivo de config central: basta adicionar
um arquivo em tools/.

Conversao para o formato de function calling do Gen AI SDK feita em
`as_genai_tools()`. A selecao por agente respeita `tools_enabled` da config;
se vazio, todas as universais ficam ativas + nenhuma de dominio (seguro por
padrao). Tools universais estao sempre disponiveis.
"""

from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache

from google.genai import types

from agent.logging_config import get_logger
from agent.tool_base import AgentTool

log = get_logger(__name__)


@lru_cache
def _discover() -> dict[str, AgentTool]:
    import tools  # pacote do colaborador

    registry: dict[str, AgentTool] = {}
    for mod_info in pkgutil.iter_modules(tools.__path__):
        if mod_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"tools.{mod_info.name}")
        tool = getattr(module, "TOOL", None)
        if tool is None:
            continue
        if not isinstance(tool, AgentTool):
            log.warning(f"tools/{mod_info.name}.py expoe TOOL que nao e AgentTool — ignorado")
            continue
        if tool.name in registry:
            raise ValueError(f"Tool duplicada: {tool.name!r} (em tools/{mod_info.name}.py)")
        registry[tool.name] = tool
    log.info("Tools descobertas", extra={"fields": {"count": len(registry), "names": list(registry)}})
    return registry


def all_tools() -> dict[str, AgentTool]:
    return dict(_discover())


def tools_for_agent(tools_enabled: list[str]) -> dict[str, AgentTool]:
    """Retorna as tools ativas para um agente: universais sempre + as habilitadas."""
    registry = _discover()
    selected: dict[str, AgentTool] = {
        name: t for name, t in registry.items() if t.category == "universal"
    }
    for name in tools_enabled:
        tool = registry.get(name)
        if tool is None:
            log.warning(f"tools_enabled refere tool inexistente: {name!r}")
            continue
        selected[name] = tool
    return selected


def as_genai_tools(tools: dict[str, AgentTool]) -> list[types.Tool]:
    """Converte AgentTool -> types.Tool (FunctionDeclaration) do Gen AI SDK."""
    if not tools:
        return []
    declarations = [
        types.FunctionDeclaration(
            name=t.name,
            description=t.description,
            parameters=t.parameters,
        )
        for t in tools.values()
    ]
    return [types.Tool(function_declarations=declarations)]
