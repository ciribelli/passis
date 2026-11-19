import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _ensure_stub_modules():
    """Garante stubs mínimos quando o ambiente local não tem dependências web instaladas."""
    stubs = {}
    for name in ("requests", "sqlalchemy", "pytz", "agent", "main", "app", "homilias", "homilias.channel", "homilias.store"):
        if name not in sys.modules:
            try:
                importlib.import_module(name)
            except Exception:
                mod = types.ModuleType(name)
                sys.modules[name] = mod
                stubs[name] = mod
    if "requests" in stubs:
        sys.modules["requests"].post = MagicMock()
        sys.modules["requests"].get = MagicMock()
        sys.modules["requests"].exceptions = types.SimpleNamespace(RequestException=Exception)
    if "homilias" in stubs:
        sys.modules["homilias"].channel = sys.modules["homilias.channel"]
        sys.modules["homilias"].store = sys.modules["homilias.store"]
    if "pytz" in stubs:
        class _FakeTZ:
            def localize(self, dt):
                return dt
        sys.modules["pytz"].utc = _FakeTZ()
        sys.modules["pytz"].timezone = lambda _: None


_ensure_stub_modules()

import send_msg  # noqa: E402
import chathub  # noqa: E402


class SendWappAudioReplyTest(unittest.TestCase):
    @patch.dict(os.environ, {"WHATSAPP_TOKEN": "tok"})
    @patch("send_msg.requests.post")
    def test_short_transcript_sends_single_interactive_card_with_homilia_button(self, mock_post):
        mock_post.return_value = MagicMock()
        send_msg.send_wapp_audio_reply("phone1", "5521999", "Me lembra de comprar remédio amanhã às 10h", audio_id="media123")

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["type"], "interactive")
        self.assertEqual(payload["interactive"]["body"]["text"], "Me lembra de comprar remédio amanhã às 10h")
        buttons = payload["interactive"]["action"]["buttons"]
        self.assertEqual(
            [(b["reply"]["id"], b["reply"]["title"]) for b in buttons],
            [
                ("0", "Executar ação"),
                ("1", "Memorizar"),
                ("gerar_homilia:media123", "🎙️ Homilia"),
            ],
        )

    @patch.dict(os.environ, {"WHATSAPP_TOKEN": "tok"})
    @patch("send_msg.requests.post")
    def test_long_transcript_sends_full_text_before_truncated_card(self, mock_post):
        mock_post.return_value = MagicMock()
        long_text = "palavra " * 200  # 1600 chars (> 1024)
        send_msg.send_wapp_audio_reply("phone1", "5521999", long_text)

        self.assertEqual(mock_post.call_count, 2)
        first_payload = mock_post.call_args_list[0].kwargs["json"]
        second_payload = mock_post.call_args_list[1].kwargs["json"]
        self.assertEqual(first_payload["text"]["body"], long_text)
        card_body = second_payload["interactive"]["body"]["text"]
        self.assertEqual(len(card_body), 1024)
        self.assertTrue(card_body.endswith("..."))
        third_btn = second_payload["interactive"]["action"]["buttons"][2]["reply"]
        self.assertEqual(third_btn["id"], "gerar_homilia")


class EhAudioHomiliaTest(unittest.TestCase):
    @patch.object(chathub, "_tem_contexto_homilia_recente", return_value=False)
    def test_short_ordinary_audio_is_not_homilia(self, _):
        self.assertFalse(chathub.eh_audio_homilia(None, "Me lembra de comprar remédio amanhã às 10h", "owner"))

    @patch.object(chathub, "_tem_contexto_homilia_recente", return_value=False)
    def test_short_audio_with_religious_word_is_not_homilia(self, _):
        self.assertFalse(chathub.eh_audio_homilia(None, "Me lembra de ir à missa na Páscoa", "owner"))

    @patch.object(chathub, "_tem_contexto_homilia_recente", return_value=False)
    def test_long_non_liturgical_audio_is_not_homilia(self, _):
        text = "reunião de projeto orçamento entrega " * 80
        self.assertFalse(chathub.eh_audio_homilia(None, text, "owner"))

    @patch.object(chathub, "_tem_contexto_homilia_recente", return_value=False)
    def test_long_liturgical_audio_is_homilia(self, _):
        text = "Meus queridos irmãos, no Santo Evangelho de hoje " + ("reflexão cristã " * 140)
        self.assertTrue(chathub.eh_audio_homilia(None, text, "owner"))

    @patch.object(chathub, "_tem_contexto_homilia_recente", return_value=True)
    def test_recent_context_triggers_homilia(self, _):
        self.assertTrue(chathub.eh_audio_homilia(None, "áudio curto", "owner"))


