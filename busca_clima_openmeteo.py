# busca_clima_openmeteo.py
#
# Substitui a função busca_Clima (main.py) que hoje usa a API Advisor da Climatempo,
# descontinuada em 15/07/2026. Mesma assinatura de retorno (texto, JSON), mas agora
# aceita qualquer cidade (não só Rio de Janeiro) e já traz a previsão, não só o clima atual.
#
# Endpoints Open-Meteo usados:
#   - Geocoding: https://geocoding-api.open-meteo.com/v1/search?name={cidade}
#   - Forecast:  https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..
# Não exige API key. Limite gratuito: 10.000 chamadas/dia (uso não-comercial).

from typing import Optional, Tuple

import re
import requests
from weather_codes import descreve_clima

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def geocodifica_cidade(nome_cidade: str) -> Optional[dict]:
    """
    Converte nome de cidade em lat/lon usando a Open-Meteo Geocoding API.
    Retorna o primeiro resultado (mais relevante) ou None se não encontrar.
    """
    params = {
        "name": nome_cidade,
        "count": 1,
        "language": "pt",
        "format": "json",
    }
    resp = requests.get(GEOCODING_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    resultados = data.get("results")
    if not resultados:
        return None

    r = resultados[0]
    return {
        "nome": r.get("name"),
        "estado": r.get("admin1"),
        "pais": r.get("country"),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "timezone": r.get("timezone"),
    }


def busca_Clima(cidade: str = "Rio de Janeiro") -> Tuple[str, dict]:
    """
    Busca clima atual + previsão de 3 dias para a cidade informada.
    Mantém o padrão de retorno (texto, JSON) usado pelo agente do Passis.

    Parâmetro novo em relação à versão Climatempo: `cidade` (antes fixo em RJ).
    """
    # Validação rápida: entradas que parecem hashes/ids longos geralmente
    # não são nomes de cidade — detectamos e devolvemos mensagem mais útil.
    if cidade and re.fullmatch(r"[0-9a-fA-F]{16,}", cidade.strip()):
        return (
            f"Entrada inválida para cidade: '{cidade}'. Por favor informe o nome da cidade (ex: 'Rio de Janeiro').",
            {},
        )

    local = geocodifica_cidade(cidade)
    if local is None:
        return f"Não encontrei a cidade '{cidade}'.", {}

    params = {
        "latitude": local["latitude"],
        "longitude": local["longitude"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                   "precipitation,weather_code,wind_speed_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "forecast_days": 3,
        "timezone": local["timezone"] or "auto",
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=10)
    resp.raise_for_status()
    dados = resp.json()

    atual = dados["current"]
    descricao = descreve_clima(atual["weather_code"])

    local_str = local["nome"]
    if local["estado"]:
        local_str += f", {local['estado']}"

    texto = (
        f"Clima agora em {local_str}: {descricao}, "
        f"{atual['temperature_2m']}°C (sensação {atual['apparent_temperature']}°C), "
        f"umidade {atual['relative_humidity_2m']}%, "
        f"vento {atual['wind_speed_10m']} km/h."
    )

    return texto, dados


if __name__ == "__main__":
    # Teste rápido local
    texto, json_resp = busca_Clima("Rio de Janeiro")
    print(texto)
    print()
    texto2, _ = busca_Clima("Sao Paulo")
    print(texto2)
