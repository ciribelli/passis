import context_gpt35turboFuncCalling
import main
import send_msg
import requests
import os
import app
from datetime import datetime, timedelta
import pytz

def hora_e_data(timestamp, user_timezone='America/Sao_Paulo'):
    try:
        data_hora = datetime.fromtimestamp(int(timestamp))
        user_tz = pytz.timezone(user_timezone)
        data_hora = pytz.utc.localize(data_hora).astimezone(user_tz)
        data_formatada = data_hora.strftime('%d-%m-%Y')
        hora_formatada = data_hora.strftime('%H:%M')
        return data_formatada, hora_formatada
    except Exception as e:
        return None, f"Error: {e}"


def chatflow(entry):
    # Verifica se há mensagens na solicitação
    if 'changes' in entry and entry['changes'][0]['value'].get('messages'):
        # print('-------------------------')
        # print(entry)
        # print('-------------------------')
        message = entry['changes'][0]['value']['messages'][0]
        print('entry_metadata: ')
        print(entry['changes'][0]['value']['metadata'])
        phone_number_id = entry['changes'][0]['value']['metadata']['phone_number_id']
        from_number = message['from']
        print(from_number)
        # captura o timestamp das mensagem para contextos de data
        timestamp = entry['changes'][0]['value']['messages'][0]['timestamp']
        data_atual, hora_atual = hora_e_data(timestamp)

        # Verifica se há um ID de botão de resposta
        button_reply_id = message['interactive']['button_reply']['id'] if 'interactive' in message and 'button_reply' in message['interactive'] else None

        # Verifica se há um corpo de mensagem de texto
        msg_body = message['text']['body'] if 'text' in message else None

        if button_reply_id:
            print("button_reply.id:", button_reply_id)
            # Faça algo com o button_reply.id
            print("vamos entender a mensagem completa: ------------------ ENTRY")
            print(entry)
            print("vamos entender a mensagem completa: ------------------ MESSAGE")
            print(message)
        elif msg_body:
            print("msg_body:", msg_body)
            tipo_pergunta = False
            content = msg_body
            coletor = ""
            link = ""
            # para JOGOS
            if content.lower() == "jogos" or content.lower() == "jogo":
                coletor, datajson = main.get_jogos_df(data_atual)
            # para CIDADE e TRANSITO
            elif content.lower() == "cidade" or content.lower() == "cidades" or content.lower() == "transito":
                token = os.getenv('token_X')
                coletor, datajson = main.busca_X("operacoesrio", token)
            # para CLIMA
            elif content.lower() == "Clima" or content.lower() == "Climas" or content.lower() == "clima" or content.lower() == "climas":
                token = os.getenv('token_clima')
                coletor, datajson = main.busca_Clima(token)
            # para CHECKIN
            elif content.lower() == "checkin":
                data_inicio = datetime.strptime(str(data_atual), '%d-%m-%Y') - timedelta(days=4)
                data_inicio_formatada = data_inicio.strftime('%d-%m-%Y')
                coletor, datajson = app.get_checkins_by_date(data_inicio_formatada, data_atual)
                print(coletor)
            # para CLIMA
            elif content.lower() == "localização" or content.lower() == "localizacao":
                data_inicio = datetime.strptime(str(data_atual), '%d-%m-%Y') - timedelta(days=4)
                data_inicio_formatada = data_inicio.strftime('%d-%m-%Y')
                coletor, datajson = app.obter_cidade_atual_e_clima(data_inicio_formatada, data_atual)
                print(coletor)
            elif "📝" in content.lower():
                coletor = app.salvar_memoria_recebida(content.lower())
            elif "🔄" in content.lower():
                print(">>>> atualizando embeddings <<<<")
                coletor = app.inserir_dados()
            elif "📝" in content.lower():
                coletor = app.salvar_memoria_recebida(content.lower())
            elif "❤" in content.lower():
                coletor = app.plota_grafico("EDISEN", 'blue')
            elif content.lower() == "responder":
                tipo_pergunta = True
            else:
                ##### avalia se a mensagem nao eh feedback dos recursos de automacao #####
                if not "✅" in content.lower():
                    # envia mensagem para API openAI
                    coletor, link, tipo_pergunta = app.fazer_perguntas(content, data_atual, hora_atual, phone_number_id, from_number)
                    # registra mensagem de usuario na memoria
                    input_data = '{"role": "user", "content":"' + content.replace('"', ' ') + '"}'
                    app.salvar_thread(input_data)
                    input_data = '{"role": "assistant", "content":"' + coletor.replace('"', ' ') + '"}'
                    app.salvar_thread(input_data)
                    
            # envia a mensagem de retorno para o whatsapp
            try:
                if (tipo_pergunta):
                    send_msg.send_wapp_question(phone_number_id, from_number, coletor)
                else:
                    # envia a resposta texto openAI
                    send_msg.send_wapp_msg(phone_number_id, from_number, coletor)
                    # caso seja um documento, envia o arquivo/imagem
                    if( "documentos" in link.lower()):
                        # ATENCAO: ideal seria mudar nome da tabela no bd
                        link = link.replace("recuperar_lista_documentos", "recuperar_documento")
                        send_msg.send_wapp_image(phone_number_id, from_number, coletor, link)

            except requests.exceptions.RequestException as e:
                print("Erro ao enviar mensagem:", str(e))

        else:
            # arquivos de mídia tratados aqui
            print("Nem button_reply.id nem msg_body presentes.")
            try:
                # passo 1: verificar e recuperar 'tipo' e 'id' da mídia
                media_type = entry['changes'][0]['value']['messages'][0]['type']
                if media_type == 'audio':
                    # Recuperar o ID do áudio
                    audio_id = entry['changes'][0]['value']['messages'][0]['audio']['id']
                    # Enviar mensagem de transcrição em andamento
                    send_msg.send_wapp_msg(phone_number_id, from_number, "👂 _transcrevendo_ 🖋")
                    # Obter URL da mídia
                    media_url_response = send_msg.get_url_wapp_media(audio_id)
                    # Baixar a mídia
                    send_msg.download_media(media_url_response)
                    # Realizar a transcrição do áudio
                    transcricao = context_gpt35turboFuncCalling.audio_transcription()
                    # Enviar a transcrição de volta ao usuário
                    send_msg.send_wapp_msg(phone_number_id, from_number, transcricao)
                else:
                    print(f"Tipo de mídia não suportado: {media_type}")
                    send_msg.send_wapp_msg(phone_number_id, from_number, "Tipo de mídia não suportado. Por favor, envie um áudio.")
            except KeyError as e:
                print(f"Erro ao processar a mensagem: {e}")
                send_msg.send_wapp_msg(phone_number_id, from_number, "Erro ao processar a mensagem. Por favor, tente novamente.")



