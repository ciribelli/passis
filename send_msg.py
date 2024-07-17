
import requests
import os

import context_gpt35turboFuncCalling


def send_wapp_msg(phone_number_id, from_number, coletor):
    wapp_token = os.getenv('WHATSAPP_TOKEN')
    fb_url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages?access_token={wapp_token}"
    payload = {
        "messaging_product": "whatsapp",
        "to": from_number,
        "text": {"body": coletor}
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(fb_url, json=payload, headers=headers)



def send_wapp_question(phone_number_id, from_number, coletor):
    wapp_token = os.getenv('WHATSAPP_TOKEN')
    fb_url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages?access_token={wapp_token}"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": from_number,
        "type": "interactive",
        "interactive": {
            "header": {
                "type": "text",
                "text": "Registro em memória 📝"
            },
            "type": "button",
            "body": {
                "text": coletor
            },
            "footer": {  # optional
                "text": ""
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "0",
                            "title": "Sim"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "1",
                            "title": "Cancelar"
                        }
                    }
                ]
            }
        }
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(fb_url, json=payload, headers=headers)

def send_wapp_image(phone_number_id, from_number, coletor, endpoint):
    wapp_token = os.getenv('WHATSAPP_TOKEN')
    url = os.getenv('url')
    link = url + endpoint
    print('recuperando o documento em: ', link)
    fb_url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages?access_token={wapp_token}"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": from_number,
        "type": "image",
        "header":{
        "type": "text",
        "text": coletor
        },
        "image": {
            "link": link
        }
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(fb_url, json=payload, headers=headers)
    print(response.text)


def get_url_wapp_media(id):
    wapp_token = os.getenv('WHATSAPP_TOKEN')
    fb_url = f"https://graph.facebook.com/v17.0/{id}"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {wapp_token}"
    }
    response = requests.get(fb_url, headers=headers)

    if response.status_code == 200:
        response_data = response.json()
        return response_data.get('url')
    else:
        response.raise_for_status()

def download_media(url):
    wapp_token = os.getenv('WHATSAPP_TOKEN')
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {wapp_token}"
    }
    response = requests.get(url, headers=headers)

    # Verificando se a requisição foi bem-sucedida
    if response.status_code == 200:
        # Detecta o tipo de conteúdo (imagem, áudio, etc.) da resposta
        content_type = response.headers['Content-Type']
        if 'image' in content_type:
            file_extension = 'jpg'
        elif 'audio' in content_type:
            file_extension = 'mp3'
        else:
            file_extension = 'bin'

        # Salvando o conteúdo do arquivo em um arquivo local
        file_path = f"arquivo.{file_extension}"
        with open(file_path, "wb") as file:
            file.write(response.content)
        print(f"Arquivo salvo com sucesso como {file_path}!")
        return file_path  # Retorna o caminho do arquivo salvo
    else:
        print(f"Falha ao baixar o arquivo. Status code: {response.status_code}")
        print("Resposta do servidor:", response.text)
        return None