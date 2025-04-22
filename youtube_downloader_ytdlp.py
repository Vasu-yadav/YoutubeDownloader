#!/usr/bin/env python3
import os
import sys
import re
import subprocess
import json
import shutil
from urllib.parse import urlparse, parse_qs


def sanitize_filename(title):
    """Sanitize the filename by removing invalid characters."""
    # Replace invalid file characters
    return re.sub(r'[\\/*?:"<>|]', "", title)


def check_dependencies():
    """Check if required dependencies are installed."""
    missing_deps = []
    
    # Check for yt-dlp
    if not shutil.which('yt-dlp'):
        missing_deps.append('yt-dlp')
    
    # Check for ffmpeg
    if not shutil.which('ffmpeg'):
        missing_deps.append('ffmpeg')
    
    if missing_deps:
        print("Missing required dependencies:", ", ".join(missing_deps))
        print("\nTo install the dependencies on macOS using Homebrew:")
        print("brew install yt-dlp ffmpeg")
        return False
    return True


def get_video_info(url):
    """Get video info using yt-dlp."""
    try:
        cmd = ["yt-dlp", "--dump-json", url]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error getting video info: {result.stderr}")
            return None
            
        video_info = json.loads(result.stdout)
        return video_info
    except Exception as e:
        print(f"Error while getting video info: {str(e)}")
        return None


def download_video(url, output_path="downloads"):
    """Download YouTube video and extract audio using yt-dlp and ffmpeg."""
    if not check_dependencies():
        return False
        
    try:
        # Create the output directory if it doesn't exist
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        
        # Get video info first
        print("Getting video information...")
        video_info = get_video_info(url)
        
        if not video_info:
            print("Failed to get video information")
            return False
            
        # Get video title
        video_title = video_info.get('title', 'video')
        sanitized_title = sanitize_filename(video_title)
        
        print(f"\nDownloading: {video_title}")
        
        # File paths
        video_file = os.path.join(output_path, f"{sanitized_title}.mp4")
        audio_file = os.path.join(output_path, f"{sanitized_title}.mp3")
        
        # Download MP4 video
        print("\nDownloading MP4 (video)...")
        video_cmd = [
            "yt-dlp", 
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best", 
            "-o", video_file,
            url
        ]
        video_result = subprocess.run(video_cmd, capture_output=True, text=True)
        
        if video_result.returncode != 0:
            print(f"Error downloading video: {video_result.stderr}")
            # Try simpler format selection if first attempt fails
            video_cmd = ["yt-dlp", "-f", "best", "-o", video_file, url]
            video_result = subprocess.run(video_cmd, capture_output=True, text=True)
            if video_result.returncode != 0:
                print(f"Error downloading video (second attempt): {video_result.stderr}")
                return False
        
        print(f"MP4 download complete: {video_file}")
        
        # Extract MP3 audio
        print("\nExtracting MP3 (audio)...")
        audio_cmd = [
            "ffmpeg",
            "-i", video_file,
            "-vn",  # No video
            "-acodec", "libmp3lame",
            "-q:a", "2",  # High quality audio
            audio_file,
            "-y"  # Overwrite if exists
        ]
        audio_result = subprocess.run(audio_cmd, capture_output=True, text=True)
        
        if audio_result.returncode != 0:
            print(f"Error extracting audio: {audio_result.stderr}")
            return False
            
        print(f"MP3 extraction complete: {audio_file}")
        print(f"\nFiles saved to: {os.path.abspath(output_path)}")
        
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python youtube_downloader_ytdlp.py <youtube_url> [output_folder]")
        print("Example: python youtube_downloader_ytdlp.py https://www.youtube.com/watch?v=dQw4w9WgXcQ my_downloads")
        sys.exit(1)
    
    url = sys.argv[1]
    output_folder = sys.argv[2] if len(sys.argv) > 2 else "downloads"
    
    success = download_video(url, output_folder)
    if not success:
        sys.exit(1)