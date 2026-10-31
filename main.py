import requests
import json
import os
import re
import busca_clima_openmeteo
import uol_futebol_scraper as uol

# ---------------- futebol (UOL) ----------------

def get_jogos(data_hora):
    """JSON (string) com os jogos da data (dd-mm-yyyy). Usado pelo endpoint /v1/jogos e pelas tools."""
    return json.dumps(uol.get_games(data_hora), ensure_ascii=False)

def get_jogos_df(data_hora):
    """(texto formatado para WhatsApp, lista de jogos). Usado pelo chathub."""
    jogos = uol.get_games(data_hora)
    return uol.format_games(jogos), jogos

def get_time(nome_time):
    """JSON com os jogos de um time em toda a janela disponivel no UOL."""
    alvo = nome_time.strip().lower()
    jogos = [j for j in uol.get_games() if alvo in j['time1'].lower() or alvo in j['time2'].lower()]
    return json.dumps(jogos, ensure_ascii=False)

################### funcao X ################

def busca_X2(x_token, id_X):
    url = f"https://api.twitter.com/2/users/{id_X}/tweets"
    querystring = {"tweet.fields":"created_at","max_results":"5"}
    headers = {
        "Authorization": f"Bearer {x_token}"
    }

    response = requests.request("GET", url, headers=headers, params=querystring, verify=False)
    # Verifica o status da resposta
    if response.status_code == 200:
        response_data = response.json()
        if "data" in response_data:
            # Gera o texto em formato plain_text
            plain_text = "; ".join(
                [f"created_at: {tweet['created_at']} - {tweet['text']}" for tweet in response_data["data"]]
            )
            return plain_text, response.text
        else:
            return "Resposta válida, mas sem o campo 'data'."
    elif response.status_code == 429:
        return "Erro 429: Too Many Requests. Aguarde antes de tentar novamente.", response.text
    else:
        return f"Erro: {response.status_code} - {response.text}", response.text

def busca_Clima(cidade: str = "Rio de Janeiro"):
    """
    Compatibilidade: originalmente aceitava um `token` (string).
    Agora aceita o nome da cidade. Se receber uma string que parece um
    token/hash, assume chamada legacy e usa o default "Rio de Janeiro".
    Delega para `busca_clima_openmeteo.busca_Clima` e retorna (texto, json).
    """
    # backward-compat: if caller passed a token/hash, use default city
    if cidade and re.fullmatch(r"[0-9a-fA-F]{8,}", cidade.strip()):
        cidade = "Rio de Janeiro"

    try:
        texto, dados = busca_clima_openmeteo.busca_Clima(cidade)
        return texto, dados
    except Exception as e:
        return f"Erro ao obter clima para {cidade}: {e}", {}

# busca em tempo real utilizando a API do X com modelo Grok
def real_time(prompt, context):
    url = "https://api.x.ai/v1/responses"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('XAI_API_KEY')}"
    }

    system_content = (
        "Você é um buscador de informações em tempo real, seja no X ou Web. "
        "Colete as fontes e retorne de forma resumida. "
        "Forneça a fonte de onde você coletou as informações."
    )
    if context:
        system_content += (
            "\n\nInformações pessoais do usuário como referência:\n"
            + context
        )

    payload = {
        "model": os.getenv("GROK_MODEL", "grok-4-latest"),
        "tools": [
            {
                "type": "web_search",
                "max_results": 8
            }
        ],
        "input": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()
        for item in data.get("output", []):
            if item.get("type") == "message" and "content" in item:
                return item["content"][0]["text"]
        print(f"[real_time] Resposta sem mensagem: {str(data)[:200]}")
        return "Erro: resposta da API não contém mensagem."
    except requests.exceptions.Timeout:
        print("[real_time] Timeout na API do Grok")
        return "Erro: timeout ao consultar a API do Grok."
    except requests.exceptions.RequestException as e:
        error_details = e.response.text if getattr(e, 'response', None) is not None else "Sem detalhes"
        print(f"[real_time] Erro de requisição: {e} | Detalhes: {error_details}")
        return f"Erro ao conectar com a API do Grok. Status: {e}"
    except (KeyError, IndexError) as e:
        print(f"[real_time] Resposta inesperada: {response.text[:200]}")
        return f"Erro ao processar resposta da API: {e}"


