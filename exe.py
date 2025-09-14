# ========================================
# BUILD CONFIGURATION FOR WINDOWS ONLY
# ========================================

import os
import sys
import subprocess
import shutil
from pathlib import Path
import requests
import zipfile
import io

def download_file(url, dest):
    """Download file from URL to destination"""
    print(f"🌐 Downloading {url}...")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        shutil.copyfileobj(r.raw, f)
    print(f"✅ Downloaded: {dest}")

def ensure_ytdlp(dist_dir):
    """Ensure yt-dlp.exe is available"""
    ytdlp_exe = dist_dir / "yt-dlp.exe"
    if ytdlp_exe.exists():
        print("📋 yt-dlp.exe already present")
        return
    try:
        url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        download_file(url, ytdlp_exe)
    except Exception as e:
        print(f"⚠️ Could not download yt-dlp: {e}")

def ensure_ffmpeg(dist_dir):
    """Ensure ffmpeg.exe and ffprobe.exe are available"""
    ffmpeg_exe = dist_dir / "ffmpeg.exe"
    ffprobe_exe = dist_dir / "ffprobe.exe"
    if ffmpeg_exe.exists() and ffprobe_exe.exists():
        print("📋 ffmpeg.exe and ffprobe.exe already present")
        return
    try:
        # Using gyan.dev static builds (win64)
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        print("🌐 Downloading FFmpeg package...")
        r = requests.get(url, stream=True)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in z.namelist():
                if name.endswith("ffmpeg.exe"):
                    with z.open(name) as src, open(ffmpeg_exe, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                elif name.endswith("ffprobe.exe"):
                    with z.open(name) as src, open(ffprobe_exe, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        print("✅ Extracted ffmpeg.exe and ffprobe.exe")
    except Exception as e:
        print(f"⚠️ Could not download FFmpeg: {e}")

def create_exe():
    """Create Windows EXE using PyInstaller"""
    
    print("🔨 Building Windows EXE...")
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Create build directory
    build_dir = Path("build_exe")
    build_dir.mkdir(exist_ok=True)
    
    # Build command
    cmd = [
        "pyinstaller",
        "--clean",
        "--onefile",
        "--windowed",
        "--name=SocialMediaDownloader",
        "--icon=assets/icons/app_icon.ico",
        "--add-data=assets;assets",
        "--add-data=config;config",
        "--hidden-import=customtkinter",
        "--hidden-import=PIL._tkinter_finder",
        "main.py"
    ]
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ EXE created successfully!")
        print("📁 Location: dist/SocialMediaDownloader.exe")
        
        # Ensure extra tools
        dist_dir = Path("dist")
        if dist_dir.exists():
            ensure_ytdlp(dist_dir)
            ensure_ffmpeg(dist_dir)
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error creating EXE: {e}")
        print(f"Output: {e.output}")
        return False

def create_installer():
    """Create Windows installer using NSIS"""
    
    nsis_script = '''
!define APPNAME "Social Media Downloader"
!define COMPANYNAME "YourCompany"
!define DESCRIPTION "Download social media content easily"
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define VERSIONBUILD 0
!define HELPURL "https://github.com/yourusername/social-media-downloader"
!define UPDATEURL "https://github.com/yourusername/social-media-downloader/releases"
!define ABOUTURL "https://github.com/yourusername/social-media-downloader"
!define INSTALLSIZE 50000

RequestExecutionLevel admin

InstallDir "$PROGRAMFILES\\${APPNAME}"
LicenseData "LICENSE.txt"
Name "${APPNAME}"
Icon "assets\\icons\\app_icon.ico"
outFile "SocialMediaDownloaderSetup.exe"

!include LogicLib.nsh

page license
page directory
page instfiles

!macro VerifyUserIsAdmin
UserInfo::GetAccountType
pop $0
${If} $0 != "admin"
    messageBox mb_iconstop "Administrator rights required!"
    setErrorLevel 740
    quit
${EndIf}
!macroend

function .onInit
    setShellVarContext all
    !insertmacro VerifyUserIsAdmin
functionEnd

section "install"
    setOutPath $INSTDIR
    file "dist\\SocialMediaDownloader.exe"
    file "dist\\yt-dlp.exe"
    file "dist\\ffmpeg.exe"
    file "dist\\ffprobe.exe"
    file /r "dist\\*.*"
    
    writeUninstaller "$INSTDIR\\uninstall.exe"
    
    createDirectory "$SMPROGRAMS\\${APPNAME}"
    createShortCut "$SMPROGRAMS\\${APPNAME}\\${APPNAME}.lnk" "$INSTDIR\\SocialMediaDownloader.exe"
    createShortCut "$DESKTOP\\${APPNAME}.lnk" "$INSTDIR\\SocialMediaDownloader.exe"
    
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "UninstallString" "$INSTDIR\\uninstall.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "DisplayIcon" "$INSTDIR\\SocialMediaDownloader.exe"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "HelpLink" "${HELPURL}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "URLUpdateInfo" "${UPDATEURL}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "VersionMajor" ${VERSIONMAJOR}
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "VersionMinor" ${VERSIONMINOR}
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}" "EstimatedSize" ${INSTALLSIZE}
sectionEnd

section "uninstall"
    delete "$INSTDIR\\SocialMediaDownloader.exe"
    delete "$INSTDIR\\yt-dlp.exe"
    delete "$INSTDIR\\ffmpeg.exe"
    delete "$INSTDIR\\ffprobe.exe"
    delete "$INSTDIR\\uninstall.exe"
    rmDir /r "$INSTDIR"
    
    delete "$SMPROGRAMS\\${APPNAME}\\${APPNAME}.lnk"
    rmDir "$SMPROGRAMS\\${APPNAME}"
    delete "$DESKTOP\\${APPNAME}.lnk"
    
    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\${APPNAME}"
sectionEnd
'''
    
    with open("installer.nsi", 'w') as f:
        f.write(nsis_script)
    
    print("📝 NSIS installer script created: installer.nsi")
    print("💡 Run with: makensis installer.nsi")

if __name__ == "__main__":
    success = create_exe()
    if success:
        ensure_ytdlp(Path("dist"))
        ensure_ffmpeg(Path("dist"))
        create_installer()