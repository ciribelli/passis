
import requests
import os

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