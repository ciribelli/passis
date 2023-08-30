json_data = {
    "https://twitter.com/OperacoesRio/status/1697002317512400957?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet": {
        "link": "https://twitter.com/OperacoesRio/status/1697002317512400957?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet",
        "snippet": "🚘 CARRO ENGUIÇADO NA TRANSOLÍMPICA Veículo ocupa uma faixa na altura de Colônia, sentido Avenida Brasil. Concessionária no local. Trânsito com retenções desde a Avenida Abelardo Bueno. #viasexpressas #CORInforma",
        "published_date": "há 39 minutos"
    },
    "https://twitter.com/OperacoesRio/status/1697001794180669761?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet": {
        "link": "https://twitter.com/OperacoesRio/status/1697001794180669761?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet",
        "snippet": "🚗🏍️🚌 TRÂNSITO NA AVENIDA BRASIL Sentido Centro com retenções no Caju; Sentido Zona Oeste lentidão em Coelho Neto e em Bangu. #viasexpressas #CORInforma",
        "published_date": "há 42 minutos"
    },
    "https://twitter.com/OperacoesRio/status/1696999263903924571?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet": {
        "link": "https://twitter.com/OperacoesRio/status/1696999263903924571?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet",
        "snippet": "ALERTA DE VENTO MODERADO NO RIO Entre 17h e 18h, houve registro de vento moderado no Forte de Copacabana (46,4 km/h). Fonte: INMET. #temporj #CORInforma",
        "published_date": "há 52 minutos"
    },
    "https://twitter.com/OperacoesRio/status/1696998722125676766?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet": {
        "link": "https://twitter.com/OperacoesRio/status/1696998722125676766?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet",
        "snippet": "✅ AVENIDA RIO BRANCO LIBERADA Via foi liberada após manifestação na altura da Avenida Nilo Peçanha, no Centro. Trânsito com boas condições no local. #centro #CORInforma",
        "published_date": "há 54 minutos"
    },
    "https://twitter.com/OperacoesRio/status/1696993982612492642?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet": {
        "link": "https://twitter.com/OperacoesRio/status/1696993982612492642?ref_src=twsrc%5Egoogle%7Ctwcamp%5Eserp%7Ctwgr%5Etweet",
        "snippet": "✅ TÚNEL REBOUÇAS LIBERADO Via foi liberada após CET-Rio ocupar uma faixa na saída da 1ª Galeria para reparos. Trânsito ainda lento desde o Elevado Rufino Pizarro. #viasexpressas #CORInforma",
        "published_date": "há 1 hora"
    }
}

saida = ""
for link, info in json_data.items():
    saida = saida + "✖️ " + info["snippet"] + ' ⏰ ' +  info["published_date"] + '\n'
print (saida)
