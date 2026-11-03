"""Discoverable commands must consume the existing bounded, scoped services."""
import time

import pytest
from PySide6.QtCore import QPoint

from morgan_media_downloader.models import JobStatus
from test_collection_ui import _APP,choose,finish,populate,window


def test_more_actions_are_discoverable_without_losing_direct_clear_completed(window):
    populate(window,16); choose(window,"a")
    window.resize(900,650); _APP.processEvents()
    window.queue_more_menu.aboutToShow.emit()
    assert window.queue_more_button.isVisible()
    assert window.rect().contains(window.queue_more_button.mapTo(window,window.queue_more_button.rect().bottomRight()))
    assert {"retry_failed","restart_selected","clear_selected","clear_cancelled","clear_failed","clear_collection","cancel_collection"}<=set(window.queue_more_actions)
    assert window.collections.clear_button.text()=="Clear Completed" and window.collections.clear_button.isVisible()
    assert window.queue_more_actions["retry_failed"].isEnabled()


def test_more_actions_scope_heading_is_actually_visible_in_native_menu(window):
    populate(window,16); choose(window,"a")
    window.queue_more_menu.popup(window.queue_more_button.mapToGlobal(QPoint(0,0))); _APP.processEvents()
    try:
        heading=window.queue_more_heading
        assert "Collection A" in heading.text()
        assert window.queue_more_menu.actionGeometry(heading).height()>0,"Scope cannot be an invisible native menu section"
    finally: window.queue_more_menu.hide()


@pytest.mark.parametrize("count",[800,5000])
def test_retry_failed_uses_captured_scope_one_confirmation_and_shared_auth_policy(window,tmp_path,monkeypatch,count):
    values=populate(window,count); choose(window,"a")
    targets=[value for value in values[:count//2] if value.status==JobStatus.FAILED]
    for value in values:
        value.options.download_dir=str(tmp_path/"downloads"); value.options.authentication_mode="None"
    before_other={value.id:value.to_dict() for value in values[count//2:]}
    targets[0].failure_code="auth.required"; targets[0].error="Sign in to view this private video"
    targets[0].options.quality="720p"
    window.database.save_jobs(values); window._refresh_queue()
    window.queue_more_menu.aboutToShow.emit(); choose(window,"b")
    window.queue_status_filter.setCurrentText("Waiting")  # A status action is not the visible-row selection.
    prompts=[]; slices=[]
    original=window._apply_queue_slice
    def apply(ids,*args): slices.append(len(ids)); return original(ids,*args)
    monkeypatch.setattr(window,"_apply_queue_slice",apply)
    def confirm(action,jobs,scope):
        prompts.append((action,{value.id for value in jobs},scope))
        targets[-1].status=JobStatus.COMPLETED
        targets[-2].collection_id="b"
        window.database.save_jobs(targets[-2:])
        # A newly applied account during the modal is the existing retry policy's source.
        window.settings.authentication_mode="Browser Cookies"; window.settings.cookies_browser="Firefox"
        window.settings.browser_profile="synthetic-profile"; window.settings.cookies_file=""
        return True
    monkeypatch.setattr(window,"_confirm_collection_action",confirm)
    window.queue_more_actions["retry_failed"].trigger(); finish(window)
    expected={value.id for value in targets[:-2]}
    assert len(prompts)==1 and prompts[0][1]=={value.id for value in targets} and "Collection A" in prompts[0][2]
    assert all(window.jobs[key].status==JobStatus.WAITING for key in expected)
    assert window.jobs[targets[-1].id].status==JobStatus.COMPLETED
    assert window.jobs[targets[-2].id].status==JobStatus.FAILED
    assert {key:window.jobs[key].to_dict() for key in before_other}==before_other
    retried=window.jobs[targets[0].id]
    assert (retried.options.authentication_mode,retried.options.cookies_browser,retried.options.browser_profile,retried.options.quality)==(
        "Browser Cookies","Firefox","synthetic-profile","720p")
    assert window.jobs[targets[1].id].options.authentication_mode=="None"
    assert slices and max(slices)<=32 and window.queue_batch.describe()["skipped"]==2
    saved={value.id:value for value in window.database.load_jobs()}
    assert all(saved[key].status==JobStatus.WAITING for key in expected)


def test_more_clear_failed_keeps_captured_collection_when_current_filter_changes(window,monkeypatch):
    values=populate(window,16); choose(window,"a")
    expected={value.id for value in values[:8] if value.status==JobStatus.FAILED}
    window.queue_more_menu.aboutToShow.emit(); choose(window,"b")
    prompts=[]
    monkeypatch.setattr(window,"_confirm_clear",lambda jobs,scope:prompts.append(({value.id for value in jobs},scope)) or "list")
    window.queue_more_actions["clear_failed"].trigger(); finish(window)
    assert len(prompts)==1 and prompts[0][0]==expected and "Collection A" in prompts[0][1]
    assert set(window.jobs)=={value.id for value in values}-expected


def test_retry_failed_does_not_touch_a_failed_job_with_a_live_owner(window):
    values=populate(window,8); choose(window,"a"); target=values[2]
    task=window.task_manager.start("synthetic-retry-owner",lambda cancel,_progress:cancel.wait(5),
        on_finished=lambda *_:window.active.pop(target.id,None))
    window.active[target.id]=task
    try:
        window.queue_more_menu.aboutToShow.emit()
        assert not window.queue_more_actions["retry_failed"].isEnabled()
        window.queue_more_actions["retry_failed"].trigger(); _APP.processEvents()
        assert window.jobs[target.id].status==JobStatus.FAILED and not window.queue_batch.busy
    finally:
        window.task_manager.cancel(task); deadline=time.monotonic()+3
        while window.task_manager.active_count and time.monotonic()<deadline: _APP.processEvents(); time.sleep(.001)
        assert window.task_manager.active_count==0


def test_cancelling_failed_retry_keeps_every_captured_record(window,monkeypatch):
    values=populate(window,16); choose(window,"a"); before={value.id:value.to_dict() for value in values}
    window.queue_more_menu.aboutToShow.emit()
    monkeypatch.setattr(window,"_confirm_collection_action",lambda *_:False)
    window.queue_more_actions["retry_failed"].trigger(); _APP.processEvents()
    assert not window.queue_batch.busy and {key:value.to_dict() for key,value in window.jobs.items()}==before


def test_running_batch_disables_more_actions(window):
    populate(window,16)
    window.queue_batch.start(tuple(window.jobs),lambda _ids:0,"Synthetic pending action")
    assert not window.queue_more_button.isEnabled()
    finish(window)
    assert window.queue_more_button.isEnabled()
