import numpy as np
import pandas as pd
import openai
from openai.embeddings_utils import distances_from_embeddings
from dotenv import load_dotenv
import os


def create_context(
    question, df, max_len=1800, size="ada"
):
    """
    Create a context for a question by finding the most similar context from the dataframe
    """
    load_dotenv()
    openai.api_key = os.getenv('OPENAI_API_KEY')

    # Get the embeddings for the question
    q_embeddings = openai.Embedding.create(input=question, engine='text-embedding-ada-002')['data'][0]['embedding']

    # Get the distances from the embeddings
    df['distances'] = distances_from_embeddings(q_embeddings, df['embeddings'].values, distance_metric='cosine')

    returns = []
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

    # Return the context
    return "\n\n###\n\n".join(returns)


def answer_question(
    df,
    model="text-davinci-003",
    question="Am I allowed to publish model outputs to Twitter, without a human review?",
    max_len=1800,
    size="ada",
    debug=True,
    max_tokens=500,
    stop_sequence="\n"
):
    """
    Answer a question based on the most similar context from the dataframe texts
    """
    context = create_context(
        question,
        df,
        max_len=max_len,
        size=size,
    )
    # If debug, print the raw model response
    if debug:
        print("Context:\n" + context)
        print("\n\n")

    try:
        # Create a completions using the question and context
        response = openai.Completion.create(
            prompt=f"Você é meu assistente para assuntos pessoais e me ajuda com ideias e lembrentes sobre minha rotina e o que acontece no mundo. Responda por favor a pergunta que chegou abaixo sendo objetivo e preciso, dentro do possível: \n\nContexto: {context}\n\n---\n\nPergunta: {question}\nAnswer:",
            temperature=0,
            max_tokens=max_tokens,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            stop="20",
            model=model,
        )
        return response["choices"][0]["text"].strip()
    except Exception as e:
        print(e)
        return ""

def responde(pergunta):
    df=pd.read_csv('embeddings.csv', index_col=0)
    df['embeddings'] = df['embeddings'].apply(eval).apply(np.array)
    print(df)
    resposta = answer_question(df, question=pergunta).replace("\n", '<br>')
    resposta = resposta.replace("<br>", "\n")
    return resposta

