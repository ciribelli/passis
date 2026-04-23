"""
passis_tools.py — Definição de tools para o Passis.

Tenta usar FastMCP para geração automática de schemas.
Se FastMCP não estiver disponível (Python < 3.10), usa registry puro.

Para adicionar uma nova tool:
1. Crie a função com type hints e docstring
2. Decore com @register_tool
3. Pronto — schema e dispatch são automáticos.
"""

import os
import pandas as pd
from dotenv import load_dotenv
import main

load_dotenv()

# ---------------------------------------------------------------------------
# Tenta carregar FastMCP. Fallback se Python < 3.10 ou lib ausente.
# ---------------------------------------------------------------------------
try:
    from fastmcp import FastMCP
    mcp = FastMCP("Passis")
    _HAS_FASTMCP = True
    print("[passis_tools] FastMCP carregado ✅")
except ImportError:
    mcp = None
    _HAS_FASTMCP = False
    print("[passis_tools] FastMCP indisponível — usando registry puro")


# ---------------------------------------------------------------------------
# REGISTRY — funciona com qualquer versão do Python
# ---------------------------------------------------------------------------
REGISTRY = {}  # nome -> {"fn": callable, "schema": dict}


def register_tool(openai_params=None):
    """Decorator que registra a tool no REGISTRY e opcionalmente no FastMCP.

    Uso:
        @register_tool({"type": "object", "properties": {...}, "required": [...]})
        def minha_tool(param: str) -> str:
            '''Docstring vira a description.'''
            ...

        @register_tool()   # tool sem parâmetros
        def outra_tool() -> str:
            ...
    """
    if openai_params is None:
        openai_params = {}

    def decorator(fn):
        # Registra no dict local
        REGISTRY[fn.__name__] = {
            "fn": fn,
            "schema": {
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    "description": (fn.__doc__ or "").strip(),
                    "parameters": openai_params,
                }
            },
        }
        # Registra no FastMCP se disponível
        if _HAS_FASTMCP and mcp is not None:
            mcp.tool(fn)
        return fn

    return decorator


# ---------------------------------------------------------------------------
# CONTEXTO DE SISTEMA — injetado pelo agent antes de cada dispatch
# ---------------------------------------------------------------------------
_ctx = {}

def set_context(data_atual: str, question: str, context_text: str):
    """Chamado pelo agent antes de despachar tool calls."""
    global _ctx
    _ctx = {
        "data_atual": data_atual,
        "question": question,
        "context": context_text,
    }


# ---------------------------------------------------------------------------
# TOOLS
# ---------------------------------------------------------------------------

@register_tool()
def busca_Clima() -> str:
    """Busca informações em tempo real para o clima do Rio de Janeiro:
    temperatura, precipitação, ventos, umidade e sensação térmica."""
    token = os.getenv('token_clima')
    output, _ = main.busca_Clima(token)
    return output


@register_tool({
    "type": "object",
    "properties": {
        "date": {
            "type": "string",
            "description": "A data dos jogos deve ser informada no formato dd-mm-yyyy",
        }
    },
    "required": ["date"],
})
def busca_Jogos(date: str) -> str:
    """Busca uma lista de jogos de futebol para uma data específica."""
    return main.get_jogos(date)


@register_tool()
def busca_Cidade() -> str:
    """Busca informações em tempo real sobre o trânsito e eventos
    na cidade do Rio de Janeiro. Fonte: Centro de Operações Rio."""
    token = os.getenv('token_X')
    output, _ = main.busca_X2(token, "226409689")
    return output


@register_tool()
def musk_knows() -> str:
    """Busca os últimos 5 tweets do Elon Musk no X.
    Acionada quando o usuário quer saber algo sobre Elon Musk."""
    token = os.getenv('token_X')
    output, _ = main.busca_X2(token, "44196397")
    return output


@register_tool({
    "type": "object",
    "properties": {
        "date": {
            "type": "string",
            "description": "A data de início da janela do intervalo no formato dd-mm-yyyy",
        }
    },
    "required": ["date"],
})
def obter_cidade_atual_e_clima(date: str) -> str:
    """Busca informações sobre minha localização (em qual cidade estou) e o clima
    desta região num intervalo de tempo entre uma data específica e a data atual."""
    # Importa aqui para evitar circular import
    import app as flask_app
    _, datajson = flask_app.obter_cidade_atual_e_clima(date, _ctx["data_atual"])
    df = pd.read_json(datajson, orient='records', convert_dates=['data'])
    return df.to_string(index=False)


@register_tool({
    "type": "object",
    "properties": {
        "date": {
            "type": "string",
            "description": "A data de início da janela do intervalo no formato dd-mm-yyyy",
        }
    },
    "required": ["date"],
})
def busca_Checkin(date: str) -> str:
    """Busca uma lista de checkins num intervalo entre uma data específica e a data atual.
    Checkins podem ser compromissos quaisquer tais como, hora que acorda, hora que bebe água,
    hora que foi à academia, hora que chegou ao trabalho ou algum lugar.
    O atributo direction descreve se alguém está entrando ou saindo do checkin (in ou out).
    Checkins NÃO trazem informação sobre minha localização."""
    import app as flask_app
    _, datajson = flask_app.get_checkins_by_date(date, _ctx["data_atual"])
    df = pd.read_json(datajson, orient='records', convert_dates=['data'])
    return df.to_string(index=False)


@register_tool()
def ultimo_Checkin() -> str:
    """Busca detalhes do último checkin realizado pelo usuário no banco de dados.
    Retorna tipo de checkin, hora e direction (in/out).
    Quando o usuário perguntar 'qual foi o meu último checkin?', essa é a função a ser chamada."""
    import app as flask_app
    return flask_app.get_last_checkin_details()


@register_tool()
def registra_Memoria() -> str:
    """Detecta quando o usuário quer salvar uma informação qualquer na memória eterna."""
    return "__REGISTRAR_MEMORIA__"


@register_tool()
def real_time() -> str:
    """Aciona o modelo Grok para consultas em tempo real ao X e Web."""
    return main.real_time(_ctx["question"], _ctx["context"])
