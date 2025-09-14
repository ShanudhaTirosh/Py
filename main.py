import sys
import os
import json
import sqlite3
import threading
import asyncio
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import urllib.parse

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox, 
    QProgressBar, QTextEdit, QTabWidget, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QFrame, QScrollArea, QGroupBox,
    QCheckBox, QSlider, QSpinBox, QTableWidget, QTableWidgetItem,
    QSplitter, QSystemTrayIcon, QMenu, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSettings, QSize, QRect,
    QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
)
from PyQt6.QtGui import (
    QFont, QPixmap, QIcon, QPalette, QColor, QLinearGradient,
    QBrush, QPainter, QAction, QClipboard
)

# Import the fixed download manager
from download_manager import DownloadManager, DownloadItem, DownloadStatus, MediaExtractor

# You'll need to install these packages:
# pip install PyQt6 yt-dlp requests pillow

try:
    import yt_dlp
    import requests
    from PIL import Image
except ImportError:
    print("Please install required packages: pip install yt-dlp requests pillow")
    sys.exit(1)


class ModernButton(QPushButton):
    """Custom modern button with hover effects"""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setup_style()
    
    def setup_style(self):
        self.setStyleSheet("""
            ModernButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4A90E2, stop:1 #357ABD);
                border: none;
                border-radius: 8px;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 8px 16px;
            }
            ModernButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5BA0F2, stop:1 #4A8ACD);
            }
            ModernButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #357ABD, stop:1 #2E6BA8);
            }
            ModernButton:disabled {
                background: #CCCCCC;
                color: #888888;
            }
        """)


class ModernLineEdit(QLineEdit):
    """Custom modern line edit with styling"""
    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(40)
        self.setup_style()
    
    def setup_style(self):
        self.setStyleSheet("""
            ModernLineEdit {
                border: 2px solid #E0E0E0;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
                background: white;
            }
            ModernLineEdit:focus {
                border-color: #4A90E2;
            }
            ModernLineEdit:hover {
                border-color: #B0B0B0;
            }
        """)


class DownloadWorker(QThread):
    """Worker thread for downloading content - simplified version"""
    progress = pyqtSignal(int)  # Progress percentage
    status = pyqtSignal(str)    # Status message
    finished = pyqtSignal(str)  # Finished with file path
    error = pyqtSignal(str)     # Error message
    
    def __init__(self, url, output_path, format_info):
        super().__init__()
        self.url = url
        self.output_path = output_path
        self.format_info = format_info
        self.is_cancelled = False
    
    def run(self):
        try:
            self.status.emit("Preparing download...")
            
            # Validate URL
            if not self.is_valid_url(self.url):
                self.error.emit("Invalid URL format")
                return
            
            # Configure yt-dlp options
            ydl_opts = {
                'outtmpl': os.path.join(self.output_path, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_hook],
                'socket_timeout': 60,
                'retries': 3,
            }
            
            # Set format based on user selection
            if self.format_info['type'] == 'video':
                if self.format_info['quality'] == 'Best Available':
                    ydl_opts['format'] = 'best[ext=mp4]/best'
                else:
                    # Extract resolution number
                    resolution = ''.join(filter(str.isdigit, self.format_info['quality']))
                    if resolution:
                        ydl_opts['format'] = f'best[height<={resolution}][ext=mp4]/best[height<={resolution}]/best'
                    else:
                        ydl_opts['format'] = 'best[ext=mp4]/best'
                        
            elif self.format_info['type'] == 'audio':
                ydl_opts['format'] = 'bestaudio/best'
                # Extract bitrate number
                bitrate = ''.join(filter(str.isdigit, self.format_info.get('quality', '320')))
                if not bitrate:
                    bitrate = '320'
                    
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': bitrate,
                }]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if self.is_cancelled:
                    return
                
                self.status.emit("Downloading...")
                ydl.download([self.url])
                
            if not self.is_cancelled:
                self.finished.emit("Download completed successfully!")
            
        except yt_dlp.DownloadError as e:
            if not self.is_cancelled:
                self.error.emit(f"Download failed: {str(e)}")
        except Exception as e:
            if not self.is_cancelled:
                self.error.emit(f"Download failed: {str(e)}")
    
    def is_valid_url(self, url):
        """Basic URL validation"""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def progress_hook(self, d):
        """Handle download progress"""
        if self.is_cancelled:
            raise yt_dlp.DownloadError("Download cancelled")
            
        if d['status'] == 'downloading':
            try:
                if 'total_bytes' in d and d['total_bytes']:
                    percent = int(d['downloaded_bytes'] * 100 / d['total_bytes'])
                    self.progress.emit(percent)
                elif 'total_bytes_estimate' in d and d['total_bytes_estimate']:
                    percent = int(d['downloaded_bytes'] * 100 / d['total_bytes_estimate'])
                    self.progress.emit(percent)
                elif '_percent_str' in d:
                    percent_str = d['_percent_str'].strip().replace('%', '')
                    try:
                        percent = int(float(percent_str))
                        self.progress.emit(percent)
                    except (ValueError, TypeError):
                        pass
            except (KeyError, TypeError, ZeroDivisionError):
                pass
    
    def cancel(self):
        self.is_cancelled = True


