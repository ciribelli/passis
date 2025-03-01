import numpy as np
import pandas as pd
from openai import OpenAI
from scipy.spatial.distance import cosine
from dotenv import load_dotenv
import os
import json
import main
import app
import send_msg

client = OpenAI()

first_item = ""
def create_context(question, df, max_len=1200, size="ada"):
    load_dotenv()
    client.api_key = os.getenv('OPENAI_API_KEY')
    # Recupera os embeddings para a pergunta em formato dataFrame - função não documentada pela opeanAI
    q_embeddings = client.embeddings.create(input=question, model='text-embedding-ada-002').data[0].embedding
    df["distances"] = df["embeddings"].apply(lambda x: cosine(q_embeddings, x))

    returns = []
    links = []
    cur_len = 0

    # Ordena por distâncias e adiciona o texto para ao contexto respeitando o máximo tamanho configurado em max_len
    for i, row in df.sort_values('distances', ascending=True).iterrows():
        # Adiciona o tamanho do texto ao current length do contexto
        cur_len += row['n_tokens'] + 4
        # Interrompe se o contexto já é longo o suficiente
        if cur_len > max_len:
            break
        # Adiciona o texto que será retornado / adiciona também informações da tabela e o índice correspondente para futura recuperação
        returns.append(row["texto"])
        links.append(str(row["tabela"])+'/'+str(row["index"]))

    global first_item
    # Guarda a posição do primeiro item de menor distância da pergunta
    first_item = links[0]
    # Retorna o contexto
    return "\n🤖\n".join(returns)

def remove_spec_char(sentence):
    cleaned_sentence = sentence.replace('"', ' ').replace("'", ' ')
    return cleaned_sentence

