import numpy as np
import pandas as pd
from openai import OpenAI
from scipy.spatial.distance import cosine
from dotenv import load_dotenv
import os
import json
import main
import app

client = OpenAI()

first_item = ""
def create_context(question, df, max_len=1200, size="ada"):
    load_dotenv()
    client.api_key = os.getenv('OPENAI_API_KEY')
    # Get the embeddings for the question // nao documentado pela opeanAI
    q_embeddings = client.embeddings.create(input=question, model='text-embedding-ada-002').data[0].embedding
    df["distances"] = df["embeddings"].apply(lambda x: cosine(q_embeddings, x))

    returns = []
    links = []
    cur_len = 0

    # Sort by distance and add the text to the context until the context is too long
    for i, row in df.sort_values('distances', ascending=True).iterrows():
        # Add the length of the text to the current length
        cur_len += row['n_tokens'] + 4
        # If the context is too long, break
        if cur_len > max_len:
            break
        # Else add it to the text that is being returned
        returns.append(row["texto"])
        links.append(str(row["tabela"])+'/'+str(row["index"]))

    global first_item
    first_item = links[0]
    # Return the context
    return "\n🤖\n".join(returns)

def answer_question(
    df,
    data_atual="alguma data",
    hora_atual="alguma hora",
    question="aqui vem a pergunta",
    lista_threads="aqui estarao as threads",
    max_len=800,
    size="ada",
    debug=True,
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
                "name": "busca_Clima",
                "description": "Busca informações em tempo real para o clima da cidade do Rio de Janeiro. Informações como temperatura, precipitação, ventos, dentre outras. Não demanda parâmetros de entrada.",
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
    ]

    messages = [
        {
            "role": "system",
            "content": "Você é meu assistente pessoal. Receba abaixo minhas informações pessoais:" + "\n" + context + "Saiba que hoje é " + data_atual + " e agora são " + hora_atual
        }
    ]

    try:
        for thread in reversed(lista_threads):
            messages.append(json.loads(thread[0], strict=False))

        messages.append({"role": "user", "content": question})

        print("mensagens: \n", messages)

        completion = client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            messages=messages,
            tools=tools, # para chamada da funcao
            tool_choice="auto", # para chamada da funcao
        )

        respostas = completion.choices[0].message.tool_calls

        if respostas:
            # Para cada objeto na lista, extrair as informações relevantes e chamar a função
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
                    token = os.getenv('token_X')
                    function_output, datajson = main.busca_X("operacoesrio", token)
                    print("\nSaida para busca_Cidade:\n", function_output)
                #if function_name == 'busca_Checkin':
                    #coletor = app.get_checkins_by_date(data_inicio_formatada, data_atual)

                messages.append(
                    {
                        "tool_call_id": resposta.id,
                        "role": "assistant",
                        "name": function_name,
                        "content": function_output,
                    })


            second_response = client.chat.completions.create(
                model="gpt-3.5-turbo-1106",
                messages=messages
            )
            print('\n\n\n **_dentro do if que chama funcao_** \n\n\n')
            print("mensagens: \n", messages)
            return second_response.choices[0].message.content.strip()
        else:
            print('\n\n\n **_fora do if que chama funcao_** \n\n\n')
            print("mensagens: \n", messages)
            return completion.choices[0].message.content.strip()


    except Exception as e:
        print(e)
        return ""

def responde_emb(pergunta, dados, threads, data_atual, hora_atual):
    df = pd.DataFrame(dados)
    df['embeddings'] = df['embeddings'].apply(np.array)
    resposta = answer_question(df, data_atual, hora_atual, question=pergunta, lista_threads=threads).replace("\n", '<br>')
    saida = resposta.replace("<br>", "\n")
    global first_item
    return saida, first_item
