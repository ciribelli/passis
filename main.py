import requests
from bs4 import BeautifulSoup
import json
import datetime
import pandas as pd
import json
import os

def nucleo_jogos(data_hora):
    # busca a data do dia do sistema
    hoje = data_hora
    #print(datetime.date.today() + datetime.timedelta(days=1))
    url = 'http://www.uol.com.br/esporte/futebol/central-de-jogos/'
    resposta = requests.get(url)
    text = BeautifulSoup(resposta.text, 'html.parser')
    print ("Buscando jogos em: ", hoje)
    # FILTRAGEM DE DATA
    i_dia = text.find('li', {'data-ts': hoje})

    # filtro para JOGOES
    lista_jogoes=[]
    try: # porque nem sempre temos jogoes
        lista_jogao = i_dia.find('div', {'class': 'match-wrap-bigGames'})
        jogao = lista_jogao.find_all('div', {'class': "match-full match-wrapper"})
        for i in jogao:
            data_cfg = json.loads(i['data-cfg'])
            try:
                transmissao = i.find('div', {'class': 'transmitions'}).get_text().strip()
                data_cfg.update({'transmissao': transmissao})
            except:
                pass
            lista_jogoes.append(data_cfg)
    except:
        print('nao tem jogao')

    # filtro PARA JOGOS
    lista_jogos=[]
    try: # porque nem sempre temos jogos
        lista_jogo = i_dia.find('div', {'class': "match-container top-games"})
        jogo = lista_jogo.find('div', {'class': "match-wrap-content"})
        a = jogo.find_all('div', {'class': "match-full match-wrapper"})
        for i in a:
            data_cfg = json.loads(i['data-cfg'])
            try:
                transmissao = i.find('div', {'class': 'transmitions'}).get_text().strip()
                data_cfg.update({'transmissao': transmissao})
            except:
                pass
            lista_jogos.append(data_cfg)
    except:
        print('nao tem jogo')

    # filtro PARA JOGOS complementares
    lista_jogos_comp=[]
    try: # porque nem sempre temos jogos
        lista_jogoc = i_dia.find('div', {'class': "match-container today-games"})
        jogoc = lista_jogoc.find('div', {'class': "match-wrap-content"})
        ac = jogoc.find_all('div', {'class': "match-full match-wrapper"})
        for i in ac:
            data_cfg = json.loads(i['data-cfg'])
            try:
                transmissao = i.find('div', {'class': 'transmitions'}).get_text().strip()
                data_cfg.update({'transmissao': transmissao})
            except:
                pass
            lista_jogos_comp.append(data_cfg)
    except:
        print('nao tem jogo')


    # somo as duas listas contendo jogoes e jogos normais
    lista_completa = lista_jogoes + lista_jogos + lista_jogos_comp

    # Converter a lista de strings JSON em uma lista de dicionários
    lista_dicionarios = [item for item in lista_completa]

    # Converter a lista de dicionários em DataFrame
    df = pd.DataFrame(lista_dicionarios)

    # tratamento 01: jogos sem transmissão são informados como NaN
    # neste caso, serão substituídos por os NaN serão substituídos por '-'
    df_f = df.fillna({'transmissao':'-'})
    # tratamento 02: jogos encerrados e com informação pós-jogo podem ter esses campos com informações
    # NaN em eventos já superados. Esse tratamento substitui NaN por '-'
    df_f = df_f.fillna({'encerrado':'-', 'posjogo':'-'})
    return df_f

# valer da extração de colunas mais importantes com a função 'loc'

def get_jogos(data_hora):
    df_f = nucleo_jogos(data_hora)
    df_resultante = df_f.loc[:,['time1', 'time2', 'hora', 'competicao', 'transmissao']].sort_values(by=['hora'])
    print(df_resultante)
    return df_resultante.to_json()

def get_jogos_df(data_hora): # funcao teste para funcao hub
    df_f = nucleo_jogos(data_hora)
    df_resultante = df_f.loc[:,['isBigGame','time1', 'time2', 'hora', 'competicao', 'transmissao']].sort_values(by=['hora'])
    saida = ''
    for index, row in df_resultante.iterrows():
        if (row['isBigGame']):
            saida = saida + '🥇 ' + row['time1'] + ' ✖️ ' + row['time2'] + ' ⏰ ' + row['hora'] + ' 📺 ' + row[
                'transmissao'] + '\n'
        else:
            saida = saida + '⚽️ ' + row['time1'] + ' ✖️ ' + row['time2'] + ' ⏰ ' + row['hora'] + ' 📺 ' + row[
                'transmissao'] + '\n'
    return saida, df_resultante # [formato texto], [formato json]

# filtro 2 para para times específicos utilizando o dataframe completo
def get_time(elem):
    df_f = nucleo_jogos()
    df_n = df_f.loc[(df_f.time1 == elem)|(df_f.time2 == elem)]
    return df_n.to_json()

# retorna o número de jogoes
def filtro_jogao():
    n_jogoes = 0
    try:
        df_f = nucleo_jogos()
        n_jogoes = df_f['isBigGame'].value_counts()[True]
    except:
        n_jogoes = 0
    return (n_jogoes)
print(filtro_jogao())

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

def busca_Clima(token):
    # utiliza a API do Clima Tempo para fazer consultas para o Rio de Janeiro
    url = "http://apiadvisor.climatempo.com.br/api/v1/weather/locale/5959/current?token=" + token
    payload = {}
    headers = {}
    response = requests.request("GET", url, headers=headers, data=payload)

    data = json.loads(response.text)
    name = data["name"]
    date = data["data"]["date"]
    condition = data["data"]["condition"]
    temperature = data["data"]["temperature"]
    wind_velocity = data["data"]["wind_velocity"]
    wind_direction = data["data"]["wind_direction"]
    humidity = data["data"]["humidity"]
    sensation = data["data"]["sensation"]

    output = f"Clima em {name} - {date}\n"
    output += f"{condition}\n\n"
    output += f"Temperatura: {temperature}°C\n"
    output += f"Vento: {wind_velocity} km/h de {wind_direction}\n"
    output += f"Umidade: {humidity}%\n"
    output += f"Sensação térmica: {sensation}°C"
    print(output)
    return output, response

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


