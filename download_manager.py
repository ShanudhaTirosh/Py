import os
import json
import sqlite3
import threading
import asyncio
import hashlib
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import urllib.parse

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer, QSettings
import yt_dlp
import requests
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC


class DownloadStatus(Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class DownloadItem:
    id: str
    url: str
    title: str = ""
    thumbnail_url: str = ""
    duration: int = 0
    file_size: int = 0
    format_type: str = "video"  # video, audio, playlist
    quality: str = "best"
    codec: str = "mp4"
    bitrate: int = 320
    output_path: str = ""
    filename: str = ""
    status: DownloadStatus = DownloadStatus.PENDING
    progress: int = 0
    speed: float = 0.0
    eta: int = 0
    created_at: str = ""
    completed_at: str = ""
    error_message: str = ""
    retry_count: int = 0
    max_retries: int = 3


class MediaExtractor(QObject):
    """Extract media information from URLs"""
    info_extracted = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.supported_sites = {
            'youtube.com': 'YouTube',
            'youtu.be': 'YouTube',
            'tiktok.com': 'TikTok',
            'facebook.com': 'Facebook',
            'instagram.com': 'Instagram',
            'twitter.com': 'Twitter',
            'x.com': 'Twitter',
            'reddit.com': 'Reddit',
            'soundcloud.com': 'SoundCloud',
            'vimeo.com': 'Vimeo',
            'twitch.tv': 'Twitch',
            'pinterest.com': 'Pinterest'
        }
    
    def is_valid_url(self, url: str) -> bool:
        """Validate URL format"""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def extract_info(self, url: str) -> Dict:
        """Extract media information from URL"""
        if not self.is_valid_url(url):
            self.error_occurred.emit("Invalid URL format")
            return {}
            
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'socket_timeout': 30,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Process the information
                processed_info = {
                    'title': info.get('title', 'Unknown Title'),
                    'uploader': info.get('uploader', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'view_count': info.get('view_count', 0),
                    'upload_date': info.get('upload_date', ''),
                    'thumbnail': info.get('thumbnail', ''),
                    'description': info.get('description', ''),
                    'formats': info.get('formats', []),
                    'url': url,
                    'platform': self.detect_platform(url)
                }
                
                self.info_extracted.emit(processed_info)
                return processed_info
                
        except Exception as e:
            error_msg = f"Failed to extract info: {str(e)}"
            self.error_occurred.emit(error_msg)
            return {}
    
    def detect_platform(self, url: str) -> str:
        """Detect the platform from URL"""
        for domain, platform in self.supported_sites.items():
            if domain in url.lower():
                return platform
        return "Unknown"


class AdvancedDownloadWorker(QThread):
    """Advanced download worker with resume, retry, and metadata support"""
    progress_updated = pyqtSignal(str, int, float, int)  # id, progress, speed, eta
    status_changed = pyqtSignal(str, str)  # id, status
    download_completed = pyqtSignal(str, str)  # id, file_path
    error_occurred = pyqtSignal(str, str)  # id, error_message
    
    def __init__(self, download_item: DownloadItem):
        super().__init__()
        self.download_item = download_item
        self.is_cancelled = False
        self.is_paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()  # Initially not paused
        self.download_cancelled = False
    
    def run(self):
        """Main download execution"""
        try:
            self.status_changed.emit(self.download_item.id, "preparing")
            
            # Create output directory
            os.makedirs(self.download_item.output_path, exist_ok=True)
            
            # Configure yt-dlp options
            ydl_opts = self.build_ydl_options()
            
            # Start download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if self.is_cancelled:
                    return
                
                self.status_changed.emit(self.download_item.id, "downloading")
                ydl.download([self.download_item.url])
            
            if not self.is_cancelled:
                # Add metadata if audio file
                if self.download_item.format_type == "audio" and self.download_item.filename:
                    self.add_metadata()
                
                self.download_completed.emit(self.download_item.id, self.download_item.filename)
            
        except Exception as e:
            if not self.is_cancelled:
                error_msg = str(e)
                self.error_occurred.emit(self.download_item.id, error_msg)
                
                # Retry logic
                if self.download_item.retry_count < self.download_item.max_retries:
                    self.download_item.retry_count += 1
                    time.sleep(2)  # Wait before retry
                    self.run()  # Retry
    
    def build_ydl_options(self) -> Dict:
        """Build yt-dlp options based on download item"""
        # Generate safe filename
        safe_title = "".join(c for c in self.download_item.title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not safe_title:
            safe_title = f"download_{self.download_item.id[:8]}"
        
        filename = f"{safe_title}.%(ext)s"
        
        ydl_opts = {
            'outtmpl': os.path.join(self.download_item.output_path, filename),
            'progress_hooks': [self.progress_hook],
            'noplaylist': True,
            'writethumbnail': False,  # Disable by default to avoid issues
            'writeinfojson': False,   # Disable by default to avoid issues
            'socket_timeout': 60,
        }
        
        # Format-specific options
        if self.download_item.format_type == "video":
            if self.download_item.quality == "best":
                ydl_opts['format'] = 'best[ext=mp4]/best'
            else:
                # Extract resolution from quality string (e.g., "720p" -> 720)
                resolution = ''.join(filter(str.isdigit, self.download_item.quality))
                if resolution:
                    ydl_opts['format'] = f'best[height<={resolution}][ext=mp4]/best[height<={resolution}]/best'
                else:
                    ydl_opts['format'] = 'best[ext=mp4]/best'
        
        elif self.download_item.format_type == "audio":
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': self.download_item.codec if self.download_item.codec != 'mp4' else 'mp3',
                'preferredquality': str(self.download_item.bitrate),
            }]
        
        # Load advanced settings
        settings = QSettings("SocialMediaDownloader", "Advanced")
        
        # Proxy settings
        if settings.value("use_proxy", False, type=bool):
            proxy_url = settings.value("proxy_url", "")
            if proxy_url:
                ydl_opts['proxy'] = proxy_url
        
        # Connection settings
        timeout = settings.value("timeout", 60, type=int)
        ydl_opts['socket_timeout'] = timeout
        
        return ydl_opts
    
    def progress_hook(self, d):
        """Handle download progress updates"""
        if self.download_cancelled:
            raise yt_dlp.DownloadError("Download cancelled")
            
        if not self.pause_event.is_set():
            # Paused state - wait
            self.pause_event.wait()
            return
        
        if d['status'] == 'downloading':
            # Extract progress information
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            
            if total > 0:
                progress = int((downloaded / total) * 100)
            else:
                progress = 0
            
            # Speed and ETA
            speed = d.get('speed', 0) or 0
            eta = d.get('eta', 0) or 0
            
            self.progress_updated.emit(
                self.download_item.id, progress, speed, eta
            )
            
        elif d['status'] == 'finished':
            self.download_item.filename = d['filename']
            self.progress_updated.emit(self.download_item.id, 100, 0, 0)
    
    def add_metadata(self):
        """Add metadata to downloaded audio file"""
        if not self.download_item.filename or not os.path.exists(self.download_item.filename):
            return
        
        try:
            # Detect file type and add metadata
            if self.download_item.filename.lower().endswith('.mp3'):
                try:
                    audio_file = MP3(self.download_item.filename, ID3=ID3)
                    
                    # Add ID3 tags if they don't exist
                    if audio_file.tags is None:
                        audio_file.add_tags()
                    
                    audio_file.tags['TIT2'] = TIT2(encoding=3, text=self.download_item.title)
                    audio_file.save()
                except Exception as e:
                    print(f"Failed to add MP3 metadata: {e}")
                    
            elif self.download_item.filename.lower().endswith('.mp4'):
                try:
                    audio_file = MP4(self.download_item.filename)
                    audio_file['\xa9nam'] = self.download_item.title  # Title
                    audio_file.save()
                except Exception as e:
                    print(f"Failed to add MP4 metadata: {e}")
                    
        except Exception as e:
            print(f"Failed to add metadata: {e}")
    
    def pause(self):
        """Pause the download"""
        self.is_paused = True
        self.pause_event.clear()
        self.status_changed.emit(self.download_item.id, "paused")
    
    def resume(self):
        """Resume the download"""
        self.is_paused = False
        self.pause_event.set()
        self.status_changed.emit(self.download_item.id, "downloading")
    
    def cancel(self):
        """Cancel the download"""
        self.is_cancelled = True
        self.download_cancelled = True
        self.pause_event.set()  # Unblock if paused
        self.status_changed.emit(self.download_item.id, "cancelled")


class DownloadManager(QObject):
    """Manages multiple downloads with queue, history, and database storage"""
    download_added = pyqtSignal(DownloadItem)
    download_updated = pyqtSignal(DownloadItem)
    download_completed = pyqtSignal(DownloadItem)
    download_failed = pyqtSignal(DownloadItem)
    
    def __init__(self, db_path: str = None):
        super().__init__()
        
        # Database setup
        if db_path is None:
            db_dir = Path.home() / ".social_downloader"
            db_dir.mkdir(exist_ok=True)
            db_path = db_dir / "downloads.db"
        
        self.db_path = str(db_path)
        self.init_database()
        
        # Download management
        self.active_downloads: Dict[str, AdvancedDownloadWorker] = {}
        self.download_queue: List[DownloadItem] = []
        self.download_history: List[DownloadItem] = []
        self.max_concurrent = 3
        
        # Load settings
        self.load_settings()
        
        # Queue processor timer
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.process_queue)
        self.queue_timer.start(1000)  # Check every second
    
    def init_database(self):
        """Initialize the SQLite database"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = self.conn.cursor()
            
            # Create downloads table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS downloads (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    title TEXT,
                    thumbnail_url TEXT,
                    duration INTEGER,
                    file_size INTEGER,
                    format_type TEXT,
                    quality TEXT,
                    codec TEXT,
                    bitrate INTEGER,
                    output_path TEXT,
                    filename TEXT,
                    status TEXT,
                    progress INTEGER,
                    speed REAL,
                    eta INTEGER,
                    created_at TEXT,
                    completed_at TEXT,
                    error_message TEXT,
                    retry_count INTEGER,
                    max_retries INTEGER
                )
            ''')
            
            # Create settings table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            self.conn.commit()
        except Exception as e:
            print(f"Database initialization error: {e}")
            # Fallback to in-memory database
            self.conn = sqlite3.connect(":memory:")
            self.init_database()
    
    def load_settings(self):
        """Load download manager settings"""
        settings = QSettings("SocialMediaDownloader", "DownloadManager")
        self.max_concurrent = settings.value("max_concurrent", 3, type=int)
        
        # Load pending downloads from database
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM downloads WHERE status IN (?, ?, ?)
            ''', (DownloadStatus.PENDING.value, DownloadStatus.DOWNLOADING.value, DownloadStatus.PAUSED.value))
            
            for row in cursor.fetchall():
                download_item = self.row_to_download_item(row)
                if download_item.status == DownloadStatus.DOWNLOADING:
                    download_item.status = DownloadStatus.PENDING  # Reset to pending
                self.download_queue.append(download_item)
        except Exception as e:
            print(f"Error loading settings: {e}")
    
    def row_to_download_item(self, row) -> DownloadItem:
        """Convert database row to DownloadItem"""
        try:
            return DownloadItem(
                id=row[0], url=row[1], title=row[2] or "", thumbnail_url=row[3] or "",
                duration=row[4] or 0, file_size=row[5] or 0, format_type=row[6] or "video",
                quality=row[7] or "best", codec=row[8] or "mp4", bitrate=row[9] or 320,
                output_path=row[10] or "", filename=row[11] or "",
                status=DownloadStatus(row[12]), progress=row[13] or 0,
                speed=row[14] or 0.0, eta=row[15] or 0, created_at=row[16] or "",
                completed_at=row[17] or "", error_message=row[18] or "",
                retry_count=row[19] or 0, max_retries=row[20] or 3
            )
        except (ValueError, IndexError) as e:
            print(f"Error converting row to DownloadItem: {e}")
            # Return a basic item with minimal data
            return DownloadItem(
                id=row[0] if row else "unknown",
                url=row[1] if len(row) > 1 else "",
                status=DownloadStatus.FAILED
            )
    
    def save_download_item(self, item: DownloadItem):
        """Save download item to database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO downloads VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            ''', (
                item.id, item.url, item.title, item.thumbnail_url,
                item.duration, item.file_size, item.format_type,
                item.quality, item.codec, item.bitrate,
                item.output_path, item.filename, item.status.value,
                item.progress, item.speed, item.eta,
                item.created_at, item.completed_at, item.error_message,
                item.retry_count, item.max_retries
            ))
            self.conn.commit()
        except Exception as e:
            print(f"Error saving download item: {e}")
    
    def add_download(self, url: str, format_type: str = "video", 
                    quality: str = "best", output_path: str = "") -> str:
        """Add a new download to the queue"""
        # Generate unique ID
        download_id = hashlib.md5(f"{url}{time.time()}".encode()).hexdigest()[:12]
        
        # Create download item
        download_item = DownloadItem(
            id=download_id,
            url=url,
            format_type=format_type,
            quality=quality,
            output_path=output_path or str(Path.home() / "Downloads"),
            created_at=datetime.now().isoformat(),
            status=DownloadStatus.PENDING
        )
        
        # Add to queue and database
        self.download_queue.append(download_item)
        self.save_download_item(download_item)
        self.download_added.emit(download_item)
        
        return download_id
    
    def process_queue(self):
        """Process the download queue"""
        # Check if we can start new downloads
        active_count = len(self.active_downloads)
        if active_count >= self.max_concurrent:
            return
        
        # Find pending downloads
        pending_downloads = [
            item for item in self.download_queue 
            if item.status == DownloadStatus.PENDING
        ]
        
        # Start new downloads
        for item in pending_downloads[:self.max_concurrent - active_count]:
            self.start_download(item)
    
    def start_download(self, item: DownloadItem):
        """Start downloading a specific item"""
        if item.id in self.active_downloads:
            return
        
        try:
            # Create and configure worker
            worker = AdvancedDownloadWorker(item)
            worker.progress_updated.connect(self.on_progress_updated)
            worker.status_changed.connect(self.on_status_changed)
            worker.download_completed.connect(self.on_download_completed)
            worker.error_occurred.connect(self.on_download_error)
            
            # Start worker
            self.active_downloads[item.id] = worker
            item.status = DownloadStatus.DOWNLOADING
            self.save_download_item(item)
            worker.start()
        except Exception as e:
            print(f"Error starting download: {e}")
            item.status = DownloadStatus.FAILED
            item.error_message = str(e)
            self.save_download_item(item)
            self.download_failed.emit(item)
    
    def pause_download(self, download_id: str):
        """Pause a specific download"""
        if download_id in self.active_downloads:
            try:
                worker = self.active_downloads[download_id]
                worker.pause()
                
                # Update database
                item = self.get_download_item(download_id)
                if item:
                    item.status = DownloadStatus.PAUSED
                    self.save_download_item(item)
            except Exception as e:
                print(f"Error pausing download: {e}")
    
    def resume_download(self, download_id: str):
        """Resume a paused download"""
        if download_id in self.active_downloads:
            try:
                worker = self.active_downloads[download_id]
                worker.resume()
                
                # Update database
                item = self.get_download_item(download_id)
                if item:
                    item.status = DownloadStatus.DOWNLOADING
                    self.save_download_item(item)
            except Exception as e:
                print(f"Error resuming download: {e}")
    
    def cancel_download(self, download_id: str):
        """Cancel a specific download"""
        try:
            if download_id in self.active_downloads:
                worker = self.active_downloads[download_id]
                worker.cancel()
                worker.quit()
                worker.wait(5000)  # Wait max 5 seconds
                if worker.isRunning():
                    worker.terminate()  # Force terminate if needed
                del self.active_downloads[download_id]
            
            # Update database
            item = self.get_download_item(download_id)
            if item:
                item.status = DownloadStatus.CANCELLED
                self.save_download_item(item)
                
                # Remove from queue if pending
                self.download_queue = [i for i in self.download_queue if i.id != download_id]
        except Exception as e:
            print(f"Error cancelling download: {e}")
    
    def retry_download(self, download_id: str):
        """Retry a failed download"""
        try:
            item = self.get_download_item(download_id)
            if item and item.status == DownloadStatus.FAILED:
                item.status = DownloadStatus.PENDING
                item.retry_count = 0
                item.error_message = ""
                self.download_queue.append(item)
                self.save_download_item(item)
        except Exception as e:
            print(f"Error retrying download: {e}")
    
    def get_download_item(self, download_id: str) -> Optional[DownloadItem]:
        """Get download item by ID"""
        # Check queue first
        for item in self.download_queue:
            if item.id == download_id:
                return item
        
        # Check database
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM downloads WHERE id = ?', (download_id,))
            row = cursor.fetchone()
            if row:
                return self.row_to_download_item(row)
        except Exception as e:
            print(f"Error getting download item: {e}")
        
        return None
    
    def get_download_history(self, limit: int = 100) -> List[DownloadItem]:
        """Get download history"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM downloads 
                WHERE status IN (?, ?, ?) 
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (DownloadStatus.COMPLETED.value, DownloadStatus.FAILED.value, 
                  DownloadStatus.CANCELLED.value, limit))
            
            return [self.row_to_download_item(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error getting download history: {e}")
            return []
    
    def get_active_downloads(self) -> List[DownloadItem]:
        """Get currently active downloads"""
        return [
            item for item in self.download_queue 
            if item.status in [DownloadStatus.DOWNLOADING, DownloadStatus.PAUSED]
        ]
    
    def clear_completed_downloads(self):
        """Clear completed downloads from queue"""
        self.download_queue = [
            item for item in self.download_queue 
            if item.status not in [DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED]
        ]
    
    def get_download_stats(self) -> Dict:
        """Get download statistics"""
        try:
            cursor = self.conn.cursor()
            
            # Total downloads
            cursor.execute('SELECT COUNT(*) FROM downloads')
            total_downloads = cursor.fetchone()[0]
            
            # Completed downloads
            cursor.execute('SELECT COUNT(*) FROM downloads WHERE status = ?', 
                          (DownloadStatus.COMPLETED.value,))
            completed_downloads = cursor.fetchone()[0]
            
            # Failed downloads
            cursor.execute('SELECT COUNT(*) FROM downloads WHERE status = ?', 
                          (DownloadStatus.FAILED.value,))
            failed_downloads = cursor.fetchone()[0]
            
            # Total file size
            cursor.execute('SELECT SUM(file_size) FROM downloads WHERE status = ?', 
                          (DownloadStatus.COMPLETED.value,))
            total_size = cursor.fetchone()[0] or 0
            
            return {
                'total_downloads': total_downloads,
                'completed_downloads': completed_downloads,
                'failed_downloads': failed_downloads,
                'success_rate': (completed_downloads / total_downloads * 100) if total_downloads > 0 else 0,
                'total_size_mb': total_size / (1024 * 1024),
                'active_downloads': len(self.active_downloads),
                'queued_downloads': len([i for i in self.download_queue if i.status == DownloadStatus.PENDING])
            }
        except Exception as e:
            print(f"Error getting download stats: {e}")
            return {
                'total_downloads': 0,
                'completed_downloads': 0,
                'failed_downloads': 0,
                'success_rate': 0,
                'total_size_mb': 0,
                'active_downloads': len(self.active_downloads),
                'queued_downloads': len([i for i in self.download_queue if i.status == DownloadStatus.PENDING])
            }
    
    def on_progress_updated(self, download_id: str, progress: int, speed: float, eta: int):
        """Handle progress updates from workers"""
        try:
            item = self.get_download_item(download_id)
            if item:
                item.progress = progress
                item.speed = speed
                item.eta = eta
                self.save_download_item(item)
                self.download_updated.emit(item)
        except Exception as e:
            print(f"Error updating progress: {e}")
    
    def on_status_changed(self, download_id: str, status: str):
        """Handle status changes from workers"""
        try:
            item = self.get_download_item(download_id)
            if item:
                try:
                    item.status = DownloadStatus(status)
                    self.save_download_item(item)
                    self.download_updated.emit(item)
                except ValueError:
                    pass  # Invalid status
        except Exception as e:
            print(f"Error changing status: {e}")
    
    def on_download_completed(self, download_id: str, file_path: str):
        """Handle download completion"""
        try:
            item = self.get_download_item(download_id)
            if item:
                item.status = DownloadStatus.COMPLETED
                item.filename = file_path
                item.completed_at = datetime.now().isoformat()
                item.progress = 100
                
                # Get file size
                if file_path and os.path.exists(file_path):
                    item.file_size = os.path.getsize(file_path)
                
                self.save_download_item(item)
                self.download_completed.emit(item)
                
                # Remove from active downloads
                if download_id in self.active_downloads:
                    del self.active_downloads[download_id]
                
                # Remove from queue
                self.download_queue = [i for i in self.download_queue if i.id != download_id]
        except Exception as e:
            print(f"Error handling download completion: {e}")
    
    def on_download_error(self, download_id: str, error_message: str):
        """Handle download errors"""
        try:
            item = self.get_download_item(download_id)
            if item:
                item.status = DownloadStatus.FAILED
                item.error_message = error_message
                self.save_download_item(item)
                self.download_failed.emit(item)
                
                # Remove from active downloads
                if download_id in self.active_downloads:
                    del self.active_downloads[download_id]
        except Exception as e:
            print(f"Error handling download error: {e}")
    
    def export_history(self, file_path: str, format_type: str = "json"):
        """Export download history to file"""
        try:
            history = self.get_download_history(limit=1000)
            
            if format_type.lower() == "json":
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump([asdict(item) for item in history], f, indent=2, default=str)
            
            elif format_type.lower() == "csv":
                import csv
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    # Header
                    writer.writerow(['ID', 'URL', 'Title', 'Status', 'Created', 'Completed', 'File Size'])
                    # Data
                    for item in history:
                        writer.writerow([
                            item.id, item.url, item.title, item.status.value,
                            item.created_at, item.completed_at, item.file_size
                        ])
        except Exception as e:
            print(f"Error exporting history: {e}")
    
    def import_history(self, file_path: str):
        """Import download history from file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for item_data in data:
                # Convert status string back to enum
                if isinstance(item_data.get('status'), str):
                    item_data['status'] = DownloadStatus(item_data['status'])
                item = DownloadItem(**item_data)
                self.save_download_item(item)
            
            return True
        except Exception as e:
            print(f"Failed to import history: {e}")
            return False
    
    def cleanup_old_downloads(self, days: int = 30):
        """Clean up old download records"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cursor = self.conn.cursor()
            cursor.execute('''
                DELETE FROM downloads 
                WHERE status IN (?, ?, ?) AND created_at < ?
            ''', (DownloadStatus.COMPLETED.value, DownloadStatus.FAILED.value, 
                  DownloadStatus.CANCELLED.value, cutoff_date.isoformat()))
            self.conn.commit()
        except Exception as e:
            print(f"Error cleaning up old downloads: {e}")
    
    def close(self):
        """Close the download manager and cleanup"""
        try:
            # Cancel all active downloads
            for download_id, worker in list(self.active_downloads.items()):
                worker.cancel()
                worker.quit()
                worker.wait(3000)  # Wait max 3 seconds
                if worker.isRunning():
                    worker.terminate()
            
            self.active_downloads.clear()
            
            if hasattr(self, 'conn'):
                self.conn.close()
        except Exception as e:
            print(f"Error closing download manager: {e}")


class PlaylistDownloadManager:
    """Specialized manager for playlist downloads"""
    
    def __init__(self, download_manager: DownloadManager):
        self.download_manager = download_manager
        self.playlist_cache = {}
    
    def extract_playlist_info(self, url: str) -> Dict:
        """Extract playlist information"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # Only get basic info
                'skip_download': True,
                'socket_timeout': 30,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if 'entries' in info and info['entries']:
                    playlist_info = {
                        'title': info.get('title', 'Unknown Playlist'),
                        'uploader': info.get('uploader', 'Unknown'),
                        'entry_count': len([e for e in info['entries'] if e]),
                        'entries': []
                    }
                    
                    for entry in info['entries']:
                        if entry:
                            playlist_info['entries'].append({
                                'title': entry.get('title', 'Unknown'),
                                'url': entry.get('url', ''),
                                'duration': entry.get('duration', 0),
                                'id': entry.get('id', '')
                            })
                    
                    self.playlist_cache[url] = playlist_info
                    return playlist_info
        
        except Exception as e:
            print(f"Failed to extract playlist info: {e}")
        
        return {}
    
    def download_playlist(self, url: str, format_type: str = "video", 
                         quality: str = "best", output_path: str = "",
                         start_index: int = 1, end_index: int = None) -> List[str]:
        """Download entire playlist or specific range"""
        playlist_info = self.extract_playlist_info(url)
        if not playlist_info or not playlist_info.get('entries'):
            return []
        
        # Create playlist folder
        playlist_title = playlist_info['title']
        safe_title = "".join(c for c in playlist_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not safe_title:
            safe_title = "playlist"
        playlist_folder = os.path.join(output_path, safe_title)
        
        try:
            os.makedirs(playlist_folder, exist_ok=True)
        except Exception as e:
            print(f"Error creating playlist folder: {e}")
            playlist_folder = output_path
        
        # Download entries
        download_ids = []
        entries = playlist_info['entries']
        
        # Apply range selection
        if end_index is None:
            end_index = len(entries)
        
        # Ensure valid range
        start_index = max(1, start_index)
        end_index = min(len(entries), end_index)
        
        selected_entries = entries[start_index-1:end_index]
        
        for i, entry in enumerate(selected_entries, start_index):
            if entry.get('url'):
                try:
                    download_id = self.download_manager.add_download(
                        url=entry['url'],
                        format_type=format_type,
                        quality=quality,
                        output_path=playlist_folder
                    )
                    download_ids.append(download_id)
                except Exception as e:
                    print(f"Error adding playlist item to download: {e}")
        
        return download_ids