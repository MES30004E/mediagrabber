# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)
datas = [
    (str(root / "resources" / "bin"), "bin"),
    (str(root / "companion" / "chrome"), "companion/chrome"),
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
# Chrome must not launch the windowed Qt entry point as a native host. Keep a
# small independent console executable; it embeds its own stdlib/runtime and
# never imports the GUI or relies on the source checkout/venv.
host_analysis = Analysis(
    [str(root / "native_host_launcher.py")], pathex=[str(root / "src")],
    binaries=[], datas=[], hiddenimports=[], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=["PySide6", "yt_dlp"], noarchive=False,
)
host_pyz = PYZ(host_analysis.pure)
host_exe = EXE(host_pyz, host_analysis.scripts, host_analysis.binaries, host_analysis.datas, [],
               name="MorganNativeHost", debug=False, bootloader_ignore_signals=False,
               strip=False, upx=False, console=True, target_arch=None,
               codesign_identity=None, entitlements_file=None)
# GUI last retains windowed collection settings; BUNDLE uses its GUI entry name.
coll = COLLECT(host_exe, exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name="Morgan Media Downloader")
app = BUNDLE(coll, name="Morgan Media Downloader.app", icon=str(root / "resources" / "AppIcon.icns"),
             bundle_identifier="com.morgan.media-downloader", version="0.1.0",
             info_plist={"CFBundleExecutable": "Morgan Media Downloader", "NSHighResolutionCapable": True,
                         "LSMinimumSystemVersion": "12.0", "NSHumanReadableCopyright": "Copyright © 2026 Morgan"})
