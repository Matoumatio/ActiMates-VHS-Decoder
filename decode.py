import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json
import hashlib
import os
import traceback
import time
import wave
import struct

# =========================
# Configuration
# =========================

# Calibration parameters (will be adjustable in UI)
BAR_X_OFFSET = 0
BAR_Y_OFFSET = 0
BAR_WIDTH = 12
BAR_HEIGHT = 0  # 0 means use full height
LINES_IGNORE_TOP = 10
LINES_IGNORE_BOTTOM = 10

THRESHOLD_MODE = "adaptive"  # or "fixed"
FIXED_THRESHOLD = 128

PACKET_SIZE = 128

RELEVANCE_VARIANCE_THRESHOLD = 0.08
RELEVANCE_TRANSITION_MIN = 12

# Blink detection parameters
MIN_SILENCE_FRAMES = 5  # Minimum frames of silence to separate blinks
CONSTANT_SIGNAL_TOP_LINES = 5  # Number of top lines to ignore as constant signal

DEBUG_VIEW = True

COMMAND_DB_FILE = "commands.json"

AUDIO_SAMPLE_RATE = 44100
BIT_DURATION_SEC = 0.002  # 2 ms per bit

# =========================
# Utilities
# =========================

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:06.3f}".replace(".", ",")

def bits_to_audio(bits, path):
    samples = []
    samples_per_bit = int(AUDIO_SAMPLE_RATE * BIT_DURATION_SEC)

    for bit in bits:
        value = 1.0 if bit else -1.0
        samples.extend([value] * samples_per_bit)

    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(AUDIO_SAMPLE_RATE)

        for s in samples:
            wf.writeframes(struct.pack("<h", int(s * 32767)))

def video_to_spectrogram_audio(video_path, output_path, bar_x, bar_y, bar_width, bar_height,
                                ignore_top, ignore_bottom, fps, progress_callback=None):
    """
    Convert video barcode to audio by treating each vertical line as a frequency spectrum.
    Each column of pixels in the barcode becomes a frequency component at that moment in time.
    """
    cap = None
    wf = None
    
    try:
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Audio parameters
        sample_rate = 44100
        samples_per_frame = int(sample_rate / fps)  # Samples for each video frame
        
        all_samples = []
        frame_count = 0
        
        # Read and process all frames
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            try:
                # Extract barcode region
                h, w, _ = frame.shape
                actual_height = bar_height if bar_height > 0 else h - bar_y
                y_end = min(bar_y + actual_height, h)
                x_end = min(bar_x + bar_width, w)
                
                bar = frame[bar_y:y_end, bar_x:x_end]
                if bar.size == 0:
                    # Add silence for missing frames
                    all_samples.extend([0.0] * samples_per_frame)
                    continue
                
                # Convert to grayscale
                gray = cv2.cvtColor(bar, cv2.COLOR_BGR2GRAY)
                
                # Apply ignore regions
                bar_h = gray.shape[0]
                usable_start = ignore_top
                usable_end = bar_h - ignore_bottom
                
                if usable_start >= usable_end:
                    all_samples.extend([0.0] * samples_per_frame)
                    continue
                
                usable = gray[usable_start:usable_end]
                
                # Average across width to get a single column of intensity values
                column = np.mean(usable, axis=1)
                
                # Normalize to -1 to 1 range
                normalized = (column / 255.0) * 2.0 - 1.0
                
                # Generate audio samples for this frame
                # Use the pixel intensities as frequency amplitudes
                frame_samples = []
                for i in range(samples_per_frame):
                    # Interpolate through the pixel column for smooth audio
                    position = (i / samples_per_frame) * len(normalized)
                    idx = int(position)
                    if idx >= len(normalized) - 1:
                        sample = normalized[-1]
                    else:
                        # Linear interpolation
                        frac = position - idx
                        sample = normalized[idx] * (1 - frac) + normalized[idx + 1] * frac
                    
                    frame_samples.append(sample)
                
                all_samples.extend(frame_samples)
                
            except Exception as e:
                print(f"Error processing frame {frame_count}: {e}")
                # Add silence on error
                all_samples.extend([0.0] * samples_per_frame)
            
            # Progress callback
            if progress_callback and frame_count % 30 == 0:
                progress_callback(frame_count, total_frames)
        
        # Final progress update
        if progress_callback:
            progress_callback(frame_count, total_frames)
        
        cap.release()
        cap = None
        
        # Update progress for writing phase
        if progress_callback:
            progress_callback(total_frames, total_frames)
        
        print(f"Writing {len(all_samples)} samples to WAV file...")
        
        # Write WAV file more efficiently
        wf = wave.open(output_path, "wb")
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        
        # Convert all samples to bytes at once for faster writing
        audio_data = bytearray()
        for s in all_samples:
            # Clamp to -1 to 1 range
            s = max(-1.0, min(1.0, s))
            audio_data.extend(struct.pack("<h", int(s * 32767)))
        
        # Write all at once
        wf.writeframes(bytes(audio_data))
        wf.close()
        wf = None
        
        print(f"Audio export complete: {output_path}")
        
    except Exception as e:
        print(f"Error in video_to_spectrogram_audio: {e}")
        traceback.print_exc()
        raise
    finally:
        # Clean up resources
        if cap is not None:
            cap.release()
        if wf is not None:
            wf.close()

