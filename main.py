import requests
from bs4 import BeautifulSoup
import json
import datetime

# busca a data do dia do sistema
hoje = datetime.date.today().strftime('%d-%m-%Y')
url = 'http://www.uol.com.br/esporte/futebol/central-de-jogos/'
resposta = requests.get(url)
print(resposta.status_code, ' ', url, hoje)
text = BeautifulSoup(resposta.text, 'html.parser')

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

import pandas as pd
import json
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


# Uma possivel representação na interface de usuário é apresentada abaixo, fazendo-se
# valer da extração de colunas mais importantes com a função 'loc'

def get_jogos():
    df_resultante = df_f.loc[:,['time1', 'time2', 'hora', 'competicao', 'transmissao']].sort_values(by=['hora'])
    print(df_resultante)
    return df_resultante.to_json()

# filtro 1 para jogos em estádio específico utilizando o dataframe completo
def get_estadio(elem):
    df_n = df_f.loc[(df.estadio == elem)]
    return df_n

# filtro 2 para para times específicos utilizando o dataframe completo
def get_time(elem):
    df_n = df_f.loc[(df_f.time1 == elem)|(df_f.time2 == elem)]
    return df_n.to_json()

# filtro 3 para para jogões do dia utilizando o dataframe completo
# retorna o número de jogoes
def filtro_jogao():
    n_jogoes = 0
    try:
        n_jogoes = df_f['isBigGame'].value_counts()[True]
    except:
        n_jogoes = 0
    return (n_jogoes)
print(filtro_jogao())
