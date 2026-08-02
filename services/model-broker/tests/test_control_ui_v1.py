from mentat_broker.control_ui import render_control_center


def test_control_center_never_embeds_admin_authority():
    html = render_control_center().decode("utf-8")
    assert "adminToken" not in html
    assert "Authorization" not in html
    assert "Bearer " not in html
    assert "fetch(path" in html
