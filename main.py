#!/usr/bin/env python3
"""
Social Media Downloader Desktop Application
A modern, feature-rich desktop application for downloading social media content.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import customtkinter as ctk
import threading
import json
import os
import sys
import subprocess
import urllib.parse
import re
from pathlib import Path
import time
from datetime import datetime
import queue
from PIL import Image, ImageTk
import requests
from io import BytesIO

# Set appearance mode and color theme
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

class Config:
    """Application configuration manager"""
    def __init__(self):
        self.config_dir = Path.home() / ".social_downloader"
        self.config_file = self.config_dir / "config.json"
        self.config_dir.mkdir(exist_ok=True)
        
        self.default_config = {
            "theme": "system",
            "download_path": str(Path.home() / "Downloads" / "SocialDownloader"),
            "default_video_quality": "720p",
            "default_audio_quality": "192kbps",
            "max_concurrent": 3,
            "naming_pattern": "{title}",
            "create_subfolders": True,
            "platforms": {
                "youtube": True,
                "instagram": True,
                "tiktok": True,
                "twitter": True,
                "facebook": True
            }
        }
        
        self.config = self.load_config()
    
    def load_config(self):
        """Load configuration from file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                # Merge with defaults for any missing keys
                for key, value in self.default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            else:
                return self.default_config.copy()
        except Exception as e:
            print(f"Error loading config: {e}")
            return self.default_config.copy()
    
    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

class DownloadItem:
    """Represents a download item"""
    def __init__(self, url, title="", platform="", thumbnail_url="", duration="", quality="720p", format_type="mp4"):
        self.url = url
        self.title = title
        self.platform = platform
        self.thumbnail_url = thumbnail_url
        self.duration = duration
        self.quality = quality
        self.format_type = format_type
        self.status = "pending"  # pending, downloading, completed, error
        self.progress = 0
        self.file_path = ""
        self.error_message = ""