class MediaInfo(QWidget):
    """Widget to display media information and preview"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.media_extractor = MediaExtractor()
        self.media_extractor.info_extracted.connect(self.update_info)
        self.media_extractor.error_occurred.connect(self.show_error)
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # Title
        self.title_label = QLabel("Media Information")
        self.title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(self.title_label)
        
        # Info container
        info_frame = QFrame()
        info_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        info_frame.setStyleSheet("""
            QFrame {
                background: white;
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                padding: 15px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        
        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(200, 150)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #CCCCCC;
                border-radius: 4px;
                background: #F8F8F8;
            }
        """)
        self.thumbnail_label.setText("No Preview")
        info_layout.addWidget(self.thumbnail_label)
        
        # Details
        self.details_text = QTextEdit()
        self.details_text.setMaximumHeight(120)
        self.details_text.setReadOnly(True)
        info_layout.addWidget(self.details_text)
        
        layout.addWidget(info_frame)
        layout.addStretch()
    
    def extract_info(self, url):
        """Extract information from URL"""
        self.details_text.setText("Extracting information...")
        self.media_extractor.extract_info(url)
    
    def update_info(self, info_dict):
        """Update the media information display"""
        self.details_text.clear()
        details = []
        
        if 'title' in info_dict:
            details.append(f"Title: {info_dict['title']}")
        if 'uploader' in info_dict:
            details.append(f"Channel: {info_dict['uploader']}")
        if 'duration' in info_dict and info_dict['duration']:
            duration = info_dict['duration']
            minutes, seconds = divmod(duration, 60)
            details.append(f"Duration: {minutes}:{seconds:02d}")
        if 'view_count' in info_dict and info_dict['view_count']:
            details.append(f"Views: {info_dict['view_count']:,}")
        if 'platform' in info_dict:
            details.append(f"Platform: {info_dict['platform']}")
        
        self.details_text.setText('\n'.join(details))
    
    def show_error(self, error_message):
        """Show error message"""
        self.details_text.setText(f"Error: {error_message}")


class SettingsDialog(QDialog):
    """Settings dialog for application preferences"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(500, 400)
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Tab widget for different setting categories
        tabs = QTabWidget()
        
        # General settings
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        
        # Default download path
        path_group = QGroupBox("Download Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = ModernLineEdit()
        path_browse_btn = ModernButton("Browse")
        path_browse_btn.clicked.connect(self.browse_download_path)
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(path_browse_btn)
        general_layout.addWidget(path_group)
        
        # Theme settings
        theme_group = QGroupBox("Appearance")
        theme_layout = QVBoxLayout(theme_group)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "Auto"])
        theme_layout.addWidget(QLabel("Theme:"))
        theme_layout.addWidget(self.theme_combo)
        general_layout.addWidget(theme_group)
        
        general_layout.addStretch()
        tabs.addTab(general_tab, "General")
        
        # Download settings
        download_tab = QWidget()
        download_layout = QVBoxLayout(download_tab)
        
        # Default quality settings
        quality_group = QGroupBox("Default Quality")
        quality_layout = QGridLayout(quality_group)
        
        quality_layout.addWidget(QLabel("Video Quality:"), 0, 0)
        self.video_quality_combo = QComboBox()
        self.video_quality_combo.addItems(["720p", "1080p", "480p", "360p", "Best Available"])
        quality_layout.addWidget(self.video_quality_combo, 0, 1)
        
        quality_layout.addWidget(QLabel("Audio Quality:"), 1, 0)
        self.audio_quality_combo = QComboBox()
        self.audio_quality_combo.addItems(["320 kbps", "192 kbps", "128 kbps", "64 kbps"])
        quality_layout.addWidget(self.audio_quality_combo, 1, 1)
        
        download_layout.addWidget(quality_group)
        download_layout.addStretch()
        tabs.addTab(download_tab, "Downloads")
        
        layout.addWidget(tabs)
        
        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def browse_download_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if path:
            self.path_edit.setText(path)
    
    def load_settings(self):
        settings = QSettings("SocialMediaDownloader", "Settings")
        download_path = settings.value("download_path", str(Path.home() / "Downloads"))
        self.path_edit.setText(download_path)
        
        theme = settings.value("theme", "Light")
        self.theme_combo.setCurrentText(theme)
        
        video_quality = settings.value("video_quality", "720p")
        self.video_quality_combo.setCurrentText(video_quality)
        
        audio_quality = settings.value("audio_quality", "320 kbps")
        self.audio_quality_combo.setCurrentText(audio_quality)
    
    def save_settings(self):
        settings = QSettings("SocialMediaDownloader", "Settings")
        settings.setValue("download_path", self.path_edit.text())
        settings.setValue("theme", self.theme_combo.currentText())
        settings.setValue("video_quality", self.video_quality_combo.currentText())
        settings.setValue("audio_quality", self.audio_quality_combo.currentText())


