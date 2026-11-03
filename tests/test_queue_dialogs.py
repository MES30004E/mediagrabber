"""Real modal controls: clear consequences, bounded copy and expandable diagnostics."""
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtWidgets import QApplication,QMessageBox,QTextEdit

from test_collection_ui import _APP,populate,window


@pytest.mark.parametrize("mode,choice,result",[
    ("clear","keep","list"),("clear","delete","delete"),("clear","cancel","cancel"),
    ("restart","keep","keep"),("restart","delete","replace"),("restart","cancel","cancel"),
    ("collection","accept",True),("collection","cancel",False),
])
def test_counted_confirmation_keeps_technical_detail_expandable_and_choices_safe(window,mode,choice,result):
    values=populate(window,800); window.resize(900,650); _APP.processEvents()
    window.active[values[0].id]="synthetic-count-only"; seen=[]; errors=[]
    def inspect():
        box=QApplication.activeModalWidget()
        try:
            assert isinstance(box,QMessageBox)
            primary=box.text()+"\n"+box.informativeText()
            assert "800" in primary and "1 active" in primary and "200 completed" in primary
            assert box.textFormat()==Qt.TextFormat.PlainText and box.width()<=900
            assert box.escapeButton() is box.button(QMessageBox.StandardButton.Cancel)
            assert box.detailedText(),"Technical stop/ownership details must remain available"
            assert "job-owned" not in primary and "slice" not in primary
            details=box.findChildren(QTextEdit)
            assert details and not any(view.isVisible() for view in details)
            reveal=next(button for button in box.buttons() if "details" in button.text().lower())
            reveal.click(); _APP.processEvents()
            assert any(view.isVisible() and view.toPlainText()==box.detailedText() for view in details)
            if mode in {"clear","restart"}:
                assert "keep files" in box.defaultButton().text().lower()
                assert "delet" in primary.lower() and ("permanent" in primary.lower() or "trash" in primary.lower())
            else:
                assert box.defaultButton() is box.button(QMessageBox.StandardButton.Cancel)
                assert "<b>Collection A</b>" in primary
            roles={"keep":QMessageBox.ButtonRole.AcceptRole,"delete":QMessageBox.ButtonRole.DestructiveRole}
            if choice in roles:
                button=next(button for button in box.buttons() if box.buttonRole(button)==roles[choice])
            else:
                button=box.button(QMessageBox.StandardButton.Ok if choice=="accept" else QMessageBox.StandardButton.Cancel)
            seen.append(True); button.click()
        except BaseException as error:
            errors.append(error)
        finally:
            if box is not None and box.isVisible(): box.reject()
    QTimer.singleShot(0,inspect)
    try:
        actual=(window._confirm_clear(values,"selected jobs") if mode=="clear" else
                window._confirm_restart(values) if mode=="restart" else
                window._confirm_collection_action("Pause",values,"<b>Collection A</b>"))
    finally: window.active.clear()
    if errors: raise errors[0]
    assert seen==[True] and actual==result
    assert len(window.jobs)==800  # Rendering/choosing alone never starts a service.
