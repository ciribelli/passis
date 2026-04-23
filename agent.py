"""
agent.py — Cliente/Agent para o Passis.

Descobre tools do registry em passis_tools, monta schemas OpenAI,
chama GPT-4o e despacha tool calls diretamente (in-process).
Substitui context_FuncCalling.py.
"""

import json
import numpy as np
import pandas as pd
from openai import OpenAI
from scipy.spatial.distance import cosine
from dotenv import load_dotenv
import os
import send_msg
import passis_tools

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


# ---------------------------------------------------------------------------
# EMBEDDINGS / CONTEXTO
# ---------------------------------------------------------------------------

def create_context(question, df, max_len=1200):
    """Busca contexto semântico por similaridade de embeddings.
    Retorna (texto_contexto, first_item_link)."""
    q_emb = client.embeddings.create(
        input=question, model='text-embedding-ada-002'
    ).data[0].embedding

    df = df.copy()
    df["distances"] = df["embeddings"].apply(lambda x: cosine(q_emb, x))

    returns = []
    links = []
    cur_len = 0

    for _, row in df.sort_values('distances').iterrows():
        cur_len += row['n_tokens'] + 4
        if cur_len > max_len:
            break
        returns.append(row["texto"])
        links.append(str(row["tabela"]) + '/' + str(row["index"]))

    first_item = links[0] if links else ""
    return "\n🤖\n".join(returns), first_item


# ---------------------------------------------------------------------------
# OPENAI TOOL SCHEMAS — gerados do REGISTRY
# ---------------------------------------------------------------------------

def get_openai_tools():
    """Retorna a lista de tools no formato OpenAI, gerada do registry."""
    return [entry["schema"] for entry in passis_tools.REGISTRY.values()]


# ---------------------------------------------------------------------------
# DISPATCHER IN-PROCESS
# ---------------------------------------------------------------------------

def call_tool(name, args):
    """Chama a tool diretamente via registry — sem HTTP, sem subprocesso."""
    entry = passis_tools.REGISTRY.get(name)
    if entry is None:
        print("[WARN] Tool desconhecida chamada pelo modelo: '%s'" % name)
        return "Função '%s' não encontrada." % name

    try:
        result = entry["fn"](**args)
        return str(result)
    except Exception as e:
        print("[ERRO] Falha ao executar tool '%s': %s" % (name, e))
        return "Erro ao executar '%s': %s" % (name, str(e))


# ---------------------------------------------------------------------------
# AGENT PRINCIPAL — substitui answer_question + responde_emb
# ---------------------------------------------------------------------------

def responde_mcp(
    pergunta,
    dados,
    threads,
    data_atual,
    hora_atual,
    phone_number_id,
    from_number,
    eh_pergunta=False,
):
    """Entry point. Mesma assinatura de retorno que responde_emb:
    (resposta, first_item, eh_pergunta, messages)"""

    print("--> responde_mcp às %s: %s" % (hora_atual, pergunta))

    # Monta DataFrame de embeddings
    df = pd.DataFrame(dados)
    df['embeddings'] = df['embeddings'].apply(np.array)

    # Busca contexto semântico
    context, first_item = create_context(pergunta, df)
    print("Context:\n" + context + "\n\n")

    # Injeta contexto de sistema nas tools que precisam
    passis_tools.set_context(
        data_atual=data_atual,
        question=pergunta,
        context_text=context,
    )

    # System prompt (mantido igual ao original)
    system_prompt = (
        "Você é meu assistente pessoal e seus assuntos de domínio são "
        "minhas memórias, localização, compromissos (checkins), clima e o trânsito."
        "Saiba que hoje é " + data_atual + " e agora são " + hora_atual + "\n"
        "Formate todas as respostas para o WhatsApp usando: asteriscos para "
        "negrito, underscores para itálico, - para bullets, 1. 2. 3. para "
        "listas numeradas, e mantenha frases curtas para boa leitura. "
        "Não use HTML nem Markdown."
        "Receba abaixo minhas informações pessoais:"
        "\n\n\n << >> \n\n\n" + context + "\n"
    )

    messages = [{"role": "system", "content": system_prompt}]

    # Carrega histórico de threads
    try:
        for thread in reversed(threads):
            try:
                messages.append(json.loads(thread[0], strict=False))
            except json.JSONDecodeError as e:
                print("Erro de decodificação JSON: %s" % e)
    except Exception:
        pass

    messages.append({"role": "user", "content": pergunta})
    print("mensagens:\n", messages)

    try:
        # 1ª chamada ao modelo com as tools
        openai_tools = get_openai_tools()
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
        )

        tool_calls = completion.choices[0].message.tool_calls
        print("Tool calls detectadas:", tool_calls)

        # Se não houve tool calls, retorna direto
        if not tool_calls:
            return (
                completion.choices[0].message.content,
                first_item,
                eh_pergunta,
                messages,
            )

        # Sinaliza ao usuário que está processando
        send_msg.send_wapp_msg(
            phone_number_id, from_number, "⏳ _Avaliando pra você.._"
        )

        # Adiciona mensagem do assistente com as tool_calls (obrigatório pela API)
        messages.append(completion.choices[0].message)

        # Despacha cada tool call
        for tc in tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            print("[tool] Chamando '%s' com args=%s" % (tc.function.name, args))

            output = call_tool(tc.function.name, args)
            print("[tool] Saída de '%s':\n%s\n" % (tc.function.name, output))

            # Trata sinal especial de registra_Memoria
            if output == "__REGISTRAR_MEMORIA__":
                eh_pergunta = True
                output = (
                    "pergunte ao usuário se ele quer salvar essas informações. "
                    "Apresente as informações que ele pediu e confirme se ele quer mesmo."
                )

            # Role correto: "tool" (não "assistant" como no código original)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": output,
            })

        # 2ª chamada com os resultados das tools
        second_response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
        )

        print('\n\n **_dentro do if que chama funcao_** \n\n')
        return (
            second_response.choices[0].message.content,
            first_item,
            eh_pergunta,
            messages,
        )

    except Exception as e:
        print('Erro em responde_mcp: ', e)
        send_msg.send_wapp_msg(
            phone_number_id, from_number, "Aconteceu algo errado 🫤"
        )
        return "", first_item, eh_pergunta, messages


# ---------------------------------------------------------------------------
# AUDIO (mantido do original)
# ---------------------------------------------------------------------------

def audio_transcription():
    audio_file = open("arquivo.mp3", "rb")
    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file
    )
    return transcription.text
