"""`pc.py install`: one command that sets up a new user, safe to run again, never overwriting a value
already set and never printing a key."""

import io
import json
import os
import stat
import urllib.error

from paper_check import install


def test_the_config_file_is_private_and_keeps_what_is_already_set(tmp_path):
    config = tmp_path / ".paper-check" / "config.yaml"
    assert install.set_config_values(config, {"contact_email": "a.lee@univ.edu"}) == {"contact_email": "set"}
    assert stat.S_IMODE(os.stat(config).st_mode) == 0o600
    assert install.config_value(config, "contact_email") == "a.lee@univ.edu"
    assert install.config_value(config, "openalex_api_key") is None
    # A second run with another address leaves the first; a missing key is added; comments stay.
    config.write_text(config.read_text() + "# my note\n")
    outcome = install.set_config_values(config, {"contact_email": "b.kim@univ.edu", "openalex_api_key": "k-1"})
    assert outcome == {"contact_email": "already set", "openalex_api_key": "set"}
    text = config.read_text()
    assert "a.lee@univ.edu" in text and "b.kim" not in text and "# my note" in text
    assert install.config_value(config, "openalex_api_key") == "k-1"


def test_placeholder_and_malformed_addresses_are_refused():
    assert install.check_email("a.lee@univ.edu") is None
    assert "placeholder" in install.check_email("you@example.com")
    assert "not an email" in install.check_email("a.lee at univ.edu")


def test_the_skill_is_linked_once_and_nothing_in_the_way_is_replaced(tmp_path):
    skills = tmp_path / "skills"
    assert install.link_skill(skills).startswith("linked")
    assert (skills / "paper-check").resolve() == install.SKILL_DIR
    assert install.link_skill(skills).startswith("already linked")
    other = tmp_path / "other"
    (other / "paper-check").mkdir(parents=True)
    assert install.link_skill(other).startswith("left as it is")


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_an_openalex_key_is_requested_for_the_users_email_saved_and_never_shown(tmp_path, monkeypatch, capsys):
    sent = {}

    def fake_urlopen(req, timeout=30):
        sent.update(url=req.full_url, method=req.get_method(), body=json.loads(req.data),
                    agent=req.get_header("User-agent"))
        return _Response(json.dumps({"api_key": "secret-key-123", "status": "pending_activation"}).encode())
    monkeypatch.setattr(install.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(install, "sample_check", lambda: "ok: stubbed")
    monkeypatch.setattr("paper_check.env.doctor", lambda network=True: 0)
    home, skills = tmp_path / ".paper-check", tmp_path / "skills"
    assert install.run(email="a.lee@univ.edu", request_key=True, home=home, skills_root=skills) == 0
    assert sent["url"] == install.OPENALEX_KEYS and sent["method"] == "POST"
    assert sent["body"]["email"] == "a.lee@univ.edu" and "@" not in sent["agent"]
    assert install.config_value(home / "config.yaml", "openalex_api_key") == "secret-key-123"
    out = capsys.readouterr().out
    assert "secret-key-123" not in out and "Activate your OpenAlex API key" in out
    # Run again: the key is kept and not requested twice.
    sent.clear()
    assert install.run(email="a.lee@univ.edu", request_key=True, home=home, skills_root=skills) == 0
    assert not sent and "OpenAlex key: already set" in capsys.readouterr().out


def test_a_refused_key_request_says_what_to_do_instead(monkeypatch):
    def too_many(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"{}"))
    monkeypatch.setattr(install.urllib.request, "urlopen", too_many)
    key, message = install.request_openalex_key("a.lee@univ.edu")
    assert key is None and "openalex.org/signup" in message


def test_install_runs_the_sample_paper_offline(tmp_path, capsys):
    assert install.run(offline=True, home=tmp_path / ".paper-check", skills_root=tmp_path / "skills") == 0
    out = capsys.readouterr().out
    assert "Sample check: ok" in out and "Install: done" in out
    assert "Start a new Claude Code session" in out
