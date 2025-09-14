#!/usr/bin/env python3
"""
Setup script for Social Media Downloader
"""

import sys
import os
import subprocess
import platform
from pathlib import Path

def check_python_version():
    """Check if Python version is supported"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python version: {sys.version}")
    return True

def install_requirements():
    """Install required packages"""
    print("📦 Installing required packages...")
    
    requirements = [
        "PyQt6==6.6.1",
        "yt-dlp>=2023.12.30",
        "requests>=2.31.0",
        "Pillow>=10.1.0",
        "mutagen>=1.47.0",
        "psutil>=5.9.6",
        "python-dateutil>=2.8.2",
        "PySocks>=1.7.1",
        "darkdetect>=0.8.0",
        "colorlog>=6.7.0",
        "plyer>=2.1.0"
    ]
    
    for requirement in requirements:
        try:
            print(f"Installing {requirement}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", requirement])
            print(f"✅ {requirement} installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install {requirement}: {e}")
            return False
    
    return True

def check_ffmpeg():
    """Check if FFmpeg is installed"""
    print("🎥 Checking FFmpeg installation...")
    
    try:
        result = subprocess.run(["ffmpeg", "-version"], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ FFmpeg is installed")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    print("❌ FFmpeg not found")
    print_ffmpeg_instructions()
    return False

def print_ffmpeg_instructions():
    """Print FFmpeg installation instructions"""
    system = platform.system().lower()
    
    print("\n📋 FFmpeg Installation Instructions:")
    print("=" * 50)
    
    if system == "windows":
        print("Windows:")
        print("1. Download FFmpeg from: https://ffmpeg.org/download.html")
        print("2. Extract to C:\\ffmpeg")
        print("3. Add C:\\ffmpeg\\bin to your PATH environment variable")
        print("4. Or use chocolatey: choco install ffmpeg")
        print("5. Or use winget: winget install FFmpeg")
    
    elif system == "darwin":  # macOS
        print("macOS:")
        print("1. Install Homebrew if not installed: https://brew.sh/")
        print("2. Run: brew install ffmpeg")
        print("3. Or use MacPorts: sudo port install ffmpeg")
    
    elif system == "linux":
        print("Linux:")
        print("Ubuntu/Debian: sudo apt update && sudo apt install ffmpeg")
        print("Fedora/RHEL: sudo dnf install ffmpeg")
        print("Arch Linux: sudo pacman -S ffmpeg")
        print("Or compile from source: https://ffmpeg.org/download.html")
    
    print("\nAfter installing FFmpeg, restart your terminal and run this setup again.")

def create_desktop_shortcut():
    """Create desktop shortcut (Windows/Linux)"""
    system = platform.system().lower()
    
    if system == "windows":
        create_windows_shortcut()
    elif system == "linux":
        create_linux_desktop_file()

def create_windows_shortcut():
    """Create Windows desktop shortcut"""
    try:
        import winshell
        from win32com.client import Dispatch
        
        desktop = winshell.desktop()
        shortcut_path = os.path.join(desktop, "Social Media Downloader.lnk")
        
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = sys.executable
        shortcut.Arguments = os.path.join(os.getcwd(), "main.py")
        shortcut.WorkingDirectory = os.getcwd()
        shortcut.IconLocation = os.path.join(os.getcwd(), "icon.ico")
        shortcut.save()
        
        print("✅ Desktop shortcut created")
    except ImportError:
        print("⚠️  Install pywin32 for desktop shortcut: pip install pywin32")
    except Exception as e:
        print(f"⚠️  Could not create desktop shortcut: {e}")

def create_linux_desktop_file():
    """Create Linux .desktop file"""
    try:
        desktop_file_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Social Media Downloader
Comment=Download content from social media platforms
Exec={sys.executable} {os.path.join(os.getcwd(), "main.py")}
Icon={os.path.join(os.getcwd(), "icon.png")}
Terminal=false
Categories=AudioVideo;Network;
"""
        
        # Try to create in user's desktop directory
        desktop_dir = Path.home() / "Desktop"
        if desktop_dir.exists():
            desktop_file_path = desktop_dir / "social-media-downloader.desktop"
            with open(desktop_file_path, 'w') as f:
                f.write(desktop_file_content)
            os.chmod(desktop_file_path, 0o755)
            print("✅ Desktop file created")
        
        # Also create in applications directory
        apps_dir = Path.home() / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        
        app_file_path = apps_dir / "social-media-downloader.desktop"
        with open(app_file_path, 'w') as f:
            f.write(desktop_file_content)
        
        print("✅ Application menu entry created")
        
    except Exception as e:
        print(f"⚠️  Could not create desktop file: {e}")

def create_config_directory():
    """Create configuration directory"""
    config_dir = Path.home() / ".social_downloader"
    config_dir.mkdir(exist_ok=True)
    
    # Create default config file
    config_file = config_dir / "config.json"
    if not config_file.exists():
        default_config = {
            "download_path": str(Path.home() / "Downloads"),
            "theme": "Light",
            "max_concurrent_downloads": 3,
            "default_video_quality": "720p",
            "default_audio_quality": "320kbps",
            "auto_organize": True,
            "add_metadata": True
        }
        
        import json
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=2)
    
    print("✅ Configuration directory created")

def verify_installation():
    """Verify that everything is working"""
    print("\n🔍 Verifying installation...")
    
    try:
        # Test PyQt6 import
        from PyQt6.QtWidgets import QApplication
        print("✅ PyQt6 import successful")
        
        # Test yt-dlp import
        import yt_dlp
        print("✅ yt-dlp import successful")
        
        # Test other imports
        import requests, PIL, mutagen
        print("✅ All required packages imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 Social Media Downloader Setup")
    print("=" * 40)
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Install requirements
    if not install_requirements():
        print("❌ Failed to install requirements")
        return False
    
    # Check FFmpeg
    ffmpeg_ok = check_ffmpeg()
    
    # Create config directory
    create_config_directory()
    
    # Verify installation
    if not verify_installation():
        print("❌ Installation verification failed")
        return False
    
    # Create shortcuts
    print("\n🔗 Creating shortcuts...")
    create_desktop_shortcut()
    
    print("\n✅ Setup completed successfully!")
    
    if not ffmpeg_ok:
        print("\n⚠️  Note: FFmpeg is required for audio/video conversion.")
        print("The application will work for basic downloads, but some features may be limited.")
    
    print("\n🎉 You can now run the application with:")
    print(f"   python {os.path.join(os.getcwd(), 'main.py')}")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)