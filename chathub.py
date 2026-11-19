import tempfile
import unicodedata
from pathlib import Path
import sqlalchemy as sa
from homilias import channel as homilia_channel, store as homilia_store
import agent
import main
import send_msg
import requests
import os
import json
import app
from datetime import datetime, timedelta, timezone
import pytz

HOMILIA_CONTEXT_KEYWORDS = (
    "homilia",
    "evangelho",
    "liturgia",
    "domingo do tempo comum",
    "padre",
    "nos passos de cristo",
)

HOMILIA_TRANSCRIPT_MARKERS = (
    "meus queridos irmaos",
    "queridos irmaos",
    "meus irmaos",
    "santo evangelho",
    "liturgia de hoje",
    "em nome do pai",
    "tempo comum",
    "quaresma",
    "advento",
    "pascoa",
    "nos passos de cristo",
    "palavra do senhor",
    "gloria a vos, senhor",
    "gloria a vos senhor",
)

HOMILIA_MIN_WORDS = 250
HOMILIA_MIN_BYTES = int(1.5 * 1024 * 1024)
HOMILIA_CONTEXT_WINDOW_MINUTES = 5


def _normalizar_texto(texto):
    if not texto:
        return ""
    normalized = unicodedata.normalize("NFKD", str(texto).casefold())
    return "".join(c for c in normalized if not unicodedata.combining(c))


def _tem_contexto_homilia_recente(from_number, timestamp=None):
    # 1a. Texto litúrgico encaminhado previamente em homilia_incoming
    try:
        dt = datetime.fromtimestamp(int(timestamp), timezone.utc) if timestamp else datetime.now(timezone.utc)
        with homilia_store.get_engine().connect() as conn:
            pending = conn.execute(
                sa.select(homilia_store.incoming.c.source_id).where(
                    homilia_store.incoming.c.owner == from_number,
                    homilia_store.incoming.c.source_id.like("text:%"),
                    homilia_store.incoming.c.received_at >= dt - timedelta(minutes=HOMILIA_CONTEXT_WINDOW_MINUTES),
                    homilia_store.incoming.c.received_at <= dt + timedelta(minutes=1),
                )
            ).first()
            if pending:
                return True
    except Exception as e:
        print(f"Aviso ao verificar homilia_incoming: {e}")

    # 1b. Última mensagem de texto do usuário em Thread nos últimos minutos
    try:
        cutoff = datetime.utcnow() - timedelta(minutes=HOMILIA_CONTEXT_WINDOW_MINUTES)
        recent_threads = (
            app.Thread.query
            .filter(app.Thread.date_created >= cutoff)
            .order_by(app.Thread.date_created.desc())
            .limit(5)
            .all()
        )
        for thread in recent_threads:
            try:
                payload = json.loads(thread.content, strict=False)
            except (json.JSONDecodeError, TypeError):
                continue
            if payload.get("role") == "user":
                norm_msg = _normalizar_texto(payload.get("content", ""))
                if any(kw in norm_msg for kw in HOMILIA_CONTEXT_KEYWORDS):
                    return True
                break
    except Exception as e:
        print(f"Aviso ao verificar Thread recente: {e}")

    return False


def eh_audio_homilia(file_path, transcricao, from_number, timestamp=None):
    """Detecção inteligente (Opção A): retorna True se o áudio tiver perfil claro de homilia."""
    if _tem_contexto_homilia_recente(from_number, timestamp=timestamp):
        return True

    word_count = len((transcricao or "").split())
    try:
        file_size = os.path.getsize(file_path) if (file_path and os.path.exists(file_path)) else 0
    except OSError:
        file_size = 0

    if word_count >= HOMILIA_MIN_WORDS or file_size > HOMILIA_MIN_BYTES:
        norm_transcricao = _normalizar_texto(transcricao)
        if any(marker in norm_transcricao for marker in HOMILIA_TRANSCRIPT_MARKERS):
            return True

    return False


