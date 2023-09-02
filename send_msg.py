
import requests
import json
import os

def send_wapp_msg(phone_number_id, from_number, coletor):
    # Faz o envio da mensagem de volta
    wapp_token = os.getenv('WHATSAPP_TOKEN')
    fb_url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages?access_token={wapp_token}"
    payload = {
        "messaging_product": "whatsapp",
        "to": from_number,
        "text": {"body": coletor}
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(fb_url, json=payload, headers=headers)



