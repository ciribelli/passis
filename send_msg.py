
import requests
import json
import os

def send_wapp_msg(phone_number_id, from_number, coletor):
    print("enviando mensagem normal")
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
    print("enviando mensagem pergunta")
    wapp_token = os.getenv('WHATSAPP_TOKEN')
    fb_url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages?access_token={wapp_token}"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": from_number,
        "type": "interactive",
        "interactive": {
            "header": {
                "type": "text",
                "text": coletor
            },
            "type": "button",
            "body": {
                "text": "Dificuldade de acordar, sendo 1 muito fácil, 2 indiferente e 3 difícil:"
            },
            "footer": {  # optional
                "text": ""
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "sub_type": "quick_reply",
                        "reply": {
                            "id": "0",
                            "title": "1"
                        }
                    },
                    {
                        "type": "reply",
                        "sub_type": "quick_reply",
                        "reply": {
                            "id": "1",
                            "title": "2"
                        }
                    },
                    {
                        "type": "reply",
                        "sub_type": "quick_reply",
                        "reply": {
                            "id": "2",
                            "title": "3"
                        }
                    }
                ]
            }
        }
    })
    headers = {"Content-Type": "application/json"}
    response = requests.post(fb_url, json=payload, headers=headers)

