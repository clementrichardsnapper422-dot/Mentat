from mentat_broker.control_ui import render_control_center
from mentat_broker.production_http import secure_ui


def test_control_center_never_embeds_admin_authority():
    html = render_control_center().decode("utf-8")
    assert "adminToken" not in html
    assert "Authorization" not in html
    assert "Bearer " not in html
    assert "fetch(path" in html


def test_decision_ui_never_embeds_admin_authority():
    def base_ui() -> bytes:
        return b"""<script>
function render(decision) {}
const actions = `${pending ? `<div class=\"actions\"><button class=\"approve\" onclick=\"approveDecision('${decision.id}')\">Approve compute</button><button class=\"reject\" onclick=\"action('${decision.id}','reject')\">Reject</button></div>` : ''}`;
</script>"""

    html = secure_ui(base_ui).decode("utf-8")
    assert "adminToken" not in html
    assert "Authorization" not in html
    assert "Bearer " not in html
    assert "rateDecision" in html
