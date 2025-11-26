#!/usr/bin/env python3
"""
AOI2List GUI – USGS LiDAR AOI Tile Finder & LAZ Downloader
Developed by: Bill Fleming (TechBill)
Contact: billyjackrootbeer (at sign) gmail (dot) com
Donations: 
https://www.paypal.com/paypalme/techbill
https://www.buymeacoffee.com/techbill

Description:
------------------------------------
Graphical front-end for AOI2List. Given a center latitude/longitude and a
square area in square miles, this tool queries USGS ScienceBase for LiDAR
(LAZ) tiles that intersect the area of interest (AOI), displays the tiles
in a selectable list, and allows the user to:

- Save selected LAZ URLs to a text file (one URL per line)
- Download selected LAZ files directly with a progress dialog and cancel button

This GUI uses the helper functions defined in aoi2list.py:
- query_sciencebase_for_aoi(...)

License and usage:
------------------------------------
This software is provided free for personal and educational use.
If you find this tool helpful and would like to support ongoing development,
donations are appreciated at the link above.

Commercial / business use:
If you wish to use this software in a commercial product, website,
corporate workflow, or other revenue-producing environment, please
request permission from the developer first.

This software is provided “as-is” with no warranty of any kind.
Permission is granted to use, modify, and distribute this software
for non-commercial purposes, provided that credit to the original
developer (Bill Fleming) is retained in derivative works.

By using this software, you agree that the author is not liable
for any damages or loss of data that may occur from its use.

Requires:
    - Python 3
    - requests
    - Tkinter (typically included with Python on Windows and macOS)

"""

import os
import time
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser

import requests

from aoi2list import query_sciencebase_for_aoi


class DownloadProgressDialog(tk.Toplevel):
    """
    Popup window that shows download progress for LAZ files.
    Updated only from the main thread.
    """

    def __init__(self, master, cancel_event: threading.Event):
        super().__init__(master)
        self.title("Downloading LAZ tiles")
        self.geometry("480x190")
        self.resizable(False, False)
        self.transient(master)  # stay on top of parent

        self.cancel_event = cancel_event
        self._canceled = False

        # Center over parent
        self.update_idletasks()
        if master is not None:
            try:
                mx = master.winfo_rootx()
                my = master.winfo_rooty()
                mw = master.winfo_width()
                mh = master.winfo_height()
                w = self.winfo_width()
                h = self.winfo_height()
                x = mx + (mw - w) // 2
                y = my + (mh - h) // 2
                self.geometry(f"+{x}+{y}")
            except tk.TclError:
                pass

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="Preparing download...")
        ttk.Label(frame, textvariable=self.status_var, wraplength=440, justify="left").pack(
            side=tk.TOP, anchor="w"
        )

        self.progress = ttk.Progressbar(
            frame,
            orient="horizontal",
            mode="determinate",
            length=440,
            maximum=100.0,
        )
        self.progress.pack(side=tk.TOP, fill=tk.X, pady=(8, 4))

        # Cancel button
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side=tk.TOP, fill=tk.X, pady=(4, 0))
        self.cancel_button = ttk.Button(btn_frame, text="Cancel", command=self._on_cancel)
        self.cancel_button.pack(side=tk.RIGHT)

        # Internal state for speed/percent calc
        self._start_time = time.time()
        self._downloaded = 0
        self._total_bytes = None
        self._file_index = 0
        self._total_files = 0
        self._filename = ""

        # If user clicks window close "X", treat as cancel
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _on_cancel(self):
        if not self._canceled:
            self._canceled = True
            self.cancel_event.set()
            self.status_var.set("Canceling downloads...")
            self.cancel_button.config(state="disabled")

    def start_file(self, file_index, total_files, filename, total_bytes):
        """
        Called at the start of each file.
        """
        self._file_index = file_index
        self._total_files = total_files
        self._filename = filename
        self._total_bytes = total_bytes
        self._downloaded = 0
        self._start_time = time.time()

        self.progress["value"] = 0
        self.progress["maximum"] = 100.0
        self.progress["mode"] = "determinate"

        self._update_status()

    def update_chunk(self, chunk_len):
        """
        Called for each downloaded chunk.
        """
        self._downloaded += chunk_len
        self._update_status()

    def show_file_error(self, url: str, message: str, attempt: int, max_retries: int):
        """
        Show an error message for the current file.
        """
        txt = (
            f"Error downloading {self._file_index}/{self._total_files}:\n"
            f"{self._filename}\n"
            f"{message}"
        )
        if attempt < max_retries:
            txt += f"\nRetrying ({attempt}/{max_retries})..."
        else:
            txt += "\nGiving up on this file."
        self.status_var.set(txt)
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    def _update_status(self):
        elapsed = time.time() - self._start_time
        speed_bps = self._downloaded / elapsed if elapsed > 0 else 0.0
        speed_mb_s = speed_bps / (1024 * 1024)
        downloaded_mb = self._downloaded / (1024 * 1024)

        if self._total_bytes:
            total_mb = self._total_bytes / (1024 * 1024)
            pct = (self._downloaded / self._total_bytes) * 100
            try:
                self.progress["value"] = pct
            except tk.TclError:
                return  # dialog gone; bail
            status_text = (
                f"Downloading {self._file_index}/{self._total_files}: {self._filename}\n"
                f"{pct:5.1f}% ({downloaded_mb:,.1f} / {total_mb:,.1f} MB) "
                f"at {speed_mb_s:,.1f} MB/s"
            )
        else:
            # Unknown total size; just cycle bar 0–100 for "activity"
            try:
                val = self.progress["value"] + 2
                if val > 100:
                    val = 0
                self.progress["value"] = val
            except tk.TclError:
                return
            status_text = (
                f"Downloading {self._file_index}/{self._total_files}: {self._filename}\n"
                f"{downloaded_mb:,.1f} MB downloaded at {speed_mb_s:,.1f} MB/s"
            )

        self.status_var.set(status_text)
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    def close(self):
        try:
            self.destroy()
        except tk.TclError:
            pass


