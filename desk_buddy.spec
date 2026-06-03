# desk_buddy.spec
# Build with: .venv\Scripts\pyinstaller.exe desk_buddy.spec
block_cipher = None

a = Analysis(
    ["src/desk_buddy/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=["plyer.platforms.win.notification"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="desk-buddy",
    console=False,           # windowed app, no console
    onefile=True,
)
