import numpy as np
import pandas as pd
from openai import OpenAI
from scipy.spatial.distance import cosine
from dotenv import load_dotenv
import os
import json

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
    question="aqui vem a pergunta",
    lista_threads="aqui estarao as threads",
    max_len=1200,
    size="ada",
    debug=True,
):

    context = create_context(question, df, max_len=max_len, size=size,)

    if debug:
        print("Context:\n" + context)
        print("\n\n")

    message_text = ''

    for thread in lista_threads:
        content = json.loads(thread[0])['content']
        message_text += content + '\n'

    mensagem = "Você é meu assistente pessoal para ideias e lembretes sobre minha rotina. Receba abaixo minhas informações pessoais:" + "\n" + context + "\n" "Algumas mensagens já trocadas que podem ajudar com contexto: " + "\n" + message_text + "\n Agora a pergunta principal que você precisa responder: " + "\n" + question

    try:

        response = client.completions.create(
            model="gpt-3.5-turbo-instruct",
            prompt=mensagem
        )

        return response.choices[0].text.strip()

    except Exception as e:
        print(e)
        return ""

def responde_emb(pergunta, dados, threads):
    df = pd.DataFrame(dados)
    df['embeddings'] = df['embeddings'].apply(np.array)
    resposta = answer_question(df, question=pergunta, lista_threads=threads).replace("\n", '<br>')
    saida = resposta.replace("<br>", "\n")
    global first_item
    return saida, first_item