class TileSelectionWindow(tk.Toplevel):
    """
    A scrollable window showing all tiles and checkboxes so the user
    can choose which tiles to include in the download list and/or download.
    """

    def __init__(self, master, tiles):
        super().__init__(master)
        self.title("Select Tiles to Include")
        self.tiles = tiles  # list of dicts from extract_laz_tiles_with_metadata
        self.vars = []      # list of BooleanVar for checkboxes

        self.geometry("900x430")
        self.minsize(800, 320)

        self.status_var = None
        self.download_button = None

        self._build_ui()

    def _build_ui(self):
        # Top frame for buttons + status
        top_frame = ttk.Frame(self, padding=(10, 10, 10, 5))
        top_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top_frame, text="Select All", command=self.select_all).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(top_frame, text="Clear All", command=self.clear_all).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(
            top_frame,
            text="Save Selected to File",
            command=self.save_selected
        ).pack(side=tk.LEFT, padx=(20, 5))

        self.download_button = ttk.Button(
            top_frame,
            text="Download Selected LAZ",
            command=self.download_selected
        )
        self.download_button.pack(side=tk.LEFT, padx=(0, 5))

        # Right side: status label
        self.status_var = tk.StringVar()
        self.status_var.set(f"{len(self.tiles)} tiles loaded.")
        ttk.Label(top_frame, textvariable=self.status_var).pack(
            side=tk.RIGHT, anchor="e"
        )

        # Scrollable area
        container = ttk.Frame(self)
        container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        canvas = tk.Canvas(container)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.inner_frame = ttk.Frame(canvas)

        self.inner_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Column headers
        header_style = {"padding": (3, 1)}
        ttk.Label(self.inner_frame, text="Include", **header_style).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(self.inner_frame, text="Tile ID", **header_style).grid(
            row=0, column=1, sticky="w"
        )
        ttk.Label(self.inner_frame, text="Flight Date", **header_style).grid(
            row=0, column=2, sticky="w"
        )
        ttk.Label(
            self.inner_frame,
            text="BBox (minLon,minLat / maxLon,maxLat)",
            **header_style
        ).grid(row=0, column=3, sticky="w")

        # Rows for tiles
        for idx, t in enumerate(self.tiles, start=1):
            var = tk.BooleanVar(value=True)
            self.vars.append(var)

            cb = ttk.Checkbutton(self.inner_frame, variable=var)
            cb.grid(row=idx, column=0, sticky="w", padx=(0, 5))

            tile_id = t.get("tile_id", "")
            flight_date = t.get("flight_date", "")

            min_lon = t.get("min_lon")
            min_lat = t.get("min_lat")
            max_lon = t.get("max_lon")
            max_lat = t.get("max_lat")

            if None not in (min_lon, min_lat, max_lon, max_lat):
                bbox_str = f"{min_lon:.5f}, {min_lat:.5f} / {max_lon:.5f}, {max_lat:.5f}"
            else:
                bbox_str = ""

            ttk.Label(self.inner_frame, text=tile_id, padding=(3, 1)).grid(
                row=idx, column=1, sticky="w"
            )
            ttk.Label(self.inner_frame, text=flight_date, padding=(3, 1)).grid(
                row=idx, column=2, sticky="w"
            )
            ttk.Label(self.inner_frame, text=bbox_str, padding=(3, 1)).grid(
                row=idx, column=3, sticky="w"
            )

    def select_all(self):
        for v in self.vars:
            v.set(True)

    def clear_all(self):
        for v in self.vars:
            v.set(False)

    def _get_selected_tiles(self):
        """Return list of tile dicts for which the checkbox is True and have URLs."""
        selected = []
        for t, v in zip(self.tiles, self.vars):
            if v.get():
                url = t.get("url")
                if url:
                    selected.append(t)
        return selected

    def save_selected(self):
        # Collect selected URLs
        selected_tiles = self._get_selected_tiles()
        selected_urls = [t["url"].strip() for t in selected_tiles]

        if not selected_urls:
            messagebox.showwarning(
                "No Selection",
                "No tiles selected. Please select at least one tile."
            )
            return

        default_name = "downloadlist.txt"
        home = os.path.expanduser("~")
        save_path = filedialog.asksaveasfilename(
            title="Save download list",
            defaultextension=".txt",
            initialfile=default_name,
            initialdir=home,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )

        if not save_path:
            self.status_var.set("Save canceled.")
            return

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                for url in selected_urls:
                    f.write(url + "\n")
            messagebox.showinfo(
                "Saved",
                f"Saved {len(selected_urls)} URLs to:\n{save_path}"
            )
            self.status_var.set(f"Saved {len(selected_urls)} URLs.")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save file:\n{e}")
            self.status_var.set("Save failed.")

    def download_selected(self):
        """Download the selected LAZ files using a background thread."""
        selected_tiles = self._get_selected_tiles()
        if not selected_tiles:
            messagebox.showwarning(
                "No Selection",
                "No tiles selected. Please select at least one tile."
            )
            return

        count = len(selected_tiles)

        # Helper to derive filename from URL
        def filename_from_url(url: str) -> str:
            name = url.rsplit("/", 1)[-1]
            if not name.lower().endswith(".laz"):
                name = name + ".laz"
            return name

        files_to_download = []
        home = os.path.expanduser("~")

        if count == 1:
            tile = selected_tiles[0]
            url = tile["url"]
            default_name = filename_from_url(url)

            save_path = filedialog.asksaveasfilename(
                title="Save LAZ file",
                defaultextension=".laz",
                initialfile=default_name,
                initialdir=home,
                filetypes=[("LAZ files", "*.laz"), ("All files", "*.*")]
            )
            if not save_path:
                self.status_var.set("Download canceled.")
                return

            files_to_download.append(
                {
                    "url": url,
                    "dest": save_path,
                    "filename": os.path.basename(save_path) or default_name,
                }
            )
        else:
            # Multiple files: choose a folder
            folder = filedialog.askdirectory(
                title=f"Choose folder to save {count} LAZ files",
                initialdir=home,
            )
            if not folder:
                self.status_var.set("Download canceled.")
                return

            for tile in selected_tiles:
                url = tile["url"]
                filename = filename_from_url(url)
                dest_path = os.path.join(folder, filename)
                files_to_download.append(
                    {"url": url, "dest": dest_path, "filename": filename}
                )

        cancel_event = threading.Event()
        progress = DownloadProgressDialog(self, cancel_event)
        event_queue = queue.Queue()
        context = {"done": False}

        # Disable download button while busy
        if self.download_button is not None:
            self.download_button.config(state="disabled")
        self.status_var.set("Starting download...")

        def worker():
            """
            Background thread: does the actual HTTP downloads and pushes
            progress events into event_queue.
            """
            chunk_size = 1024 * 1024  # 1 MB
            total_files = len(files_to_download)
            success = 0
            failures = 0
            canceled = False
            max_retries = 3

            try:
                for idx, fi in enumerate(files_to_download, start=1):
                    if cancel_event.is_set():
                        canceled = True
                        break

                    url = fi["url"]
                    dest_path = fi["dest"]
                    filename = fi["filename"]

                    attempt = 0
                    file_ok = False

                    while attempt < max_retries and not cancel_event.is_set():
                        attempt += 1
                        try:
                            with requests.get(
                                url,
                                stream=True,
                                timeout=(10, 60),  # (connect, read) seconds
                            ) as resp:
                                resp.raise_for_status()

                                total_bytes = resp.headers.get("Content-Length")
                                try:
                                    total_bytes = (
                                        int(total_bytes) if total_bytes is not None else None
                                    )
                                except ValueError:
                                    total_bytes = None

                                folder = os.path.dirname(dest_path)
                                if folder:
                                    os.makedirs(folder, exist_ok=True)

                                # Tell main thread a new file started (or restarted)
                                event_queue.put(
                                    {
                                        "type": "start_file",
                                        "file_index": idx,
                                        "total_files": total_files,
                                        "filename": filename,
                                        "total_bytes": total_bytes,
                                    }
                                )

                                with open(dest_path, "wb") as f:
                                    for chunk in resp.iter_content(chunk_size=chunk_size):
                                        if cancel_event.is_set():
                                            canceled = True
                                            break
                                        if not chunk:
                                            continue
                                        f.write(chunk)
                                        # Tell main thread about this chunk
                                        event_queue.put(
                                            {
                                                "type": "chunk",
                                                "bytes": len(chunk),
                                            }
                                        )

                            if canceled:
                                break

                            # If we got here, this attempt succeeded
                            file_ok = True
                            break

                        except Exception as e:
                            # Tell main thread about this error (for display)
                            event_queue.put(
                                {
                                    "type": "file_error",
                                    "url": url,
                                    "message": str(e),
                                    "filename": filename,
                                    "attempt": attempt,
                                    "max_retries": max_retries,
                                    "file_index": idx,
                                    "total_files": total_files,
                                }
                            )

                    if canceled:
                        break

                    if file_ok:
                        success += 1
                    else:
                        failures += 1

                # All done or canceled
                if canceled:
                    event_queue.put(
                        {
                            "type": "canceled",
                            "success": success,
                            "failures": failures,
                        }
                    )
                else:
                    event_queue.put(
                        {
                            "type": "finished",
                            "success": success,
                            "failures": failures,
                            "multi": (total_files > 1),
                            "folder": os.path.dirname(files_to_download[0]["dest"])
                            if total_files > 1
                            else files_to_download[0]["dest"],
                        }
                    )

            except Exception as e:
                event_queue.put(
                    {
                        "type": "fatal_error",
                        "message": str(e),
                    }
                )

        # Start worker thread
        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # Start polling queue on main thread
        self._poll_download_queue(event_queue, progress, context)

    def _poll_download_queue(self, event_queue, progress_dialog, context):
        """
        Periodically called on the Tk main thread to process events
        from the background worker.
        """
        try:
            while True:
                event = event_queue.get_nowait()
                etype = event.get("type")

                if etype == "start_file":
                    if progress_dialog.winfo_exists():
                        progress_dialog.start_file(
                            event.get("file_index", 1),
                            event.get("total_files", 1),
                            event.get("filename", ""),
                            event.get("total_bytes"),
                        )

                elif etype == "chunk":
                    if progress_dialog.winfo_exists():
                        progress_dialog.update_chunk(event.get("bytes", 0))

                elif etype == "file_error":
                    # Log, and also show in the progress dialog
                    print(
                        f"Error downloading {event.get('url')}: {event.get('message')}"
                    )
                    if progress_dialog.winfo_exists():
                        progress_dialog.show_file_error(
                            url=event.get("url", ""),
                            message=event.get("message", ""),
                            attempt=event.get("attempt", 1),
                            max_retries=event.get("max_retries", 1),
                        )

                elif etype == "finished":
                    context["done"] = True
                    success = event.get("success", 0)
                    failures = event.get("failures", 0)
                    multi = event.get("multi", False)
                    target = event.get("folder", "")

                    if progress_dialog.winfo_exists():
                        progress_dialog.close()

                    if multi:
                        summary = (
                            f"Download complete.\n\n"
                            f"Successfully downloaded: {success}\n"
                            f"Failed: {failures}\n"
                            f"Location:\n{target}"
                        )
                        messagebox.showinfo("Download Summary", summary)
                        self.status_var.set(
                            f"Downloaded {success} file(s), {failures} failed."
                        )
                    else:
                        if failures == 0 and success == 1:
                            messagebox.showinfo(
                                "Download Complete",
                                f"Downloaded 1 file to:\n{target}",
                            )
                            self.status_var.set("Downloaded 1 file.")
                        else:
                            messagebox.showwarning(
                                "Download Issue",
                                f"Downloads completed with {failures} failure(s).",
                            )
                            self.status_var.set(
                                f"Download finished with {failures} failure(s)."
                            )

                    if self.download_button is not None:
                        self.download_button.config(state="normal")

                elif etype == "canceled":
                    context["done"] = True
                    success = event.get("success", 0)
                    failures = event.get("failures", 0)

                    if progress_dialog.winfo_exists():
                        progress_dialog.close()

                    messagebox.showinfo(
                        "Download Canceled",
                        f"Downloads were canceled.\n"
                        f"Completed: {success}\n"
                        f"Failed/partial: {failures}",
                    )
                    self.status_var.set("Download canceled by user.")
                    if self.download_button is not None:
                        self.download_button.config(state="normal")

                elif etype == "fatal_error":
                    context["done"] = True
                    if progress_dialog.winfo_exists():
                        progress_dialog.close()
                    messagebox.showerror(
                        "Download Error",
                        f"A fatal error occurred while downloading:\n{event.get('message')}",
                    )
                    self.status_var.set("Download failed.")
                    if self.download_button is not None:
                        self.download_button.config(state="normal")

        except queue.Empty:
            pass

        # Reschedule polling if not done
        if not context["done"]:
            self.after(100, self._poll_download_queue, event_queue, progress_dialog, context)


class AoiApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("AOI to LAZ Download List (ScienceBase)")
        self.geometry("500x310")
        self.resizable(False, False)

        self.donate_url = "https://www.paypal.com/paypalme/techbill"

        main = ttk.Frame(self, padding=15)
        main.grid(row=0, column=0, sticky="nsew")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.option_add("*Font", "Helvetica 11")

        # Input variables
        self.lat_var = tk.StringVar()
        self.lon_var = tk.StringVar()
        self.sqmi_var = tk.StringVar()   # user must fill in

        # Row 0: Latitude
        ttk.Label(main, text="Latitude (decimal):").grid(
            row=0, column=0, sticky="e", pady=5, padx=(0, 8)
        )
        self.lat_entry = ttk.Entry(main, textvariable=self.lat_var, width=20)
        self.lat_entry.grid(row=0, column=1, sticky="w", pady=5)

        # Row 1: Longitude
        ttk.Label(main, text="Longitude (decimal):").grid(
            row=1, column=0, sticky="e", pady=5, padx=(0, 8)
        )
        self.lon_entry = ttk.Entry(main, textvariable=self.lon_var, width=20)
        self.lon_entry.grid(row=1, column=1, sticky="w", pady=5)

        # Row 2: Sq miles
        ttk.Label(main, text="Area (square miles):").grid(
            row=2, column=0, sticky="e", pady=5, padx=(0, 8)
        )
        self.sqmi_entry = ttk.Entry(main, textvariable=self.sqmi_var, width=20)
        self.sqmi_entry.grid(row=2, column=1, sticky="w", pady=5)

        # Row 3: Hint label
        hint = (
            "Example (Dallas, TX area):\n"
            "Lat: 32.7767   Lon: -96.7970   Sq mi: 6"
        )
        ttk.Label(main, text=hint, justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(5, 10)
        )

        # Row 4: Generate button
        self.run_button = ttk.Button(
            main,
            text="Find Tiles (ScienceBase)",
            command=self.on_generate
        )
        self.run_button.grid(row=4, column=0, columnspan=2, pady=10, ipadx=10, ipady=4)

        # Row 5: Donation note
        donate_note = ttk.Label(
            main,
            text="If you like this tool and it helps your work, please consider supporting it:",
            wraplength=460,
            justify="left"
        )
        donate_note.grid(row=5, column=0, columnspan=2, sticky="w", pady=(5, 0))

        # Row 6: Clickable PayPal link
        donate_link = tk.Label(
            main,
            text="Donate via PayPal",
            fg="blue",
            cursor="hand2",
            font=("Helvetica", 11, "underline")
        )
        donate_link.grid(row=6, column=0, columnspan=2, sticky="w", pady=(2, 8))
        donate_link.bind("<Button-1>", lambda e: webbrowser.open(self.donate_url))

        # Row 7: Status bar
        self.status_var = tk.StringVar(value="Ready.")
        status_label = ttk.Label(main, textvariable=self.status_var, foreground="gray")
        status_label.grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.bind("<Return>", self.on_generate_event)
        self.lat_entry.focus()

    def set_status(self, text: str):
        self.status_var.set(text)
        self.update_idletasks()

    def on_generate_event(self, event):
        self.on_generate()

    def on_generate(self):
        lat = self.lat_var.get().strip()
        lon = self.lon_var.get().strip()
        sqmi = self.sqmi_var.get().strip()

        if not lat or not lon or not sqmi:
            messagebox.showwarning(
                "Missing Input",
                "Please fill in latitude, longitude, and square miles."
            )
            return

        try:
            lat_f = float(lat)
            lon_f = float(lon)
            sqmi_f = float(sqmi)
            if sqmi_f <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Invalid Input",
                "Latitude, longitude, and square miles must be numeric, and sqmi > 0."
            )
            return

        self.run_button.config(state="disabled")
        self.set_status("Querying ScienceBase...")

        try:
            tiles, info_msg = query_sciencebase_for_aoi(lat_f, lon_f, sqmi_f)
        except Exception as e:
            messagebox.showerror("Error", f"Error querying ScienceBase:\n{e}")
            self.set_status("Error querying ScienceBase.")
            self.run_button.config(state="normal")
            return

        if not tiles:
            messagebox.showinfo("No Results", f"No tiles found.\n\n{info_msg}")
            self.set_status("No results.")
            self.run_button.config(state="normal")
            return

        messagebox.showinfo(
            "Tiles Found",
            f"{info_msg}\n\nNext: choose which tiles to include in the list or download."
        )
        self.set_status(f"{len(tiles)} tiles found.")

        # Open selection window
        TileSelectionWindow(self, tiles)

        self.run_button.config(state="normal")


if __name__ == "__main__":
    app = AoiApp()
    app.mainloop()