class YouTubeDLWrapper:
    """Wrapper for yt-dlp functionality"""
    def __init__(self):
        self.is_available = self.check_ytdlp()
    
    def check_ytdlp(self):
        """Check if yt-dlp is available"""
        try:
            result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False
    
    def get_video_info(self, url):
        """Extract video information"""
        if not self.is_available:
            raise Exception("yt-dlp not found. Please install yt-dlp.")
        
        try:
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-download',
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                raise Exception(f"Failed to get video info: {result.stderr}")
            
            info = json.loads(result.stdout)
            
            # Extract relevant information
            return {
                'title': info.get('title', 'Unknown Title'),
                'platform': info.get('extractor_key', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
                'duration': self.format_duration(info.get('duration', 0)),
                'formats': self.extract_formats(info.get('formats', []))
            }
        
        except subprocess.TimeoutExpired:
            raise Exception("Request timed out")
        except json.JSONDecodeError:
            raise Exception("Invalid response from yt-dlp")
        except Exception as e:
            raise Exception(f"Error getting video info: {str(e)}")
    
    def format_duration(self, duration):
        """Format duration in seconds to MM:SS or HH:MM:SS"""
        if not duration:
            return "N/A"
        
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def extract_formats(self, formats):
        """Extract available video formats"""
        video_formats = []
        audio_formats = []
        
        for fmt in formats:
            if fmt.get('vcodec') != 'none' and fmt.get('height'):
                quality = f"{fmt['height']}p"
                if quality not in [f['quality'] for f in video_formats]:
                    video_formats.append({
                        'quality': quality,
                        'format_id': fmt['format_id']
                    })
            
            if fmt.get('acodec') != 'none' and not fmt.get('height'):
                bitrate = fmt.get('abr', 'Unknown')
                audio_formats.append({
                    'quality': f"{bitrate}kbps" if bitrate != 'Unknown' else 'Unknown',
                    'format_id': fmt['format_id']
                })
        
        # Sort by quality
        video_formats.sort(key=lambda x: int(x['quality'][:-1]), reverse=True)
        
        return {
            'video': video_formats,
            'audio': audio_formats
        }

class ThumbnailCache:
    """Cache for thumbnail images"""
    def __init__(self):
        self.cache = {}
        self.cache_dir = Path.home() / ".social_downloader" / "thumbnails"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def get_thumbnail(self, url, size=(120, 90)):
        """Get thumbnail image, cached"""
        if url in self.cache:
            return self.cache[url]
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            image = Image.open(BytesIO(response.content))
            image.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage for tkinter
            photo = ImageTk.PhotoImage(image)
            self.cache[url] = photo
            
            return photo
        
        except Exception as e:
            print(f"Error loading thumbnail: {e}")
            return None

class SocialMediaDownloader:
    """Main application class"""
    
    def __init__(self):
        self.config = Config()
        self.ytdl = YouTubeDLWrapper()
        self.thumbnail_cache = ThumbnailCache()
        self.download_queue = queue.Queue()
        self.active_downloads = {}
        self.download_items = []
        
        # Create main window
        self.root = ctk.CTk()
        self.root.title("Social Media Downloader")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Set theme
        ctk.set_appearance_mode(self.config.config["theme"])
        
        self.setup_ui()
        self.setup_styles()
        
        # Start download worker thread
        self.worker_thread = threading.Thread(target=self.download_worker, daemon=True)
        self.worker_thread.start()
        
        # Bind paste event
        self.root.bind('<Control-v>', self.paste_url)
    
    def setup_styles(self):
        """Setup custom styles for modern UI"""
        # Configure colors for glassmorphism effect
        self.colors = {
            'bg_primary': ("#f0f0f0", "#1a1a1a"),
            'bg_secondary': ("#ffffff", "#2b2b2b"),
            'bg_accent': ("#e8e8e8", "#3d3d3d"),
            'text_primary': ("#000000", "#ffffff"),
            'text_secondary': ("#666666", "#cccccc"),
            'accent': ("#007acc", "#4da6ff"),
            'success': ("#28a745", "#20c997"),
            'warning': ("#ffc107", "#ffc107"),
            'error': ("#dc3545", "#e74c3c")
        }
    
    def setup_ui(self):
        """Setup the user interface"""
        # Configure grid weights
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)
        
        # Header frame
        self.create_header()
        
        # URL input frame
        self.create_url_input()
        
        # Main content area
        self.create_main_content()
        
        # Action buttons
        self.create_action_buttons()
        
        # Status bar
        self.create_status_bar()
    
    def create_header(self):
        """Create application header"""
        header_frame = ctk.CTkFrame(self.root, height=60, corner_radius=0)
        header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        header_frame.grid_columnconfigure(1, weight=1)
        
        # App title
        title_label = ctk.CTkLabel(
            header_frame,
            text="🎬 Social Media Downloader",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=15, sticky="w")
        
        # Header buttons
        button_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        button_frame.grid(row=0, column=2, padx=20, pady=10, sticky="e")
        
        # Theme toggle button
        self.theme_button = ctk.CTkButton(
            button_frame,
            text="🌓",
            width=40,
            height=32,
            font=ctk.CTkFont(size=16),
            command=self.toggle_theme
        )
        self.theme_button.grid(row=0, column=0, padx=(0, 10))
        
        # Settings button
        settings_button = ctk.CTkButton(
            button_frame,
            text="⚙️",
            width=40,
            height=32,
            font=ctk.CTkFont(size=16),
            command=self.open_settings
        )
        settings_button.grid(row=0, column=1)
    
    def create_url_input(self):
        """Create URL input section"""
        url_frame = ctk.CTkFrame(self.root)
        url_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 0))
        url_frame.grid_columnconfigure(0, weight=1)
        
        # URL input
        url_input_frame = ctk.CTkFrame(url_frame, fg_color="transparent")
        url_input_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=15)
        url_input_frame.grid_columnconfigure(0, weight=1)
        
        url_label = ctk.CTkLabel(url_input_frame, text="URL:", font=ctk.CTkFont(size=14, weight="bold"))
        url_label.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        input_frame = ctk.CTkFrame(url_input_frame, fg_color="transparent")
        input_frame.grid(row=1, column=0, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)
        
        self.url_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Paste your social media URL here...",
            height=40,
            font=ctk.CTkFont(size=12)
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.url_entry.bind('<Return>', lambda e: self.analyze_url())
        
        # Paste button
        paste_button = ctk.CTkButton(
            input_frame,
            text="📋 Paste",
            width=80,
            height=40,
            command=self.paste_url
        )
        paste_button.grid(row=0, column=1, padx=(0, 10))
        
        # Analyze button
        self.analyze_button = ctk.CTkButton(
            input_frame,
            text="🔍 Analyze",
            width=100,
            height=40,
            command=self.analyze_url
        )
        self.analyze_button.grid(row=0, column=2)
    
    def create_main_content(self):
        """Create main content area"""
        # Create notebook for tabs
        self.notebook = ctk.CTkTabview(self.root)
        self.notebook.grid(row=2, column=0, sticky="nsew", padx=20, pady=10)
        
        # Preview tab
        self.preview_tab = self.notebook.add("Preview & Download")
        self.create_preview_section()
        
        # Queue tab
        self.queue_tab = self.notebook.add("Download Queue")
        self.create_queue_section()
        
        # History tab
        self.history_tab = self.notebook.add("History")
        self.create_history_section()
    
    def create_preview_section(self):
        """Create content preview section"""
        self.preview_tab.grid_columnconfigure(0, weight=1)
        
        # Preview frame (initially hidden)
        self.preview_frame = ctk.CTkFrame(self.preview_tab)
        
        # No content message
        self.no_content_frame = ctk.CTkFrame(self.preview_tab)
        self.no_content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.no_content_frame.grid_columnconfigure(0, weight=1)
        self.no_content_frame.grid_rowconfigure(0, weight=1)
        
        no_content_label = ctk.CTkLabel(
            self.no_content_frame,
            text="🔗 Paste a URL above to get started",
            font=ctk.CTkFont(size=16),
            text_color=("gray50", "gray50")
        )
        no_content_label.grid(row=0, column=0)
    
    def create_queue_section(self):
        """Create download queue section"""
        self.queue_tab.grid_columnconfigure(0, weight=1)
        self.queue_tab.grid_rowconfigure(0, weight=1)
        
        # Scrollable frame for queue items
        self.queue_scroll = ctk.CTkScrollableFrame(self.queue_tab)
        self.queue_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.queue_scroll.grid_columnconfigure(0, weight=1)
        
        # Empty queue message
        self.empty_queue_label = ctk.CTkLabel(
            self.queue_scroll,
            text="📥 No downloads in queue",
            font=ctk.CTkFont(size=14),
            text_color=("gray50", "gray50")
        )
        self.empty_queue_label.grid(row=0, column=0, pady=20)
    
    def create_history_section(self):
        """Create download history section"""
        self.history_tab.grid_columnconfigure(0, weight=1)
        self.history_tab.grid_rowconfigure(0, weight=1)
        
        # Scrollable frame for history items
        self.history_scroll = ctk.CTkScrollableFrame(self.history_tab)
        self.history_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.history_scroll.grid_columnconfigure(0, weight=1)
        
        # Empty history message
        self.empty_history_label = ctk.CTkLabel(
            self.history_scroll,
            text="📋 No download history",
            font=ctk.CTkFont(size=14),
            text_color=("gray50", "gray50")
        )
        self.empty_history_label.grid(row=0, column=0, pady=20)
    
    def create_action_buttons(self):
        """Create action buttons"""
        button_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        button_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))
        button_frame.grid_columnconfigure(2, weight=1)
        
        # Add to queue button
        self.add_queue_button = ctk.CTkButton(
            button_frame,
            text="➕ Add to Queue",
            width=120,
            height=36,
            command=self.add_to_queue,
            state="disabled"
        )
        self.add_queue_button.grid(row=0, column=0, padx=(0, 10))
        
        # Download all button
        self.download_all_button = ctk.CTkButton(
            button_frame,
            text="⬇️ Download All",
            width=120,
            height=36,
            command=self.start_downloads,
            state="disabled"
        )
        self.download_all_button.grid(row=0, column=1, padx=(0, 10))
        
        # Open folder button
        open_folder_button = ctk.CTkButton(
            button_frame,
            text="📁 Open Folder",
            width=120,
            height=36,
            command=self.open_download_folder
        )
        open_folder_button.grid(row=0, column=3)
    
    def create_status_bar(self):
        """Create status bar"""
        self.status_frame = ctk.CTkFrame(self.root, height=30, corner_radius=0)
        self.status_frame.grid(row=4, column=0, sticky="ew")
        self.status_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Ready",
            font=ctk.CTkFont(size=11)
        )
        self.status_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
    
    def paste_url(self, event=None):
        """Paste URL from clipboard"""
        try:
            clipboard_text = self.root.clipboard_get()
            if clipboard_text and self.is_valid_url(clipboard_text):
                self.url_entry.delete(0, 'end')
                self.url_entry.insert(0, clipboard_text)
                # Auto-analyze if it looks like a supported URL
                self.analyze_url()
            else:
                self.set_status("No valid URL found in clipboard")
        except Exception as e:
            self.set_status("Could not access clipboard")
    
    def is_valid_url(self, url):
        """Check if URL is valid"""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def analyze_url(self):
        """Analyze the URL and show preview"""
        url = self.url_entry.get().strip()
        if not url:
            return
        
        if not self.is_valid_url(url):
            messagebox.showerror("Invalid URL", "Please enter a valid URL")
            return
        
        self.set_status("Analyzing URL...")
        self.analyze_button.configure(state="disabled", text="⏳ Analyzing...")
        
        # Run analysis in background thread
        thread = threading.Thread(target=self._analyze_url_thread, args=(url,))
        thread.daemon = True
        thread.start()
    
    def _analyze_url_thread(self, url):
        """Background thread for URL analysis"""
        try:
            info = self.ytdl.get_video_info(url)
            
            # Update UI in main thread
            self.root.after(0, self._show_preview, url, info)
            
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, self._show_error, f"Error analyzing URL: {error_msg}")
    
    def _show_preview(self, url, info):
        """Show content preview"""
        self.analyze_button.configure(state="normal", text="🔍 Analyze")
        
        # Hide no content message
        self.no_content_frame.grid_remove()
        
        # Create preview content
        self.preview_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.preview_frame.grid_columnconfigure(1, weight=1)
        
        # Clear previous content
        for widget in self.preview_frame.winfo_children():
            widget.destroy()
        
        # Thumbnail
        thumbnail_frame = ctk.CTkFrame(self.preview_frame, width=140, height=105)
        thumbnail_frame.grid(row=0, column=0, rowspan=4, padx=20, pady=20, sticky="nw")
        thumbnail_frame.grid_propagate(False)
        
        # Try to load thumbnail
        if info.get('thumbnail'):
            thumbnail = self.thumbnail_cache.get_thumbnail(info['thumbnail'])
            if thumbnail:
                thumbnail_label = ctk.CTkLabel(thumbnail_frame, image=thumbnail, text="")
                thumbnail_label.grid(row=0, column=0, padx=10, pady=10)
            else:
                placeholder_label = ctk.CTkLabel(thumbnail_frame, text="🖼️\nThumbnail", font=ctk.CTkFont(size=12))
                placeholder_label.grid(row=0, column=0, padx=10, pady=10)
        else:
            placeholder_label = ctk.CTkLabel(thumbnail_frame, text="🖼️\nNo Preview", font=ctk.CTkFont(size=12))
            placeholder_label.grid(row=0, column=0, padx=10, pady=10)
        
        # Content info
        info_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="ew", padx=20, pady=20)
        info_frame.grid_columnconfigure(1, weight=1)
        
        # Title
        ctk.CTkLabel(info_frame, text="Title:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=2)
        title_label = ctk.CTkLabel(info_frame, text=info['title'][:60] + "..." if len(info['title']) > 60 else info['title'])
        title_label.grid(row=0, column=1, sticky="w", padx=(10, 0), pady=2)
        
        # Platform
        ctk.CTkLabel(info_frame, text="Platform:", font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, sticky="w", pady=2)
        ctk.CTkLabel(info_frame, text=info['platform']).grid(row=1, column=1, sticky="w", padx=(10, 0), pady=2)
        
        # Duration
        if info['duration'] != "N/A":
            ctk.CTkLabel(info_frame, text="Duration:", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, sticky="w", pady=2)
            ctk.CTkLabel(info_frame, text=info['duration']).grid(row=2, column=1, sticky="w", padx=(10, 0), pady=2)
        
        # Quality and format selection
        options_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        options_frame.grid(row=1, column=1, sticky="ew", padx=20, pady=(0, 20))
        options_frame.grid_columnconfigure((0, 2), weight=1)
        
        # Format selection
        ctk.CTkLabel(options_frame, text="Format:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.format_var = ctk.StringVar(value="mp4")
        format_menu = ctk.CTkOptionMenu(
            options_frame,
            variable=self.format_var,
            values=["mp4", "mp3"],
            command=self.on_format_change
        )
        format_menu.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        
        # Quality selection
        ctk.CTkLabel(options_frame, text="Quality:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=2, sticky="w", pady=5)
        self.quality_var = ctk.StringVar(value="720p")
        
        # Populate quality options based on available formats
        video_qualities = [f['quality'] for f in info['formats']['video']] if info['formats']['video'] else ["720p", "480p", "360p"]
        if not video_qualities:
            video_qualities = ["720p", "480p", "360p"]
        
        self.quality_menu = ctk.CTkOptionMenu(
            options_frame,
            variable=self.quality_var,
            values=video_qualities
        )
        self.quality_menu.grid(row=0, column=3, padx=10, pady=5, sticky="ew")
        
        # Store current info for download
        self.current_info = {
            'url': url,
            'title': info['title'],
            'platform': info['platform'],
            'thumbnail': info.get('thumbnail', ''),
            'duration': info['duration'],
            'formats': info['formats']
        }
        
        self.add_queue_button.configure(state="normal")
        self.set_status(f"Ready to download: {info['title']}")
    
    def on_format_change(self, format_type):
        """Handle format change"""
        if not hasattr(self, 'current_info'):
            return
        
        if format_type == "mp3":
            # Switch to audio qualities
            audio_qualities = ["320kbps", "256kbps", "192kbps", "128kbps"]
            self.quality_menu.configure(values=audio_qualities)
            self.quality_var.set("192kbps")
        else:
            # Switch to video qualities
            video_qualities = [f['quality'] for f in self.current_info['formats']['video']] if self.current_info['formats']['video'] else ["720p", "480p", "360p"]
            if not video_qualities:
                video_qualities = ["720p", "480p", "360p"]
            self.quality_menu.configure(values=video_qualities)
            self.quality_var.set("720p")
    
    def _show_error(self, error_msg):
        """Show error message"""
        self.analyze_button.configure(state="normal", text="🔍 Analyze")
        self.set_status(error_msg)
        messagebox.showerror("Error", error_msg)
    
    def add_to_queue(self):
        """Add current item to download queue"""
        if not hasattr(self, 'current_info'):
            return
        
        item = DownloadItem(
            url=self.current_info['url'],
            title=self.current_info['title'],
            platform=self.current_info['platform'],
            thumbnail_url=self.current_info['thumbnail'],
            duration=self.current_info['duration'],
            quality=self.quality_var.get(),
            format_type=self.format_var.get()
        )
        
        self.download_items.append(item)
        self.update_queue_display()
        self.download_all_button.configure(state="normal")
        
        # Clear current preview
        self.preview_frame.grid_remove()
        self.no_content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        self.add_queue_button.configure(state="disabled")
        self.url_entry.delete(0, 'end')
        
        self.set_status(f"Added to queue: {item.title}")
    
    def update_queue_display(self):
        """Update the queue display"""
        # Clear existing items
        for widget in self.queue_scroll.winfo_children():
            widget.destroy()
        
        if not self.download_items:
            self.empty_queue_label = ctk.CTkLabel(
                self.queue_scroll,
                text="📥 No downloads in queue",
                font=ctk.CTkFont(size=14),
                text_color=("gray50", "gray50")
            )
            self.empty_queue_label.grid(row=0, column=0, pady=20)
            return
        
        # Add queue items
        for i, item in enumerate(self.download_items):
            self.create_queue_item(i, item)
    
    def create_queue_item(self, index, item):
        """Create a queue item widget"""
        item_frame = ctk.CTkFrame(self.queue_scroll)
        item_frame.grid(row=index, column=0, sticky="ew", padx=10, pady=5)
        item_frame.grid_columnconfigure(1, weight=1)
        
        # Status indicator
        status_colors = {
            'pending': ("gray50", "gray50"),
            'downloading': ("#007acc", "#4da6ff"),
            'completed': ("#28a745", "#20c997"),
            'error': ("#dc3545", "#e74c3c")
        }
        
        status_icons = {
            'pending': '⏳',
            'downloading': '⬇️',
            'completed': '✅',
            'error': '❌'
        }
        
        status_label = ctk.CTkLabel(
            item_frame,
            text=status_icons.get(item.status, '?'),
            font=ctk.CTkFont(size=16),
            text_color=status_colors.get(item.status, ("gray50", "gray50"))
        )
        status_label.grid(row=0, column=0, padx=10, pady=10)
        
        # Content info
        info_frame = ctk.CTkFrame(item_frame, fg_color="transparent")
        info_frame.grid(row=0, column=1, sticky="ew", padx=10, pady=10)
        info_frame.grid_columnconfigure(0, weight=1)
        
        # Title and platform
        title_text = item.title[:50] + "..." if len(item.title) > 50 else item.title
        title_label = ctk.CTkLabel(
            info_frame,
            text=f"{title_text} ({item.platform})",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        title_label.grid(row=0, column=0, sticky="ew")
        
        # Format and quality info
        format_info = f"{item.format_type.upper()} • {item.quality}"
        if item.duration and item.duration != "N/A":
            format_info += f" • {item.duration}"
        
        format_label = ctk.CTkLabel(
            info_frame,
            text=format_info,
            font=ctk.CTkFont(size=10),
            text_color=("gray60", "gray40"),
            anchor="w"
        )
        format_label.grid(row=1, column=0, sticky="ew")
        
        # Progress bar (if downloading)
        if item.status == 'downloading':
            progress_bar = ctk.CTkProgressBar(info_frame, height=8)
            progress_bar.grid(row=2, column=0, sticky="ew", pady=(5, 0))
            progress_bar.set(item.progress / 100.0)
        
        # Error message (if error)
        if item.status == 'error' and item.error_message:
            error_label = ctk.CTkLabel(
                info_frame,
                text=f"Error: {item.error_message[:30]}...",
                font=ctk.CTkFont(size=10),
                text_color=status_colors['error'],
                anchor="w"
            )
            error_label.grid(row=2, column=0, sticky="ew")
        
        # Remove button
        remove_button = ctk.CTkButton(
            item_frame,
            text="🗑️",
            width=30,
            height=30,
            font=ctk.CTkFont(size=12),
            command=lambda: self.remove_from_queue(index)
        )
        remove_button.grid(row=0, column=2, padx=10, pady=10)
    
    def remove_from_queue(self, index):
        """Remove item from queue"""
        if 0 <= index < len(self.download_items):
            item = self.download_items[index]
            if item.status != 'downloading':
                self.download_items.pop(index)
                self.update_queue_display()
                
                if not self.download_items:
                    self.download_all_button.configure(state="disabled")
                
                self.set_status(f"Removed from queue: {item.title}")
            else:
                messagebox.showwarning("Cannot Remove", "Cannot remove item while downloading")
    
    def start_downloads(self):
        """Start downloading all queued items"""
        pending_items = [item for item in self.download_items if item.status == 'pending']
        
        if not pending_items:
            messagebox.showinfo("No Downloads", "No pending downloads in queue")
            return
        
        # Add items to download queue
        for item in pending_items:
            self.download_queue.put(item)
        
        self.set_status(f"Starting download of {len(pending_items)} items...")
    
    def download_worker(self):
        """Background worker for downloads"""
        while True:
            try:
                # Get item from queue
                item = self.download_queue.get(timeout=1)
                
                if len(self.active_downloads) >= self.config.config['max_concurrent']:
                    # Put back and wait
                    self.download_queue.put(item)
                    time.sleep(1)
                    continue
                
                # Start download in separate thread
                download_thread = threading.Thread(
                    target=self.download_item,
                    args=(item,)
                )
                download_thread.daemon = True
                self.active_downloads[item] = download_thread
                download_thread.start()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in download worker: {e}")
    
    def download_item(self, item):
        """Download a single item"""
        try:
            # Update status
            item.status = 'downloading'
            self.root.after(0, self.update_queue_display)
            
            # Prepare download path
            download_path = Path(self.config.config['download_path'])
            download_path.mkdir(parents=True, exist_ok=True)
            
            if self.config.config['create_subfolders']:
                platform_path = download_path / item.platform.lower()
                platform_path.mkdir(exist_ok=True)
                download_path = platform_path
            
            # Prepare yt-dlp command
            safe_title = re.sub(r'[<>:"/\\|?*]', '', item.title)
            filename = f"{safe_title}.%(ext)s"
            
            cmd = [
                'yt-dlp',
                '--no-playlist',
                '-o', str(download_path / filename),
                '--progress-template', '%(progress._percent_str)s',
                item.url
            ]
            
            # Add format selection
            if item.format_type == 'mp3':
                cmd.extend([
                    '-x',
                    '--audio-format', 'mp3',
                    '--audio-quality', item.quality.replace('kbps', '')
                ])
            else:
                # Video format
                quality_num = item.quality.replace('p', '')
                cmd.extend([
                    '-f', f'best[height<={quality_num}]/best'
                ])
            
            # Start download process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )
            
            # Monitor progress
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                
                # Parse progress
                if '%' in line:
                    try:
                        progress_str = line.strip().replace('%', '')
                        if progress_str.replace('.', '').isdigit():
                            progress = float(progress_str)
                            item.progress = min(progress, 100)
                            self.root.after(0, self.update_queue_display)
                    except:
                        pass
            
            # Wait for process to complete
            return_code = process.wait()
            
            if return_code == 0:
                item.status = 'completed'
                item.progress = 100
                
                # Find downloaded file
                for file_path in download_path.glob(f"{safe_title}.*"):
                    item.file_path = str(file_path)
                    break
                
                self.root.after(0, lambda: self.set_status(f"Download completed: {item.title}"))
            else:
                stderr = process.stderr.read()
                item.status = 'error'
                item.error_message = stderr[:100] if stderr else "Download failed"
                self.root.after(0, lambda: self.set_status(f"Download failed: {item.title}"))
        
        except Exception as e:
            item.status = 'error'
            item.error_message = str(e)
            self.root.after(0, lambda: self.set_status(f"Error downloading {item.title}: {str(e)}"))
        
        finally:
            # Remove from active downloads
            if item in self.active_downloads:
                del self.active_downloads[item]
            
            # Update UI
            self.root.after(0, self.update_queue_display)
    
    def open_download_folder(self):
        """Open the download folder"""
        download_path = Path(self.config.config['download_path'])
        download_path.mkdir(parents=True, exist_ok=True)
        
        try:
            if sys.platform == "win32":
                os.startfile(download_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", download_path])
            else:
                subprocess.run(["xdg-open", download_path])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder: {e}")
    
    def toggle_theme(self):
        """Toggle between light and dark theme"""
        current_mode = ctk.get_appearance_mode()
        new_mode = "light" if current_mode.lower() == "dark" else "dark"
        
        ctk.set_appearance_mode(new_mode)
        self.config.config['theme'] = new_mode
        self.config.save_config()
        
        self.set_status(f"Switched to {new_mode} theme")
    
    def open_settings(self):
        """Open settings window"""
        settings_window = SettingsWindow(self)
    
    def set_status(self, message):
        """Set status bar message"""
        self.status_label.configure(text=message)
        # Auto-clear status after 5 seconds
        self.root.after(5000, lambda: self.status_label.configure(text="Ready"))
    
    def run(self):
        """Start the application"""
        self.root.mainloop()

class SettingsWindow:
    """Settings window"""
    
    def __init__(self, parent):
        self.parent = parent
        self.config = parent.config
        
        # Create settings window
        self.window = ctk.CTkToplevel(parent.root)
        self.window.title("Settings")
        self.window.geometry("600x500")
        self.window.transient(parent.root)
        self.window.grab_set()
        
        # Center the window
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.window.winfo_screenheight() // 2) - (500 // 2)
        self.window.geometry(f"600x500+{x}+{y}")
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup settings UI"""
        # Create tabview
        tabview = ctk.CTkTabview(self.window)
        tabview.pack(fill="both", expand=True, padx=20, pady=20)
        
        # General tab
        general_tab = tabview.add("General")
        self.setup_general_tab(general_tab)
        
        # Download tab
        download_tab = tabview.add("Download")
        self.setup_download_tab(download_tab)
        
        # Platforms tab
        platforms_tab = tabview.add("Platforms")
        self.setup_platforms_tab(platforms_tab)
        
        # Buttons
        button_frame = ctk.CTkFrame(self.window, fg_color="transparent")
        button_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self.window.destroy
        ).pack(side="right", padx=(10, 0))
        
        ctk.CTkButton(
            button_frame,
            text="Save",
            command=self.save_settings
        ).pack(side="right")
    
    def setup_general_tab(self, tab):
        """Setup general settings tab"""
        # Theme selection
        theme_frame = ctk.CTkFrame(tab, fg_color="transparent")
        theme_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(theme_frame, text="Theme:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        self.theme_var = ctk.StringVar(value=self.config.config['theme'])
        theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            variable=self.theme_var,
            values=["system", "light", "dark"]
        )
        theme_menu.pack(anchor="w", pady=(5, 0))
        
        # Download location
        location_frame = ctk.CTkFrame(tab, fg_color="transparent")
        location_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(location_frame, text="Download Location:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        location_input_frame = ctk.CTkFrame(location_frame, fg_color="transparent")
        location_input_frame.pack(fill="x", pady=(5, 0))
        location_input_frame.grid_columnconfigure(0, weight=1)
        
        self.location_var = ctk.StringVar(value=self.config.config['download_path'])
        location_entry = ctk.CTkEntry(location_input_frame, textvariable=self.location_var)
        location_entry.pack(side="left", fill="x", expand=True)
        
        browse_button = ctk.CTkButton(
            location_input_frame,
            text="Browse",
            width=80,
            command=self.browse_download_location
        )
        browse_button.pack(side="right", padx=(10, 0))
    
    def setup_download_tab(self, tab):
        """Setup download settings tab"""
        # Default video quality
        video_frame = ctk.CTkFrame(tab, fg_color="transparent")
        video_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(video_frame, text="Default Video Quality:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        self.video_quality_var = ctk.StringVar(value=self.config.config['default_video_quality'])
        video_menu = ctk.CTkOptionMenu(
            video_frame,
            variable=self.video_quality_var,
            values=["4K", "1080p", "720p", "480p", "360p", "240p", "144p"]
        )
        video_menu.pack(anchor="w", pady=(5, 0))
        
        # Default audio quality
        audio_frame = ctk.CTkFrame(tab, fg_color="transparent")
        audio_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(audio_frame, text="Default Audio Quality:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        self.audio_quality_var = ctk.StringVar(value=self.config.config['default_audio_quality'])
        audio_menu = ctk.CTkOptionMenu(
            audio_frame,
            variable=self.audio_quality_var,
            values=["320kbps", "256kbps", "192kbps", "128kbps"]
        )
        audio_menu.pack(anchor="w", pady=(5, 0))
        
        # Max concurrent downloads
        concurrent_frame = ctk.CTkFrame(tab, fg_color="transparent")
        concurrent_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(concurrent_frame, text="Max Concurrent Downloads:", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        
        self.concurrent_var = ctk.StringVar(value=str(self.config.config['max_concurrent']))
        concurrent_menu = ctk.CTkOptionMenu(
            concurrent_frame,
            variable=self.concurrent_var,
            values=["1", "2", "3", "4", "5"]
        )
        concurrent_menu.pack(anchor="w", pady=(5, 0))
        
        # Create subfolders
        self.subfolder_var = ctk.BooleanVar(value=self.config.config['create_subfolders'])
        subfolder_check = ctk.CTkCheckBox(
            tab,
            text="Create platform subfolders",
            variable=self.subfolder_var
        )
        subfolder_check.pack(anchor="w", padx=20, pady=10)
    
    def setup_platforms_tab(self, tab):
        """Setup platforms settings tab"""
        ctk.CTkLabel(
            tab,
            text="Enable/Disable Platform Support:",
            font=ctk.CTkFont(weight="bold")
        ).pack(anchor="w", padx=20, pady=(10, 20))
        
        self.platform_vars = {}
        platforms = [
            ("YouTube", "youtube"),
            ("Instagram", "instagram"),
            ("TikTok", "tiktok"),
            ("Twitter/X", "twitter"),
            ("Facebook", "facebook")
        ]
        
        for display_name, key in platforms:
            self.platform_vars[key] = ctk.BooleanVar(
                value=self.config.config['platforms'].get(key, True)
            )
            
            check = ctk.CTkCheckBox(
                tab,
                text=display_name,
                variable=self.platform_vars[key]
            )
            check.pack(anchor="w", padx=40, pady=5)
    
    def browse_download_location(self):
        """Browse for download location"""
        folder = filedialog.askdirectory(
            title="Select Download Location",
            initialdir=self.location_var.get()
        )
        
        if folder:
            self.location_var.set(folder)
    
    def save_settings(self):
        """Save settings and close window"""
        # Update configuration
        self.config.config['theme'] = self.theme_var.get()
        self.config.config['download_path'] = self.location_var.get()
        self.config.config['default_video_quality'] = self.video_quality_var.get()
        self.config.config['default_audio_quality'] = self.audio_quality_var.get()
        self.config.config['max_concurrent'] = int(self.concurrent_var.get())
        self.config.config['create_subfolders'] = self.subfolder_var.get()
        
        # Update platform settings
        for key, var in self.platform_vars.items():
            self.config.config['platforms'][key] = var.get()
        
        # Save configuration
        self.config.save_config()
        
        # Apply theme change
        current_theme = ctk.get_appearance_mode()
        new_theme = self.theme_var.get()
        if current_theme.lower() != new_theme.lower() and new_theme != "system":
            ctk.set_appearance_mode(new_theme)
        elif new_theme == "system":
            ctk.set_appearance_mode("system")
        
        self.parent.set_status("Settings saved successfully")
        self.window.destroy()

def check_dependencies():
    """Check if required dependencies are installed"""
    missing = []
    
    try:
        import customtkinter
    except ImportError:
        missing.append("customtkinter")
    
    try:
        import requests
    except ImportError:
        missing.append("requests")
    
    try:
        from PIL import Image, ImageTk
    except ImportError:
        missing.append("Pillow")
    
    # Check yt-dlp
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True)
        if result.returncode != 0:
            missing.append("yt-dlp")
    except FileNotFoundError:
        missing.append("yt-dlp")
    
    if missing:
        print("Missing dependencies:")
        for dep in missing:
            print(f"  - {dep}")
        print("\nInstall missing dependencies:")
        if "yt-dlp" in missing:
            print("  pip install yt-dlp")
        python_deps = [dep for dep in missing if dep != "yt-dlp"]
        if python_deps:
            print(f"  pip install {' '.join(python_deps)}")
        return False
    
    return True

if __name__ == "__main__":
    # Check dependencies
    if not check_dependencies():
        print("\nPlease install missing dependencies and try again.")
        sys.exit(1)
    
    try:
        # Create and run application
        app = SocialMediaDownloader()
        app.run()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()