def iniciar_fluxo_homilia(phone_number_id, from_number, source_id, audio_id, timestamp, transcricao, audio_bytes=None):
    """Registra o áudio no pipeline de homilias reutilizando a transcrição já gerada."""
    with homilia_store.get_engine().begin() as conn:
        homilia_store.register_audio(conn, source_id, from_number, timestamp)
        eid = homilia_store.offer(conn, source_id, from_number, phone_number_id, audio_id, transcricao or "")
        if audio_bytes:
            homilia_store.put_asset(conn, eid, "source", audio_bytes)
        homilia_store.transition(conn, eid, from_number, 1, "offered", "queued")
        tem_texto = bool(homilia_store.source_text(conn, source_id))

    if tem_texto:
        msg = (
            "🎙️ Homilia identificada e colocada na fila de preparo! "
            "Assim que a prévia (capa, áudio e descrição) ficar pronta, envio o link aqui."
        )
    else:
        msg = (
            "🎙️ Homilia identificada e colocada na fila de preparo! "
            "Se ainda não enviou o texto/título litúrgico, encaminhe-o agora "
            "(ou responda a este áudio) para orientar a edição."
        )
    send_msg.send_wapp_msg(phone_number_id, from_number, msg)
    return eid

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
        input_data = json.dumps({"role": "user", "content": content}, ensure_ascii=False)
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
        input_data = json.dumps({"role": "assistant", "content": coletor}, ensure_ascii=False)
        app.salvar_thread(input_data, wapp_id)
    else:
        print("Resposta sem mensagens. Nada salvo em thread.")

