from pathlib import Path


def test_postinst_creates_intelligence_group_before_using_it():
    postinst = (Path(__file__).parents[1] / "packaging" / "postinst").read_text(encoding="utf-8")
    create_group = "if ! getent group solarminer-intelligence >/dev/null 2>&1; then addgroup --system solarminer-intelligence; fi"
    create_user = "if ! getent passwd solarminer-intelligence >/dev/null 2>&1; then adduser --system --ingroup solarminer-intelligence"
    use_group = "install -d -o root -g solarminer-intelligence -m 0750 /var/lib/solarminer-intelligence"

    assert create_group in postinst
    assert create_user in postinst
    assert postinst.index(create_group) < postinst.index(use_group)
    assert postinst.index(create_user) < postinst.index(use_group)
