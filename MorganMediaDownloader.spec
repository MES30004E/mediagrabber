# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
datas = [
    (str(root / "resources" / "bin"), "bin"),
    (str(root / "bgutil-ytdlp-pot-provider" / "plugin" / "yt_dlp_plugins"), "provider_plugin/yt_dlp_plugins"),
]
hiddenimports = [
    "yt_dlp_plugins.extractor.getpot_bgutil",
    "yt_dlp_plugins.extractor.getpot_bgutil_http",
    "yt_dlp_plugins.extractor.getpot_bgutil_script",
]

a = Analysis(
    [str(root / "launcher.py")],
    pathex=[str(root / "src"), str(root / "bgutil-ytdlp-pot-provider" / "plugin")],
    binaries=[], datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Morgan Media Downloader", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / "resources" / "AppIcon.icns"), target_arch=None, codesign_identity=None,
          entitlements_file=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name="Morgan Media Downloader")
app = BUNDLE(coll, name="Morgan Media Downloader.app", icon=str(root / "resources" / "AppIcon.icns"),
             bundle_identifier="com.morgan.media-downloader", version="0.1.0",
             info_plist={"NSHighResolutionCapable": True, "LSMinimumSystemVersion": "12.0", "NSHumanReadableCopyright": "Copyright © 2026 Morgan"})
