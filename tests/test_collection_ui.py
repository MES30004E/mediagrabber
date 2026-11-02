import copy
import time

import pytest
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication

from morgan_media_downloader.models import DownloadOptions, JobStatus, MediaItem
from test_queue_collections import job
from test_ui_diagnostics import _APP, _window


@pytest.fixture
def window(tmp_path, monkeypatch):
    monkeypatch.setenv("MORGAN_CACHE_DIR",str(tmp_path/"cache"))
    value=_window(tmp_path,monkeypatch)
    for timer in value.findChildren(QTimer): timer.stop()
    value.tabs.setCurrentIndex(1); _APP.processEvents()
    try: yield value
    finally: value.close(); _APP.processEvents()


def populate(window, count=16):
    states=[JobStatus.WAITING,JobStatus.COMPLETED_WARNINGS,JobStatus.FAILED,JobStatus.CANCELLED]
    values=[job(i,group="a" if i<count//2 else "b",name="Collection A" if i<count//2 else "Collection B",status=states[i%4]) for i in range(count)]
    window.jobs={value.id:value for value in values}; window.database.save_jobs(values)
    window._refresh_queue(); window._refresh_history()
    return values


def choose(window,key):
    row=window.collections.model.row_for_id(key); assert row is not None
    window.collections.selector.setCurrentIndex(row); _APP.processEvents()


def finish(window):
    deadline=time.monotonic()+15
    while window.queue_batch.busy and time.monotonic()<deadline: _APP.processEvents(); time.sleep(.001)
    assert not window.queue_batch.busy


def test_enqueue_persists_distinct_same_title_collections_and_failed_admission_publishes_nothing(window,tmp_path,monkeypatch):
    items=[MediaItem(f"https://example.test/video/{i}",f"Video{i}",original_url=f"https://example.test/list/{i//2}",
                    collection_title="Same",collection_type="Playlist") for i in range(4)]
    options=DownloadOptions(download_dir=str(tmp_path),authentication_mode="None")
    original=window.database.save_jobs
    def fail(_values): raise OSError("synthetic admission failure")
    monkeypatch.setattr(window.database,"save_jobs",fail)
    with pytest.raises(OSError): window._enqueue_payload(items,None,options)
    assert not window.jobs and window.collections.model.summary("").total==0
    monkeypatch.setattr(window.database,"save_jobs",original); window._enqueue_payload(items,None,options)
    values=list(window.jobs.values()); first={value.collection_id for value in values}
    assert len(first)==2 and values[0].collection_id==values[1].collection_id!=values[2].collection_id
    window._enqueue_payload(items,None,options)
    assert len({value.collection_id for value in window.jobs.values()})==4
    assert {value.collection_id for value in window.database.load_jobs()}=={value.collection_id for value in window.jobs.values()}


def test_collection_filters_and_progress_use_cached_index_without_source_scan(window,monkeypatch):
    values=populate(window); choose(window,"a")
    def unexpected(*_args,**_kw): raise AssertionError("Filter/progress must not rescan collections")
    monkeypatch.setattr(window.collections.model.index_state,"sync",unexpected)
    window.queue_search.setText("Video"); window.queue_status_filter.setCurrentText("Waiting")
    assert window.queue_proxy.rowCount()==2
    window.queue_status_filter.setCurrentText("All"); changed=copy.deepcopy(values[0]); changed.status=JobStatus.DOWNLOADING; changed.progress=40
    window._job_changed(changed)
    assert window.collections.model.summary("a").total==8
    assert dict(window.collections.model.summary("a").counts)["Running"]==1
    assert "8 jobs" in window.collections.summary_label.text() and "Running: 1" in window.collections.summary_label.text()
    window.queue_selection_actions["all"].trigger()
    assert window.collections.selector.currentData()=="" and len(window._selected_jobs())==16


@pytest.mark.parametrize("count",[800,5000])
@pytest.mark.parametrize("status,raw",[("Completed",JobStatus.COMPLETED_WARNINGS),("Cancelled",JobStatus.CANCELLED),("Failed",JobStatus.FAILED)])
def test_status_clear_is_one_named_scope_ignoring_row_filters_but_not_other_collection(window,monkeypatch,count,status,raw):
    values=populate(window,count); choose(window,"a"); window.queue_search.setText("NO MATCH")
    expected={value.id for value in values if value.collection_id=="a" and value.status==raw}; prompts=[]
    def confirm(jobs,scope): prompts.append(({value.id for value in jobs},scope)); return "list"
    monkeypatch.setattr(window,"_confirm_clear",confirm)
    window.clear_queue_status(status); finish(window)
    assert len(prompts)==1 and prompts[0][0]==expected and "Collection A" in prompts[0][1]
    assert set(window.jobs)=={value.id for value in values}-expected
    assert {value.id for value in window.database.load_jobs()}==set(window.jobs)


def test_collection_cancel_preserves_completion_during_confirmation_and_other_groups(window,monkeypatch):
    values=populate(window,800); choose(window,"a")
    target=next(value for value in values if value.collection_id=="a" and value.status==JobStatus.WAITING)
    def confirm(action,jobs,scope):
        assert action=="Cancel" and len(jobs)==400 and "Collection A" in scope
        target.status=JobStatus.COMPLETED; window.database.save_job(target); return True
    monkeypatch.setattr(window,"_confirm_collection_action",confirm)
    window.act_on_collection("Cancel"); finish(window)
    assert window.jobs[target.id].status==JobStatus.COMPLETED
    assert all(window.jobs[value.id].status==JobStatus.COMPLETED_WARNINGS if value.status==JobStatus.COMPLETED_WARNINGS else
               window.jobs[value.id].status in {JobStatus.COMPLETED,JobStatus.CANCELLED} for value in values if value.collection_id=="a")
    assert all(window.jobs[value.id].status==value.status for value in values if value.collection_id=="b")


def test_small_selected_cancel_does_not_downgrade_completed_output(window):
    values=populate(window,4); window.queue_table.selectAll(); window.cancel_selected(); finish(window)
    assert window.jobs[values[1].id].status==JobStatus.COMPLETED_WARNINGS


def test_open_clear_menu_cannot_broaden_to_all_when_selected_collection_disappears(window,monkeypatch):
    values=populate(window,16); choose(window,"a"); prompts=[]
    monkeypatch.setattr(window,"_confirm_clear",lambda *_args: prompts.append(True) or "list")
    window.collections.clear_menu.popup(window.mapToGlobal(QPoint(200,200))); _APP.processEvents()
    assert window.collections.clear_menu.isVisible()
    removed=[value.id for value in values if value.collection_id=="a"]
    window.database.remove_jobs(removed)
    for key in removed: window.jobs.pop(key)
    window._refresh_queue()
    window.collections.clear_actions["Completed"].trigger(); window.collections.clear_menu.hide(); _APP.processEvents()
    assert not prompts and len(window.jobs)==8


def test_named_clear_dialog_is_plain_text_keep_default_and_cancel_safe(window):
    values=populate(window); observed=[]
    def inspect():
        box=QApplication.activeModalWidget(); observed.append((box.textFormat(),box.defaultButton().text(),box.text())); box.reject()
    QTimer.singleShot(0,inspect)
    assert window._confirm_clear(values,"<b>Collection A</b>")=="cancel"
    assert observed[0][0]==Qt.TextFormat.PlainText and "keep" in observed[0][1].lower()
    assert "<b>Collection A</b>" in observed[0][2] and len(window.jobs)==16


@pytest.mark.parametrize("width,height",[(900,650),(1180,820)])
def test_collection_controls_fit_supported_sizes(window,width,height):
    populate(window,800); choose(window,"a"); window.resize(width,height); _APP.processEvents()
    for control in (window.collections.selector,window.collections.progress,window.collections.summary_label,window.collections.actions_button):
        assert control.isVisible() and control.width()>=control.minimumSizeHint().width()
        assert window.rect().contains(control.mapTo(window,control.rect().bottomRight()))


def test_failed_clear_cannot_delete_job_that_completed_during_confirmation(window,monkeypatch):
    values=populate(window,8); choose(window,"a"); target=values[2]; cleaned=[]
    def confirm(jobs,_scope):
        assert {value.id for value in jobs}=={target.id}
        target.status=JobStatus.COMPLETED; window.database.save_job(target); return "delete"
    monkeypatch.setattr(window,"_confirm_clear",confirm)
    window.file_removal.deleter=lambda value:cleaned.append(value.id) or []
    window.clear_queue_status("Failed"); finish(window)
    assert target.id in window.jobs and window.jobs[target.id].status==JobStatus.COMPLETED and not cleaned


def test_later_clear_slice_rechecks_status_instead_of_deleting_newly_completed_job(window,monkeypatch):
    values=populate(window,800); choose(window,"a")
    for value in values[:400]: value.status=JobStatus.FAILED
    window.database.save_jobs(values); window._refresh_queue(); target=values[399]
    monkeypatch.setattr(window,"_confirm_clear",lambda *_args:"list")
    window.clear_queue_status("Failed")
    target.status=JobStatus.COMPLETED; window.database.save_job(target)
    finish(window)
    assert set(window.jobs)=={value.id for value in values[400:]}|{target.id}
    assert window.queue_batch.describe()["completed"]==399 and window.queue_batch.describe()["skipped"]==1


@pytest.mark.parametrize("change",["completed","other_collection"])
def test_deferred_clear_rechecks_scope_after_actual_owner_stops(window,monkeypatch,change):
    import threading
    values=populate(window,8); choose(window,"a"); target=values[2]
    stopped=threading.Event(); release=threading.Event(); cleaned=[]
    def transfer(cancel,_progress):
        assert cancel.wait(5); stopped.set(); assert release.wait(5)
    task="job-"+target.id
    window.active[target.id]=window.task_manager.start("download-media",transfer,task_id=task,on_finished=window._job_finished)
    monkeypatch.setattr(window,"_confirm_clear",lambda *_args:"delete")
    window.file_removal.deleter=lambda value:cleaned.append(value.id) or []
    window.clear_queue_status("Failed"); deadline=time.monotonic()+3
    try:
        while not stopped.is_set() and time.monotonic()<deadline: _APP.processEvents()
        assert stopped.is_set()
        changed=copy.deepcopy(target)
        if change=="completed": changed.status=JobStatus.COMPLETED
        else: changed.collection_id="b"; changed.collection_name="Collection B"
        window._job_changed(changed)
    finally: release.set()
    finish(window)
    assert target.id in window.jobs and not cleaned and window.task_manager.active_count==0


def test_group_pause_resume_and_restart_keep_persisted_identity(window,monkeypatch,tmp_path):
    values=populate(window,800); choose(window,"a"); prompts=[]
    for value in values[:400]: value.status=JobStatus.WAITING; value.options.download_dir=str(tmp_path)
    window.database.save_jobs(values); window._refresh_queue()
    monkeypatch.setattr(window,"_confirm_collection_action",lambda action,jobs,scope:prompts.append((action,len(jobs),scope)) or True)
    window.act_on_collection("Pause"); finish(window)
    assert all(window.jobs[value.id].status==JobStatus.PAUSED for value in values[:400])
    window.act_on_collection("Resume"); finish(window)
    assert all(window.jobs[value.id].status==JobStatus.WAITING for value in values[:400])
    assert [action for action,_,_ in prompts]==["Pause","Resume"] and all(count==400 for _,count,_ in prompts)
    window.queue_selection_actions["filtered"].trigger()
    monkeypatch.setattr(window,"_confirm_restart",lambda _jobs:"keep")
    window.restart_selected(); finish(window)
    assert all(value.collection_id=="a" and value.collection_name=="Collection A" for value in window.database.load_jobs() if value.id in {job.id for job in values[:400]})
    assert all(window.jobs[value.id].status==value.status for value in values[400:])


def test_clear_entire_collection_drains_owner_once_and_keeps_files(window,monkeypatch,tmp_path):
    values=populate(window,800); choose(window,"a"); target=values[0]; target.status=JobStatus.DOWNLOADING
    output=tmp_path/"retained.mp4"; output.write_bytes(b"synthetic owned output")
    target.final_files=[str(output)]; target.options.download_dir=str(tmp_path); window.database.save_job(target)
    task="job-"+target.id
    window.active[target.id]=window.task_manager.start("download-media",lambda cancel,_p:cancel.wait(5),task_id=task,on_finished=window._job_finished)
    prompts=[]; monkeypatch.setattr(window,"_confirm_clear",lambda jobs,scope:prompts.append((len(jobs),scope)) or "list")
    def unexpected(_job): raise AssertionError("Keep must not invoke file deletion")
    window.file_removal.deleter=unexpected
    window.clear_collection(); finish(window)
    assert len(prompts)==1 and prompts[0][0]==400 and "Collection A" in prompts[0][1]
    assert set(window.jobs)=={value.id for value in values[400:]} and window.task_manager.active_count==0
    assert output.read_bytes()==b"synthetic owned output"


def test_all_unknown_progress_is_labelled_unknown_not_completed(window):
    values=populate(window)
    for value in values[:8]: value.status=JobStatus.FAILED; value.progress=float("nan")
    window._refresh_queue(); choose(window,"a")
    assert window.collections.progress.format()=="Unknown" and "Failed: 8" in window.collections.summary_label.text()


def test_progress_callback_cannot_erase_frozen_collection_name(window):
    values=populate(window); changed=copy.deepcopy(values[0]); changed.collection_name=""; changed.progress=10
    window._job_changed(changed)
    persisted={value.id:value for value in window.database.load_jobs()}
    assert persisted[changed.id].collection_id=="a" and persisted[changed.id].collection_name=="Collection A"


@pytest.mark.parametrize("status",[JobStatus.COMPLETED,JobStatus.COMPLETED_WARNINGS])
@pytest.mark.parametrize("action",["collection","selected"])
def test_pause_preserves_completed_download_while_real_owner_is_draining(window,monkeypatch,status,action):
    import threading
    values=populate(window,4); choose(window,"a"); target=values[0]; release=threading.Event()
    def transfer(cancel,progress):
        completed=copy.deepcopy(target); completed.status=status; completed.progress=100
        progress(completed); assert release.wait(5)
    key="job-"+target.id
    window.active[target.id]=window.task_manager.start("download-media",transfer,task_id=key,
        on_progress=window._job_changed,on_finished=window._job_finished)
    deadline=time.monotonic()+3
    try:
        while window.jobs[target.id].status!=status and time.monotonic()<deadline: _APP.processEvents()
        assert window.jobs[target.id].status==status and target.id in window.active
        monkeypatch.setattr(window,"_confirm_collection_action",lambda *_args:True)
        if action=="collection": window.act_on_collection("Pause"); finish(window)
        else: window._pause([window.jobs[target.id]])
        assert window.jobs[target.id].status==status
    finally:
        release.set(); deadline=time.monotonic()+3
        while window.task_manager.active_count and time.monotonic()<deadline: _APP.processEvents(); time.sleep(.001)
    assert target.id not in window.active and {value.id:value for value in window.database.load_jobs()}[target.id].status==status


@pytest.mark.parametrize("when",["modal","later_slice"])
def test_collection_cancel_rechecks_membership_before_each_admission(window,monkeypatch,when):
    values=populate(window,800); choose(window,"a"); target=values[399]
    waiting=copy.deepcopy(target); waiting.status=JobStatus.WAITING; window._job_changed(waiting)
    def move():
        changed=copy.deepcopy(window.jobs[target.id]); changed.collection_id="b"; changed.collection_name="Collection B"
        window._job_changed(changed)
    def confirm(*_args):
        if when=="modal": move()
        return True
    monkeypatch.setattr(window,"_confirm_collection_action",confirm)
    window.act_on_collection("Cancel")
    if when=="later_slice": move()
    finish(window)
    assert window.jobs[target.id].collection_id=="b" and window.jobs[target.id].status==JobStatus.WAITING
    assert {value.id:value for value in window.database.load_jobs()}[target.id].status==JobStatus.WAITING


def test_small_completed_clear_is_atomic_and_reconciles_a_second_delete_failure(window,monkeypatch):
    values=populate(window,8); expected={value.id for value in values}
    for value in values: value.status=JobStatus.COMPLETED
    window.database.save_jobs(values); window._refresh_queue()
    window.database._connection.execute("CREATE TRIGGER reject_second BEFORE DELETE ON jobs WHEN OLD.id='1' BEGIN SELECT RAISE(ABORT,'synthetic clear failure'); END")
    monkeypatch.setattr(window,"_confirm_clear",lambda *_args:"list")
    try: window.clear_completed()
    except Exception: pass  # Inspect real committed/UI state even on the broken path.
    finish(window)
    assert {value.id for value in window.database.load_jobs()}==set(window.jobs)==expected
    assert window.queue_model.rowCount()==window.collections.model.summary("").total==8
    info=window.queue_batch.describe(); assert info["failed"]==8 and info["completed"]==0 and info["pending"]==0


def test_small_clear_deferred_owner_delete_failure_is_settled_and_retained(window,monkeypatch):
    import threading
    values=populate(window,4); target=values[1]; stopped=threading.Event(); release=threading.Event()
    window.database._connection.execute("CREATE TRIGGER reject_owned BEFORE DELETE ON jobs WHEN OLD.id='1' BEGIN SELECT RAISE(ABORT,'synthetic owned clear failure'); END")
    def transfer(cancel,_progress):
        assert cancel.wait(5); stopped.set(); assert release.wait(5)
    key="job-"+target.id
    window.active[target.id]=window.task_manager.start("download-media",transfer,task_id=key,on_finished=window._job_finished)
    monkeypatch.setattr(window,"_confirm_clear",lambda *_args:"list")
    window.clear_completed(); deadline=time.monotonic()+3
    try:
        while not stopped.is_set() and time.monotonic()<deadline: _APP.processEvents()
        assert stopped.is_set()
    finally: release.set()
    finish(window)
    assert target.id in window.jobs and window.task_manager.active_count==0
    assert window.jobs[target.id].status==JobStatus.COMPLETED_WARNINGS
    info=window.queue_batch.describe(); assert info["failed"]==1 and info["completed"]==0 and info["pending"]==0


def test_mixed_unknown_progress_does_not_show_a_whole_collection_percentage(window):
    values=populate(window,4)
    for value in values[:2]: value.status=JobStatus.DOWNLOADING
    values[0].progress=100; values[1].progress=float("nan")
    window._refresh_queue(); choose(window,"a")
    assert window.collections.progress.isHidden()
    text=window.collections.summary_label.text().lower()
    assert "unknown" in text and "1/2" in text and "0/2" in text


def test_direct_clear_completed_button_uses_current_scope_once_and_keeps_other_states(window,monkeypatch):
    from PySide6.QtWidgets import QToolButton
    values=populate(window,800); choose(window,"a"); expected={value.id for value in values[:400] if value.status==JobStatus.COMPLETED_WARNINGS}
    prompts=[]; monkeypatch.setattr(window,"_confirm_clear",lambda jobs,scope:prompts.append(({value.id for value in jobs},scope)) or "list")
    button=window.collections.clear_button
    assert button.text()=="Clear Completed" and button.isVisible()
    assert button.popupMode()==QToolButton.ToolButtonPopupMode.MenuButtonPopup
    button.click(); finish(window)
    assert len(prompts)==1 and prompts[0][0]==expected and "Collection A" in prompts[0][1]
    assert set(window.jobs)=={value.id for value in values}-expected
