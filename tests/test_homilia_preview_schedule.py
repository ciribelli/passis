from datetime import datetime, timezone
import importlib
import sys
import types
import unittest
from zoneinfo import ZoneInfo


def _ensure_stubs():
    for name in ("requests", "sqlalchemy", "sqlalchemy.dialects", "sqlalchemy.dialects.postgresql", "flask"):
        if name not in sys.modules:
            try:
                importlib.import_module(name)
            except Exception:
                mod = types.ModuleType(name)
                sys.modules[name] = mod
    req_mod = sys.modules["requests"]
    if not hasattr(req_mod, "post"):
        req_mod.post = lambda *a, **kw: None
        req_mod.get = lambda *a, **kw: None
        req_mod.exceptions = types.SimpleNamespace(RequestException=Exception)
    sa_mod = sys.modules["sqlalchemy"]
    if not hasattr(sa_mod, "MetaData"):
        sa_mod.MetaData = lambda: object()
        sa_mod.Table = lambda *a, **kw: types.SimpleNamespace(c=types.SimpleNamespace(id=None))
        sa_mod.Column = lambda *a, **kw: object()
        sa_mod.String = lambda *a, **kw: object()
        sa_mod.Text = object()
        sa_mod.Integer = object()
        sa_mod.Boolean = object()
        sa_mod.DateTime = lambda *a, **kw: object()
        sa_mod.LargeBinary = object()
        sa_mod.ForeignKey = lambda *a, **kw: object()
        sa_mod.false = lambda: False
        sys.modules["sqlalchemy.dialects.postgresql"].insert = lambda *a, **kw: None
    flask_mod = sys.modules["flask"]
    if not hasattr(flask_mod, "Blueprint"):
        for attr in ("Blueprint", "abort", "redirect", "render_template", "request", "send_file", "url_for"):
            setattr(flask_mod, attr, None)


_ensure_stubs()

from homilias import channel  # noqa: E402

BR_TZ = ZoneInfo("America/Sao_Paulo")


class PublishScheduleHelpersTest(unittest.TestCase):
    def test_parse_br_date_without_time(self):
        dt, has_time = channel.parse_br_publish_datetime("18/10/2026", "")
        self.assertFalse(has_time)
        self.assertEqual((dt.day, dt.month, dt.year), (18, 10, 2026))
        self.assertEqual((dt.hour, dt.minute), (8, 0))
        self.assertEqual(dt.tzinfo, BR_TZ)

    def test_parse_br_date_with_optional_time(self):
        dt, has_time = channel.parse_br_publish_datetime("05/07/2025", "19:30")
        self.assertTrue(has_time)
        self.assertEqual((dt.day, dt.month, dt.year, dt.hour, dt.minute), (5, 7, 2025, 19, 30))

    def test_parse_br_date_rejects_invalid_format(self):
        with self.assertRaises(ValueError):
            channel.parse_br_publish_datetime("31/02/2026", "")
        with self.assertRaises(ValueError):
            channel.parse_br_publish_datetime("18/10/2026", "25:99")
        with self.assertRaises(ValueError):
            channel.parse_br_publish_datetime("", "")

    def test_publish_meta_immediate_default(self):
        meta = channel.publish_meta({"publish_mode": "immediate", "publish_at": None, "publish_has_time": False})
        self.assertEqual(meta["mode"], "immediate")
        self.assertFalse(meta["is_scheduled"])
        self.assertFalse(meta["is_past"])
        self.assertEqual(meta["date_br"], "")

    def test_publish_meta_retroactive_past_date_without_time(self):
        dt_br = datetime(2026, 10, 12, 8, 0, tzinfo=BR_TZ)
        now_br = datetime(2026, 11, 18, 23, 0, tzinfo=BR_TZ)
        meta = channel.publish_meta(
            {"publish_mode": "scheduled", "publish_at": dt_br.astimezone(timezone.utc), "publish_has_time": False},
            now=now_br,
        )
        self.assertTrue(meta["is_scheduled"])
        self.assertTrue(meta["is_past"])
        self.assertEqual(meta["date_br"], "12/10/2026")
        self.assertEqual(meta["time_br"], "")
        self.assertEqual(meta["display"], "12/10/2026")

    def test_publish_meta_future_date_with_time(self):
        dt_br = datetime(2026, 12, 6, 9, 15, tzinfo=BR_TZ)
        now_br = datetime(2026, 11, 18, 23, 0, tzinfo=BR_TZ)
        meta = channel.publish_meta(
            {"publish_mode": "scheduled", "publish_at": dt_br.astimezone(timezone.utc), "publish_has_time": True},
            now=now_br,
        )
        self.assertTrue(meta["is_scheduled"])
        self.assertFalse(meta["is_past"])
        self.assertEqual(meta["display"], "06/12/2026 às 09:15")

    def test_extract_spotify_id(self):
        self.assertEqual(
            channel.extract_spotify_id("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk?si=abc"),
            "4rOoJ6Egrf8K2IrywzwOMk",
        )
        self.assertEqual(channel.extract_spotify_id("4rOoJ6Egrf8K2IrywzwOMk"), "4rOoJ6Egrf8K2IrywzwOMk")
        self.assertIsNone(channel.extract_spotify_id(""))
        self.assertIsNone(channel.extract_spotify_id("link-invalido"))


if __name__ == "__main__":
    unittest.main()
