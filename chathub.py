import main
import send_msg
import requests
import os
import app

def chatflow(entry):
    # Verifica se há mensagens na solicitação
    if 'changes' in entry and entry['changes'][0]['value'].get('messages'):
        message = entry['changes'][0]['value']['messages'][0]
        phone_number_id = entry['changes'][0]['value']['metadata']['phone_number_id']
        from_number = message['from']

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
                coletor, datajson = main.get_jogos_df()
            # para CIDADE e TRANSITO
            elif content.lower() == "cidade" or content.lower() == "cidades" or content.lower() == "transito":
                token = os.getenv('token_X')
                coletor, datajson = main.busca_X("operacoesrio", token)
            # para CLIMA
            elif content.lower() == "Clima" or content.lower() == "Climas" or content.lower() == "clima" or content.lower() == "climas":
                token = os.getenv('token_clima')
                coletor, datajson = main.busca_Clima(token)
            elif "📝" in content.lower():
                coletor = app.salvar_memoria_recebida(content.lower())
            elif "🔄" in content.lower():
                print(">>>> atualizando embeddings <<<<")
                coletor = app.inserir_dados()
            elif content.lower() == "responder":
                tipo_pergunta = True
            else:
                ##### avalia se a mensagem nao eh feedback dos recursos de automacao #####
                if not "✅" in content.lower():
                    coletor, link = app.fazer_perguntas(content)
                    
            # envia a mensagem de retorno para o whatsapp
            try:
                if (tipo_pergunta):
                    send_msg.send_wapp_image(phone_number_id, from_number, "Aqui será o texto da pergunta")
                else:
                    # envia a resposta texto openAI
                    send_msg.send_wapp_msg(phone_number_id, from_number, coletor)
                    # caso seja um documento, envia o arquivo/imagem
                    if( "documentos" in link.lower()):
                        send_msg.send_wapp_image(phone_number_id, from_number, coletor, link)

            except requests.exceptions.RequestException as e:
                print("Erro ao enviar mensagem:", str(e))

        else:
            print("Nem button_reply.id nem msg_body presentes.")