# =========================
# Command database
# =========================

class CommandDB:
    def __init__(self, path):
        self.path = path
        self.commands = {}
        self.pending_changes = {}
        self.batch_mode = False
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                data = json.load(f)
                # Support both old format (string) and new format (dict with name/timestamps)
                if data and isinstance(list(data.values())[0], dict):
                    self.commands = data
                else:
                    # Convert old format to new format
                    self.commands = {h: {"name": n, "timestamps": []} for h, n in data.items()}

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.commands, f, indent=2)
    
    def start_batch(self):
        """Enable batch mode - don't save immediately"""
        self.batch_mode = True
        self.pending_changes.clear()

    def end_batch(self):
        """Disable batch mode and save all pending changes"""
        if self.pending_changes:
            # Merge pending changes with existing commands, combining timestamps
            for h, pending_entry in self.pending_changes.items():
                if h in self.commands:
                    # Merge timestamps with existing entry
                    existing_entry = self.commands[h]
                    if isinstance(existing_entry, dict):
                        existing_ts = existing_entry.get("timestamps", [])
                    else:
                        existing_ts = []
                    
                    new_ts = pending_entry.get("timestamps", [])
                    combined_ts = sorted(list(set(existing_ts + new_ts)))
                    
                    self.commands[h] = {
                        "name": pending_entry["name"],
                        "timestamps": combined_ts
                    }
                else:
                    # New entry
                    self.commands[h] = pending_entry
            
            self.save()
            self.pending_changes.clear()
        self.batch_mode = False

    def get_name(self, h):
        # Check pending changes first, then saved commands
        if h in self.pending_changes:
            return self.pending_changes[h]["name"]
        entry = self.commands.get(h)
        if entry:
            return entry["name"] if isinstance(entry, dict) else entry
        return None
    
    def get_entry(self, h):
        """Get full entry including timestamps"""
        if h in self.pending_changes:
            return self.pending_changes[h]
        return self.commands.get(h)

    def set_name(self, h, name, timestamp=None):
        # Determine the base entry to work with
        if self.batch_mode and h in self.pending_changes:
            # Use pending entry if it exists
            entry = self.pending_changes[h]
        elif h in self.commands:
            # Use existing entry
            existing = self.commands[h]
            if isinstance(existing, dict):
                entry = existing.copy()
            else:
                entry = {"name": existing, "timestamps": []}
        else:
            # New entry
            entry = {"name": name, "timestamps": []}
        
        # Update name
        entry["name"] = name
        
        # Add timestamp if provided
        if timestamp is not None and timestamp not in entry["timestamps"]:
            entry["timestamps"].append(timestamp)
            entry["timestamps"].sort()
        
        if self.batch_mode:
            self.pending_changes[h] = entry
        else:
            self.commands[h] = entry
            self.save()

# =========================
# Decoder
# =========================

class ActimatesDecoder:
    def extract_bits_from_frame(self, frame, x_offset, y_offset, width, height, 
                                ignore_top, ignore_bottom, constant_top):
        h, w, _ = frame.shape
        
        # Calculate actual height
        actual_height = height if height > 0 else h - y_offset
        
        # Extract the bar region
        y_end = min(y_offset + actual_height, h)
        x_end = min(x_offset + width, w)
        
        bar = frame[y_offset:y_end, x_offset:x_end]
        if bar.size == 0:
            return []
            
        gray = cv2.cvtColor(bar, cv2.COLOR_BGR2GRAY)

        # Apply ignore regions
        bar_height = gray.shape[0]
        usable_start = ignore_top
        usable_end = bar_height - ignore_bottom
        
        if usable_start >= usable_end:
            return []
            
        usable = gray[usable_start:usable_end]

        threshold = (
            np.mean(usable)
            if THRESHOLD_MODE == "adaptive"
            else FIXED_THRESHOLD
        )

        bits = [1 if np.mean(line) > threshold else 0 for line in usable]
        
        # Remove constant signal from top
        if constant_top > 0 and len(bits) > constant_top:
            bits = bits[constant_top:]
        
        return bits

    def is_relevant_signal(self, bits):
        if len(bits) < 20:
            return False

        transitions = sum(bits[i] != bits[i + 1] for i in range(len(bits) - 1))
        variance = np.var(bits)

        if transitions < RELEVANCE_TRANSITION_MIN:
            return False
        if variance < RELEVANCE_VARIANCE_THRESHOLD:
            return False

        return True

    def packetize(self, bits):
        packets = []
        for i in range(0, len(bits) - PACKET_SIZE, PACKET_SIZE):
            packets.append(bits[i:i + PACKET_SIZE])
        return packets

    @staticmethod
    def hash_packet(packet):
        return hashlib.sha1(bytes(packet)).hexdigest()

