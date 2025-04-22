#!/usr/bin/env python3
import os
import sys
import re
import json
import subprocess
import shutil
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QProgressBar, QFileDialog, QMessageBox, QGroupBox,
                            QCheckBox)
from PyQt5.QtCore import Qt, pyqtSignal, QObject


def sanitize_filename(title):
    """Sanitize the filename by removing invalid characters."""
    return re.sub(r'[\\/*?:"<>|]', "", title)


class WorkerSignals(QObject):
    """Defines the signals available for a worker thread."""
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    log = pyqtSignal(str)


class DownloadWorker(threading.Thread):
    """Thread worker for downloading videos without freezing the UI."""
    def __init__(self, url, output_path, download_video=True, download_audio=True):
        super().__init__()
        self.url = url
        self.output_path = output_path
        self.download_video = download_video
        self.download_audio = download_audio
        self.signals = WorkerSignals()
        self.daemon = True
        self.process = None
    
    def check_dependencies(self):
        """Check if required dependencies are installed."""
        missing_deps = []
        
        # Check for yt-dlp
        if not shutil.which('yt-dlp'):
            missing_deps.append('yt-dlp')
        
        # Check for ffmpeg
        if not shutil.which('ffmpeg'):
            missing_deps.append('ffmpeg')
        
        return missing_deps
    
    def get_video_info(self):
        """Get video info using yt-dlp."""
        self.signals.status.emit("Getting video information...")
        self.signals.progress.emit(10)
        
        try:
            cmd = ["yt-dlp", "--dump-json", self.url]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                error_msg = result.stderr or "Failed to get video information"
                self.signals.error.emit(f"Error getting video info: {error_msg}")
                return None
                
            video_info = json.loads(result.stdout)
            self.signals.progress.emit(20)
            return video_info
        except Exception as e:
            self.signals.error.emit(f"Error while getting video info: {str(e)}")
            return None
    
    def run(self):
        try:
            # Check dependencies first
            missing_deps = self.check_dependencies()
            if missing_deps:
                dep_msg = ", ".join(missing_deps)
                self.signals.error.emit(
                    f"Missing required dependencies: {dep_msg}\n\n"
                    "To install them on macOS using Homebrew:\n"
                    "brew install " + " ".join(missing_deps)
                )
                return
                
            # Create the output directory if it doesn't exist
            if not os.path.exists(self.output_path):
                os.makedirs(self.output_path)
            
            # Get video info
            video_info = self.get_video_info()
            if not video_info:
                return
            
            # Get video title
            video_title = video_info.get('title', 'video')
            sanitized_title = sanitize_filename(video_title)
            
            self.signals.status.emit(f"Downloading: {video_title}")
            
            # File paths
            video_file = os.path.join(self.output_path, f"{sanitized_title}.mp4")
            audio_file = os.path.join(self.output_path, f"{sanitized_title}.mp3")
            
            # Download video if requested
            if self.download_video:
                self.signals.status.emit("Downloading MP4 (video)...")
                self.signals.log.emit("\nDownloading video...")
                
                video_cmd = [
                    "yt-dlp", 
                    "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best", 
                    "-o", video_file,
                    "--progress",
                    self.url
                ]
                
                self.signals.progress.emit(30)
                process = subprocess.Popen(
                    video_cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )
                
                # Process output and update progress
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        self.signals.log.emit(line.strip())
                        # Try to parse progress if available
                        if "%" in line:
                            try:
                                progress_str = line.split('%')[0].strip().split(' ')[-1]
                                progress = float(progress_str)
                                # Scale progress to 30-70 range
                                scaled_progress = 30 + (progress * 0.4)
                                self.signals.progress.emit(int(scaled_progress))
                            except:
                                pass
                
                if process.returncode != 0:
                    # Try simpler format selection if first attempt fails
                    self.signals.status.emit("Trying alternative video format...")
                    self.signals.log.emit("\nTrying alternative video format...")
                    
                    video_cmd = ["yt-dlp", "-f", "best", "-o", video_file, self.url]
                    process = subprocess.run(video_cmd, capture_output=True, text=True)
                    
                    if process.returncode != 0:
                        self.signals.error.emit(f"Error downloading video: {process.stderr}")
                        return
                
                self.signals.log.emit("MP4 download complete!")
            
            # Extract/download audio if requested
            if self.download_audio:
                self.signals.status.emit("Extracting MP3 (audio)...")
                self.signals.log.emit("\nExtracting MP3 audio...")
                self.signals.progress.emit(70)
                
                if self.download_video:
                    # Extract audio from the downloaded video
                    audio_cmd = [
                        "ffmpeg",
                        "-i", video_file,
                        "-vn",  # No video
                        "-acodec", "libmp3lame",
                        "-q:a", "2",  # High quality audio
                        audio_file,
                        "-y"  # Overwrite if exists
                    ]
                    process = subprocess.run(audio_cmd, capture_output=True, text=True)
                    
                    if process.returncode != 0:
                        self.signals.error.emit(f"Error extracting audio: {process.stderr}")
                        return
                else:
                    # If only audio is needed, download it directly
                    audio_cmd = [
                        "yt-dlp",
                        "-x",  # Extract audio
                        "--audio-format", "mp3",
                        "--audio-quality", "0",  # Best quality
                        "-o", audio_file,
                        self.url
                    ]
                    process = subprocess.run(audio_cmd, capture_output=True, text=True)
                    
                    if process.returncode != 0:
                        self.signals.error.emit(f"Error downloading audio: {process.stderr}")
                        return
                
                self.signals.log.emit("MP3 extraction complete!")
            
            self.signals.progress.emit(100)
            self.signals.status.emit("Download complete!")
            self.signals.finished.emit(self.output_path)
            
        except Exception as e:
            self.signals.error.emit(f"Error: {str(e)}")


class YouTubeDownloaderApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Downloader (yt-dlp + ffmpeg)")
        self.setMinimumSize(700, 400)
        
        # Initialize UI
        self.init_ui()
        
        # Set default download path
        self.output_path_edit.setText(os.path.join(os.path.expanduser("~"), "Downloads"))
        
    def init_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)
        
        # Header
        header_label = QLabel("YouTube MP3 & MP4 Downloader")
        header_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(header_label)
        
        # URL Input
        url_group = QGroupBox("Video URL")
        url_layout = QHBoxLayout()
        url_group.setLayout(url_layout)
        
        url_label = QLabel("YouTube URL:")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_edit)
        
        main_layout.addWidget(url_group)
        
        # Output Path
        path_group = QGroupBox("Output Location")
        path_layout = QHBoxLayout()
        path_group.setLayout(path_layout)
        
        path_label = QLabel("Output Folder:")
        self.output_path_edit = QLineEdit()
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_output_path)
        
        path_layout.addWidget(path_label)
        path_layout.addWidget(self.output_path_edit)
        path_layout.addWidget(browse_btn)
        
        main_layout.addWidget(path_group)
        
        # Options
        options_group = QGroupBox("Download Options")
        options_layout = QHBoxLayout()
        options_group.setLayout(options_layout)
        
        self.mp4_checkbox = QCheckBox("Download MP4 Video")
        self.mp4_checkbox.setChecked(True)
        self.mp3_checkbox = QCheckBox("Extract MP3 Audio")
        self.mp3_checkbox.setChecked(True)
        
        options_layout.addWidget(self.mp4_checkbox)
        options_layout.addWidget(self.mp3_checkbox)
        
        main_layout.addWidget(options_group)
        
        # Download Button
        self.download_btn = QPushButton("Download")
        self.download_btn.clicked.connect(self.start_download)
        self.download_btn.setMinimumHeight(40)
        main_layout.addWidget(self.download_btn)
        
        # Progress
        progress_group = QGroupBox("Download Progress")
        progress_layout = QVBoxLayout()
        progress_group.setLayout(progress_layout)
        
        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Ready to download")
        self.status_label.setAlignment(Qt.AlignCenter)
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.status_label)
        
        main_layout.addWidget(progress_group)
        
        # Log area
        log_group = QGroupBox("Download Log")
        log_layout = QVBoxLayout()
        log_group.setLayout(log_layout)
        
        self.log_label = QLabel()
        self.log_label.setStyleSheet("background-color: #f0f0f0; padding: 5px; font-family: monospace;")
        self.log_label.setWordWrap(True)
        self.log_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.log_label.setText("Waiting for download to start...")
        
        log_layout.addWidget(self.log_label)
        
        main_layout.addWidget(log_group)
    
    def browse_output_path(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if folder_path:
            self.output_path_edit.setText(folder_path)
    
    def start_download(self):
        url = self.url_edit.text().strip()
        output_path = self.output_path_edit.text().strip()
        download_mp4 = self.mp4_checkbox.isChecked()
        download_mp3 = self.mp3_checkbox.isChecked()
        
        if not url:
            QMessageBox.critical(self, "Error", "Please enter a YouTube URL")
            return
        
        if not output_path:
            QMessageBox.critical(self, "Error", "Please select an output folder")
            return
            
        if not download_mp4 and not download_mp3:
            QMessageBox.critical(self, "Error", "Please select at least one format to download")
            return
        
        # Disable button during download
        self.download_btn.setEnabled(False)
        
        # Clear log
        self.log_label.setText("")
        
        # Create and start the worker thread
        self.worker = DownloadWorker(url, output_path, download_mp4, download_mp3)
        
        # Connect signals
        self.worker.signals.progress.connect(self.update_progress)
        self.worker.signals.status.connect(self.update_status)
        self.worker.signals.finished.connect(self.download_finished)
        self.worker.signals.error.connect(self.download_error)
        self.worker.signals.log.connect(self.append_log)
        
        # Start download
        self.worker.start()
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_status(self, message):
        self.status_label.setText(message)
    
    def append_log(self, text):
        current_text = self.log_label.text()
        self.log_label.setText(current_text + "\n" + text)
    
    def download_finished(self, output_path):
        # Re-enable button
        self.download_btn.setEnabled(True)
        
        QMessageBox.information(self, "Success", f"Download complete!\nSaved to: {output_path}")
    
    def download_error(self, error_msg):
        # Re-enable button
        self.download_btn.setEnabled(True)
        
        self.update_status(f"Error: Download failed")
        QMessageBox.critical(self, "Error", f"Download failed:\n\n{error_msg}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = YouTubeDownloaderApp()
    window.show()
    sys.exit(app.exec_())