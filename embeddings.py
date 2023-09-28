import requests
import pandas as pd
import json
from app import app  # Importe a instância de app de app.py

def remove_newlines(serie):
    serie = serie.replace('\n', ' ')
    serie = serie.replace('\\n', ' ')
    serie = serie.replace('\r', ' ')
    serie = serie.replace('\r', ' ')
    serie = serie.replace('   ', ' ')
    serie = serie.replace('  ', ' ')
    serie = serie.replace('-', ' ')
    serie = serie.replace(',', ' ')
    serie = serie.replace('_', ' ')
    serie = serie.replace('📝', '')
    return serie

def update_embeddings():
    table_list = ['memorias', 'recuperar_lista_documentos']


    resultados = []  # Lista para armazenar os valores concatenados de todas as linhas


    for table in table_list:
        response = app.test_client().get('/'+str(table))
        data = json.loads(response.text)
        df = pd.DataFrame(data)
        # Iterar pelas linhas do DataFrame
        for index, row in df.iterrows():
            concatenated_values = ''
            # Iterar pelas colunas e adicionar o nome da coluna e o valor à string
            for col_name in df.columns:
                concatenated_values += col_name + ': ' + remove_newlines(str(row[col_name])) + '. '
            # Adicionar o nome da tabela, o ID (índice) e o conteúdo concatenado à lista de resultados
            resultados.append([table, index, concatenated_values])

    df = pd.DataFrame(resultados, columns=['tabela', 'index', 'texto'])


    import tiktoken
    # from openai.embeddings_utils import get_embedding, cosine_similarity
    tokenizer = tiktoken.get_encoding("cl100k_base")

    df['n_tokens'] = df.texto.apply(lambda x: len(tokenizer.encode(x)))
    max_tokens = 200


    def split_into_many(text, max_tokens = max_tokens):

        # Split the text into sentences
        sentences = text.split('. ')
        print('--------------------', sentences)
        # Get the number of tokens for each sentence
        n_tokens = [len(tokenizer.encode(" " + sentence)) for sentence in sentences]
        print(n_tokens)
        chunks = []
        tokens_so_far = 0
        chunk = []

        # Loop through the sentences and tokens joined together in a tuple
        for sentence, token in zip(sentences, n_tokens):

            # If the number of tokens so far plus the number of tokens in the current sentence is greater
            # than the max number of tokens, then add the chunk to the list of chunks and reset
            # the chunk and tokens so far
            if tokens_so_far + token > max_tokens:
                chunks.append(". ".join(chunk) + ".")
                chunk = []
                tokens_so_far = 0

            # If the number of tokens in the current sentence is greater than the max number of
            # tokens, go to the next sentence
            if token > max_tokens:
                continue

            # Otherwise, add the sentence to the chunk and add the number of tokens to the total
            chunk.append(sentence)
            tokens_so_far += token + 1

        return chunks

    shortened = []

    # Loop through the dataframe
    for row in df.iterrows():

        # If the text is None, go to the next row
        if row[1]['texto'] is None:
            continue

        # If the number of tokens is greater than the max number of tokens, split the text into chunks
        if row[1]['n_tokens'] > max_tokens:
            shortened += split_into_many(row[1]['texto'])

        # Otherwise, add the text to the list of shortened texts
        else:
            shortened.append( row[1]['texto'] )


    df2 = pd.DataFrame(shortened, columns = ['texto'])
    df2['n_tokens'] = df.texto.apply(lambda x: len(tokenizer.encode(x)))


    import openai
    import os
    from dotenv import load_dotenv

    load_dotenv()
    openai.api_key = os.getenv('OPENAI_API_KEY')
    df['embeddings'] = df.texto.apply(lambda x: openai.Embedding.create(input=x, engine='text-embedding-ada-002')['data'][0]['embedding'])
    df.to_csv('embeddings.csv', index=False)
    return ('Atualizado ✅')
