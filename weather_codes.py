# weather_codes.py
# Tradução dos códigos WMO retornados pela Open-Meteo (campo weather_code)
# Referência: https://open-meteo.com/en/docs (seção WMO Weather interpretation codes)

WMO_CODES = {
    0: "céu limpo",
    1: "predominantemente limpo",
    2: "parcialmente nublado",
    3: "nublado",
    45: "neblina",
    48: "neblina com geada",
    51: "garoa fraca",
    53: "garoa moderada",
    55: "garoa forte",
    56: "garoa congelante fraca",
    57: "garoa congelante forte",
    61: "chuva fraca",
    63: "chuva moderada",
    65: "chuva forte",
    66: "chuva congelante fraca",
    67: "chuva congelante forte",
    71: "neve fraca",
    73: "neve moderada",
    75: "neve forte",
    77: "grãos de neve",
    80: "pancadas de chuva fracas",
    81: "pancadas de chuva moderadas",
    82: "pancadas de chuva violentas",
    85: "pancadas de neve fracas",
    86: "pancadas de neve fortes",
    95: "trovoada",
    96: "trovoada com granizo fraco",
    99: "trovoada com granizo forte",
}


def descreve_clima(codigo: int) -> str:
    """Converte o weather_code da Open-Meteo em descrição em português."""
    return WMO_CODES.get(codigo, f"condição desconhecida (código {codigo})")