# =========================
# Debug visualization
# =========================

def show_debug_view(frame, bits, x_offset, y_offset, width, height, ignore_top, 
                    ignore_bottom, constant_top):
    vis = frame.copy()
    h, w, _ = vis.shape
    
    # Calculate actual height
    actual_height = height if height > 0 else h - y_offset
    
    # Draw the extraction rectangle
    cv2.rectangle(vis, (x_offset, y_offset), 
                  (x_offset + width, y_offset + actual_height), (0, 255, 0), 2)
    
    # Draw ignore regions
    cv2.rectangle(vis, (x_offset, y_offset), 
                  (x_offset + width, y_offset + ignore_top), (0, 0, 255), 1)
    cv2.rectangle(vis, (x_offset, y_offset + actual_height - ignore_bottom),
                  (x_offset + width, y_offset + actual_height), (0, 0, 255), 1)
    
    # Draw constant signal region
    if constant_top > 0:
        cv2.rectangle(vis, (x_offset, y_offset + ignore_top),
                      (x_offset + width, y_offset + ignore_top + constant_top),
                      (255, 0, 0), 1)

    # Draw bits
    for i, bit in enumerate(bits):
        y = i + y_offset + ignore_top + constant_top
        if y >= h:
            break
        color = (255, 255, 255) if bit else (0, 0, 255)
        cv2.circle(vis, (x_offset + width + 5, y), 1, color, -1)

    cv2.imshow("Barcode Debug View", vis)
    cv2.waitKey(1)

