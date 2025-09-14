# ========================================
# BUILD CONFIGURATION FOR WINDOWS ONLY
# ========================================

import os
import sys
import subprocess
import shutil
from pathlib import Path

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
        
        # Copy additional files
        dist_dir = Path("dist")
        if dist_dir.exists():
            try:
                ytdlp_path = shutil.which("yt-dlp")
                if ytdlp_path:
                    shutil.copy2(ytdlp_path, dist_dir / "yt-dlp.exe")
                    print("📋 Copied yt-dlp.exe to dist folder")
            except Exception as e:
                print(f"⚠️ Could not copy yt-dlp: {e}")
        
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
        create_installer()