
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
    url = "https://graph.facebook.com/v17.0/116447921532317/messages"
    wapp_token = os.getenv('WHATSAPP_TOKEN')
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + wapp_token
    }
    # https://developers.facebook.com/docs/whatsapp/guides/interactive-messages/
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "5521983163900",
        "type": "interactive",
        "interactive": {
            "header": {
                "type": "text",
                "text": "Sobre o sono"
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
                        "reply": {
                            "id": "0",
                            "title": "1"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "1",
                            "title": "2"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "2",
                            "title": "3"
                        }
                    }
                ]
            }
        }
    })

    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.text)
    #
    # print("enviando mensagem pergunta", coletor)
    # wapp_token = os.getenv('WHATSAPP_TOKEN')
    # fb_url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages?access_token={wapp_token}"
    # payload = json.dumps({
    #     "messaging_product": "whatsapp",
    #     "recipient_type": "individual",
    #     "to": from_number,
    #     "type": "interactive",
    #     "interactive": {
    #         "header": {
    #             "type": "text",
    #             "text": coletor
    #         },
    #         "type": "button",
    #         "body": {
    #             "text": "Dificuldade de acordar, sendo 1 muito fácil, 2 indiferente e 3 difícil:"
    #         },
    #         "footer": {  # optional
    #             "text": ""
    #         },
    #         "action": {
    #             "buttons": [
    #                 {
    #                     "type": "reply",
    #                     "reply": {
    #                         "id": "0",
    #                         "title": "1"
    #                     }
    #                 },
    #                 {
    #                     "type": "reply",
    #                     "reply": {
    #                         "id": "1",
    #                         "title": "2"
    #                     }
    #                 },
    #                 {
    #                     "type": "reply",
    #                     "reply": {
    #                         "id": "2",
    #                         "title": "3"
    #                     }
    #                 }
    #             ]
    #         }
    #     }
    # })
    # headers = {"Content-Type": "application/json"}
    # response = requests.post(fb_url, json=payload, headers=headers)
    # print(response)
    # print(response.text)

