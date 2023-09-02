
import requests
import json

url = "https://graph.facebook.com/v17.0/116447921532317/messages"

def send_wapp_msg(content, token):
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "5521983163900",
        "type": "text",
        "text": {
            "preview_url": "false",
            "body": content
        },

    })
    headers = {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + token
    }


    response = requests.request("POST", url, headers=headers, data=payload)
    print(response.text)



