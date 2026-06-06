import agent
import main
import send_msg
import requests
import os
import json
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

def envia_prompt_api(content, data_atual, hora_atual, phone_number_id, from_number, wapp_id):
    if "✅" not in content:
        # envia mensagem para API openAI
        coletor, link, tipo_pergunta, prompt_final = app.fazer_perguntas(content, data_atual, hora_atual, phone_number_id, from_number)
        # 📅 registra mensagem recebida de usuario em threads📅
        input_data = '{"role": "user", "content":"' + content.replace('"', ' ') + '"}'
        app.salvar_thread(input_data, wapp_id)
        app.salvar_prompt(json.dumps(prompt_final, ensure_ascii=False), wapp_id)
        print('>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> \n\n ', prompt_final)
        return coletor, link, tipo_pergunta  
    # se tiver "✅", não faz nada e retorna valores nulos
    return None, None, None

def responde_usuario_salva_thread(phone_number_id, from_number, coletor):
    # envia a resposta texto openAI
    wapp_response = send_msg.send_wapp_msg(phone_number_id, from_number, coletor)
    response_dict = wapp_response.json()
    if "messages" in response_dict and response_dict["messages"]:
        wapp_id = response_dict["messages"][0]["id"]
        # 📅 registra mensagem gerada pelo sistema em threads 📅
        input_data = '{"role": "assistant", "content":"' + coletor.replace('"', ' ') + '"}'
        app.salvar_thread(input_data, wapp_id)
    else:
        print("Resposta sem mensagens. Nada salvo em thread.")

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
        wapp_id = message['id']
        print(from_number)
        # captura o timestamp das mensagem para contextos de data
        timestamp = entry['changes'][0]['value']['messages'][0]['timestamp']
        data_atual, hora_atual = hora_e_data(timestamp)

        # Verifica se há um ID de botão de resposta
        button_reply_id = message['interactive']['button_reply']['id'] if 'interactive' in message and 'button_reply' in message['interactive'] else None

        # Verifica se há um corpo de mensagem de texto
        msg_body = message['text']['body'] if 'text' in message else None

        if button_reply_id:
            # Tratando o conteúdo do reply:
            button_id = message['interactive']['button_reply']['id']
            button_action = message['interactive']['button_reply']['title']
            wapp_id = message['context']['id']
            print('>>>> ', button_id, button_action, wapp_id)
            if button_id == "1":
                # memorizar a informação
                content = app.get_thread_content_by_wapp_id(wapp_id)
                print(content)
                coletor = app.salvar_memoria_recebida(content.lower())
                # responde o usuario no wapp e salva a conversa
                responde_usuario_salva_thread(phone_number_id, from_number, coletor)
            elif button_id == "0":
                # memorizar a informação
                content = app.get_thread_content_by_wapp_id(wapp_id)
                print(content)
                coletor, link, tipo_pergunta = envia_prompt_api(content, data_atual, hora_atual, phone_number_id, from_number, wapp_id)
                responde_usuario_salva_thread(phone_number_id, from_number, coletor)
            elif button_id == "save_img":
                content = app.get_thread_content_by_wapp_id(wapp_id)
                try:
                    content_json = json.loads(content)
                    text = content_json.get("content", "")
                except json.JSONDecodeError:
                    text = content
                
                import re
                titulo = "Imagem Documento"
                descricao = text
                image_id = None
                
                m_titulo = re.search(r'Título:\s*(.*?)\\n', text) or re.search(r'Título:\s*(.*?)\n', text)
                if m_titulo:
                    titulo = m_titulo.group(1).strip()
                    
                m_desc = re.search(r'Descrição:\s*(.*?)\\n\[ID:', text, re.DOTALL) or re.search(r'Descrição:\s*(.*?)\n\[ID:', text, re.DOTALL)
                if m_desc:
                    descricao = m_desc.group(1).strip()
                    
                m_id = re.search(r'\[ID:\s*([^\]]+)\]', text)
                if m_id:
                    image_id = m_id.group(1).strip()
                    
                if image_id and os.path.exists(f"{image_id}.jpg"):
                    with open(f"{image_id}.jpg", "rb") as f:
                        binario = f.read()
                    app.salvar_documento_direto(titulo, descricao, binario)
                    send_msg.send_wapp_msg(phone_number_id, from_number, f"✅ Documento '{titulo}' salvo com sucesso no repositório!")
                else:
                    send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Erro: Arquivo da imagem não encontrado localmente.")
            elif button_id == "cancel_img":
                send_msg.send_wapp_msg(phone_number_id, from_number, "Ok, a imagem foi descartada.")
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
                coletor, datajson = main.busca_X2(token)
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
                # avalia se a mensagem não é feedback dos recursos de automação
                if "✅" not in content:
                    coletor, link, tipo_pergunta = envia_prompt_api(content, data_atual, hora_atual, phone_number_id, from_number, wapp_id)
                    
            # envia a mensagem de retorno para o whatsapp
            try:
                if (tipo_pergunta):
                    send_msg.send_wapp_question(phone_number_id, from_number, coletor)
                else:
                    # responde o usuario no wapp e salva a conversa
                    responde_usuario_salva_thread(phone_number_id, from_number, coletor)

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
                    transcricao = agent.audio_transcription()
                    # Enviar a transcrição de volta ao usuário
                    wapp_response = send_msg.send_wapp_audio_reply(phone_number_id, from_number, transcricao)
                    # 📅 registra transcrição gerada pelo sistema em threads📅
                    response_dict = wapp_response.json()
                    wapp_id = response_dict["messages"][0]["id"]
                    input_data = '{"role": "assistant", "content":"' + transcricao.replace('"', ' ') + '"}'
                    app.salvar_thread(input_data, wapp_id)
                elif media_type == 'image':
                    image_id = entry['changes'][0]['value']['messages'][0]['image']['id']
                    send_msg.send_wapp_msg(phone_number_id, from_number, "👁 _analisando imagem_ 🖼")
                    
                    media_url = send_msg.get_url_wapp_media(image_id)
                    file_path = send_msg.download_media(media_url, filename=image_id)
                    
                    if file_path:
                        analysis = agent.analyze_image(file_path)
                        analysis_with_id = f"{analysis}\n[ID: {image_id}]"
                        
                        wapp_response = send_msg.send_wapp_image_reply(phone_number_id, from_number, analysis_with_id)
                        
                        response_dict = wapp_response.json()
                        if "messages" in response_dict and response_dict["messages"]:
                            wapp_id = response_dict["messages"][0]["id"]
                            input_dict = {"role": "assistant", "content": analysis_with_id}
                            input_data = json.dumps(input_dict, ensure_ascii=False)
                            app.salvar_thread(input_data, wapp_id)
                    else:
                        send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Erro ao baixar a imagem.")
                else:
                    print(f"Tipo de mídia não suportado: {media_type}")
                    send_msg.send_wapp_msg(phone_number_id, from_number, "Tipo de mídia não suportado. Por favor, envie um áudio ou imagem.")
            except KeyError as e:
                print(f"Erro ao processar a mensagem: {e}")
                send_msg.send_wapp_msg(phone_number_id, from_number, "Erro ao processar a mensagem. Por favor, tente novamente.")