# =========================
# Tkinter App
# =========================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("ActiMates VHS Decoder")

        self.decoder = ActimatesDecoder()
        self.db = CommandDB(COMMAND_DB_FILE)

        self.video = None
        self.video_path = None
        self.frame_index = 0
        self.total_frames = 0
        self.fps = 30.0

        self.events = []
        
        # Fast analysis mode
        self.frame_skip = tk.IntVar(value=1)
        
        # Calibration variables
        self.bar_x = tk.IntVar(value=BAR_X_OFFSET)
        self.bar_y = tk.IntVar(value=BAR_Y_OFFSET)
        self.bar_width = tk.IntVar(value=BAR_WIDTH)
        self.bar_height = tk.IntVar(value=BAR_HEIGHT)
        self.ignore_top = tk.IntVar(value=LINES_IGNORE_TOP)
        self.ignore_bottom = tk.IntVar(value=LINES_IGNORE_BOTTOM)
        self.constant_top = tk.IntVar(value=CONSTANT_SIGNAL_TOP_LINES)
        
        # Blink detection
        self.last_signal_frame = -1
        self.silence_count = 0
        self.current_blink_id = 0
        self.current_blink_bits = []
        
        # Preview frame storage
        self.preview_frame = None
        
        # Ultra fast mode
        self.ultra_fast_mode = tk.BooleanVar(value=False)
        
        # Progress tracking
        self.progress_window = None
        self.progress_bar = None
        self.progress_label = None

        self.build_ui()

    def build_ui(self):
        # Top button bar
        bar = tk.Frame(self.root)
        bar.pack(fill="x")

        tk.Button(bar, text="Open Video", command=self.open_video).pack(side="left")
        tk.Button(bar, text="Preview Frame", command=self.preview_random_frame).pack(side="left")
        tk.Button(bar, text="Decode...", command=self.show_decode_dialog, 
                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side="left")
        tk.Button(bar, text="Step Frame", command=self.step_frame).pack(side="left")
        tk.Button(bar, text="Export SRT", command=self.export_srt).pack(side="left")
        tk.Button(bar, text="Export Barcode Audio", command=self.export_audio).pack(side="left")
        
        # Fast analysis speed control
        speed_frame = tk.Frame(bar)
        speed_frame.pack(side="left", padx=10)
        tk.Label(speed_frame, text="Speed:").pack(side="left")
        speed_options = [
            ("1x", 1),
            ("2x", 2),
            ("5x", 5),
            ("10x", 10),
            ("20x", 20)
        ]
        for label, value in speed_options:
            tk.Radiobutton(
                speed_frame,
                text=label,
                variable=self.frame_skip,
                value=value
            ).pack(side="left")
        
        # Ultra fast mode checkbox
        tk.Checkbutton(
            speed_frame,
            text="ULTRA FAST (No Preview)",
            variable=self.ultra_fast_mode,
            fg="red",
            font=("Arial", 9, "bold")
        ).pack(side="left", padx=10)

        # Calibration controls
        cal_frame = tk.LabelFrame(self.root, text="Barcode Region Calibration", padx=10, pady=10)
        cal_frame.pack(fill="x", padx=5, pady=5)
        
        # Row 1: Position
        row1 = tk.Frame(cal_frame)
        row1.pack(fill="x")
        
        tk.Label(row1, text="X Offset:").pack(side="left")
        tk.Scale(row1, from_=0, to=200, orient="horizontal", variable=self.bar_x, 
                 length=150, command=self.on_calibration_change).pack(side="left")
        
        tk.Label(row1, text="Y Offset:").pack(side="left", padx=(20, 0))
        tk.Scale(row1, from_=0, to=200, orient="horizontal", variable=self.bar_y,
                 length=150, command=self.on_calibration_change).pack(side="left")
        
        # Row 2: Dimensions
        row2 = tk.Frame(cal_frame)
        row2.pack(fill="x")
        
        tk.Label(row2, text="Width:").pack(side="left")
        tk.Scale(row2, from_=5, to=100, orient="horizontal", variable=self.bar_width,
                 length=150, command=self.on_calibration_change).pack(side="left")
        
        tk.Label(row2, text="Height (0=auto):").pack(side="left", padx=(20, 0))
        tk.Scale(row2, from_=0, to=500, orient="horizontal", variable=self.bar_height,
                 length=150, command=self.on_calibration_change).pack(side="left")
        
        # Row 3: Ignore regions
        row3 = tk.Frame(cal_frame)
        row3.pack(fill="x")
        
        tk.Label(row3, text="Ignore Top:").pack(side="left")
        tk.Scale(row3, from_=0, to=100, orient="horizontal", variable=self.ignore_top,
                 length=150, command=self.on_calibration_change).pack(side="left")
        
        tk.Label(row3, text="Ignore Bottom:").pack(side="left", padx=(20, 0))
        tk.Scale(row3, from_=0, to=100, orient="horizontal", variable=self.ignore_bottom,
                 length=150, command=self.on_calibration_change).pack(side="left")
        
        tk.Label(row3, text="Constant Top Lines:").pack(side="left", padx=(20, 0))
        tk.Scale(row3, from_=0, to=50, orient="horizontal", variable=self.constant_top,
                 length=150, command=self.on_calibration_change).pack(side="left")

        # Log output
        self.text = tk.Text(self.root, height=24, width=120)
        self.text.pack(fill="both", expand=True)

    def log(self, msg):
        self.text.insert("end", msg + "\n")
        self.text.see("end")

    def open_video(self):
        try:
            path = filedialog.askopenfilename()
            if not path:
                return

            # Show progress
            self.create_progress_window("Loading Video", 100)
            self.update_progress(10, "Opening video file...")
            
            self.video = cv2.VideoCapture(path)
            self.video_path = path
            self.frame_index = 0
            self.events.clear()
            
            self.update_progress(40, "Reading video properties...")
            
            # Reset blink tracking
            self.last_signal_frame = -1
            self.silence_count = 0
            self.current_blink_id = 0
            self.current_blink_bits = []
            self.preview_frame = None

            self.update_progress(70, "Analyzing video...")
            
            self.total_frames = int(self.video.get(cv2.CAP_PROP_FRAME_COUNT))
            self.fps = self.video.get(cv2.CAP_PROP_FPS) or 30.0

            self.update_progress(100, "Video loaded successfully!")
            time.sleep(0.3)  # Brief pause to show completion
            self.close_progress()

            self.log(f"Opened video: {path}")
            self.log(f"Frames: {self.total_frames}, FPS: {self.fps}")

        except Exception:
            self.close_progress()
            traceback.print_exc()
    
    def preview_random_frame(self):
        """Show a random frame for calibration without decoding"""
        try:
            if not self.video:
                messagebox.showwarning("No Video", "Please open a video first.")
                return
            
            # Pick a random frame
            import random
            random_frame_num = random.randint(0, max(0, self.total_frames - 1))
            
            # Save current position
            current_pos = self.video.get(cv2.CAP_PROP_POS_FRAMES)
            
            # Seek to random frame
            self.video.set(cv2.CAP_PROP_POS_FRAMES, random_frame_num)
            ret, frame = self.video.read()
            
            # Restore position
            self.video.set(cv2.CAP_PROP_POS_FRAMES, current_pos)
            
            if ret:
                self.preview_frame = frame
                self.show_preview()
                self.log(f"Preview: Frame {random_frame_num}")
            else:
                self.log("Failed to read random frame")
                
        except Exception:
            traceback.print_exc()
    
    def on_calibration_change(self, value=None):
        """Update preview when calibration sliders change"""
        if self.preview_frame is not None:
            self.show_preview()
    
    def show_preview(self):
        """Display the preview frame with current calibration"""
        if self.preview_frame is None:
            return
            
        # Get calibration values
        x_off = self.bar_x.get()
        y_off = self.bar_y.get()
        width = self.bar_width.get()
        height = self.bar_height.get()
        ignore_t = self.ignore_top.get()
        ignore_b = self.ignore_bottom.get()
        const_top = self.constant_top.get()
        
        # Extract bits (for visualization)
        bits = self.decoder.extract_bits_from_frame(
            self.preview_frame, x_off, y_off, width, height, ignore_t, ignore_b, const_top
        )
        
        # Show debug view
        show_debug_view(self.preview_frame, bits, x_off, y_off, width, height,
                       ignore_t, ignore_b, const_top)
    
    def create_progress_window(self, title, total_items):
        """Create a progress window"""
        if self.progress_window:
            self.progress_window.destroy()
        
        self.progress_window = tk.Toplevel(self.root)
        self.progress_window.title(title)
        self.progress_window.geometry("500x150")
        self.progress_window.resizable(False, False)
        
        # Make modal
        self.progress_window.transient(self.root)
        self.progress_window.grab_set()
        
        # Center window
        self.progress_window.update_idletasks()
        x = (self.progress_window.winfo_screenwidth() // 2) - (self.progress_window.winfo_width() // 2)
        y = (self.progress_window.winfo_screenheight() // 2) - (self.progress_window.winfo_height() // 2)
        self.progress_window.geometry(f"+{x}+{y}")
        
        # Progress label
        self.progress_label = tk.Label(self.progress_window, text="Starting...", 
                                       font=("Arial", 10))
        self.progress_label.pack(pady=20)
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(self.progress_window, length=450, 
                                           mode='determinate', maximum=total_items)
        self.progress_bar.pack(pady=10)
        
        # Stats label
        self.progress_stats = tk.Label(self.progress_window, text="", 
                                       font=("Arial", 9), fg="gray")
        self.progress_stats.pack(pady=5)
        
        self.progress_window.update()
    
    def update_progress(self, value, label_text="", stats_text=""):
        """Update progress bar"""
        if self.progress_bar:
            self.progress_bar['value'] = value
        if self.progress_label and label_text:
            self.progress_label.config(text=label_text)
        if hasattr(self, 'progress_stats') and stats_text:
            self.progress_stats.config(text=stats_text)
        if self.progress_window:
            self.progress_window.update()
    
    def close_progress(self):
        """Close progress window"""
        if self.progress_window:
            self.progress_window.grab_release()
            self.progress_window.destroy()
            self.progress_window = None
            self.progress_bar = None
            self.progress_label = None
    
    def show_decode_dialog(self):
        """Show dialog to configure decode options"""
        if not self.video:
            messagebox.showwarning("No Video", "Please open a video first.")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Decode Configuration")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        
        # Make dialog modal
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Export options
        export_frame = tk.LabelFrame(dialog, text="Auto-Export After Decode", padx=20, pady=10)
        export_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        export_srt_var = tk.BooleanVar(value=True)
        export_audio_var = tk.BooleanVar(value=True)
        
        tk.Checkbutton(export_frame, text="Export SRT subtitle file", 
                      variable=export_srt_var, font=("Arial", 10)).pack(anchor="w", pady=5)
        tk.Checkbutton(export_frame, text="Export Barcode Audio (WAV)", 
                      variable=export_audio_var, font=("Arial", 10)).pack(anchor="w", pady=5)
        
        # Info label
        info_label = tk.Label(export_frame, 
                             text="Files will be auto-saved to the same\ndirectory as the video file.",
                             fg="gray", font=("Arial", 9))
        info_label.pack(pady=10)
        
        # Buttons
        button_frame = tk.Frame(dialog)
        button_frame.pack(fill="x", padx=10, pady=10)
        
        def start_decode():
            dialog.destroy()
            self.run_full(
                auto_export_srt=export_srt_var.get(),
                auto_export_audio=export_audio_var.get()
            )
        
        tk.Button(button_frame, text="Start Decode", command=start_decode,
                 bg="#4CAF50", fg="white", font=("Arial", 10, "bold"),
                 width=15).pack(side="left", padx=5)
        tk.Button(button_frame, text="Cancel", command=dialog.destroy,
                 width=15).pack(side="left", padx=5)
        
        # Center dialog
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

    def step_frame(self):
        try:
            if not self.video:
                return

            ret, frame = self.video.read()
            if not ret:
                self.log("End of video")
                return

            self.frame_index += 1
            self.process_frame(frame)

        except Exception:
            traceback.print_exc()

    def run_full(self, auto_export_srt=False, auto_export_audio=False):
        try:
            if not self.video:
                return

            skip = self.frame_skip.get()
            ultra_fast = self.ultra_fast_mode.get()
            start = time.time()
            last_percent = -1
            frames_processed = 0

            mode_str = "ULTRA FAST" if ultra_fast else f"{skip}x speed"
            self.log(f"Starting decode in {mode_str} mode (processing every {skip} frame(s))...")
            
            # Create progress window
            self.create_progress_window("Decoding Video", self.total_frames)
            
            # Enable batch mode for JSON updates
            self.db.start_batch()
            
            # Close any existing debug window in ultra fast mode
            if ultra_fast:
                cv2.destroyAllWindows()

            while True:
                ret, frame = self.video.read()
                if not ret:
                    break

                self.frame_index += 1
                
                # Process frame only if it's on the skip interval
                if (self.frame_index - 1) % skip == 0:
                    self.process_frame(frame)
                    frames_processed += 1

                # Update progress bar
                if self.frame_index % 30 == 0:  # Update every 30 frames for performance
                    elapsed = time.time() - start
                    fps_rate = frames_processed / elapsed if elapsed > 0 else 0
                    percent = int((self.frame_index / self.total_frames) * 100) if self.total_frames > 0 else 0
                    
                    self.update_progress(
                        self.frame_index,
                        f"Decoding: {percent}% complete ({self.current_blink_id} blinks found)",
                        f"Frame {self.frame_index}/{self.total_frames} | Speed: {fps_rate:.0f} fps | Time: {elapsed:.1f}s"
                    )

                if self.total_frames > 0:
                    percent = int((self.frame_index / self.total_frames) * 100)
                    if percent != last_percent and percent % 5 == 0:
                        elapsed = time.time() - start
                        fps_rate = frames_processed / elapsed if elapsed > 0 else 0
                        print(f"[{percent}%] Frame {self.frame_index}/{self.total_frames} | Processed: {frames_processed} | Time: {elapsed:.1f}s | Speed: {fps_rate:.0f} fps")
                        last_percent = percent
            
            # Process any remaining blink
            self.update_progress(self.total_frames, "Processing final data...")
            if self.current_blink_bits:
                self.process_blink()
            
            # Save all JSON changes at once
            self.update_progress(self.total_frames, "Saving command database...")
            
            # Count timestamps before saving
            total_timestamps = sum(len(entry.get("timestamps", [])) 
                                  for entry in self.db.pending_changes.values())
            
            self.db.end_batch()
            
            # Verify timestamps were saved
            saved_timestamps = sum(len(entry.get("timestamps", [])) 
                                   for entry in self.db.commands.values() 
                                   if isinstance(entry, dict))
            
            print(f"Saved {len(self.db.commands)} commands with {total_timestamps} recorded timestamps")
            print(f"Verification: {saved_timestamps} timestamps in saved database")
            
            if saved_timestamps != total_timestamps:
                print(f"WARNING: Timestamp mismatch! Recorded {total_timestamps} but saved {saved_timestamps}")

            elapsed = time.time() - start
            fps_rate = frames_processed / elapsed if elapsed > 0 else 0
            print(f"Finished in {elapsed:.2f}s")
            print(f"Total frames: {self.frame_index}, Processed: {frames_processed} ({skip}x speed)")
            print(f"Processing speed: {fps_rate:.0f} fps")
            
            self.update_progress(self.total_frames, "Decode complete!", 
                               f"Processed {frames_processed} frames @ {fps_rate:.0f} fps in {elapsed:.1f}s")
            time.sleep(0.5)
            self.close_progress()
            
            self.log(f"Full decode finished in {elapsed:.2f}s ({frames_processed} frames @ {fps_rate:.0f} fps).")
            self.log(f"Total blinks detected: {self.current_blink_id}")
            
            # Auto-export if requested
            if auto_export_srt or auto_export_audio:
                self.auto_export_files(auto_export_srt, auto_export_audio)

        except Exception:
            # Make sure to end batch mode even on error
            self.db.end_batch()
            self.close_progress()
            traceback.print_exc()

    def process_frame(self, frame):
        # Get calibration values
        x_off = self.bar_x.get()
        y_off = self.bar_y.get()
        width = self.bar_width.get()
        height = self.bar_height.get()
        ignore_t = self.ignore_top.get()
        ignore_b = self.ignore_bottom.get()
        const_top = self.constant_top.get()
        
        bits = self.decoder.extract_bits_from_frame(
            frame, x_off, y_off, width, height, ignore_t, ignore_b, const_top
        )

        # Only show debug view if not in ultra fast mode
        if DEBUG_VIEW and not self.ultra_fast_mode.get():
            show_debug_view(frame, bits, x_off, y_off, width, height, 
                          ignore_t, ignore_b, const_top)

        # Check if this frame has a relevant signal
        has_signal = self.decoder.is_relevant_signal(bits)
        
        if has_signal:
            # Accumulate bits for current blink
            self.current_blink_bits.extend(bits)
            self.last_signal_frame = self.frame_index
            self.silence_count = 0
        else:
            # Count silence frames
            if self.last_signal_frame > 0:
                self.silence_count += 1
                
                # If enough silence, process the accumulated blink
                if self.silence_count >= MIN_SILENCE_FRAMES and self.current_blink_bits:
                    self.process_blink()
        
    def process_blink(self):
        """Process accumulated bits from a blink sequence"""
        if not self.current_blink_bits:
            return
            
        packets = self.decoder.packetize(self.current_blink_bits)
        timestamp = self.last_signal_frame / self.fps
        
        # Validate timestamp
        if timestamp < 0:
            print(f"WARNING: Invalid timestamp {timestamp} at frame {self.last_signal_frame}")
            timestamp = 0
        
        self.current_blink_id += 1
        
        for packet in packets:
            h = self.decoder.hash_packet(packet)
            name = self.db.get_name(h)

            if not name:
                name = f"UNKNOWN_{h[:8]}"
            
            # Add timestamp to database - CRITICAL: timestamp parameter must be passed
            self.db.set_name(h, name, timestamp=timestamp)
            
            # Debug: verify timestamp was added (only print first few)
            if self.current_blink_id <= 3:
                entry = self.db.get_entry(h)
                ts_count = len(entry.get("timestamps", [])) if entry else 0
                print(f"DEBUG: Blink {self.current_blink_id}, hash {h[:8]}, timestamp {timestamp:.3f}, entry has {ts_count} timestamps")

            self.log(f"[Blink {self.current_blink_id} @ Frame {self.last_signal_frame} / {format_time(timestamp)}] {name}")

            self.events.append({
                "time": timestamp,
                "name": name,
                "bits": packet,
                "blink_id": self.current_blink_id,
                "hash": h
            })
        
        # Reset for next blink
        self.current_blink_bits = []

    def export_srt(self):
        try:
            if not self.events:
                messagebox.showwarning("No data", "No events to export.")
                return

            path = filedialog.asksaveasfilename(
                defaultextension=".srt",
                filetypes=[("SubRip", "*.srt")]
            )
            if not path:
                return

            # Show progress
            self.create_progress_window("Exporting SRT", len(self.events))
            
            with open(path, "w", encoding="utf-8") as f:
                for i, e in enumerate(self.events, 1):
                    start = e["time"]
                    end = start + 0.5

                    f.write(f"{i}\n")
                    f.write(f"{format_time(start)} --> {format_time(end)}\n")
                    f.write(f"{e['name']}\n\n")
                    
                    # Update progress every 100 events
                    if i % 100 == 0:
                        self.update_progress(i, f"Writing subtitle {i}/{len(self.events)}...")
            
            self.update_progress(len(self.events), "SRT export complete!")
            time.sleep(0.3)
            self.close_progress()
            
            self.log(f"SRT exported to {path}")

        except Exception:
            self.close_progress()
            traceback.print_exc()

    def export_audio(self):
        try:
            if not self.video_path:
                messagebox.showwarning("No Video", "Please open a video first to export barcode audio.")
                return

            path = filedialog.asksaveasfilename(
                defaultextension=".wav",
                filetypes=[("WAV Audio", "*.wav")]
            )
            if not path:
                return

            # Get calibration values
            x_off = self.bar_x.get()
            y_off = self.bar_y.get()
            width = self.bar_width.get()
            height = self.bar_height.get()
            ignore_t = self.ignore_top.get()
            ignore_b = self.ignore_bottom.get()

            # Show progress
            self.create_progress_window("Exporting Barcode Audio (Spectrogram)", self.total_frames)
            
            def progress_update(current, total):
                percent = int((current / total) * 100) if total > 0 else 0
                if current >= total:
                    self.update_progress(
                        current,
                        f"Writing audio file...",
                        f"Please wait, finalizing WAV file..."
                    )
                else:
                    self.update_progress(
                        current,
                        f"Generating spectrogram audio: {percent}%",
                        f"Frame {current}/{total}"
                    )
            
            self.update_progress(0, "Starting audio generation from video...")
            
            # Generate audio from video spectrogram
            video_to_spectrogram_audio(
                self.video_path,
                path,
                x_off, y_off, width, height,
                ignore_t, ignore_b,
                self.fps,
                progress_callback=progress_update
            )
            
            self.update_progress(self.total_frames, "Audio export complete!")
            time.sleep(0.3)
            self.close_progress()
            
            self.log(f"Barcode spectrogram audio exported to {path}")

        except Exception:
            self.close_progress()
            traceback.print_exc()
            messagebox.showerror("Export Error", "Failed to export barcode audio. Check console for details.")
    
    def auto_export_files(self, export_srt, export_audio):
        """Auto-export files to same directory as video"""
        try:
            if not self.video_path:
                self.log("Video path unknown, skipping auto-export.")
                return
            
            # Get base path without extension
            base_path = os.path.splitext(self.video_path)[0]
            
            exported = []
            
            # Count total export operations
            total_ops = (1 if export_srt else 0) + (1 if export_audio else 0)
            
            if total_ops == 0:
                return
            
            current_op = 0
            
            self.create_progress_window("Auto-Exporting Files", self.total_frames if export_audio else len(self.events))
            
            # Export SRT
            if export_srt:
                if not self.events:
                    self.log("No decoded events for SRT export.")
                else:
                    current_op += 1
                    self.update_progress(0, f"Exporting SRT ({current_op}/{total_ops})...")
                    
                    srt_path = base_path + "_decoded.srt"
                    with open(srt_path, "w", encoding="utf-8") as f:
                        for i, e in enumerate(self.events, 1):
                            start = e["time"]
                            end = start + 0.5

                            f.write(f"{i}\n")
                            f.write(f"{format_time(start)} --> {format_time(end)}\n")
                            f.write(f"{e['name']}\n\n")
                    
                    exported.append(f"SRT: {srt_path}")
                    self.log(f"✓ Auto-exported SRT to {srt_path}")
            
            # Export Audio as spectrogram
            if export_audio:
                current_op += 1
                
                # Get calibration values
                x_off = self.bar_x.get()
                y_off = self.bar_y.get()
                width = self.bar_width.get()
                height = self.bar_height.get()
                ignore_t = self.ignore_top.get()
                ignore_b = self.ignore_bottom.get()
                
                audio_path = base_path + "_barcode.wav"
                
                def progress_update(current, total):
                    percent = int((current / total) * 100) if total > 0 else 0
                    if current >= total:
                        self.update_progress(
                            current,
                            f"Writing audio file ({current_op}/{total_ops})...",
                            f"Please wait, finalizing WAV file..."
                        )
                    else:
                        self.update_progress(
                            current,
                            f"Generating spectrogram audio ({current_op}/{total_ops}): {percent}%",
                            f"Frame {current}/{total}"
                        )
                
                video_to_spectrogram_audio(
                    self.video_path,
                    audio_path,
                    x_off, y_off, width, height,
                    ignore_t, ignore_b,
                    self.fps,
                    progress_callback=progress_update
                )
                
                exported.append(f"Audio: {audio_path}")
                self.log(f"✓ Auto-exported barcode spectrogram audio to {audio_path}")
            
            self.update_progress(self.total_frames if export_audio else len(self.events), "All exports complete!")
            time.sleep(0.5)
            self.close_progress()
            
            if exported:
                messagebox.showinfo("Export Complete", 
                                   "Files exported successfully:\n\n" + "\n".join(exported))
        
        except Exception:
            self.close_progress()
            traceback.print_exc()
            messagebox.showerror("Export Error", "Failed to auto-export files.")

# =========================
# Main
# =========================

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = App(root)
        root.mainloop()
    except Exception:
        traceback.print_exc()