def answer_question(
    df,
    data_atual="alguma data",
    hora_atual="alguma hora",
    phone_number_id = "algum num",
    from_number = "algum codigo",
    question="aqui vem a pergunta",
    lista_threads="aqui estarao as threads",
    max_len=800,
    size="ada",
    debug=True,
    eh_pergunta=False,
):

    context = create_context(question, df, max_len=max_len, size=size,)

    if debug:
        print("Context:\n" + context)
        print("\n\n")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "busca_Jogos",
                "description": "Busca uma lista de jogos de futebol para uma data específica.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "A data dos jogos deve ser informada no formato dd-mm-yyyy",
                        }
                    },
                    "required": ["date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "obter_cidade_atual_e_clima",
                "description": "Busca informações sobre minha localização (em qual cidade estou) e o clima desta região (temperatura, vento, umidade, probabilidade de chuva) num intervalo de tempo compreendido entre uma data específica e a data atual.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "A data de início da janela do intervalo deve ser informada no formato dd-mm-yyyy",
                        }
                    },
                    "required": ["date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "busca_Checkin",
                "description": "Busca uma lista de checkins num intervalo compreendido entre uma data específica e a data atual. Checkins podem ser compromissos quaisquer tais como, hora que acorda, hora que bebe água, hora que foi à academia, hora que chegou ao trabalho ou algum lugar. O atributo direction descreve se alguém está entrando ou saindo do checkin (in ou out). Por exemplo, checkin 'awake' direction 'out' quer dizer 'dormir'. Checkins NÃO trazem informação sobre minha localização",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {
                            "type": "string",
                            "description": "A data de início da janela do intervalo deve ser informada no formato dd-mm-yyyy",
                        }
                    },
                    "required": ["date"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ultimo_Checkin",
                "description": "função para buscar detalhes do último checkin realizado pelo usuário no banco de dados. Atributos como tipo de checkin, hora, e direction podem ser o objetivo do usuário. Quando o usuário perguntar 'qual foi o meu último checkin?', ou 'a que horas foi meu ultimo checkin?', essa é a função a ser chamada",
            },
        },
        {
            "type": "function",
            "function": {
                "name": "busca_Clima",
                "description": "Busca informações em tempo real para o clima da especificamente para a cidade do Rio de Janeiro. Informações como temperatura, precipitação, ventos, dentre outras. Não demanda parâmetros de entrada.",
                "parameters": {},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "busca_Cidade",
                "description": "Busca informações em tempo real sobre o trânsito e eventos na cidade do Rio de Janeiro. Fonte das informações é Centro de Operações Rio.",
                "parameters": {},
            },
        },
                {
            "type": "function",
            "function": {
                "name": "musk_knows",
                "description": "Essa função simplesmente entende quando o usuário quer saber algo sobre Elon Musk. Uma vez que isso seja detectado, a função busca os últimos 5 twittes do Elon Musk no X.",
                "parameters": {},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "registra_Memoria",
                "description": "Essa função simplesmente entende quando o usuário quer salvar uma informação qualquer na memória eterna.",
                "parameters": {},
            },
        },
    ]

    messages = [
        {
            "role": "system",
            "content": "Você é meu assistente pessoal e seus assuntos de domínio são minhas memórias, localização, compromissos (checkins), clima e o trânsito. Receba abaixo minhas informações pessoais:" + "\n" + context + "Saiba que hoje é " + data_atual + " e agora são " + hora_atual + "\n"
        }
    ]

    try:
        for thread in reversed(lista_threads):
            try:
                messages.append(json.loads(thread[0], strict=False))
            except json.JSONDecodeError as e:
                print(f"Erro de decodificação JSON: {e}")

        messages.append({"role": "user", "content": question})
        print("mensagens: \n", messages)

        completion = client.chat.completions.create(
            #model="gpt-3.5-turbo-0125",
            model="gpt-4o",
            messages=messages,
            tools=tools, # para chamada da funcao
            tool_choice="auto", # para chamada da funcao
        )
        
        respostas = completion.choices[0].message.tool_calls

        if respostas:
            # Para cada objeto na lista, extrair as informações relevantes e chamar a função
            # Envio uma mensagem para reduzir ansiedade
            send_msg.send_wapp_msg(phone_number_id, from_number, "⏳ _Avaliando pra você.._")
            for resposta in respostas:
                function_name = resposta.function.name
                function_args = json.loads(resposta.function.arguments)

                # Chamar a função com base nas informações extraídas
                if function_name == 'busca_Clima':
                    token = os.getenv('token_clima')
                    function_output, datajson = main.busca_Clima(token)
                    print("\nSaida para busca_Clima:\n", function_output)
                if function_name == 'busca_Jogos':
                    function_output = main.get_jogos(function_args.get("date"))
                    print("\nSaida para busca_Jogos:\n", function_output, "\nData alvo sugerida pela funcao:\n", function_args.get("date"))
                if function_name == 'busca_Cidade':
                    # 226409689 id Operacoes Rio
                    token = os.getenv('token_X')
                    function_output, datajson = main.busca_X2(token, "226409689")
                    print("\nSaida para busca_Cidade:\n", function_output)
                if function_name == 'musk_knows':
                    # 44196397 id Elon Musk
                    token = os.getenv('token_X')
                    function_output, datajson = main.busca_X2(token, "44196397")
                    print("\nSaida para Musk:\n", function_output)
                if function_name == 'obter_cidade_atual_e_clima':
                    print('estou na função obter cidade e clima')
                    print('data alvo:')
                    print(function_args.get("date"))
                    text_output, datajson = app.obter_cidade_atual_e_clima(function_args.get("date"), data_atual)
                    df_result_from_json = pd.read_json(datajson, orient='records', convert_dates=['data'])
                    # convertendo json para dataframe e dataframe into text para melhor expericia com LLM
                    function_output = df_result_from_json.to_string(index=False)
                    print("\nSaida para obter_cidade_atual_e_clima:\n", function_output, "\nData alvo sugerida pela funcao:\n", function_args.get("date"))
                if function_name == 'busca_Checkin':
                    text_output, datajson = app.get_checkins_by_date(function_args.get("date"), data_atual)
                    #converter json para dataframe
                    df_result_from_json = pd.read_json(datajson, orient='records', convert_dates=['data'])
                    # convertendo json para dataframe e dataframe into text para melhor expericia com LLM
                    function_output = df_result_from_json.to_string(index=False)
                    print("\nSaida para busca_Checkin:\n", function_output, "\nData alvo sugerida pela funcao:\n", function_args.get("date"))
                if function_name == 'ultimo_Checkin':
                    function_output = app.get_last_checkin_details()
                    print("\nSaida para ultimo_Checkin:\n", function_output)
                if function_name == 'registra_Memoria':
                    eh_pergunta = True
                    function_output = "pergunte ao usuário se ele quer salvar essas informações. Apresente as informações que ele pediu e confirme se ele quer mesmo."
                    print("\nSaida para registra_Memoria, pois isso claramente é um pedido para salvar na memória:\n", function_output)
                messages.append(
                    {
                        "tool_call_id": resposta.id,
                        "role": "assistant",
                        "name": function_name,
                        "content": function_output,
                    })

            second_response = client.chat.completions.create(
                model="o3-mini",
                reasoning_effort="low",
                messages=messages,
                temperature=0.1  # Valor baixo para respostas mais determinísticas
                    model="o3-mini",

            )

            print('\n\n\n **_dentro do if que chama funcao_** \n\n\n')
            print("mensagens: \n", messages)
            return second_response.choices[0].message.content.strip(), eh_pergunta
        else:
            print('\n\n\n **_fora do if que chama funcao_** \n\n\n')
            print("mensagens: \n", messages)
            return completion.choices[0].message.content.strip(), eh_pergunta

    except Exception as e:
        print('Erro no método completions: ', e)
        send_msg.send_wapp_msg(phone_number_id, from_number, "Aconteceu algo errado 🫤")
        return "", eh_pergunta


def audio_transcription():

    audio_file = open("arquivo.mp3", "rb")

    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file
    )
    return (transcription.text)
    print(transcription.text)

def responde_emb(pergunta, dados, threads, data_atual, hora_atual, phone_number_id, from_number):
    df = pd.DataFrame(dados)
    df['embeddings'] = df['embeddings'].apply(np.array)
    resposta, tipo = answer_question(df, data_atual, hora_atual, phone_number_id, from_number, question=pergunta, lista_threads=threads, )
    print('------------------>>>>>>>>>>>>>>>>>>>>>>>>>', tipo)
    global first_item
    return resposta, first_item, tipo