class SocialMediaDownloader(QMainWindow):
    """Main application window"""
    def __init__(self):
        super().__init__()
        self.current_worker = None
        self.download_history = []
        self.setup_database()
        self.setup_ui()
        self.load_settings()
        self.setup_system_tray()
        
        # Initialize download manager
        self.download_manager = DownloadManager()
        self.download_manager.download_completed.connect(self.on_download_completed)
        self.download_manager.download_failed.connect(self.on_download_failed)
        self.download_manager.download_updated.connect(self.on_download_updated)
    
    def setup_database(self):
        """Initialize SQLite database for storing history and settings"""
        try:
            db_path = Path.home() / ".social_downloader" / "history.db"
            db_path.parent.mkdir(exist_ok=True)
            
            self.conn = sqlite3.connect(str(db_path))
            cursor = self.conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY,
                    url TEXT,
                    title TEXT,
                    file_path TEXT,
                    download_date TEXT,
                    file_size INTEGER,
                    format_type TEXT
                )
            ''')
            self.conn.commit()
        except Exception as e:
            print(f"Database setup error: {e}")
            # Fallback to in-memory database
            self.conn = sqlite3.connect(":memory:")
            self.setup_database()
    
    def setup_ui(self):
        """Setup the main user interface"""
        self.setWindowTitle("Social Media Downloader")
        self.setMinimumSize(1000, 700)
        self.center_window()
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(20)
        
        # Left panel
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel, 2)
        
        # Right panel
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel, 1)
        
        # Setup menu bar
        self.setup_menu_bar()
        
        # Setup status bar
        self.statusBar().showMessage("Ready to download")
        
        # Apply modern styling
        self.apply_modern_style()
    
    def create_left_panel(self):
        """Create the main download interface panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(20)
        
        # Header
        header_label = QLabel("Social Media Downloader")
        header_label.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)
        
        # URL input section
        url_group = QGroupBox("Enter URL")
        url_layout = QVBoxLayout(url_group)
        
        # URL input with paste button
        url_input_layout = QHBoxLayout()
        self.url_input = ModernLineEdit("Paste your URL here...")
        self.url_input.textChanged.connect(self.on_url_changed)
        
        paste_btn = ModernButton("Paste")
        paste_btn.setFixedWidth(80)
        paste_btn.clicked.connect(self.paste_from_clipboard)
        
        url_input_layout.addWidget(self.url_input)
        url_input_layout.addWidget(paste_btn)
        url_layout.addLayout(url_input_layout)
        
        # Format selection
        format_layout = QHBoxLayout()
        
        # Type selection
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Video", "Audio", "Auto-detect"])
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        
        # Quality selection
        self.quality_combo = QComboBox()
        self.update_quality_options("Video")
        
        format_layout.addWidget(QLabel("Type:"))
        format_layout.addWidget(self.type_combo)
        format_layout.addWidget(QLabel("Quality:"))
        format_layout.addWidget(self.quality_combo)
        url_layout.addLayout(format_layout)
        
        layout.addWidget(url_group)
        
        # Download section
        download_group = QGroupBox("Download")
        download_layout = QVBoxLayout(download_group)
        
        # Download path
        path_layout = QHBoxLayout()
        self.path_label = QLabel("Downloads")
        path_browse_btn = ModernButton("Change Location")
        path_browse_btn.clicked.connect(self.browse_download_location)
        path_layout.addWidget(QLabel("Save to:"))
        path_layout.addWidget(self.path_label)
        path_layout.addStretch()
        path_layout.addWidget(path_browse_btn)
        download_layout.addLayout(path_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        download_layout.addWidget(self.progress_bar)
        
        # Download button
        self.download_btn = ModernButton("Download")
        self.download_btn.setFixedHeight(50)
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setEnabled(False)
        download_layout.addWidget(self.download_btn)
        
        layout.addWidget(download_group)
        
        # Download queue/batch section
        queue_group = QGroupBox("Batch Downloads")
        queue_layout = QVBoxLayout(queue_group)
        
        self.queue_list = QListWidget()
        self.queue_list.setMaximumHeight(150)
        queue_layout.addWidget(self.queue_list)
        
        queue_btn_layout = QHBoxLayout()
        add_to_queue_btn = ModernButton("Add to Queue")
        add_to_queue_btn.clicked.connect(self.add_to_queue)
        clear_queue_btn = ModernButton("Clear Queue")
        clear_queue_btn.clicked.connect(self.clear_queue)
        
        queue_btn_layout.addWidget(add_to_queue_btn)
        queue_btn_layout.addWidget(clear_queue_btn)
        queue_layout.addLayout(queue_btn_layout)
        
        layout.addWidget(queue_group)
        layout.addStretch()
        
        return panel
    
    def create_right_panel(self):
        """Create the information and history panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Tab widget for different views
        self.info_tabs = QTabWidget()
        
        # Media info tab
        self.media_info = MediaInfo()
        self.info_tabs.addTab(self.media_info, "Media Info")
        
        # History tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["Title", "Type", "Date", "Size"])
        self.load_download_history()
        history_layout.addWidget(self.history_table)
        
        self.info_tabs.addTab(history_tab, "History")
        
        layout.addWidget(self.info_tabs)
        
        return panel
    
    def setup_menu_bar(self):
        """Setup the application menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        settings_action = QAction("Settings", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_system_tray(self):
        """Setup system tray icon"""
        try:
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray_icon = QSystemTrayIcon(self)
                self.tray_icon.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaPlay))
                
                tray_menu = QMenu()
                show_action = tray_menu.addAction("Show")
                show_action.triggered.connect(self.show)
                quit_action = tray_menu.addAction("Quit")
                quit_action.triggered.connect(self.close)
                
                self.tray_icon.setContextMenu(tray_menu)
                self.tray_icon.show()
        except Exception as e:
            print(f"System tray setup failed: {e}")
    
    def center_window(self):
        """Center the window on the screen"""
        try:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.geometry()
                window_geometry = self.geometry()
                x = (screen_geometry.width() - window_geometry.width()) // 2
                y = (screen_geometry.height() - window_geometry.height()) // 2
                self.move(x, y)
        except Exception as e:
            print(f"Window centering failed: {e}")
    
    def apply_modern_style(self):
        """Apply modern styling to the application"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F5F5F5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #CCCCCC;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: white;
            }
            QTabWidget::pane {
                border: 1px solid #C0C0C0;
                background-color: white;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #E0E0E0;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: 2px solid #4A90E2;
            }
            QTableWidget {
                gridline-color: #E0E0E0;
                background-color: white;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
            }
            QListWidget {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                background-color: white;
            }
            QProgressBar {
                border: 2px solid #CCCCCC;
                border-radius: 8px;
                text-align: center;
                background-color: #F0F0F0;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4A90E2, stop:1 #357ABD);
                border-radius: 6px;
            }
        """)
    
    def on_url_changed(self, text):
        """Handle URL input changes"""
        self.download_btn.setEnabled(bool(text.strip()))
        if text.strip():
            # Auto-detect media type and update UI
            self.detect_media_type(text)
            # Extract info if valid URL
            if self.is_valid_url(text.strip()):
                self.media_info.extract_info(text.strip())
    
    def is_valid_url(self, url):
        """Basic URL validation"""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def on_type_changed(self, type_text):
        """Handle format type changes"""
        self.update_quality_options(type_text)
    
    def update_quality_options(self, media_type):
        """Update quality options based on media type"""
        self.quality_combo.clear()
        if media_type == "Video":
            self.quality_combo.addItems([
                "Best Available", "2160p (4K)", "1440p (2K)", 
                "1080p", "720p", "480p", "360p", "240p", "144p"
            ])
        elif media_type == "Audio":
            self.quality_combo.addItems([
                "320 kbps", "192 kbps", "128 kbps", "64 kbps"
            ])
        else:  # Auto-detect
            self.quality_combo.addItems(["Best Available", "720p", "320 kbps"])
    
    def detect_media_type(self, url):
        """Auto-detect media type from URL"""
        # Simple URL pattern matching for auto-detection
        url_lower = url.lower()
        if any(platform in url_lower for platform in ['youtube.com', 'youtu.be', 'vimeo.com']):
            self.type_combo.setCurrentText("Video")
        elif any(platform in url_lower for platform in ['soundcloud.com', 'spotify.com']):
            self.type_combo.setCurrentText("Audio")
        else:
            self.type_combo.setCurrentText("Auto-detect")
    
    def paste_from_clipboard(self):
        """Paste URL from clipboard"""
        try:
            clipboard = QApplication.clipboard()
            text = clipboard.text()
            if text:
                self.url_input.setText(text.strip())
        except Exception as e:
            print(f"Clipboard paste failed: {e}")
    
    def browse_download_location(self):
        """Browse for download location"""
        try:
            path = QFileDialog.getExistingDirectory(self, "Select Download Directory")
            if path:
                self.path_label.setText(Path(path).name)
                settings = QSettings("SocialMediaDownloader", "Settings")
                settings.setValue("download_path", path)
        except Exception as e:
            print(f"Browse directory failed: {e}")
    
    def add_to_queue(self):
        """Add current URL to download queue"""
        url = self.url_input.text().strip()
        if url and self.is_valid_url(url):
            item_text = f"{url} ({self.type_combo.currentText()} - {self.quality_combo.currentText()})"
            self.queue_list.addItem(item_text)
            self.url_input.clear()
        else:
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid URL")
    
    def clear_queue(self):
        """Clear download queue"""
        self.queue_list.clear()
    
    def start_download(self):
        """Start the download process"""
        url = self.url_input.text().strip()
        if not url:
            return
        
        if not self.is_valid_url(url):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid URL")
            return
        
        # Get download settings
        settings = QSettings("SocialMediaDownloader", "Settings")
        download_path = settings.value("download_path", str(Path.home() / "Downloads"))
        
        # Ensure download directory exists
        try:
            os.makedirs(download_path, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Directory Error", f"Cannot create download directory: {e}")
            return
        
        # Determine format type and quality
        format_type = self.type_combo.currentText().lower()
        if format_type == "auto-detect":
            format_type = "video"  # Default to video for auto-detect
        
        # Add to download manager
        try:
            download_id = self.download_manager.add_download(
                url=url,
                format_type=format_type,
                quality=self.quality_combo.currentText(),
                output_path=download_path
            )
            
            # Update UI
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.download_btn.setText("Cancel")
            self.download_btn.clicked.disconnect()
            self.download_btn.clicked.connect(lambda: self.cancel_download(download_id))
            self.statusBar().showMessage("Download started...")
            
        except Exception as e:
            QMessageBox.critical(self, "Download Error", f"Failed to start download: {e}")
    
    def cancel_download(self, download_id):
        """Cancel current download"""
        try:
            self.download_manager.cancel_download(download_id)
            self.reset_download_ui()
            self.statusBar().showMessage("Download cancelled")
        except Exception as e:
            print(f"Cancel download error: {e}")
    
    def reset_download_ui(self):
        """Reset download UI to initial state"""
        self.progress_bar.setVisible(False)
        self.download_btn.setText("Download")
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self.start_download)
    
    def on_download_completed(self, download_item):
        """Handle download completion"""
        self.reset_download_ui()
        self.statusBar().showMessage("Download completed!")
        
        # Show notification
        if hasattr(self, 'tray_icon') and hasattr(self.tray_icon, 'showMessage'):
            try:
                self.tray_icon.showMessage("Download Complete", 
                                         f"Downloaded: {download_item.title}", 
                                         QSystemTrayIcon.MessageIcon.Information)
            except Exception as e:
                print(f"Notification error: {e}")
        
        # Update history
        self.update_download_history(download_item)
    
    def on_download_failed(self, download_item):
        """Handle download failure"""
        self.reset_download_ui()
        self.statusBar().showMessage("Download failed")
        
        error_msg = download_item.error_message or "Unknown error occurred"
        QMessageBox.critical(self, "Download Error", f"Download failed: {error_msg}")
    
    def on_download_updated(self, download_item):
        """Handle download progress updates"""
        if download_item.progress > 0:
            self.progress_bar.setValue(download_item.progress)
            
        # Update status with speed info
        if download_item.speed > 0:
            speed_mb = download_item.speed / (1024 * 1024)
            self.statusBar().showMessage(f"Downloading... {download_item.progress}% - {speed_mb:.1f} MB/s")
    
    def update_download_history(self, download_item):
        """Update the download history table"""
        try:
            # Save to database
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO downloads (url, title, file_path, download_date, file_size, format_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                download_item.url,
                download_item.title,
                download_item.filename,
                download_item.completed_at,
                download_item.file_size,
                download_item.format_type
            ))
            self.conn.commit()
            
            # Refresh history table
            self.load_download_history()
            
        except Exception as e:
            print(f"Error updating history: {e}")
    
    def load_download_history(self):
        """Load download history from database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT title, format_type, download_date, file_size FROM downloads ORDER BY id DESC LIMIT 100')
            rows = cursor.fetchall()
            
            self.history_table.setRowCount(len(rows))
            for row_idx, row in enumerate(rows):
                title, format_type, date, size = row
                
                # Format the data
                title = title[:50] + "..." if title and len(title) > 50 else (title or "Unknown")
                format_type = format_type or "Unknown"
                
                # Format date
                try:
                    if date:
                        date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                        formatted_date = date_obj.strftime("%Y-%m-%d %H:%M")
                    else:
                        formatted_date = "Unknown"
                except Exception:
                    formatted_date = date or "Unknown"
                
                # Format file size
                if size and size > 0:
                    if size > 1024 * 1024:
                        size_str = f"{size / (1024 * 1024):.1f} MB"
                    else:
                        size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = "Unknown"
                
                # Add to table
                self.history_table.setItem(row_idx, 0, QTableWidgetItem(title))
                self.history_table.setItem(row_idx, 1, QTableWidgetItem(format_type))
                self.history_table.setItem(row_idx, 2, QTableWidgetItem(formatted_date))
                self.history_table.setItem(row_idx, 3, QTableWidgetItem(size_str))
                
        except Exception as e:
            print(f"Error loading history: {e}")
    
    def open_settings(self):
        """Open settings dialog"""
        try:
            dialog = SettingsDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                dialog.save_settings()
                self.load_settings()
        except Exception as e:
            print(f"Settings dialog error: {e}")
    
    def load_settings(self):
        """Load application settings"""
        try:
            settings = QSettings("SocialMediaDownloader", "Settings")
            download_path = settings.value("download_path", str(Path.home() / "Downloads"))
            self.path_label.setText(Path(download_path).name)
            
            # Load theme settings
            theme = settings.value("theme", "Light")
            self.apply_theme(theme)
            
            # Load default quality settings
            video_quality = settings.value("video_quality", "720p")
            audio_quality = settings.value("audio_quality", "320 kbps")
            
            # Apply to combo boxes if they match
            if video_quality in [self.quality_combo.itemText(i) for i in range(self.quality_combo.count())]:
                self.quality_combo.setCurrentText(video_quality)
                
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def apply_theme(self, theme):
        """Apply the selected theme"""
        if theme == "Dark":
            self.setStyleSheet(self.get_dark_stylesheet())
        else:
            self.apply_modern_style()  # Light theme
    
    def get_dark_stylesheet(self):
        """Get dark theme stylesheet"""
        return """
            QMainWindow {
                background-color: #2B2B2B;
                color: #FFFFFF;
            }
            QWidget {
                background-color: #2B2B2B;
                color: #FFFFFF;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #3C3C3C;
                color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: #3C3C3C;
                color: #FFFFFF;
            }
            ModernLineEdit {
                border: 2px solid #555555;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
                background: #3C3C3C;
                color: #FFFFFF;
            }
            ModernLineEdit:focus {
                border-color: #4A90E2;
            }
            QComboBox {
                border: 2px solid #555555;
                border-radius: 4px;
                padding: 5px;
                background-color: #3C3C3C;
                color: #FFFFFF;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                border: none;
            }
            QTableWidget {
                gridline-color: #555555;
                background-color: #3C3C3C;
                border: 1px solid #555555;
                border-radius: 4px;
                color: #FFFFFF;
            }
            QListWidget {
                border: 1px solid #555555;
                border-radius: 4px;
                background-color: #3C3C3C;
                color: #FFFFFF;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #3C3C3C;
                border-radius: 4px;
            }
            QTabBar::tab {
                background-color: #555555;
                color: #FFFFFF;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #3C3C3C;
                border-bottom: 2px solid #4A90E2;
            }
            QProgressBar {
                border: 2px solid #555555;
                border-radius: 8px;
                text-align: center;
                background-color: #3C3C3C;
                color: #FFFFFF;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4A90E2, stop:1 #357ABD);
                border-radius: 6px;
            }
        """
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About Social Media Downloader", 
                         """
                         <h3>Social Media Downloader v1.0</h3>
                         <p>A modern, comprehensive social media content downloader</p>
                         <p><b>Supported platforms:</b><br>
                         YouTube, TikTok, Facebook, Instagram, Twitter, Reddit, SoundCloud, and more</p>
                         <p><b>Features:</b><br>
                         • Multiple format support (MP4, MP3, WAV, AAC)<br>
                         • Batch downloads<br>
                         • Resume & retry functionality<br>
                         • Modern, customizable interface<br>
                         • Download history tracking</p>
                         <p>Built with Python, PyQt6, and yt-dlp</p>
                         """)
    
    def closeEvent(self, event):
        """Handle application close event"""
        try:
            if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
                self.hide()
                event.ignore()
            else:
                # Clean up
                if hasattr(self, 'download_manager'):
                    self.download_manager.close()
                if hasattr(self, 'conn'):
                    self.conn.close()
                event.accept()
        except Exception as e:
            print(f"Close event error: {e}")
            event.accept()


def main():
    """Main application entry point"""
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Social Media Downloader")
        app.setApplicationVersion("1.0")
        app.setOrganizationName("SocialDownloader")
        
        # Set application icon
        app.setWindowIcon(app.style().standardIcon(app.style().StandardPixmap.SP_MediaPlay))
        
        # Create and show main window
        window = SocialMediaDownloader()
        window.show()
        
        # Start event loop
        sys.exit(app.exec())
        
    except Exception as e:
        print(f"Application startup error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()