class ChatflowAudioIntegrationTest(unittest.TestCase):
    def _audio_entry(self, sender="owner", audio_id="media123", msg_id="wamid_audio"):
        return {
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "phone1"},
                    "messages": [{
                        "from": sender,
                        "id": msg_id,
                        "timestamp": "1700000000",
                        "type": "audio",
                        "audio": {"id": audio_id},
                    }],
                }
            }]
        }

    def _button_entry(self, button_id, sender="owner", context_id="wamid_card"):
        return {
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "phone1"},
                    "messages": [{
                        "from": sender,
                        "id": "wamid_btn",
                        "timestamp": "1700000010",
                        "type": "interactive",
                        "context": {"id": context_id},
                        "interactive": {
                            "button_reply": {"id": button_id, "title": "🎙️ Homilia"}
                        },
                    }],
                }
            }]
        }

    @patch.object(chathub, "hora_e_data", return_value=("18-11-2026", "22:00"))
    @patch.object(chathub, "iniciar_fluxo_homilia")
    @patch.object(chathub, "eh_audio_homilia", return_value=False)
    def test_ordinary_audio_uses_basic_flow(self, mock_detect, mock_homilia, _):
        with tempfile.TemporaryDirectory() as tmp:
            fake_audio = Path(tmp) / "audio.ogg"
            fake_audio.write_bytes(b"ogg-bytes")
            fake_resp = MagicMock()
            fake_resp.json.return_value = {"messages": [{"id": "wamid_card"}]}
            with patch.object(chathub.homilia_channel, "reviewer", return_value=True, create=True), \
                 patch.object(chathub.send_msg, "send_wapp_msg"), \
                 patch.object(chathub.send_msg, "get_url_wapp_media", return_value="https://media.test/1"), \
                 patch.object(chathub.send_msg, "download_media", return_value=str(fake_audio)), \
                 patch.object(chathub.agent, "audio_transcription", return_value="qual a previsão do tempo?", create=True), \
                 patch.object(chathub.send_msg, "send_wapp_audio_reply", return_value=fake_resp) as mock_reply, \
                 patch.object(chathub.app, "salvar_thread", create=True) as mock_save:
                chathub.chatflow(self._audio_entry(), verified=True)

                mock_homilia.assert_not_called()
                mock_reply.assert_called_once_with(
                    "phone1", "owner", "qual a previsão do tempo?", audio_id="media123"
                )
                mock_save.assert_called_once_with(
                    json.dumps({"role": "assistant", "content": "qual a previsão do tempo?"}, ensure_ascii=False),
                    "wamid_card",
                )

    @patch.object(chathub, "hora_e_data", return_value=("18-11-2026", "22:00"))
    @patch.object(chathub, "iniciar_fluxo_homilia")
    @patch.object(chathub, "eh_audio_homilia", return_value=True)
    def test_detected_homilia_audio_triggers_homilia_pipeline(self, mock_detect, mock_homilia, _):
        with tempfile.TemporaryDirectory() as tmp:
            fake_audio = Path(tmp) / "audio.ogg"
            fake_audio.write_bytes(b"homilia-bytes")
            with patch.object(chathub.homilia_channel, "reviewer", return_value=True, create=True), \
                 patch.object(chathub.send_msg, "send_wapp_msg"), \
                 patch.object(chathub.send_msg, "get_url_wapp_media", return_value="https://media.test/1"), \
                 patch.object(chathub.send_msg, "download_media", return_value=str(fake_audio)), \
                 patch.object(chathub.agent, "audio_transcription", return_value="Meus queridos irmãos...", create=True), \
                 patch.object(chathub.send_msg, "send_wapp_audio_reply") as mock_reply:
                chathub.chatflow(self._audio_entry(), verified=True)

                mock_reply.assert_not_called()
                mock_homilia.assert_called_once_with(
                    "phone1", "owner", "wamid_audio", "media123",
                    "1700000000", "Meus queridos irmãos...", audio_bytes=b"homilia-bytes"
                )

    @patch.object(chathub, "hora_e_data", return_value=("18-11-2026", "22:00"))
    @patch.object(chathub, "iniciar_fluxo_homilia")
    def test_manual_homilia_button_triggers_pipeline_for_owner(self, mock_homilia, _):
        with patch.object(chathub.homilia_channel, "reviewer", return_value=True, create=True), \
             patch.object(chathub.app, "get_thread_content_by_wapp_id", return_value="Texto transcrito", create=True):
            chathub.chatflow(self._button_entry("gerar_homilia:media123"), verified=True)

            mock_homilia.assert_called_once_with(
                "phone1", "owner", "wamid_card", "media123", "1700000010", "Texto transcrito"
            )

    @patch.object(chathub, "hora_e_data", return_value=("18-11-2026", "22:00"))
    @patch.object(chathub, "iniciar_fluxo_homilia")
    def test_manual_homilia_button_blocks_non_owner(self, mock_homilia, _):
        with patch.object(chathub.homilia_channel, "reviewer", return_value=False, create=True), \
             patch.object(chathub.send_msg, "send_wapp_msg") as mock_send:
            chathub.chatflow(self._button_entry("gerar_homilia:media123", sender="other"), verified=True)

            mock_homilia.assert_not_called()
            mock_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
