"""Portable presentation state cannot reset authentication or runtime settings."""
import json

from morgan_media_downloader.settings import AppSettings,SettingsStore


def test_presentation_preferences_roundtrip_and_old_settings_keep_defaults(tmp_path):
    store=SettingsStore(tmp_path/"settings.json")
    value=AppSettings(authentication_mode="None",sidebar_collapsed=True,queue_details_expanded=True,
        queue_visible_columns={"Media":["Title","Status","Progress","Source"]},
        queue_column_widths={"Media":{"Title":310,"Source":90}})
    store.save(value); restored=store.load()
    assert restored.sidebar_collapsed and restored.queue_details_expanded
    assert restored.queue_visible_columns=={"Media":["Title","Status","Progress","Source"]}
    assert restored.queue_column_widths=={"Media":{"Title":310,"Source":90}}
    store.path.write_text(json.dumps({"settings_schema_version":6,"authentication_mode":"None"}))
    legacy=store.load()
    assert not legacy.sidebar_collapsed and not legacy.queue_details_expanded
    assert legacy.queue_visible_columns==legacy.queue_column_widths=={} and legacy.authentication_mode=="None"


def test_corrupt_presentation_fields_are_sanitised_without_resetting_other_preferences(tmp_path):
    store=SettingsStore(tmp_path/"settings.json")
    store.path.write_text(json.dumps({"settings_schema_version":6,"authentication_mode":"None","quality":"1440p",
        "sidebar_collapsed":"false","queue_details_expanded":[True],
        "queue_visible_columns":{"Media":["Title","Status","Status",None,12],"All":None,"Bogus":["Title"]},
        "queue_column_widths":{"Media":{"Title":310,"Status":True,"Source":-1,"Progress":999999},"All":[],"Bogus":{"Title":30}}}))
    value=store.load()
    assert value.authentication_mode=="None" and value.quality=="1440p" and not store.last_warning
    assert value.sidebar_collapsed is False and value.queue_details_expanded is False
    assert value.queue_visible_columns=={"Media":["Title","Status"]}
    assert value.queue_column_widths=={"Media":{"Title":310}}


def test_presentation_defaults_are_not_shared_mutable_state():
    first,second=AppSettings(),AppSettings()
    first.queue_visible_columns["Media"]=["Title"]
    first.queue_column_widths["Media"]={"Title":200}
    assert second.queue_visible_columns==second.queue_column_widths=={}