def chatflow(entry, verified=False):
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
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        button_reply_id = reply.get("id")
        podcast_owner = verified and homilia_channel.reviewer(from_number)


        # Verifica se há um corpo de mensagem de texto
        msg_body = message['text']['body'] if 'text' in message else None

        if button_reply_id:
            # Tratando o conteúdo do reply:
            button_id = button_reply_id
            button_action = reply.get('title')
            wapp_id = message.get('context', {}).get('id')
            audio_content = None
            if button_id.startswith('hom:'):
                if not podcast_owner:
                    return
                with homilia_store.get_engine().connect() as conn:
                    audio_content, button_id = homilia_channel.legacy_audio_action(conn, from_number, button_id)
                if not button_id:
                    return
            print('>>>> ', button_id, button_action, wapp_id)
            if button_id == "save_mem":
                # salvar memória via botão descritivo
                content = app.get_thread_content_by_wapp_id(wapp_id)
                print(content)
                if content:
                    coletor = app.salvar_memoria_recebida(content.lower())
                else:
                    coletor = "❌ Não encontrei o conteúdo para salvar."
                responde_usuario_salva_thread(phone_number_id, from_number, coletor)
            elif button_id == "cancel_mem":
                send_msg.send_wapp_msg(phone_number_id, from_number, "Ok, memória descartada.")
            elif button_id == "1":
                # memorizar a informação (áudio)
                content = audio_content or app.get_thread_content_by_wapp_id(wapp_id)
                print(content)
                if content:
                    coletor = app.salvar_memoria_recebida(content.lower())
                else:
                    coletor = "❌ Não encontrei o conteúdo para salvar."
                # responde o usuario no wapp e salva a conversa
                responde_usuario_salva_thread(phone_number_id, from_number, coletor)
            elif button_id == "0":
                # executar ação (áudio)
                content = audio_content or app.get_thread_content_by_wapp_id(wapp_id)
                print(content)
                coletor, link, tipo_pergunta = envia_prompt_api(content, data_atual, hora_atual, phone_number_id, from_number, wapp_id)
                responde_usuario_salva_thread(phone_number_id, from_number, coletor)
            elif button_id == "gerar_homilia" or button_id.startswith("gerar_homilia:"):
                # disparar manualmente o fluxo de homilia a partir do card de transcrição
                if not podcast_owner:
                    send_msg.send_wapp_msg(phone_number_id, from_number, "🔒 Recurso de homilias disponível apenas para o administrador do podcast.")
                    return
                audio_id = button_id.split(":", 1)[1] if ":" in button_id else None
                content = app.get_thread_content_by_wapp_id(wapp_id)
                if not audio_id:
                    send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Não foi possível identificar o áudio original. Reenvie o áudio para gerar a homilia.")
                    return
                iniciar_fluxo_homilia(phone_number_id, from_number, wapp_id or message['id'], audio_id, timestamp, content or "")
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
                    
                file_ext = None
                if image_id:
                    if os.path.exists(f"{image_id}.jpg"):
                        file_ext = "jpg"
                    elif os.path.exists(f"{image_id}.pdf"):
                        file_ext = "pdf"
                        
                if file_ext:
                    with open(f"{image_id}.{file_ext}", "rb") as f:
                        binario = f.read()
                    app.salvar_documento_direto(titulo, descricao, binario)
                    send_msg.send_wapp_msg(phone_number_id, from_number, f"✅ Documento '{titulo}' salvo com sucesso no repositório!")
                else:
                    send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Erro: Arquivo da mídia não encontrado localmente.")
            elif button_id == "cancel_img":
                send_msg.send_wapp_msg(phone_number_id, from_number, "Ok, a imagem foi descartada.")
            elif button_id.startswith("snooze_reminder_"):
                memoria_id = int(button_id.replace("snooze_reminder_", ""))
                resultado = app.snooze_lembrete(memoria_id)
                if resultado:
                    send_msg.send_wapp_msg(phone_number_id, from_number, resultado)
                else:
                    send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Lembrete não encontrado.")
            elif button_id.startswith("done_reminder_"):
                memoria_id = int(button_id.replace("done_reminder_", ""))
                memoria = app.Memoria.query.get(memoria_id)
                if memoria:
                    memoria.reminder_status = 'concluido'
                    app.db.session.commit()
                    send_msg.send_wapp_msg(phone_number_id, from_number, "✅ Lembrete concluído!")
                else:
                    send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Lembrete não encontrado.")
            elif button_id.startswith("archive_reminder_"):
                memoria_id = int(button_id.replace("archive_reminder_", ""))
                memoria = app.Memoria.query.get(memoria_id)
                if memoria:
                    memoria.reminder_status = 'arquivado'
                    memoria.reminder_time = None
                    app.db.session.commit()
                    send_msg.send_wapp_msg(phone_number_id, from_number, "📋 Lembrete arquivado. O conteúdo continua salvo nas suas memórias.")
                else:
                    send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Lembrete não encontrado.")
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
                # Chamamos sem token: a função agora usa Open-Meteo por cidade (default Rio de Janeiro)
                coletor, datajson = main.busca_Clima()
            # para CHECKIN
            elif content.lower() == "checkin":
                data_inicio = datetime.strptime(str(data_atual), '%d-%m-%Y') - timedelta(days=4)
                data_inicio_formatada = data_inicio.strftime('%d-%m-%Y')
                coletor, datajson = app.get_checkins_by_date(data_inicio_formatada, data_atual)
                print(coletor)
            # para RELATORIO
            elif content.lower() in {"relatorio", "relatório", "relatorio semanal", "relatório semanal"}:
                import weekly_report
                weekly_report.gerar_e_enviar_relatorio(phone_number_id, from_number)
                return
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
                try:
                    coletor = app.recalcular_embeddings()
                except Exception as e:
                    print("Erro ao recalcular embeddings:", e)
                    coletor = "❌ Erro ao atualizar embeddings: %s" % e
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
                    father_phone = os.getenv('WHATSAPP_PHONE_NUMBER', '5521983163900')
                    clean_from = ''.join(filter(str.isdigit, str(from_number)))
                    clean_father = ''.join(filter(str.isdigit, str(father_phone)))
                    is_from_father = bool(clean_from and (clean_from in clean_father or clean_father in clean_from))

                    # Verifica se contém emoji/prefixo reservado para os filhos (👶, 👧, 👦, filhos:, etc)
                    kid_prefixes = ['👶', '👧', '👦', 'filhos:', 'filho:', 'filha:', 'k:', 'maria:', 'jose:', 'josé:']
                    raw_lower = content.strip().lower()
                    has_kid_prefix = any(raw_lower.startswith(p) or content.strip().startswith(p) for p in kid_prefixes)

                    if is_from_father and has_kid_prefix:
                        raw_msg = content.strip()
                        target_kid_id = None

                        if raw_msg.startswith('👧') or raw_lower.startswith('filha:') or raw_lower.startswith('maria:'):
                            target_kid_id = 1
                        elif raw_msg.startswith('👦') or raw_lower.startswith('filho:') or raw_lower.startswith('jose:') or raw_lower.startswith('josé:'):
                            target_kid_id = 2

                        # Remoção completa de emojis e prefixos no início do texto
                        import re
                        clean_text = raw_msg
                        # Remove emojis de crianças (👶 👧 👦) e modificadores de tom de pele / variação
                        clean_text = re.sub(r'^[\s\U0001F476\U0001F467\U0001F466\U0001F3FB-\U0001F3FF\uFE0F\u200D]+', '', clean_text)
                        # Remove prefixos textuais (filhos:, filho:, filha:, maria:, jose:, k:)
                        clean_text = re.sub(r'^(?:filhos?|filha|maria|josé?|k)\s*[:\-\s]*', '', clean_text, flags=re.IGNORECASE)
                        # Limpa qualquer emoji remanescente no início
                        clean_text = re.sub(r'^[\s\U0001F476\U0001F467\U0001F466\U0001F3FB-\U0001F3FF\uFE0F\u200D]+', '', clean_text).strip()

                        if clean_text:
                            success, kid_name = app.salvar_resposta_pai_whatsapp(clean_text, from_number, target_kid_id)
                            if success:
                                send_msg.send_wapp_msg(phone_number_id, from_number, f"✅ Recado enviado para *{kid_name}* no Cofre dos Filhos!")
                            else:
                                send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Erro ao enviar recado para os filhos.")
                        return


                    coletor, link, tipo_pergunta = envia_prompt_api(content, data_atual, hora_atual, phone_number_id, from_number, wapp_id)

                    
            # envia a mensagem de retorno para o whatsapp
            try:
                if (tipo_pergunta):
                    wapp_response = send_msg.send_wapp_question(phone_number_id, from_number, coletor)
                    response_dict = wapp_response.json()
                    if "messages" in response_dict and response_dict["messages"]:
                        resp_wapp_id = response_dict["messages"][0]["id"]
                        input_data = json.dumps({"role": "assistant", "content": coletor}, ensure_ascii=False)
                        app.salvar_thread(input_data, resp_wapp_id)
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
                audio_document = (podcast_owner and media_type == 'document' and
                                  message['document'].get('mime_type', '').startswith('audio/'))
                if media_type == 'audio' or audio_document:
                    # Recuperar o ID do áudio
                    audio_id = message[media_type]['id']
                    # Enviar mensagem de transcrição em andamento
                    send_msg.send_wapp_msg(phone_number_id, from_number, "👂 _transcrevendo_ 🖋")
                    # Obter URL da mídia
                    media_url_response = send_msg.get_url_wapp_media(audio_id)
                    # Baixar a mídia e avaliar Detecção Inteligente (Opção A)
                    with tempfile.TemporaryDirectory() as tmp:
                        file_path = send_msg.download_media(media_url_response, str(Path(tmp) / "audio"))
                        if not file_path:
                            raise RuntimeError("Falha ao baixar áudio.")
                        transcricao = agent.audio_transcription(file_path)
                        is_homilia = podcast_owner and eh_audio_homilia(
                            file_path, transcricao, from_number, timestamp=timestamp
                        )
                        audio_bytes = Path(file_path).read_bytes() if is_homilia else None
                    if is_homilia:
                        iniciar_fluxo_homilia(
                            phone_number_id, from_number, wapp_id, audio_id,
                            timestamp, transcricao, audio_bytes=audio_bytes
                        )
                    else:
                        # Fluxo Básico: envia transcrição com botões Executar ação / Memorizar / Homilia
                        wapp_response = send_msg.send_wapp_audio_reply(
                            phone_number_id, from_number, transcricao, audio_id=audio_id
                        )
                        # 📅 registra transcrição gerada pelo sistema em threads📅
                        response_dict = wapp_response.json()
                        if "messages" in response_dict and response_dict["messages"]:
                            resp_wapp_id = response_dict["messages"][0]["id"]
                            input_data = json.dumps({"role": "assistant", "content": transcricao}, ensure_ascii=False)
                            app.salvar_thread(input_data, resp_wapp_id)
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
                elif media_type == 'document':
                    document_id = entry['changes'][0]['value']['messages'][0]['document']['id']
                    send_msg.send_wapp_msg(phone_number_id, from_number, "📄 _lendo documento_ 🔎")
                    
                    media_url = send_msg.get_url_wapp_media(document_id)
                    file_path = send_msg.download_media(media_url, filename=document_id)
                    
                    if file_path:
                        analysis = agent.analyze_pdf(file_path)
                        analysis_with_id = f"{analysis}\n[ID: {document_id}]"
                        
                        wapp_response = send_msg.send_wapp_image_reply(phone_number_id, from_number, analysis_with_id, header_text="Análise de Arquivo 📄")
                        
                        response_dict = wapp_response.json()
                        if "messages" in response_dict and response_dict["messages"]:
                            wapp_id = response_dict["messages"][0]["id"]
                            input_dict = {"role": "assistant", "content": analysis_with_id}
                            input_data = json.dumps(input_dict, ensure_ascii=False)
                            app.salvar_thread(input_data, wapp_id)
                    else:
                        send_msg.send_wapp_msg(phone_number_id, from_number, "❌ Erro ao baixar o documento.")
                else:
                    print(f"Tipo de mídia não suportado: {media_type}")
                    send_msg.send_wapp_msg(phone_number_id, from_number, "Tipo de mídia não suportado. Por favor, envie um áudio ou imagem.")
            except Exception as e:
                print(f"Erro ao processar a mensagem: {e}")
                send_msg.send_wapp_msg(phone_number_id, from_number, "Erro ao processar a mensagem. Por favor, tente novamente.")



