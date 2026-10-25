"""
DAV to MP4 Converter - High Performance Desktop GUI
Optimized for Multi-core Processing, GPU Acceleration, and Lightning Fast Remuxing.
"""

import os
import sys
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

try:
    import windnd
    HAS_WINDND = True
except Exception:
    HAS_WINDND = False

from converter_engine import (
    DAVConverter,
    ConversionTask,
    get_vlc_path,
    get_ffmpeg_path
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class QueueItemWidget(ctk.CTkFrame):
    """Widget representing one file in the conversion queue."""

    def __init__(self, master, task: ConversionTask, vlc_path: Optional[str], on_remove_callback):
        super().__init__(master, corner_radius=8, fg_color=("gray88", "#242730"), border_width=1, border_color=("gray75", "#323746"))
        self.task = task
        self.vlc_path = vlc_path
        self.on_remove_callback = on_remove_callback

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # File info container
        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.info_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 4))
        self.info_frame.grid_columnconfigure(0, weight=1)

        # File name
        base_name = os.path.basename(task.input_path)
        self.name_label = ctk.CTkLabel(
            self.info_frame,
            text=base_name,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        )
        self.name_label.grid(row=0, column=0, sticky="w")

        # Sub details
        sub_text = f"{task.file_size_str}  •  {task.preset}  •  {os.path.dirname(task.input_path)}"
        self.details_label = ctk.CTkLabel(
            self.info_frame,
            text=sub_text,
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65"),
            anchor="w"
        )
        self.details_label.grid(row=1, column=0, sticky="w", pady=(1, 4))

        # Status & Progress row
        self.status_frame = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        self.status_frame.grid(row=2, column=0, sticky="ew")

        self.status_badge = ctk.CTkLabel(
            self.status_frame,
            text="⏳ Pending",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#FFA500",
            anchor="w"
        )
        self.status_badge.pack(side="left", padx=(0, 10))

        self.progress_bar = ctk.CTkProgressBar(self.status_frame, height=8, corner_radius=4)
        self.progress_bar.set(0.0)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.stats_label = ctk.CTkLabel(
            self.status_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray65")
        )
        self.stats_label.pack(side="left")

        # Buttons container (Right side)
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=0, column=1, padx=12, pady=8, sticky="e")

        self.retry_btn = ctk.CTkButton(
            self.btn_frame,
            text="🔄 Re-run",
            font=ctk.CTkFont(size=11),
            width=70,
            height=28,
            fg_color=("gray75", "#3a3f50"),
            hover_color=("gray65", "#474d61"),
            command=self.reset_to_pending
        )
        self.retry_btn.pack(side="left", padx=3)

        self.play_vlc_btn = ctk.CTkButton(
            self.btn_frame,
            text="▶ Play in VLC",
            font=ctk.CTkFont(size=11, weight="bold"),
            width=95,
            height=28,
            fg_color="#E57A00",
            hover_color="#CC6A00",
            state="disabled",
            command=self.play_in_vlc
        )
        self.play_vlc_btn.pack(side="left", padx=3)

        self.open_folder_btn = ctk.CTkButton(
            self.btn_frame,
            text="📁 Folder",
            font=ctk.CTkFont(size=11),
            width=70,
            height=28,
            fg_color=("gray75", "#3a3f50"),
            hover_color=("gray65", "#474d61"),
            state="disabled",
            command=self.open_folder
        )
        self.open_folder_btn.pack(side="left", padx=3)

        self.remove_btn = ctk.CTkButton(
            self.btn_frame,
            text="✕",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=28,
            height=28,
            fg_color="transparent",
            hover_color=("#ffdddd", "#502020"),
            text_color=("gray20", "gray80"),
            command=self.remove_self
        )
        self.remove_btn.pack(side="left", padx=(3, 0))

    def update_view(self):
        """Refreshes status and progress on the UI."""
        status = self.task.status
        self.progress_bar.set(self.task.progress)

        if status == "Pending":
            self.status_badge.configure(text="⏳ Pending", text_color="#FFA500")
            self.stats_label.configure(text="")
        elif status == "Converting":
            pct = int(self.task.progress * 100)
            spd = f" ({self.task.speed})" if self.task.speed else ""
            self.status_badge.configure(text=f"⚙ Converting {pct}%", text_color="#3B82F6")
            self.stats_label.configure(text=f"Time: {self.task.time_str}{spd}")
            self.remove_btn.configure(state="disabled")
        elif status == "Completed":
            self.status_badge.configure(text="✓ Completed", text_color="#10B981")
            self.progress_bar.set(1.0)
            self.stats_label.configure(text=f"Converted: {self.task._format_size(self.task.output_path)}")
            self.play_vlc_btn.configure(state="normal")
            self.open_folder_btn.configure(state="normal")
            self.remove_btn.configure(state="normal")
        elif status == "Failed":
            self.status_badge.configure(text="✕ Failed", text_color="#EF4444")
            self.stats_label.configure(text=self.task.error_msg[:30] if self.task.error_msg else "Error")
            self.remove_btn.configure(state="normal")
        elif status == "Cancelled":
            self.status_badge.configure(text="⊘ Cancelled", text_color="#9CA3AF")
            self.remove_btn.configure(state="normal")

    def reset_to_pending(self):
        self.task.status = "Pending"
        self.task.progress = 0.0
        self.task.error_msg = ""
        self.task.speed = ""
        self.task.time_str = "00:00:00"
        self.update_view()

    def play_in_vlc(self):
        """Launches the converted MP4 in VLC or default player."""
        if not os.path.isfile(self.task.output_path):
            messagebox.showerror("File Not Found", f"Converted file does not exist:\n{self.task.output_path}")
            return

        if self.vlc_path and os.path.isfile(self.vlc_path):
            try:
                subprocess.Popen([self.vlc_path, self.task.output_path])
                return
            except Exception as e:
                print(f"Could not launch VLC: {e}")

        try:
            os.startfile(self.task.output_path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open video:\n{e}")

    def open_folder(self):
        """Opens Windows Explorer and highlights the converted file."""
        if os.path.isfile(self.task.output_path):
            subprocess.Popen(f'explorer /select,"{os.path.abspath(self.task.output_path)}"')
        else:
            folder = os.path.dirname(os.path.abspath(self.task.output_path))
            if os.path.isdir(folder):
                subprocess.Popen(f'explorer "{folder}"')

    def remove_self(self):
        if self.on_remove_callback:
            self.on_remove_callback(self)


class DAVConverterApp(ctk.CTk):
    """Main Application Window."""

    DEFAULT_PRESET = "Lightning Remux (Lossless, Instant - Recommended)"

    def __init__(self):
        super().__init__()

        self.title("DAV to MP4 Converter - CCTV Video Player Ready")
        self.geometry("980x740")
        self.minsize(840, 600)

        # Converter Engine
        self.converter = DAVConverter()
        self.vlc_path = self.converter.vlc_path
        self.ffmpeg_path = self.converter.ffmpeg_path

        # Tasks state
        self.tasks: List[ConversionTask] = []
        self.task_widgets: List[QueueItemWidget] = []
        self.is_converting = False
        self.output_dir_custom: Optional[str] = None
        self.output_mode = "same"

        # Build UI
        self._create_widgets()

        # Setup Drag and Drop
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(self, func=self._on_files_dropped)
            except Exception as e:
                self.log(f"Drag and drop hook notice: {e}")

        # Start periodic GUI updater
        self._periodic_update()

    def _create_widgets(self):
        # 1. Top Header Frame
        header = ctk.CTkFrame(self, fg_color=("gray90", "#1E2028"), corner_radius=0, height=72)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title_container = ctk.CTkFrame(header, fg_color="transparent")
        title_container.pack(side="left", padx=20, pady=10)

        title_label = ctk.CTkLabel(
            title_container,
            text="🎬 DAV to MP4 Converter",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(anchor="w")

        vlc_status_text = "✓ VLC Media Player Ready" if self.vlc_path else "ℹ Default Windows Player Ready"
        vlc_status_color = "#10B981" if self.vlc_path else "#F59E0B"
        sub_title = ctk.CTkLabel(
            title_container,
            text=f"High-Speed Surveillance Video Engine  •  Multi-Core Accelerated  •  {vlc_status_text}",
            font=ctk.CTkFont(size=11),
            text_color=vlc_status_color
        )
        sub_title.pack(anchor="w")

        theme_frame = ctk.CTkFrame(header, fg_color="transparent")
        theme_frame.pack(side="right", padx=20)

        theme_switch = ctk.CTkSwitch(
            theme_frame,
            text="Dark Mode",
            command=self._toggle_theme,
            onvalue="Dark",
            offvalue="Light"
        )
        theme_switch.select()
        theme_switch.pack()

        # 2. Main Controls Card
        control_card = ctk.CTkFrame(self, corner_radius=10, fg_color=("gray95", "#1B1E26"))
        control_card.pack(fill="x", padx=16, pady=10)

        # Settings Row 1: Presets & Multi-Core Parallelism
        row1 = ctk.CTkFrame(control_card, fg_color="transparent")
        row1.pack(fill="x", padx=14, pady=(10, 6))

        # Preset Box
        preset_box = ctk.CTkFrame(row1, fg_color="transparent")
        preset_box.pack(side="left", fill="x", expand=True, padx=(0, 20))

        preset_title = ctk.CTkLabel(preset_box, text="Conversion Preset (Speed & Quality):", font=ctk.CTkFont(size=12, weight="bold"))
        preset_title.pack(anchor="w", pady=(0, 2))

        self.preset_combo = ctk.CTkComboBox(
            preset_box,
            values=list(DAVConverter.PRESETS.keys()),
            width=360,
            command=self._on_preset_change
        )
        self.preset_combo.set(self.DEFAULT_PRESET)
        self.preset_combo.pack(anchor="w")

        self.preset_desc_label = ctk.CTkLabel(
            preset_box,
            text=DAVConverter.PRESETS[self.DEFAULT_PRESET]["desc"],
            font=ctk.CTkFont(size=11),
            text_color="#10B981",
            wraplength=380,
            justify="left"
        )
        self.preset_desc_label.pack(anchor="w", pady=(3, 0))

        # Parallelism Box (Utilize Multiple Cores)
        parallel_box = ctk.CTkFrame(row1, fg_color="transparent")
        parallel_box.pack(side="right", padx=(10, 0))

        parallel_title = ctk.CTkLabel(parallel_box, text="⚙ Parallel Processing (Cores):", font=ctk.CTkFont(size=12, weight="bold"))
        parallel_title.pack(anchor="w", pady=(0, 2))

        self.parallel_combo = ctk.CTkComboBox(
            parallel_box,
            values=[
                "1 file at a time",
                "2 files in parallel (Faster)",
                "3 files in parallel (Recommended for 4-core)",
                "4 files in parallel (Maximum Cores)"
            ],
            width=270
        )
        self.parallel_combo.set("2 files in parallel (Faster)")
        self.parallel_combo.pack(anchor="w")

        cpu_tip_label = ctk.CTkLabel(
            parallel_box,
            text="Concurrently processes files across all 8 CPU threads",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray65")
        )
        cpu_tip_label.pack(anchor="w", pady=(3, 0))

        # Settings Row 2: Aspect Ratio Selection
        row_aspect = ctk.CTkFrame(control_card, fg_color="transparent")
        row_aspect.pack(fill="x", padx=14, pady=(2, 6))

        aspect_title = ctk.CTkLabel(row_aspect, text="Aspect Ratio / Stretch:", font=ctk.CTkFont(size=12, weight="bold"))
        aspect_title.pack(side="left", padx=(0, 15))

        self.aspect_combo = ctk.CTkComboBox(
            row_aspect,
            values=[
                "16:9 Widescreen (1080N Stretch - Recommended)",
                "Auto (Detect from file)",
                "4:3 Standard Landscape",
                "8:9 Original Square (960x1080)",
                "9:16 Portrait / Vertical"
            ],
            width=320,
            command=self._on_aspect_change
        )
        self.aspect_combo.set("16:9 Widescreen (1080N Stretch - Recommended)")
        self.aspect_combo.pack(side="left", padx=(0, 12))

        aspect_tip = ctk.CTkLabel(
            row_aspect,
            text="Fixes squished CCTV video so VLC opens in proper widescreen",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray65")
        )
        aspect_tip.pack(side="left")

        # Settings Row 3: Output Destination
        row2 = ctk.CTkFrame(control_card, fg_color="transparent")
        row2.pack(fill="x", padx=14, pady=(6, 10))

        output_title = ctk.CTkLabel(row2, text="Destination Folder:", font=ctk.CTkFont(size=12, weight="bold"))
        output_title.pack(side="left", padx=(0, 15))

        self.out_radio_var = ctk.StringVar(value="same")
        self.radio_same = ctk.CTkRadioButton(
            row2,
            text="Same folder as original .DAV file",
            variable=self.out_radio_var,
            value="same",
            font=ctk.CTkFont(size=11),
            command=self._on_output_mode_change
        )
        self.radio_same.pack(side="left", padx=(0, 15))

        self.radio_custom = ctk.CTkRadioButton(
            row2,
            text="Custom destination...",
            variable=self.out_radio_var,
            value="custom",
            font=ctk.CTkFont(size=11),
            command=self._on_output_mode_change
        )
        self.radio_custom.pack(side="left", padx=(0, 10))

        self.btn_browse_out = ctk.CTkButton(
            row2,
            text="Browse...",
            width=80,
            height=24,
            font=ctk.CTkFont(size=11),
            command=self._browse_custom_output,
            state="disabled"
        )
        self.btn_browse_out.pack(side="left", padx=(0, 10))

        self.custom_path_label = ctk.CTkLabel(
            row2,
            text="",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray65"),
            anchor="w"
        )
        self.custom_path_label.pack(side="left")

        # 3. Add Files / Action Bar
        action_bar = ctk.CTkFrame(self, fg_color="transparent")
        action_bar.pack(fill="x", padx=16, pady=(0, 8))

        btn_add_files = ctk.CTkButton(
            action_bar,
            text="➕ Add .DAV Files",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=34,
            command=self._browse_files
        )
        btn_add_files.pack(side="left", padx=(0, 8))

        btn_add_dir = ctk.CTkButton(
            action_bar,
            text="📁 Add Folder",
            font=ctk.CTkFont(size=12),
            height=34,
            fg_color=("gray75", "#2D323F"),
            hover_color=("gray65", "#3D4353"),
            command=self._browse_directory
        )
        btn_add_dir.pack(side="left", padx=(0, 8))

        btn_clear_done = ctk.CTkButton(
            action_bar,
            text="🧹 Clear Completed",
            font=ctk.CTkFont(size=11),
            height=34,
            fg_color="transparent",
            border_width=1,
            border_color=("gray70", "#4B5563"),
            command=self._clear_completed
        )
        btn_clear_done.pack(side="left", padx=(0, 8))

        btn_clear_all = ctk.CTkButton(
            action_bar,
            text="🗑 Clear All",
            font=ctk.CTkFont(size=11),
            height=34,
            fg_color="transparent",
            border_width=1,
            border_color=("gray70", "#4B5563"),
            hover_color=("#ffdddd", "#502020"),
            command=self._clear_all
        )
        btn_clear_all.pack(side="left")

        self.queue_stats_label = ctk.CTkLabel(
            action_bar,
            text="0 files in queue",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray30", "gray70")
        )
        self.queue_stats_label.pack(side="right", padx=6)

        # 4. Drop Zone & Scrollable Queue
        self.list_container = ctk.CTkFrame(self, fg_color=("gray95", "#15171E"), corner_radius=8)
        self.list_container.pack(fill="both", expand=True, padx=16, pady=4)

        self.empty_label = ctk.CTkLabel(
            self.list_container,
            text="📂 Drag & Drop .DAV files or folders here\nor click '+ Add .DAV Files' above to begin\n\n💡 Tip: 'Lightning Remux' mode converts in 2-5 seconds with 100% original quality!",
            font=ctk.CTkFont(size=14),
            text_color=("gray50", "gray55")
        )
        self.empty_label.pack(expand=True, fill="both", pady=40)

        self.scroll_frame = ctk.CTkScrollableFrame(self.list_container, fg_color="transparent")

        # 5. Expandable Live Logs
        self.log_container = ctk.CTkFrame(self, fg_color=("gray92", "#181B22"), corner_radius=6, height=100)
        self.log_visible = False

        self.log_textbox = ctk.CTkTextbox(
            self.log_container,
            height=90,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=("white", "#101217"),
            wrap="word"
        )
        self.log_textbox.pack(fill="both", expand=True, padx=6, pady=6)

        # 6. Bottom Master Footer
        footer = ctk.CTkFrame(self, fg_color=("gray90", "#1E2028"), corner_radius=0, height=72)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        # Overall progress
        progress_container = ctk.CTkFrame(footer, fg_color="transparent")
        progress_container.pack(side="left", fill="x", expand=True, padx=20, pady=12)

        self.overall_label = ctk.CTkLabel(
            progress_container,
            text="Ready to convert",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w"
        )
        self.overall_label.pack(fill="x", pady=(0, 4))

        self.overall_progress = ctk.CTkProgressBar(progress_container, height=10, corner_radius=5)
        self.overall_progress.set(0.0)
        self.overall_progress.pack(fill="x")

        # Footer Actions
        footer_btns = ctk.CTkFrame(footer, fg_color="transparent")
        footer_btns.pack(side="right", padx=20, pady=12)

        self.btn_toggle_log = ctk.CTkButton(
            footer_btns,
            text="📋 View Logs",
            width=90,
            height=36,
            font=ctk.CTkFont(size=11),
            fg_color=("gray75", "#2D323F"),
            hover_color=("gray65", "#3D4353"),
            command=self._toggle_logs
        )
        self.btn_toggle_log.pack(side="left", padx=(0, 10))

        self.btn_stop = ctk.CTkButton(
            footer_btns,
            text="⏹ Stop",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=80,
            height=36,
            fg_color="#EF4444",
            hover_color="#DC2626",
            state="disabled",
            command=self._stop_conversion
        )
        self.btn_stop.pack(side="left", padx=(0, 10))

        self.btn_start = ctk.CTkButton(
            footer_btns,
            text="Convert to MP4",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=150,
            height=36,
            fg_color="#10B981",
            hover_color="#059669",
            command=self._start_conversion
        )
        self.btn_start.pack(side="left")

    def _toggle_theme(self):
        curr = ctk.get_appearance_mode()
        ctk.set_appearance_mode("Light" if curr == "Dark" else "Dark")

    def _on_preset_change(self, choice):
        info = DAVConverter.PRESETS.get(choice, {})
        desc = info.get("desc", "")
        self.preset_desc_label.configure(text=desc)

        # Update all tasks and reset to Pending so the new mode takes effect immediately
        for t in self.tasks:
            t.preset = choice
            t.status = "Pending"
            t.progress = 0.0
        for w in self.task_widgets:
            sub_text = f"{w.task.file_size_str}  •  {w.task.preset}  •  {os.path.dirname(w.task.input_path)}"
            w.details_label.configure(text=sub_text)
            w.update_view()

    def _parse_selected_aspect(self) -> str:
        val = self.aspect_combo.get()
        if "16:9" in val:
            return "16:9"
        if "4:3" in val:
            return "4:3"
        if "9:16" in val:
            return "9:16"
        if "8:9" in val:
            return "8:9"
        return "Auto"

    def _on_aspect_change(self, choice):
        ratio = self._parse_selected_aspect()
        for t in self.tasks:
            t.aspect_ratio = ratio
        self.log(f"Display aspect ratio set to: {ratio}")

    def _on_output_mode_change(self):
        mode = self.out_radio_var.get()
        if mode == "custom":
            self.btn_browse_out.configure(state="normal")
            if not self.output_dir_custom:
                self._browse_custom_output()
        else:
            self.btn_browse_out.configure(state="disabled")
            self.custom_path_label.configure(text="")

    def _browse_custom_output(self):
        chosen = filedialog.askdirectory(title="Select Destination Folder for Converted MP4 Files")
        if chosen:
            self.output_dir_custom = chosen
            self.custom_path_label.configure(text=chosen)
        else:
            if not self.output_dir_custom:
                self.out_radio_var.set("same")
                self.btn_browse_out.configure(state="disabled")

    def _browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Select DAV Video Files",
            filetypes=[
                ("DAV Surveillance Files", "*.dav;*.DAV"),
                ("All Supported Videos", "*.dav;*.DAV;*.h264;*.264;*.mp4"),
                ("All Files", "*.*")
            ]
        )
        if paths:
            self.add_files(paths)

    def _browse_directory(self):
        folder = filedialog.askdirectory(title="Select Folder Containing .DAV Files")
        if folder:
            found = []
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(('.dav', '.264', '.h264')):
                        found.append(os.path.join(root, f))
            if found:
                self.add_files(found)
            else:
                messagebox.showinfo("No Files Found", f"No .dav files were found in:\n{folder}")

    def _on_files_dropped(self, files):
        file_list = []
        for item in files:
            path = item.decode('utf-8', errors='replace') if isinstance(item, bytes) else str(item)
            if os.path.isdir(path):
                for root, _, fs in os.walk(path):
                    for f in fs:
                        if f.lower().endswith(('.dav', '.264', '.h264')):
                            file_list.append(os.path.join(root, f))
            elif os.path.isfile(path):
                if path.lower().endswith(('.dav', '.264', '.h264', '.mp4')):
                    file_list.append(path)

        if file_list:
            self.add_files(file_list)

    def add_files(self, paths: List[str]):
        """Adds files to the queue without duplicates."""
        existing_paths = {t.input_path for t in self.tasks}
        added_count = 0
        preset = self.preset_combo.get()

        for p in paths:
            clean_path = os.path.normpath(p)
            if clean_path in existing_paths:
                # If already in queue, reset it to Pending with current preset
                for t in self.tasks:
                    if t.input_path == clean_path:
                        t.status = "Pending"
                        t.progress = 0.0
                        t.preset = preset
                for w in self.task_widgets:
                    if w.task.input_path == clean_path:
                        w.update_view()
                continue

            base, _ = os.path.splitext(clean_path)
            if self.out_radio_var.get() == "custom" and self.output_dir_custom:
                out_name = os.path.splitext(os.path.basename(clean_path))[0] + ".mp4"
                out_path = os.path.join(self.output_dir_custom, out_name)
            else:
                out_path = base + ".mp4"

            task = ConversionTask(clean_path, out_path, preset=preset, aspect_ratio=self._parse_selected_aspect())
            self.tasks.append(task)
            existing_paths.add(clean_path)

            widget = QueueItemWidget(self.scroll_frame, task, self.vlc_path, self._remove_task_widget)
            widget.pack(fill="x", pady=4, padx=4)
            self.task_widgets.append(widget)
            added_count += 1

        if added_count > 0:
            self._update_queue_ui()
            self.log(f"Added {added_count} file(s) to queue.")

    def _remove_task_widget(self, widget: QueueItemWidget):
        if widget in self.task_widgets:
            idx = self.task_widgets.index(widget)
            task = self.tasks[idx]
            if task.status == "Converting":
                return
            self.tasks.pop(idx)
            self.task_widgets.pop(idx)
            widget.destroy()
            self._update_queue_ui()

    def _clear_completed(self):
        if self.is_converting:
            return
        to_remove = []
        for w, t in zip(self.task_widgets, self.tasks):
            if t.status in ("Completed", "Cancelled"):
                to_remove.append((w, t))

        for w, t in to_remove:
            self.task_widgets.remove(w)
            self.tasks.remove(t)
            w.destroy()

        self._update_queue_ui()

    def _clear_all(self):
        if self.is_converting:
            messagebox.showwarning("Busy", "Cannot clear queue while conversion is in progress. Please stop conversion first.")
            return

        for w in self.task_widgets:
            w.destroy()
        self.task_widgets.clear()
        self.tasks.clear()
        self._update_queue_ui()

    def _update_queue_ui(self):
        count = len(self.tasks)
        if count == 0:
            self.scroll_frame.pack_forget()
            self.empty_label.pack(expand=True, fill="both", pady=40)
            self.queue_stats_label.configure(text="0 files in queue")
        else:
            self.empty_label.pack_forget()
            self.scroll_frame.pack(fill="both", expand=True, padx=4, pady=4)
            completed_count = sum(1 for t in self.tasks if t.status == "Completed")
            self.queue_stats_label.configure(text=f"{count} files ({completed_count} completed)")

    def _toggle_logs(self):
        if self.log_visible:
            self.log_container.pack_forget()
            self.btn_toggle_log.configure(text="📋 View Logs")
            self.log_visible = False
        else:
            self.log_container.pack(fill="x", padx=16, pady=(0, 8), before=self.list_container.master.winfo_children()[-1])
            self.btn_toggle_log.configure(text="✕ Hide Logs")
            self.log_visible = True

    def log(self, message: str):
        """Appends log entry to log textbox and stdout."""
        ts = time.strftime("[%H:%M:%S] ")
        line = ts + str(message) + "\n"
        try:
            # Safe print to stdout
            sys.stdout.buffer.write(line.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            pass
        try:
            self.log_textbox.insert("end", line)
            self.log_textbox.see("end")
        except Exception:
            pass

    def _start_conversion(self):
        if self.is_converting:
            return

        if not self.tasks:
            messagebox.showinfo("Queue Empty", "Please add at least one .DAV file to the queue first.")
            return

        pending_tasks = [t for t in self.tasks if t.status in ("Pending", "Failed", "Cancelled")]
        if not pending_tasks:
            # All files were marked Completed - reset all to Pending so user can re-run
            for t in self.tasks:
                t.status = "Pending"
                t.progress = 0.0
                t.error_msg = ""
                t.speed = ""
                t.time_str = "00:00:00"
            for w in self.task_widgets:
                w.update_view()
            pending_tasks = list(self.tasks)

        if self.out_radio_var.get() == "custom" and self.output_dir_custom:
            for t in pending_tasks:
                out_name = os.path.splitext(os.path.basename(t.input_path))[0] + ".mp4"
                t.output_path = os.path.join(self.output_dir_custom, out_name)

        current_preset = self.preset_combo.get()
        current_aspect = self._parse_selected_aspect()
        for t in pending_tasks:
            t.preset = current_preset
            t.aspect_ratio = current_aspect
            for w in self.task_widgets:
                if w.task is t:
                    sub_text = f"{t.file_size_str}  •  {t.preset}  •  {os.path.dirname(t.input_path)}"
                    w.details_label.configure(text=sub_text)

        self.is_converting = True
        self.converter._stop_flag = False
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.preset_combo.configure(state="disabled")
        self.parallel_combo.configure(state="disabled")

        threading.Thread(target=self._conversion_worker, daemon=True).start()

    def _stop_conversion(self):
        if not self.is_converting:
            return
        self.log("Stopping conversion queue...")
        self.converter.stop()
        self.overall_label.configure(text="Stopping...")

    def _conversion_worker(self):
        """Worker thread supporting multi-worker parallel conversion."""
        total = len(self.tasks)
        pending = [t for t in self.tasks if t.status != "Completed"]
        
        # Parse max workers from combobox
        workers_str = self.parallel_combo.get()
        try:
            max_workers = int(workers_str.split()[0])
        except Exception:
            max_workers = 2

        self.log(f"--- Conversion Queue Started ({len(pending)} files, {max_workers} parallel workers) ---")
        self.overall_label.configure(text=f"Converting with {max_workers} parallel thread(s)...")

        def run_task(task: ConversionTask):
            if self.converter._stop_flag:
                return False
            return self.converter.convert_single(task, log_callback=self.log)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(run_task, t): t for t in pending}
            for fut in as_completed(futures):
                if self.converter._stop_flag:
                    break
                completed = sum(1 for t in self.tasks if t.status == "Completed")
                self.overall_progress.set(completed / total if total > 0 else 0.0)
                self.overall_label.configure(text=f"Progress: {completed}/{total} completed")

        self.is_converting = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.preset_combo.configure(state="normal")
        self.parallel_combo.configure(state="normal")

        completed_count = sum(1 for t in self.tasks if t.status == "Completed")
        self.overall_label.configure(text=f"Done: {completed_count}/{total} files converted.")
        self.log(f"--- Queue Finished: {completed_count}/{total} converted successfully ---")

        if completed_count > 0:
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass

    def _periodic_update(self):
        """Periodic UI refresh loop every 120ms."""
        for widget in self.task_widgets:
            widget.update_view()

        self.after(120, self._periodic_update)


def main():
    app = DAVConverterApp()
    app.mainloop()

if __name__ == "__main__":
    main()
