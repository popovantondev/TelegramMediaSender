from PyInstaller.utils.hooks import collect_all

datas = [("src/telegram_media_sender/assets/app-icon.svg", "assets")]
binaries = []
hiddenimports = []
package_datas, package_binaries, package_hidden = collect_all("telethon")
datas += package_datas
binaries += package_binaries
hiddenimports += package_hidden

analysis = Analysis(
    ["run_app.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    name="Telegram Media Sender",
    exclude_binaries=True,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch="arm64",
    codesign_identity=None,
    entitlements_file=None,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Telegram Media Sender",
)
app = BUNDLE(
    collection,
    name="Telegram Media Sender.app",
    icon="build-assets/TelegramMediaSender.icns",
    bundle_identifier="com.telegrammediasender.app",
    info_plist={
        "CFBundleShortVersionString": "1.1.2",
        "CFBundleVersion": "1.1.2",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
    },
)
