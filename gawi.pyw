import tkinter as tk
from tkinter import ttk, font, messagebox, colorchooser
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw, ImageTk, ImageFont
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
import winsound
import sys
import os
import queue
import subprocess
import shutil
import ctypes
import winreg

# --- CONFIGURATION ---
ICON_FILE = 'icon2.png'
CHECK_INTERVAL = 5
APP_ID = 'Gawi.Pro.v9.9.4'

# Timezone Registry — all supported timezones
TZ_REGISTRY = {
    "ET":  {"display": "Eastern",     "windows_id": "Eastern Standard Time",  "base_offset": -5, "has_dst": True,  "dst_offset": -4},
    "CT":  {"display": "Central",     "windows_id": "Central Standard Time",  "base_offset": -6, "has_dst": True,  "dst_offset": -5},
    "MT":  {"display": "Mountain",    "windows_id": "Mountain Standard Time", "base_offset": -7, "has_dst": True,  "dst_offset": -6},
    "PT":  {"display": "Pacific",     "windows_id": "Pacific Standard Time",  "base_offset": -8, "has_dst": True,  "dst_offset": -7},
    "PHT": {"display": "Philippines", "windows_id": "Singapore Standard Time","base_offset": 8,  "has_dst": False, "dst_offset": 8},
    "JST": {"display": "Japan",       "windows_id": "Tokyo Standard Time",    "base_offset": 9,  "has_dst": False, "dst_offset": 9},
    "GMT": {"display": "GMT/UTC",     "windows_id": "GMT Standard Time",      "base_offset": 0,  "has_dst": False, "dst_offset": 0},
}
TZ_LABELS = sorted(TZ_REGISTRY.keys())

# --- PATH RESOLUTION ---
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    RESOURCE_DIR = sys._MEIPASS
    DATA_DIR = os.path.join(os.getenv('APPDATA'), 'Gawi')
    os.makedirs(DATA_DIR, exist_ok=True)
else:
    # Running as script
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCE_DIR = DATA_DIR

DB_FILE = os.path.join(DATA_DIR, 'gawi.db')

# --- PALETTES ---
PALETTE_DARK = {
    "BG": "#1e1e1e",
    "FG": "#d4d4d4",
    "ACCENT": "#007acc",
    "INPUT": "#2d2d2d",
    "DISABLED": "#1a1a1a",
    "ERROR": "#e74c3c",
    "SUCCESS": "#27ae60",
    "WARNING": "#f39c12",
    "WARNING_DIM": "#d35400",
    "CARD_BG": "#2d2d2d",
    "CARD_INACTIVE": "#151515",
    "TEXT_MAIN": "white",
    "TEXT_DIM": "#aaa",
    "BTN_EDIT": "#d35400",
    "BTN_DEL": "#c0392b",
    "SCROLL_BG": "#1e1e1e",
    "SCROLL_FG": "#444444"
}

PALETTE_LIGHT = {
    "BG": "#e0e0e0",
    "FG": "#333333",
    "ACCENT": "#007acc",
    "INPUT": "#eaeaea",
    "DISABLED": "#c8c8c8",
    "ERROR": "#e74c3c",
    "SUCCESS": "#2ecc71",
    "WARNING": "#f39c12",
    "WARNING_DIM": "#d35400",
    "CARD_BG": "#ebebeb",
    "CARD_INACTIVE": "#d0d0d0",
    "TEXT_MAIN": "#2c3e50",
    "TEXT_DIM": "#6b7b8d",
    "BTN_EDIT": "#e67e22",
    "BTN_DEL": "#e74c3c",
    "SCROLL_BG": "#e0e0e0",
    "SCROLL_FG": "#b0b0b0"
}

class ToolTip(object):
    def __init__(self, widget, text='widget info'):
        self.waittime = 500     # miliseconds
        self.wraplength = 250   # pixels
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)
        self.id = None
        self.tw = None

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.waittime, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        x = y = 0
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(self.tw, text=self.text, justify='left',
                       background="#ffffe0", foreground="#000000", relief='solid', borderwidth=1,
                       font=("tahoma", "8", "normal"), wraplength=self.wraplength)
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tw
        self.tw= None
        if tw:
            tw.destroy()

class GawiApp:
    def __init__(self):
        self.lock_file = os.path.join(DATA_DIR, 'gawi.lock')
        
        if not self.acquire_lock():
            sys.exit(0)
        
        self.hide_console()
        
        if sys.platform == 'win32':
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
            except Exception:
                pass
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Gawi")
        self.root.update_idletasks()
        sh = self.root.winfo_screenheight()
        win_h = min(1020, sh - 100)
        self.root.geometry(f"650x{win_h}")
        self.root.minsize(550, 750)
        self.root.maxsize(800, 2000)
        
        self.icon_path = os.path.join(RESOURCE_DIR, ICON_FILE)
        
        if os.path.exists(self.icon_path):
            try:
                icon_img = tk.PhotoImage(file=self.icon_path)
                self.root.iconphoto(False, icon_img)
            except Exception as e:
                print(f"Icon Load Warning: {e}")

        self.is_dark_mode = True
        self.colors = PALETTE_DARK
        self.root.configure(bg=self.colors["BG"])
        self.root.protocol('WM_DELETE_WINDOW', self.hide_window)
        
        self.init_state_variables()

        self.active_popups = set()
        self.last_trigger_minute = {}
        self.cached_tz = None
        self._saved_work_hours = (7, 0, 17, 0, '0,1,2,3,4', 'ET', 'PHT', 'ET')
        self._window_x = None
        self._window_y = None
        self.icon = None
        self.cache = [] 
        self.add_draft = None
        self.gui_queue = queue.Queue()
        self.editing_id = None
        self._editor_built = False

        self.init_db()
        self.load_global_settings()
        self.reset_stale_reminders()
        self.load_cache_from_db() 
        self.build_ui()
        self.set_title_bar_dark(self.is_dark_mode)
        self.apply_window_position()
        self.update_header()
        
        self.running = True
        self.next_tz_check = self.get_now_utc()
        
        self.checker_thread = threading.Thread(target=self.check_loop, daemon=True)
        self.checker_thread.start()
        
        self.tray_thread = threading.Thread(target=self.start_tray, daemon=True)
        self.tray_thread.start()

        self.process_queue()
        self.root.mainloop()

    def init_state_variables(self):
        self.var_startup = tk.IntVar(value=self.check_startup_state())
        self.popup_color = "#111111"
        self.v_sound = tk.StringVar(value="Default")
        self.day_vars = [tk.IntVar(value=1) for _ in range(7)]
        self.var_use_hours = tk.IntVar(value=0)
        self.v_timezone = tk.StringVar(value="ET")
        self.var_double_check = tk.IntVar(value=0)
        self.var_enable_snooze = tk.IntVar(value=1)
        self.v_max_snoozes = tk.StringVar(value="3")
        self.v_snooze_behavior = tk.StringVar(value="shift")
        self.var_use_pattern = tk.IntVar(value=0)
        self.v_pattern_minute = tk.StringVar(value="00")
        self.v_pattern_timezone = tk.StringVar(value="PHT") 
        self.var_one_time = tk.IntVar(value=0)
        
        self.v_tt_mm = tk.StringVar()
        self.v_tt_dd = tk.StringVar()
        self.v_tt_yy = tk.StringVar(value=datetime.now(timezone.utc).strftime("%y"))
        self.v_tt_hh = tk.StringVar()
        self.v_tt_min = tk.StringVar()
        self.v_tt_tz = tk.StringVar(value="PHT")

        self.var_work_start_h = tk.StringVar(value="07")
        self.var_work_start_m = tk.StringVar(value="00")
        self.var_work_end_h = tk.StringVar(value="17")
        self.var_work_end_m = tk.StringVar(value="00")
        self.var_tz_paused = tk.IntVar(value=0)
        self.var_work_days = [tk.IntVar(value=1 if i <= 4 else 0) for i in range(7)]  # Mon-Fri default
        self.var_work_zone = tk.StringVar(value="ET")
        self.var_personal_zone = tk.StringVar(value="PHT")
        self.var_baseline_display_zone = tk.StringVar(value="ET")
        self.tz_blocks = []
        self.selected_block_id = None
        self._dst_warning_dismissed = False
        self._block_widgets = {}

    # --- TIMEZONE SWITCHER LOGIC ---

    def _get_work_days_str(self):
        return ','.join(str(i) for i in range(7) if self.var_work_days[i].get() == 1)

    def _get_work_days_set(self):
        return set(i for i in range(7) if self.var_work_days[i].get() == 1)

    def _get_work_zone(self):
        return self.var_work_zone.get() or "ET"

    def _get_personal_zone(self):
        return self.var_personal_zone.get() or "PHT"

    def load_tz_blocks(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM tz_blocks ORDER BY sort_order")
            self.tz_blocks = [dict(row) for row in c.fetchall()]
            conn.close()
        except Exception as e:
            print(f"Error loading tz_blocks: {e}")
            self.tz_blocks = []

    def save_tz_block(self, block_dict):
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            if block_dict.get('id'):
                c.execute("""UPDATE tz_blocks SET zone=?, start_h=?, start_m=?, end_h=?, end_m=?, active_days=?
                             WHERE id=?""",
                          (block_dict['zone'], block_dict['start_h'], block_dict['start_m'],
                           block_dict['end_h'], block_dict['end_m'], block_dict['active_days'], block_dict['id']))
            else:
                max_order = 0
                c.execute("SELECT MAX(sort_order) FROM tz_blocks")
                row = c.fetchone()
                if row and row[0] is not None:
                    max_order = row[0] + 1
                c.execute("""INSERT INTO tz_blocks (zone, start_h, start_m, end_h, end_m, active_days, sort_order)
                             VALUES (?,?,?,?,?,?,?)""",
                          (block_dict['zone'], block_dict['start_h'], block_dict['start_m'],
                           block_dict['end_h'], block_dict['end_m'], block_dict['active_days'], max_order))
            conn.commit()
            conn.close()
            self.load_tz_blocks()
            self.gui_queue.put(('REFRESH_TZ_BLOCKS_UI',))
        except Exception as e:
            print(f"Error saving tz_block: {e}")

    def delete_tz_block(self, block_id):
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("DELETE FROM tz_blocks WHERE id=?", (block_id,))
            # Rebuild sort_order
            c.execute("SELECT id FROM tz_blocks ORDER BY sort_order")
            for i, row in enumerate(c.fetchall()):
                c.execute("UPDATE tz_blocks SET sort_order=? WHERE id=?", (i, row[0]))
            conn.commit()
            conn.close()
            self.load_tz_blocks()
            self.gui_queue.put(('REFRESH_TZ_BLOCKS_UI',))
        except Exception as e:
            print(f"Error deleting tz_block: {e}")

    def reorder_tz_blocks(self, block_id, direction):
        idx = None
        for i, b in enumerate(self.tz_blocks):
            if b['id'] == block_id:
                idx = i
                break
        if idx is None:
            return
        swap_idx = idx - 1 if direction == "up" else idx + 1
        if swap_idx < 0 or swap_idx >= len(self.tz_blocks):
            return
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            id_a, order_a = self.tz_blocks[idx]['id'], self.tz_blocks[idx]['sort_order']
            id_b, order_b = self.tz_blocks[swap_idx]['id'], self.tz_blocks[swap_idx]['sort_order']
            c.execute("UPDATE tz_blocks SET sort_order=? WHERE id=?", (order_b, id_a))
            c.execute("UPDATE tz_blocks SET sort_order=? WHERE id=?", (order_a, id_b))
            conn.commit()
            conn.close()
            self.load_tz_blocks()
            self.gui_queue.put(('REFRESH_TZ_BLOCKS_UI',))
        except Exception as e:
            print(f"Error reordering tz_blocks: {e}")

    def find_active_tz_block(self, now_utc):
        for block in sorted(self.tz_blocks, key=lambda b: b['sort_order']):
            zone_time = self.convert_utc_to_zone(now_utc, block['zone'])
            weekday = zone_time.weekday()
            active_days = block.get('active_days') or '0,1,2,3,4'
            if str(weekday) not in active_days.split(','):
                continue
            now_mins = zone_time.hour * 60 + zone_time.minute
            start_mins = block['start_h'] * 60 + block['start_m']
            end_mins = block['end_h'] * 60 + block['end_m']
            if start_mins <= end_mins:
                if start_mins <= now_mins < end_mins:
                    return block['zone']
            else:
                if now_mins >= start_mins or now_mins < end_mins:
                    return block['zone']
        return self._get_personal_zone()

    def detect_tz_blocks_conflicts(self, ref_utc=None):
        if ref_utc is None:
            ref_utc = self.get_now_utc()
        conflicts = []
        blocks = sorted(self.tz_blocks, key=lambda b: b['sort_order'])
        ref_date = ref_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                a, b = blocks[i], blocks[j]
                a_days = (a.get('active_days') or '0,1,2,3,4').split(',')
                b_days = (b.get('active_days') or '0,1,2,3,4').split(',')
                shared_days = set(a_days) & set(b_days)
                if not shared_days:
                    continue
                # Build datetime ranges in UTC using a reference date
                a_start_local = ref_date.replace(hour=a['start_h'], minute=a['start_m'])
                a_end_local = ref_date.replace(hour=a['end_h'], minute=a['end_m'])
                if a_end_local <= a_start_local:
                    a_end_local += timedelta(days=1)
                b_start_local = ref_date.replace(hour=b['start_h'], minute=b['start_m'])
                b_end_local = ref_date.replace(hour=b['end_h'], minute=b['end_m'])
                if b_end_local <= b_start_local:
                    b_end_local += timedelta(days=1)
                # Convert to UTC
                a_cross = a['end_h'] * 60 + a['end_m'] <= a['start_h'] * 60 + a['start_m']
                b_cross = b['end_h'] * 60 + b['end_m'] <= b['start_h'] * 60 + b['start_m']
                a_utc_s = self.convert_zone_to_utc(a_start_local, a['zone'])
                a_utc_e = self.convert_zone_to_utc(a_end_local, a['zone'])
                b_utc_s = self.convert_zone_to_utc(b_start_local, b['zone'])
                b_utc_e = self.convert_zone_to_utc(b_end_local, b['zone'])
                # Cross-midnight blocks span two calendar days, so also check shifted -1 day
                a_intervals = [(a_utc_s, a_utc_e)]
                if a_cross:
                    a_intervals.append((a_utc_s - timedelta(days=1), a_utc_e - timedelta(days=1)))
                b_intervals = [(b_utc_s, b_utc_e)]
                if b_cross:
                    b_intervals.append((b_utc_s - timedelta(days=1), b_utc_e - timedelta(days=1)))
                # Overlap check: any pair of intervals overlaps
                overlap_found = False
                for as_, ae_ in a_intervals:
                    for bs_, be_ in b_intervals:
                        if as_ < be_ and bs_ < ae_:
                            overlap_found = True
                            break
                    if overlap_found:
                        break
                if overlap_found:
                    day_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
                    shared_str = ",".join(day_names.get(int(d), d) for d in sorted(shared_days))
                    explanation = f"{a['zone']} {a['start_h']:02d}:{a['start_m']:02d}-{a['end_h']:02d}:{a['end_m']:02d} overlaps {b['zone']} {b['start_h']:02d}:{b['start_m']:02d}-{b['end_h']:02d}:{b['end_m']:02d} on {shared_str}"
                    conflicts.append((a['id'], b['id'], explanation))
        return conflicts

    def get_dst_warning_if_needed(self, now_utc):
        # Check if any DST transition is within 7 days for zones used in blocks
        dst_zones = set()
        for block in self.tz_blocks:
            cfg = TZ_REGISTRY.get(block['zone'])
            if cfg and cfg['has_dst']:
                dst_zones.add(block['zone'])
        if not dst_zones:
            return None
        year = now_utc.year
        march_1st = datetime(year, 3, 1)
        days_to_2nd_sun = (6 - march_1st.weekday() + 7) % 7 + 7
        dst_start = march_1st + timedelta(days=days_to_2nd_sun, hours=2)
        nov_1st = datetime(year, 11, 1)
        days_to_1st_sun = (6 - nov_1st.weekday() + 7) % 7
        dst_end = nov_1st + timedelta(days=days_to_1st_sun, hours=2)
        for transition in [dst_start, dst_end]:
            days_until = (transition - now_utc).total_seconds() / 86400
            if 0 < days_until <= 7:
                # Check if conflicts change after transition
                pre_conflicts = self.detect_tz_blocks_conflicts()
                # Simulate post-DST by checking conflicts (offsets will differ)
                post_utc = transition + timedelta(hours=1)
                post_conflicts = self.detect_tz_blocks_conflicts(ref_utc=post_utc)
                new_conflicts = [c for c in post_conflicts if c not in pre_conflicts]
                if new_conflicts:
                    date_str = transition.strftime("%b %d")
                    warnings = "; ".join(c[2] for c in new_conflicts[:2])
                    return f"DST change on {date_str}: {warnings}. Adjust blocks to avoid conflict."
        return None

    def _tz_label_from_windows_id(self, windows_id):
        for label, cfg in TZ_REGISTRY.items():
            if cfg["windows_id"] == windows_id:
                return label
        return self._get_work_zone()

    def get_current_timezone(self):
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                ['powershell', '-WindowStyle', 'Hidden', '-Command', '(Get-TimeZone).Id'],
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return result.stdout.strip()
        except:
            return None

    def set_timezone(self, timezone_id):
        self.cached_tz = timezone_id
        def _set_tz():
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE

                subprocess.run(
                    ['powershell', '-WindowStyle', 'Hidden', '-Command', f'Set-TimeZone -Id "{timezone_id}"'],
                    check=True,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                self.gui_queue.put(('UPDATE_ICON',))
            except Exception as e:
                print(f"Error switching timezone: {e}")

        threading.Thread(target=_set_tz, daemon=True).start()

    def get_minutes_until_next_switch(self):
        now_utc = self.get_now_utc()
        current_zone = self.find_active_tz_block(now_utc)
        for m in range(1, 1441):
            future_utc = now_utc + timedelta(minutes=m)
            if self.find_active_tz_block(future_utc) != current_zone:
                return m
        return 1440

    def check_and_switch_timezone(self, now_utc):
        if self.var_tz_paused.get() == 1:
            return
        target_zone = self.find_active_tz_block(now_utc)
        target_tz_id = TZ_REGISTRY[target_zone]["windows_id"]
        current_tz = self.cached_tz or self.get_current_timezone()
        if current_tz != target_tz_id:
            self.set_timezone(target_tz_id)

    def quick_toggle_tz(self, icon=None, item=None):
        personal_zone_id = TZ_REGISTRY[self._get_personal_zone()]["windows_id"]
        current_tz = self.cached_tz or self.get_current_timezone()
        if current_tz and current_tz != personal_zone_id:
            self.set_timezone(personal_zone_id)
        else:
            # Switch to first block's zone, or work zone fallback
            if self.tz_blocks:
                first_zone = self.tz_blocks[0]['zone']
            else:
                first_zone = self._get_work_zone()
            self.set_timezone(TZ_REGISTRY[first_zone]["windows_id"])

    def toggle_tz_pause(self, icon=None, item=None):
        current = self.var_tz_paused.get()
        new_val = 0 if current == 1 else 1
        self.var_tz_paused.set(new_val)
        self.save_global_settings()
        self.gui_queue.put(('UPDATE_ICON',))

    def create_dynamic_icon(self):
        width = 64
        height = 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)

        paused = self.var_tz_paused.get() == 1
        now_utc = self.get_now_utc()
        active_zone = self.find_active_tz_block(now_utc)
        personal_zone = self._get_personal_zone()

        if paused:
            color = (128, 128, 128)
        elif active_zone != personal_zone:
            color = (152, 251, 152)  # Green = work block active
        else:
            color = (0, 191, 255)    # Blue = personal zone

        minutes_until = self.get_minutes_until_next_switch()

        if minutes_until > 60:
            max_hours = 8
            hours_until = minutes_until / 60.0
            bars = 8 if hours_until >= max_hours else max(1, int(hours_until))

            bar_width = 28
            bar_height = 6
            spacing = 1
            total_bars = 8
            total_height = total_bars * bar_height + (total_bars - 1) * spacing
            start_x = (width - bar_width) // 2
            start_y = (height + total_height) // 2

            for i in range(total_bars):
                y = start_y - (i + 1) * (bar_height + spacing)
                dc.rectangle([start_x - 1, y - 1, start_x + bar_width + 1, y + bar_height + 1], outline=(0, 0, 0), width=1)

            for i in range(bars):
                y = start_y - (i + 1) * (bar_height + spacing)
                dc.rectangle([start_x, y, start_x + bar_width, y + bar_height], fill=color)
        else:
            countdown_text = f"{minutes_until}"
            try:
                font = ImageFont.truetype("arialbd.ttf", 62)
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", 62)
                except:
                    font = ImageFont.load_default()

            try:
                bbox = dc.textbbox((0, 0), countdown_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except:
                text_width, text_height = font.getsize(countdown_text)

            x = (width - text_width) // 2
            y = (height - text_height) // 2 - 2
            dc.text((x, y), countdown_text, fill=color, font=font)

        if len(self.active_popups) > 0:
            badge_radius = 8
            dc.ellipse([width - (badge_radius*2), 0, width, badge_radius*2], fill="#e74c3c")

        return image

    # --- TIMEZONE AND UTC ENGINE HELPERS ---

    def get_now_utc(self):
        return datetime.now(timezone.utc).replace(tzinfo=None)

    def get_now_zone(self, tz_label):
        return self.convert_utc_to_zone(self.get_now_utc(), tz_label)

    def get_offset_at(self, tz_label, utc_time):
        cfg = TZ_REGISTRY.get(tz_label)
        if not cfg:
            return 0
        if not cfg["has_dst"]:
            return cfg["base_offset"]
        # US DST: 2nd Sunday March 2:00 UTC → 1st Sunday November 2:00 UTC
        year = utc_time.year
        march_1st = datetime(year, 3, 1)
        days_to_2nd_sun = (6 - march_1st.weekday() + 7) % 7 + 7
        dst_start = march_1st + timedelta(days=days_to_2nd_sun)
        dst_start = dst_start.replace(hour=2)
        nov_1st = datetime(year, 11, 1)
        days_to_1st_sun = (6 - nov_1st.weekday() + 7) % 7
        dst_end = nov_1st + timedelta(days=days_to_1st_sun)
        dst_end = dst_end.replace(hour=2)
        if dst_start <= utc_time < dst_end:
            return cfg["dst_offset"]
        else:
            return cfg["base_offset"]

    def convert_utc_to_zone(self, utc_time, tz_label):
        offset = self.get_offset_at(tz_label, utc_time)
        return utc_time + timedelta(hours=offset)

    def convert_zone_to_utc(self, zone_time, tz_label):
        offset = self.get_offset_at(tz_label, zone_time)
        utc_guess = zone_time - timedelta(hours=offset)
        actual_offset = self.get_offset_at(tz_label, utc_guess)
        return zone_time - timedelta(hours=actual_offset)

    def is_time_valid(self, check_time_utc, use_hours, s_h, s_m, e_h, e_m, days_str, tz_label="ET"):
        zone_time = self.convert_utc_to_zone(check_time_utc, tz_label)
        
        days_list = [int(x) for x in days_str.split(',')]
        if zone_time.weekday() not in days_list:
            return False
            
        if use_hours:
            zone_min = zone_time.hour * 60 + zone_time.minute
            start_min = s_h * 60 + s_m
            end_min = e_h * 60 + e_m
            if not (start_min <= zone_min < end_min):
                return False
        return True

    def calculate_next_trigger_with_pattern(self, now_utc, interval_mins, use_pattern, pattern_hour, pattern_minute, pattern_tz, use_hours, s_h, s_m, e_h, e_m, days_str, active_tz):
        if not use_pattern:
            return self.get_next_valid_time(now_utc, interval_mins, use_hours, s_h, s_m, e_h, e_m, days_str, active_tz)
        
        pattern_now = self.convert_utc_to_zone(now_utc, pattern_tz)
        target_minute = int(pattern_minute)
        
        if pattern_hour is not None and str(pattern_hour).strip() != '':
            target_hour = int(pattern_hour)
            anchor_zone = pattern_now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        else:
            anchor_zone = pattern_now.replace(minute=target_minute, second=0, microsecond=0)
            
        anchor_utc = self.convert_zone_to_utc(anchor_zone, pattern_tz)
        
        if interval_mins > 0:
            while anchor_utc <= now_utc:
                anchor_utc += timedelta(minutes=interval_mins)
        else:
            if anchor_utc <= now_utc:
                if pattern_hour is not None and str(pattern_hour).strip() != '':
                    anchor_utc += timedelta(days=1)
                else:
                    anchor_utc += timedelta(hours=1)
        
        return self.get_next_valid_time(anchor_utc, 0, use_hours, s_h, s_m, e_h, e_m, days_str, active_tz)

    def get_next_valid_time(self, start_time_utc, interval_mins, use_hours, s_h, s_m, e_h, e_m, days_str, tz_label="ET"):
        candidate_utc = start_time_utc + timedelta(minutes=interval_mins)
        for _ in range(7 * 24 * 60):
            if self.is_time_valid(candidate_utc, use_hours, s_h, s_m, e_h, e_m, days_str, tz_label):
                return candidate_utc
            candidate_utc += timedelta(minutes=1)
        print(f"[get_next_valid_time] No valid time in 7 days from {start_time_utc}, returning fallback")
        return start_time_utc + timedelta(minutes=max(interval_mins, 60))

    # --- SYSTEM INTEGRATION ---

    def hide_console(self):
        if sys.platform == 'win32':
            try:
                kernel32 = ctypes.WinDLL('kernel32')
                user32 = ctypes.WinDLL('user32')
                hWnd = kernel32.GetConsoleWindow()
                if hWnd:
                    user32.ShowWindow(hWnd, 0)
            except Exception:
                pass

    def _is_gawi_process(self, pid):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010
            handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, 0, pid)
            if not handle:
                return False
            try:
                buf = ctypes.create_unicode_buffer(260)
                psapi.GetModuleBaseNameW(handle, None, buf, 260)
                name = buf.value.lower()
                return name in ('pythonw.exe', 'python.exe', 'gawi.exe')
            finally:
                kernel32.CloseHandle(handle)
        except:
            return False

    def acquire_lock(self):
        try:
            if os.path.exists(self.lock_file):
                try:
                    with open(self.lock_file, 'r') as f:
                        pid = int(f.read().strip())
                    if sys.platform == 'win32':
                        if self._is_gawi_process(pid):
                            wake_file = os.path.join(DATA_DIR, 'wake.flag')
                            try:
                                with open(wake_file, 'w') as wf:
                                    wf.write('wake')
                            except:
                                pass

                            return False
                        else:
                            os.remove(self.lock_file)
                except:
                    try:
                       os.remove(self.lock_file)
                    except:
                        pass
            
            with open(self.lock_file, 'w') as f:
                f.write(str(os.getpid()))
            return True
        except Exception as e:
            return True 

    def release_lock(self):
        try:
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
        except:
            pass

    def set_startup_registry(self, enable=True):
        if getattr(sys, 'frozen', False):
            # Exe mode: use shell:Startup shortcut (more reliable than registry)
            import ctypes.wintypes
            CSIDL_STARTUP = 7
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_STARTUP, None, 0, buf)
            shortcut_path = os.path.join(buf.value, "Gawi.lnk")
            if enable:
                exe_path = sys.executable.replace("\\", "\\\\")
                sc_path = shortcut_path.replace("\\", "\\\\")
                ps_cmd = f'$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut("{sc_path}"); $s.TargetPath = "{exe_path}"; $s.Save()'
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                               startupinfo=startupinfo, creationflags=0x08000000)
            else:
                try:
                    os.remove(shortcut_path)
                except:
                    pass
        else:
            # Script mode: use registry
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "Gawi"
            python_exe = sys.executable.replace("python.exe", "pythonw.exe")
            script_path = os.path.abspath(__file__)
            cmd = f'"{python_exe}" "{script_path}"'
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
                if enable:
                    winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, app_name)
                    except FileNotFoundError:
                        pass
                winreg.CloseKey(key)
            except Exception as e:
                print(f"Registry Error: {e}")

    def toggle_startup_check(self):
        is_enabled = self.var_startup.get()
        self.set_startup_registry(enable=(is_enabled == 1))

    def check_startup_state(self):
        if getattr(sys, 'frozen', False):
            # Exe mode: check shell:Startup shortcut
            import ctypes.wintypes
            CSIDL_STARTUP = 7
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_STARTUP, None, 0, buf)
            shortcut_path = os.path.join(buf.value, "Gawi.lnk")
            return 1 if os.path.exists(shortcut_path) else 0
        else:
            # Script mode: check registry
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            app_name = "Gawi"
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
                winreg.QueryValueEx(key, app_name)
                winreg.CloseKey(key)
                return 1
            except FileNotFoundError:
                return 0
            except Exception:
                return 0

    # --- DATABASE ---

    def init_db(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS reminders
                     (id INTEGER PRIMARY KEY, 
                      title TEXT, 
                      message TEXT, 
                      next_trigger TEXT, 
                      interval_minutes INTEGER,
                      sound TEXT DEFAULT 'Default',
                      active_days TEXT DEFAULT '0,1,2,3,4,5,6',
                      start_hour INTEGER DEFAULT 0,
                      end_hour INTEGER DEFAULT 23,
                      double_check INTEGER DEFAULT 0,
                      confirm_msg TEXT DEFAULT 'Are you sure?',
                      use_active_hours INTEGER DEFAULT 0,
                      is_active INTEGER DEFAULT 1,
                      sort_order INTEGER DEFAULT 0,
                      popup_bg_color TEXT DEFAULT '#111111',
                      timezone TEXT DEFAULT 'ET',
                      start_minute INTEGER DEFAULT 0,
                      end_minute INTEGER DEFAULT 0,
                      enable_snooze INTEGER DEFAULT 1,
                      max_snoozes INTEGER DEFAULT 3,
                      snoozes_used INTEGER DEFAULT 0,
                      use_start_pattern INTEGER DEFAULT 0,
                      pattern_hour INTEGER DEFAULT NULL,
                      pattern_minute INTEGER DEFAULT 0,
                      pattern_timezone TEXT DEFAULT 'ET',
                      snooze_behavior TEXT DEFAULT 'shift',
                      is_one_time INTEGER DEFAULT 0,
                      one_time_date TEXT DEFAULT NULL)''')
                      
        c.execute("PRAGMA table_info(reminders)")
        cols = [info[1] for info in c.fetchall()]
        migrations = [
            ('sound', "TEXT DEFAULT 'Default'"),
            ('active_days', "TEXT DEFAULT '0,1,2,3,4,5,6'"),
            ('start_hour', "INTEGER DEFAULT 0"),
            ('end_hour', "INTEGER DEFAULT 23"),
            ('double_check', "INTEGER DEFAULT 0"),
            ('confirm_msg', "TEXT DEFAULT 'Are you sure?'"),
            ('use_active_hours', "INTEGER DEFAULT 0"),
            ('is_active', "INTEGER DEFAULT 1"),
            ('sort_order', "INTEGER DEFAULT 0"),
            ('popup_bg_color', "TEXT DEFAULT '#111111'"),
            ('timezone', "TEXT DEFAULT 'ET'"),
            ('start_minute', "INTEGER DEFAULT 0"),
            ('end_minute', "INTEGER DEFAULT 0"),
            ('enable_snooze', "INTEGER DEFAULT 1"),
            ('max_snoozes', "INTEGER DEFAULT 3"),
            ('snoozes_used', "INTEGER DEFAULT 0"),
            ('use_start_pattern', "INTEGER DEFAULT 0"),
            ('pattern_hour', "INTEGER DEFAULT NULL"),
            ('pattern_minute', "INTEGER DEFAULT 0"),
            ('pattern_timezone', "TEXT DEFAULT 'ET'"),
            ('snooze_behavior', "TEXT DEFAULT 'shift'"),
            ('is_one_time', "INTEGER DEFAULT 0"),
            ('one_time_date', "TEXT DEFAULT NULL")
        ]
        for col, dtype in migrations:
            if col not in cols:
                try:
                    c.execute(f"ALTER TABLE reminders ADD COLUMN {col} {dtype}")
                except:
                    pass

        c.execute('''CREATE TABLE IF NOT EXISTS settings
                     (id INTEGER PRIMARY KEY,
                      work_start_h INTEGER DEFAULT 7,
                      work_start_m INTEGER DEFAULT 0,
                      work_end_h INTEGER DEFAULT 17,
                      work_end_m INTEGER DEFAULT 0,
                      tz_paused INTEGER DEFAULT 0,
                      window_x INTEGER DEFAULT NULL,
                      window_y INTEGER DEFAULT NULL)''')
        
        c.execute("SELECT count(*) FROM settings")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO settings (id) VALUES (1)")

        c.execute("PRAGMA table_info(settings)")
        settings_cols = [info[1] for info in c.fetchall()]
        for col, dtype in [('window_x', 'INTEGER DEFAULT NULL'), ('window_y', 'INTEGER DEFAULT NULL'), ('work_days', "TEXT DEFAULT '0,1,2,3,4'"), ('work_zone', "TEXT DEFAULT 'ET'"), ('personal_zone', "TEXT DEFAULT 'PHT'"), ('baseline_display_zone', "TEXT DEFAULT 'ET'")]:
            if col not in settings_cols:
                try: c.execute(f"ALTER TABLE settings ADD COLUMN {col} {dtype}")
                except: pass

        c.execute('''CREATE TABLE IF NOT EXISTS tz_blocks
                     (id INTEGER PRIMARY KEY,
                      zone TEXT NOT NULL,
                      start_h INTEGER NOT NULL,
                      start_m INTEGER NOT NULL,
                      end_h INTEGER NOT NULL,
                      end_m INTEGER NOT NULL,
                      active_days TEXT NOT NULL DEFAULT '0,1,2,3,4',
                      sort_order INTEGER DEFAULT 0)''')

        # Auto-migrate: if tz_blocks is empty and old work settings exist, create one block
        c.execute("SELECT count(*) FROM tz_blocks")
        if c.fetchone()[0] == 0:
            c.execute("SELECT work_zone, work_start_h, work_start_m, work_end_h, work_end_m, work_days FROM settings WHERE id=1")
            srow = c.fetchone()
            if srow and srow[0]:
                c.execute("INSERT INTO tz_blocks (zone, start_h, start_m, end_h, end_m, active_days, sort_order) VALUES (?,?,?,?,?,?,0)",
                          (srow[0], srow[1] or 7, srow[2] or 0, srow[3] or 17, srow[4] or 0, srow[5] or '0,1,2,3,4'))

        conn.commit()
        conn.close()

    def load_global_settings(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM settings WHERE id=1")
            row = c.fetchone()
            if row:
                self.var_work_start_h.set(f"{row['work_start_h']:02d}")
                self.var_work_start_m.set(f"{row['work_start_m']:02d}")
                self.var_work_end_h.set(f"{row['work_end_h']:02d}")
                self.var_work_end_m.set(f"{row['work_end_m']:02d}")
                self.var_tz_paused.set(row['tz_paused'])
                self._window_x = row['window_x']
                self._window_y = row['window_y']
                work_days_str = row['work_days'] if 'work_days' in row.keys() else '0,1,2,3,4'
                if work_days_str:
                    wd_set = set(d for d in (int(x) for x in work_days_str.split(',') if x.strip().isdigit()) if 0 <= d <= 6)
                    for i in range(7):
                        self.var_work_days[i].set(1 if i in wd_set else 0)
                if 'work_zone' in row.keys() and row['work_zone']:
                    self.var_work_zone.set(row['work_zone'])
                if 'personal_zone' in row.keys() and row['personal_zone']:
                    self.var_personal_zone.set(row['personal_zone'])
                if 'baseline_display_zone' in row.keys() and row['baseline_display_zone']:
                    self.var_baseline_display_zone.set(row['baseline_display_zone'])
            conn.close()
            self.load_tz_blocks()
            self._saved_work_hours = (int(self.var_work_start_h.get()), int(self.var_work_start_m.get()), int(self.var_work_end_h.get()), int(self.var_work_end_m.get()), self._get_work_days_str(), self.var_work_zone.get(), self.var_personal_zone.get(), self.var_baseline_display_zone.get())
        except:
            pass

    def _get_virtual_screen_bounds(self):
        try:
            user32 = ctypes.windll.user32
            vx = user32.GetSystemMetrics(76)
            vy = user32.GetSystemMetrics(77)
            vw = user32.GetSystemMetrics(78)
            vh = user32.GetSystemMetrics(79)
            return vx, vy, vx + vw, vy + vh
        except:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            return 0, 0, sw, sh

    def _format_interval(self, minutes):
        preset_map = {15:"15m", 30:"30m", 60:"1h", 120:"2h", 240:"4h", 480:"8h", 720:"12h", 1440:"Daily", 10080:"Weekly", 43200:"Monthly"}
        return preset_map.get(minutes, f"{minutes}m")

    def _parse_interval(self, text):
        text = str(text).strip()
        reverse_map = {"15m":15, "30m":30, "1h":60, "2h":120, "4h":240, "8h":480, "12h":720, "daily":1440, "weekly":10080, "monthly":43200}
        if text.lower() in reverse_map:
            return reverse_map[text.lower()]
        try:
            return int(text)
        except ValueError:
            return 60

    def apply_window_position(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if self._window_x is not None and self._window_y is not None:
            x, y = self._window_x, self._window_y
            vx_min, vy_min, vx_max, vy_max = self._get_virtual_screen_bounds()
            if x + w < vx_min + 50 or x > vx_max - 50 or y + h < vy_min + 50 or y > vy_max - 50:
                sw = self.root.winfo_screenwidth()
                sh = self.root.winfo_screenheight()
                x = (sw - w) // 2
                y = (sh - h) // 2
            self.root.geometry(f"+{x}+{y}")
        else:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.root.geometry(f"+{x}+{y}")
        self.root.deiconify()

    def save_window_position(self):
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            def worker():
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("UPDATE settings SET window_x=?, window_y=? WHERE id=1", (x, y))
                    conn.commit()
                    conn.close()
                except: pass
            threading.Thread(target=worker, daemon=True).start()
        except: pass

    def save_global_settings(self):
        try:
            w_s_h = int(self.var_work_start_h.get().strip())
            w_s_m = int(self.var_work_start_m.get().strip())
            w_e_h = int(self.var_work_end_h.get().strip())
            w_e_m = int(self.var_work_end_m.get().strip())
            
            if not (0 <= w_s_h <= 23) or not (0 <= w_s_m <= 59) or not (0 <= w_e_h <= 23) or not (0 <= w_e_m <= 59):
                return

            work_days_str = self._get_work_days_str()
            work_zone = self.var_work_zone.get()
            personal_zone = self.var_personal_zone.get()
            baseline_display_zone = self.var_baseline_display_zone.get()

            def worker():
                try:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.execute("""UPDATE settings SET
                                 work_start_h=?, work_start_m=?, work_end_h=?, work_end_m=?, tz_paused=?, work_days=?, work_zone=?, personal_zone=?, baseline_display_zone=?
                                 WHERE id=1""",
                              (w_s_h, w_s_m, w_e_h, w_e_m, self.var_tz_paused.get(), work_days_str, work_zone, personal_zone, baseline_display_zone))
                    conn.commit()
                    conn.close()
                    self.gui_queue.put(('SAVE_FEEDBACK',))
                except:
                    pass

            self._saved_work_hours = (int(self.var_work_start_h.get()), int(self.var_work_start_m.get()), int(self.var_work_end_h.get()), int(self.var_work_end_m.get()), self._get_work_days_str(), work_zone, personal_zone, baseline_display_zone)
            threading.Thread(target=worker, daemon=True).start()
            self.gui_queue.put(('UPDATE_ICON',))
            self.next_tz_check = self.get_now_utc()
        except Exception as e:
            pass

    def reset_stale_reminders(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM reminders")
            rows = c.fetchall()
            now_utc = self.get_now_utc()
            updates = []
            for row in rows:
                item = dict(row)
                if item.get('is_one_time', 0) == 1:
                    continue

                try:
                    trig_time = datetime.strptime(item['next_trigger'], "%Y-%m-%d %H:%M:%S")
                    if trig_time < now_utc:
                        # Always set to now — check_loop fires immediately (like Target Tasks).
                        # The pattern anchor is preserved in the DB for close_and_mark_done().
                        # If outside active hours, check_loop's is_time_valid reschedules without popup.
                        updates.append((now_utc.strftime("%Y-%m-%d %H:%M:%S"), item['id']))
                except Exception as e:
                    print(f"[reset_stale] Skipping id={item.get('id','?')}: {e}")
            if updates:
                c.executemany("UPDATE reminders SET next_trigger=? WHERE id=?", updates)
                conn.commit()
                conn.close()
                self.load_cache_from_db()
            else:
                conn.close()
        except Exception as e:
            pass

    def load_cache_from_db(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM reminders ORDER BY sort_order ASC")
            rows = c.fetchall()
            self.cache = []
            for row in rows:
                item = dict(row)
                item['widget_ref'] = None 
                item['lbl_title'] = None
                item['lbl_status'] = None
                self.cache.append(item)
            conn.close()
        except Exception as e:
            pass

    def bg_save_item(self, item_dict):
        def worker():
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                if 'id' in item_dict and item_dict['id'] is not None:
                    cols = [k for k in item_dict.keys() if k not in ['widget_ref', 'lbl_title', 'lbl_status']]
                    vals = [item_dict[k] for k in cols]
                    cols.remove('id')
                    vals_ordered = [item_dict[k] for k in cols]
                    vals_ordered.append(item_dict['id'])
                    set_clause = ", ".join([f"{c}=?" for c in cols])
                    c.execute(f"UPDATE reminders SET {set_clause} WHERE id=?", vals_ordered)
                conn.commit()
                conn.close()
            except Exception as e:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def bg_delete_item(self, r_id):
        def worker():
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("DELETE FROM reminders WHERE id=?", (r_id,))
                conn.commit()
                conn.close()
            except:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def bg_save_order(self):
        current_order = [(item['sort_order'], item['id']) for item in self.cache]
        def worker():
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.executemany("UPDATE reminders SET sort_order=? WHERE id=?", current_order)
                conn.commit()
                conn.close()
            except:
                pass
        threading.Thread(target=worker, daemon=True).start()

    # --- UI RENDERING ---

    def update_header(self):
        try:
            if self.cached_tz is None:
                self.cached_tz = self.get_current_timezone()
            tz_label = self._tz_label_from_windows_id(self.cached_tz) if self.cached_tz else self._get_personal_zone()
            now_utc = self.get_now_utc()
            active_zone = self.find_active_tz_block(now_utc)
            personal_zone = self._get_personal_zone()
            if active_zone != personal_zone:
                mode_str = f"{tz_label} (Work Mode)"
            else:
                mode_str = f"{tz_label} (Personal Mode)"

            self.lbl_header_mode.config(text=f"{mode_str}")
        except:
            pass
        self.root.after(5000, self.update_header)

    def _auto_tab(self, event, current_var, max_len, next_widget):
        if len(current_var.get()) >= max_len and event.keysym not in ('BackSpace', 'Tab', 'Shift_L', 'Shift_R'):
            next_widget.focus()

    def build_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.root.configure(bg=self.colors["BG"])

        self.root.option_add('*TCombobox*Listbox.background', self.colors["INPUT"])
        self.root.option_add('*TCombobox*Listbox.foreground', self.colors["TEXT_MAIN"])
        self.root.option_add('*TCombobox*Listbox.selectBackground', self.colors["ACCENT"])
        self.root.option_add('*TCombobox*Listbox.selectForeground', 'white')

        style = ttk.Style()
        style.theme_use('clam') 
        style.configure("Dark.Vertical.TScrollbar", 
                        troughcolor=self.colors["SCROLL_BG"], 
                        background=self.colors["SCROLL_FG"], 
                        bordercolor=self.colors["SCROLL_BG"], 
                        arrowcolor=self.colors["SCROLL_FG"],
                        gripcount=0)
        style.map('TCombobox', fieldbackground=[('readonly', self.colors["INPUT"])],
                                selectbackground=[('readonly', self.colors["INPUT"])],
                                selectforeground=[('readonly', self.colors["TEXT_MAIN"])],
                                background=[('readonly', self.colors["INPUT"])])
        style.configure("TCombobox", 
                        background=self.colors["INPUT"], 
                        fieldbackground=self.colors["INPUT"], 
                        foreground=self.colors["TEXT_MAIN"],
                        arrowcolor=self.colors["TEXT_MAIN"],
                        bordercolor=self.colors["BG"])
        style.configure("TFrame", background=self.colors["BG"])
        style.configure("TLabel", background=self.colors["BG"], foreground=self.colors["FG"])
        style.configure("TCheckbutton", background=self.colors["BG"], foreground=self.colors["FG"])
        
        style.configure("TRadiobutton", background=self.colors["BG"], foreground=self.colors["FG"])
        style.map('TRadiobutton',
            background=[('active', self.colors["BG"])],
            foreground=[('active', self.colors["ACCENT"])],
            indicatorcolor=[('selected', self.colors["ACCENT"])]
        )

        header = tk.Frame(self.root, bg=self.colors["BG"])
        header.pack(fill="x", padx=20, pady=15)
        
        theme_icon = "☾" if self.is_dark_mode else "☀"
        tk.Button(header, text=theme_icon, command=self.toggle_theme, 
                  bg=self.colors["INPUT"], fg=self.colors["FG"], 
                  font=("Segoe UI", 12, "bold"), relief="flat", width=3).pack(side="left")

        tk.Checkbutton(header, text="Run on Startup", variable=self.var_startup, 
                       bg=self.colors["BG"], fg=self.colors["FG"], 
                       activebackground=self.colors["BG"], activeforeground=self.colors["FG"],
                       selectcolor=self.colors["BG"],
                       command=self.toggle_startup_check).pack(side="left", padx=(10, 0))

        self.lbl_header_mode = tk.Label(header, text="PHT (Personal Mode)", bg=self.colors["BG"], fg=self.colors["ACCENT"], font=("Segoe UI", 9, "bold"))
        self.lbl_header_mode.pack(side="left", fill="x", expand=True)
        
        tk.Button(header, text="HIDE", command=self.hide_window, 
                  bg=self.colors["INPUT"], fg=self.colors["FG"], font=("Segoe UI", 8, "bold"), 
                  relief="flat", padx=10).pack(side="right")
        
        tk.Button(header, text="RELOAD", command=self.restart_app, 
                  bg=self.colors["INPUT"], fg=self.colors["ACCENT"], font=("Segoe UI", 8, "bold"), 
                  relief="flat", padx=10).pack(side="right", padx=(0, 10))

        # --- GLOBAL SETTINGS ---
        settings_frame = tk.LabelFrame(self.root, text="  Time Zone Blocks  ",
                                        bg=self.colors["BG"], fg=self.colors["ACCENT"],
                                        font=("Segoe UI", 11, "bold"), relief="flat", bd=2)
        settings_frame.pack(fill="x", padx=20, pady=5)
        self._tz_blocks_frame = settings_frame

        # Header row: personal zone + baseline + pause + add
        sf_header = tk.Frame(settings_frame, bg=self.colors["BG"])
        sf_header.pack(fill="x", padx=10, pady=(10, 5))

        tk.Label(sf_header, text="Personal:", bg=self.colors["BG"], fg=self.colors["FG"], font=("Segoe UI", 9, "bold")).pack(side="left")
        cb_personal_zone = ttk.Combobox(sf_header, textvariable=self.var_personal_zone, values=TZ_LABELS, state="readonly", width=5)
        cb_personal_zone.pack(side="left", padx=(5, 10))
        cb_personal_zone.bind("<<ComboboxSelected>>", lambda e: self.save_global_settings())

        tk.Label(sf_header, text="Baseline:", bg=self.colors["BG"], fg=self.colors["FG"], font=("Segoe UI", 9, "bold")).pack(side="left")
        cb_baseline = ttk.Combobox(sf_header, textvariable=self.var_baseline_display_zone, values=TZ_LABELS, state="readonly", width=5)
        cb_baseline.pack(side="left", padx=(5, 10))
        cb_baseline.bind("<<ComboboxSelected>>", lambda e: (self.save_global_settings(), self._render_tz_blocks_table()))
        ToolTip(cb_baseline, "Display all block times converted to this zone for easy comparison")

        tk.Checkbutton(sf_header, text="Pause", variable=self.var_tz_paused, command=self.save_global_settings,
                       bg=self.colors["BG"], fg=self.colors["WARNING"],
                       activebackground=self.colors["BG"], activeforeground=self.colors["WARNING"],
                       selectcolor=self.colors["BG"], font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))

        tk.Button(sf_header, text="+ ADD BLOCK", command=self._add_new_block,
                  bg=self.colors["ACCENT"], fg="white", relief="flat",
                  font=("Segoe UI", 8, "bold")).pack(side="right")

        self.save_dot = tk.Label(sf_header, text="", bg=self.colors["BG"], font=("Segoe UI", 9, "bold"))
        self.save_dot.pack(side="right", padx=(0, 5))

        # DST warning banner (hidden by default)
        self._dst_banner_frame = tk.Frame(settings_frame, bg=self.colors["ERROR"])
        self._dst_banner_label = tk.Label(self._dst_banner_frame, text="", bg=self.colors["ERROR"], fg="white",
                                          font=("Segoe UI", 8), wraplength=550, justify="left")
        self._dst_banner_label.pack(side="left", fill="x", expand=True, padx=5, pady=3)
        tk.Button(self._dst_banner_frame, text="Dismiss", command=self._dismiss_dst_warning,
                  bg=self.colors["ERROR"], fg="white", relief="flat", font=("Segoe UI", 7)).pack(side="right", padx=5)

        # Block table container
        self._blocks_table_frame = tk.Frame(settings_frame, bg=self.colors["BG"])
        self._blocks_table_frame.pack(fill="x", padx=10, pady=(0, 5))

        # Block editor (hidden by default)
        self._block_editor_frame = tk.Frame(settings_frame, bg=self.colors["INPUT"])
        self._block_editor_built = False

        self._render_tz_blocks_table()
        self._check_dst_warning()

        # --- EDITOR ZONE (lazy-loaded on first Add/Edit) ---
        self._editor_anchor = tk.Frame(self.root, bg=self.colors["BG"])
        self._editor_anchor.pack(fill="x", padx=20, pady=5)
        self._editor_built = False
        self._add_btn_placeholder = tk.Frame(self._editor_anchor, bg=self.colors["BG"])
        self._add_btn_placeholder.pack(fill="x", padx=10, pady=5)
        tk.Button(self._add_btn_placeholder, text="+ ADD REMINDER", command=self._open_editor,
                  bg=self.colors["ACCENT"], fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold")).pack(fill="x")

        list_frame = tk.LabelFrame(self.root, text="  Multi-Task Reminder  ", 
                                   bg=self.colors["BG"], fg=self.colors["ACCENT"], 
                                   font=("Segoe UI", 11, "bold"), relief="flat", bd=2)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.canvas = tk.Canvas(list_frame, bg=self.colors["BG"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview, style="Dark.Vertical.TScrollbar")
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.colors["BG"])
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        self.scrollable_frame.bind("<Configure>", lambda e: self.update_scroll_region())
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.bind('<Enter>', self._bound_to_mousewheel)
        self.canvas.bind('<Leave>', self._unbound_to_mousewheel)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        self.refresh_list()

    def _render_tz_blocks_table(self):
        for w in self._blocks_table_frame.winfo_children():
            w.destroy()
        self._block_widgets = {}
        conflicts = self.detect_tz_blocks_conflicts()
        conflict_ids = set()
        conflict_msgs = {}
        for a_id, b_id, msg in conflicts:
            conflict_ids.add(a_id)
            conflict_ids.add(b_id)
            conflict_msgs.setdefault(a_id, []).append(msg)
            conflict_msgs.setdefault(b_id, []).append(msg)

        baseline = self.var_baseline_display_zone.get() or "ET"
        now_utc = self.get_now_utc()

        if not self.tz_blocks:
            tk.Label(self._blocks_table_frame, text="No work blocks — always in personal zone",
                     bg=self.colors["BG"], fg=self.colors["TEXT_DIM"],
                     font=("Segoe UI", 9, "italic")).pack(pady=5)
            return

        for block in sorted(self.tz_blocks, key=lambda b: b['sort_order']):
            has_conflict = block['id'] in conflict_ids
            border_color = self.colors["ERROR"] if has_conflict else self.colors["CARD_BG"]
            row_frame = tk.Frame(self._blocks_table_frame, bg=border_color, bd=1, relief="solid")
            row_frame.pack(fill="x", pady=1)
            inner = tk.Frame(row_frame, bg=self.colors["CARD_BG"])
            inner.pack(fill="x", padx=1, pady=1)

            # Convert block times to baseline zone for display
            ref_date = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            block_start_local = ref_date.replace(hour=block['start_h'], minute=block['start_m'])
            block_end_local = ref_date.replace(hour=block['end_h'], minute=block['end_m'])
            if block_end_local <= block_start_local:
                block_end_local += timedelta(days=1)
            start_utc = self.convert_zone_to_utc(block_start_local, block['zone'])
            end_utc = self.convert_zone_to_utc(block_end_local, block['zone'])
            start_baseline = self.convert_utc_to_zone(start_utc, baseline)
            end_baseline = self.convert_utc_to_zone(end_utc, baseline)
            start_str = start_baseline.strftime("%I:%M %p").lstrip("0")
            end_str = end_baseline.strftime("%I:%M %p").lstrip("0")

            day_names = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri",5:"Sat",6:"Sun"}
            days_list = sorted(int(d) for d in block['active_days'].split(',') if d.strip().isdigit())
            if days_list == [0,1,2,3,4]:
                days_str = "Mon-Fri"
            elif days_list == [0,1,2,3,4,5,6]:
                days_str = "Every day"
            else:
                days_str = ",".join(day_names.get(d, str(d)) for d in days_list)

            tk.Label(inner, text=block['zone'], bg=self.colors["CARD_BG"], fg=self.colors["ACCENT"],
                     font=("Segoe UI", 9, "bold"), width=4).pack(side="left", padx=(5, 5))
            tk.Label(inner, text=f"{start_str} - {end_str}", bg=self.colors["CARD_BG"], fg=self.colors["TEXT_MAIN"],
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 5))
            tk.Label(inner, text=f"(in {baseline})", bg=self.colors["CARD_BG"], fg=self.colors["TEXT_DIM"],
                     font=("Segoe UI", 7)).pack(side="left", padx=(0, 5))
            tk.Label(inner, text=days_str, bg=self.colors["CARD_BG"], fg=self.colors["TEXT_DIM"],
                     font=("Segoe UI", 8)).pack(side="left", padx=(5, 5))

            if has_conflict:
                conflict_tip = "; ".join(conflict_msgs.get(block['id'], []))
                warn_lbl = tk.Label(inner, text="\u26a0", bg=self.colors["CARD_BG"], fg=self.colors["ERROR"],
                                    font=("Segoe UI", 10))
                warn_lbl.pack(side="left", padx=2)
                ToolTip(warn_lbl, conflict_tip)
            else:
                tk.Label(inner, text="\u2713", bg=self.colors["CARD_BG"], fg=self.colors["SUCCESS"],
                         font=("Segoe UI", 9)).pack(side="left", padx=2)

            bid = block['id']
            btn_frame = tk.Frame(inner, bg=self.colors["CARD_BG"])
            btn_frame.pack(side="right", padx=5)
            tk.Button(btn_frame, text="\u25b2", command=lambda b=bid: self.reorder_tz_blocks(b, "up"),
                      bg=self.colors["CARD_BG"], fg=self.colors["TEXT_DIM"], relief="flat",
                      font=("Segoe UI", 7), width=2).pack(side="left")
            tk.Button(btn_frame, text="\u25bc", command=lambda b=bid: self.reorder_tz_blocks(b, "down"),
                      bg=self.colors["CARD_BG"], fg=self.colors["TEXT_DIM"], relief="flat",
                      font=("Segoe UI", 7), width=2).pack(side="left")
            tk.Button(btn_frame, text="Edit", command=lambda b=bid: self._edit_tz_block(b),
                      bg=self.colors["CARD_BG"], fg=self.colors["BTN_EDIT"], relief="flat",
                      font=("Segoe UI", 7, "bold"), width=3).pack(side="left", padx=(3,0))

            self._block_widgets[bid] = row_frame

    def _add_new_block(self):
        self._show_block_editor(None)

    def _edit_tz_block(self, block_id):
        self._show_block_editor(block_id)

    def _show_block_editor(self, block_id):
        self.selected_block_id = block_id
        if self._block_editor_built:
            self._block_editor_frame.pack_forget()
        # Build editor inline
        for w in self._block_editor_frame.winfo_children():
            w.destroy()
        self._block_editor_frame.configure(bg=self.colors["INPUT"])

        if block_id:
            block = next((b for b in self.tz_blocks if b['id'] == block_id), None)
        else:
            block = None

        ef = tk.Frame(self._block_editor_frame, bg=self.colors["INPUT"])
        ef.pack(fill="x", padx=10, pady=8)

        # Row 1: Zone + Start + End
        var_zone = tk.StringVar(value=block['zone'] if block else "ET")
        var_start_h = tk.StringVar(value=f"{block['start_h']:02d}" if block else "09")
        var_start_m = tk.StringVar(value=f"{block['start_m']:02d}" if block else "00")
        var_end_h = tk.StringVar(value=f"{block['end_h']:02d}" if block else "17")
        var_end_m = tk.StringVar(value=f"{block['end_m']:02d}" if block else "00")

        tk.Label(ef, text="Zone:", bg=self.colors["INPUT"], fg=self.colors["FG"], font=("Segoe UI", 9, "bold")).pack(side="left")
        cb_zone = ttk.Combobox(ef, textvariable=var_zone, values=TZ_LABELS, state="readonly", width=5)
        cb_zone.pack(side="left", padx=(5, 10))

        tk.Label(ef, text="Start:", bg=self.colors["INPUT"], fg=self.colors["FG"], font=("Segoe UI", 9, "bold")).pack(side="left")
        tk.Entry(ef, textvariable=var_start_h, bg=self.colors["BG"], fg=self.colors["TEXT_MAIN"], width=3, relief="flat", insertbackground=self.colors["FG"]).pack(side="left", padx=(5,0))
        tk.Label(ef, text=":", bg=self.colors["INPUT"], fg=self.colors["FG"]).pack(side="left")
        tk.Entry(ef, textvariable=var_start_m, bg=self.colors["BG"], fg=self.colors["TEXT_MAIN"], width=3, relief="flat", insertbackground=self.colors["FG"]).pack(side="left")

        tk.Label(ef, text="  End:", bg=self.colors["INPUT"], fg=self.colors["FG"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=(10, 0))
        tk.Entry(ef, textvariable=var_end_h, bg=self.colors["BG"], fg=self.colors["TEXT_MAIN"], width=3, relief="flat", insertbackground=self.colors["FG"]).pack(side="left", padx=(5,0))
        tk.Label(ef, text=":", bg=self.colors["INPUT"], fg=self.colors["FG"]).pack(side="left")
        tk.Entry(ef, textvariable=var_end_m, bg=self.colors["BG"], fg=self.colors["TEXT_MAIN"], width=3, relief="flat", insertbackground=self.colors["FG"]).pack(side="left")

        # Row 2: Days + Buttons
        ef2 = tk.Frame(self._block_editor_frame, bg=self.colors["INPUT"])
        ef2.pack(fill="x", padx=10, pady=(0, 8))

        tk.Label(ef2, text="Days:", bg=self.colors["INPUT"], fg=self.colors["FG"], font=("Segoe UI", 9, "bold")).pack(side="left")
        block_day_vars = [tk.IntVar(value=0) for _ in range(7)]
        if block:
            active = set(int(d) for d in block['active_days'].split(',') if d.strip().isdigit())
            for i in range(7):
                block_day_vars[i].set(1 if i in active else 0)
        else:
            for i in range(5):
                block_day_vars[i].set(1)
        wd_labels = ["M", "T", "W", "T", "F", "S", "S"]
        for i, lbl in enumerate(wd_labels):
            tk.Checkbutton(ef2, text=lbl, variable=block_day_vars[i],
                           bg=self.colors["INPUT"], fg=self.colors["FG"], selectcolor=self.colors["INPUT"],
                           activebackground=self.colors["ACCENT"], activeforeground="white",
                           highlightthickness=0, bd=0, font=("Segoe UI", 9)).pack(side="left", padx=2)

        # Error label (hidden by default)
        error_label = tk.Label(self._block_editor_frame, text="", bg=self.colors["INPUT"],
                               fg=self.colors["ERROR"], font=("Segoe UI", 8, "bold"))

        def _show_editor_error(msg):
            error_label.config(text=msg)
            error_label.pack(fill="x", padx=10)
            def _clear_error():
                if error_label.winfo_exists():
                    error_label.pack_forget()
            self._block_editor_frame.after(3000, _clear_error)

        # Buttons (right-aligned)
        def _save_block():
            try:
                s_h = int(var_start_h.get().strip())
                s_m = int(var_start_m.get().strip())
                e_h = int(var_end_h.get().strip())
                e_m = int(var_end_m.get().strip())
                if not (0 <= s_h <= 23 and 0 <= s_m <= 59 and 0 <= e_h <= 23 and 0 <= e_m <= 59):
                    _show_editor_error("Invalid time — hours 0-23, minutes 0-59")
                    return
            except ValueError:
                _show_editor_error("Invalid time — enter numbers only")
                return
            if s_h == e_h and s_m == e_m:
                _show_editor_error("Start and end times cannot be the same")
                return
            days = ','.join(str(i) for i in range(7) if block_day_vars[i].get() == 1)
            if not days:
                _show_editor_error("Select at least one day")
                return
            bd = {'zone': var_zone.get(), 'start_h': s_h, 'start_m': s_m, 'end_h': e_h, 'end_m': e_m, 'active_days': days}
            if block_id:
                bd['id'] = block_id
            self.save_tz_block(bd)
            self._block_editor_frame.pack_forget()
            self._block_editor_built = False

        def _delete_block():
            if block_id:
                self.delete_tz_block(block_id)
            self._block_editor_frame.pack_forget()
            self._block_editor_built = False

        def _cancel_block():
            self._block_editor_frame.pack_forget()
            self._block_editor_built = False

        tk.Button(ef2, text="SAVE", command=_save_block,
                  bg=self.colors["ACCENT"], fg="white", relief="flat",
                  font=("Segoe UI", 8, "bold")).pack(side="right", padx=(3, 0))
        tk.Button(ef2, text="CANCEL", command=_cancel_block,
                  bg=self.colors["CARD_BG"], fg=self.colors["FG"], relief="flat",
                  font=("Segoe UI", 8)).pack(side="right", padx=(3, 0))
        if block_id:
            tk.Button(ef2, text="DELETE", command=_delete_block,
                      bg=self.colors["BTN_DEL"], fg="white", relief="flat",
                      font=("Segoe UI", 8, "bold")).pack(side="right", padx=(3, 0))

        self._block_editor_frame.pack(fill="x", padx=10, pady=(0, 8))
        self._block_editor_built = True

    def _dismiss_dst_warning(self):
        self._dst_warning_dismissed = True
        self._dst_banner_frame.pack_forget()

    def _check_dst_warning(self):
        if self._dst_warning_dismissed:
            return
        now_utc = self.get_now_utc()
        warning = self.get_dst_warning_if_needed(now_utc)
        if warning:
            self._dst_banner_label.config(text=f"\u26a0 {warning}")
            self._dst_banner_frame.pack(fill="x", padx=10, pady=(0, 5), before=self._blocks_table_frame)
        else:
            self._dst_banner_frame.pack_forget()

    def _open_editor(self):
        self._ensure_editor()
        self.edit_frame.pack(fill="x")
        self._add_btn_placeholder.pack_forget()
        self.clear_form()

    def _hide_editor(self):
        if self._editor_built and hasattr(self, 'edit_frame'):
            self.edit_frame.pack_forget()
            self._add_btn_placeholder.pack(fill="x")
            self.editing_id = None

    def _ensure_editor(self):
        if not self._editor_built:
            self._add_btn_placeholder.pack_forget()
            self._build_editor()

    def _build_editor(self):
        self.edit_frame = tk.LabelFrame(self._editor_anchor, text="  Editor  ",
                                        bg=self.colors["BG"], fg=self.colors["ACCENT"],
                                        font=("Segoe UI", 11, "bold"), relief="flat", bd=2)
        self.edit_frame.pack(fill="x")

        gf = tk.Frame(self.edit_frame, bg=self.colors["BG"])
        gf.pack(fill="x", padx=10, pady=10)

        def lbl(parent, txt):
            return tk.Label(parent, text=txt, bg=self.colors["BG"], fg=self.colors["FG"], font=("Segoe UI", 10, "bold"), anchor="w")

        gf.columnconfigure(0, minsize=90, weight=0)
        gf.columnconfigure(1, weight=1)
        gf.columnconfigure(3, weight=1)

        # ZONE 1: DAILY DRIVERS
        lbl(gf, "Title *").grid(row=0, column=0, sticky="w", pady=5)

        title_row = tk.Frame(gf, bg=self.colors["BG"], highlightthickness=0, bd=0)
        title_row.grid(row=0, column=1, columnspan=3, sticky="ew", pady=5)

        self.chk_one_time = tk.Checkbutton(title_row, text="One-Time Task", variable=self.var_one_time,
                                           bg=self.colors["BG"], fg=self.colors["ACCENT"],
                                           activebackground=self.colors["BG"], activeforeground=self.colors["ACCENT"],
                                           selectcolor=self.colors["BG"],
                                           font=("Segoe UI", 9, "bold"),
                                           highlightthickness=0, bd=0,
                                           command=self.toggle_one_time_entry)
        self.chk_one_time.pack(side="right", padx=(5, 10))

        self.e_title = tk.Entry(title_row, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"],
                                relief="flat", insertbackground=self.colors["FG"])
        self.e_title.pack(side="left", fill="x", expand=True)

        lbl(gf, "Message").grid(row=1, column=0, sticky="w", pady=5)
        self.e_msg = tk.Entry(gf, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"],
                              relief="flat", insertbackground=self.colors["FG"])
        self.e_msg.grid(row=1, column=1, columnspan=4, sticky="ew", padx=(0, 10))

        self.lbl_interval = lbl(gf, "Every")
        self.lbl_interval.grid(row=2, column=0, sticky="w", pady=5)

        row2_container = tk.Frame(gf, bg=self.colors["BG"], highlightthickness=0, bd=0)
        row2_container.grid(row=2, column=1, columnspan=3, sticky="ew", padx=(0, 10))
        row2_container.columnconfigure(0, weight=1)

        self.e_int = ttk.Combobox(row2_container, values=["15m","30m","1h","2h","4h","8h","12h","Daily","Weekly","Monthly"], width=8)
        self.e_int.set("1h")
        self.e_int.pack(side="left")

        self.one_time_frame = tk.Frame(row2_container, bg=self.colors["BG"], highlightthickness=0, bd=0)

        self.e_ot_mm = tk.Entry(self.one_time_frame, textvariable=self.v_tt_mm, width=3, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"], relief="flat", justify="center", insertbackground=self.colors["FG"])
        self.e_ot_dd = tk.Entry(self.one_time_frame, textvariable=self.v_tt_dd, width=3, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"], relief="flat", justify="center", insertbackground=self.colors["FG"])
        self.e_ot_yy = tk.Entry(self.one_time_frame, textvariable=self.v_tt_yy, width=3, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"], relief="flat", justify="center", insertbackground=self.colors["FG"])

        self.e_ot_mm.pack(side="left")
        tk.Label(self.one_time_frame, text="/", bg=self.colors["BG"], fg=self.colors["FG"]).pack(side="left", padx=2)
        self.e_ot_dd.pack(side="left")
        tk.Label(self.one_time_frame, text="/", bg=self.colors["BG"], fg=self.colors["FG"]).pack(side="left", padx=2)
        self.e_ot_yy.pack(side="left")

        tk.Label(self.one_time_frame, text=" — ", bg=self.colors["BG"], fg=self.colors["FG"]).pack(side="left", padx=5)

        self.e_ot_h = tk.Entry(self.one_time_frame, textvariable=self.v_tt_hh, width=3, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"], relief="flat", justify="center", insertbackground=self.colors["FG"])
        self.e_ot_m = tk.Entry(self.one_time_frame, textvariable=self.v_tt_min, width=3, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"], relief="flat", justify="center", insertbackground=self.colors["FG"])

        self.e_ot_h.pack(side="left")
        tk.Label(self.one_time_frame, text=":", bg=self.colors["BG"], fg=self.colors["FG"]).pack(side="left", padx=2)
        self.e_ot_m.pack(side="left")

        self.e_ot_mm.bind("<KeyRelease>", lambda e: self._auto_tab(e, self.v_tt_mm, 2, self.e_ot_dd))
        self.e_ot_dd.bind("<KeyRelease>", lambda e: self._auto_tab(e, self.v_tt_dd, 2, self.e_ot_yy))
        self.e_ot_yy.bind("<KeyRelease>", lambda e: self._auto_tab(e, self.v_tt_yy, 2, self.e_ot_h))
        self.e_ot_h.bind("<KeyRelease>", lambda e: self._auto_tab(e, self.v_tt_hh, 2, self.e_ot_m))

        self.cb_tt_tz = ttk.Combobox(self.one_time_frame, textvariable=self.v_tt_tz, values=TZ_LABELS, state="readonly", width=5)
        self.cb_tt_tz.pack(side="left", padx=10)

        quick_frame = tk.Frame(self.one_time_frame, bg=self.colors["BG"], highlightthickness=0, bd=0)
        quick_frame.pack(side="right")

        def set_ot_time(minutes_add=0):
            now_zone = self.get_now_zone(self.v_tt_tz.get())
            target = now_zone + timedelta(minutes=minutes_add)
            self.v_tt_mm.set(f"{target.month:02d}")
            self.v_tt_dd.set(f"{target.day:02d}")
            self.v_tt_yy.set(target.strftime("%y"))
            self.v_tt_hh.set(f"{target.hour:02d}")
            self.v_tt_min.set(f"{target.minute:02d}")

        tk.Button(quick_frame, text="+15m", command=lambda: set_ot_time(15),
                  bg=self.colors["INPUT"], fg=self.colors["FG"], relief="flat", font=("Segoe UI", 7)).pack(side="left", padx=1)
        tk.Button(quick_frame, text="+1h", command=lambda: set_ot_time(60),
                  bg=self.colors["INPUT"], fg=self.colors["FG"], relief="flat", font=("Segoe UI", 7)).pack(side="left", padx=1)

        lbl(gf, "Sound").grid(row=3, column=0, sticky="w", pady=5)
        sound_frame = tk.Frame(gf, bg=self.colors["BG"])
        sound_frame.grid(row=3, column=1, columnspan=4, sticky="w", padx=(0, 10))

        self.cb_sound = ttk.Combobox(sound_frame, textvariable=self.v_sound, values=["Default", "Ping", "Double", "Long", "Error"], state="readonly", width=12)
        self.cb_sound.pack(side="left")
        tk.Button(sound_frame, text="▶", command=self.test_sound,
                  bg=self.colors["INPUT"], fg=self.colors["ACCENT"], relief="flat", width=3).pack(side="left", padx=(5, 0))

        tk.Label(sound_frame, text=" | ", bg=self.colors["BG"], fg=self.colors["TEXT_DIM"]).pack(side="left")
        tk.Label(sound_frame, text="Color", bg=self.colors["BG"], fg=self.colors["FG"], font=("Segoe UI", 10, "bold")).pack(side="left")
        self.color_preview = tk.Label(sound_frame, text="   ", bg=self.popup_color, relief="solid", bd=1, width=4)
        self.color_preview.pack(side="left", padx=(8, 5))
        tk.Button(sound_frame, text="Pick", command=self.pick_color,
                  bg=self.colors["INPUT"], fg=self.colors["FG"], relief="flat").pack(side="left")

        lbl(gf, "Confirm").grid(row=4, column=0, sticky="nw", pady=5)
        dc_frame = tk.Frame(gf, bg=self.colors["BG"])
        dc_frame.grid(row=4, column=1, columnspan=4, sticky="ew", padx=(0, 10))
        self.chk_dc = tk.Checkbutton(dc_frame, text="Require Double-Check", variable=self.var_double_check,
                                     bg=self.colors["BG"], fg=self.colors["FG"], selectcolor=self.colors["BG"],
                                     activebackground=self.colors["BG"], activeforeground=self.colors["FG"],
                                     command=self.toggle_confirm_entry)
        self.chk_dc.pack(side="left")

        self.e_confirm_msg = tk.Entry(dc_frame, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"],
                                      disabledbackground=self.colors["DISABLED"], disabledforeground="#777",
                                      relief="flat", insertbackground=self.colors["FG"])
        self.e_confirm_msg.insert(0, "Are you sure?")
        self.e_confirm_msg.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.toggle_confirm_entry()

        self.lbl_snooze = lbl(gf, "Snooze")
        self.lbl_snooze.grid(row=5, column=0, sticky="nw", pady=5)
        self.snooze_frame = tk.Frame(gf, bg=self.colors["BG"])
        self.snooze_frame.grid(row=5, column=1, columnspan=4, sticky="ew", padx=(0, 10))

        self.chk_snooze = tk.Checkbutton(self.snooze_frame, text="Enable", variable=self.var_enable_snooze,
                                         bg=self.colors["BG"], fg=self.colors["FG"], selectcolor=self.colors["BG"],
                                         activebackground=self.colors["BG"], activeforeground=self.colors["FG"],
                                         command=self.toggle_snooze_entry)
        self.chk_snooze.pack(side="left")

        tk.Label(self.snooze_frame, text="Max:", bg=self.colors["BG"], fg=self.colors["FG"]).pack(side="left", padx=(5, 2))

        self.cb_max_snoozes = ttk.Combobox(self.snooze_frame, textvariable=self.v_max_snoozes,
                                           values=["1", "3", "5", "10", "Custom", "Unli"],
                                           state="readonly", width=7)
        self.cb_max_snoozes.pack(side="left")
        self.cb_max_snoozes.bind("<<ComboboxSelected>>", self.on_snooze_combo_change)

        self.e_custom_snooze = tk.Entry(self.snooze_frame, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"],
                                        width=3, relief="flat", insertbackground=self.colors["FG"],
                                        disabledbackground=self.colors["DISABLED"], disabledforeground="#777")
        self.e_custom_snooze.pack(side="left", padx=(2, 0))

        tk.Label(self.snooze_frame, text="| Mode:", bg=self.colors["BG"], fg=self.colors["FG"]).pack(side="left", padx=(10, 2))

        lbl_mode_help = tk.Label(self.snooze_frame, text="(?)", bg=self.colors["BG"], fg="#777", font=("Segoe UI", 8, "bold"), cursor="hand2")
        lbl_mode_help.pack(side="left", padx=(0, 5))
        ToolTip(lbl_mode_help, "SHIFT: Delays subsequent reminders.\nKEEP: Temporary snooze, preserves original schedule.")

        self.cb_snooze_behavior = ttk.Combobox(self.snooze_frame, textvariable=self.v_snooze_behavior,
                                               values=["shift", "keep"], state="readonly", width=8)
        self.cb_snooze_behavior.pack(side="left")

        self.toggle_snooze_entry()

        tk.Frame(gf, bg="#333", height=1).grid(row=6, column=0, columnspan=4, sticky="ew", pady=10)

        self.constraints_section = tk.Frame(gf, bg=self.colors["BG"])
        self.constraints_section.grid(row=7, column=0, columnspan=5, sticky="ew")
        self.constraints_section.columnconfigure(1, weight=1)

        cs = self.constraints_section

        self.lbl_days = lbl(cs, "Days")
        self.lbl_days.grid(row=0, column=0, sticky="w", pady=5, padx=(0, 5))
        self.days_frame = tk.Frame(cs, bg=self.colors["BG"], bd=0, highlightthickness=0)
        self.days_frame.grid(row=0, column=1, sticky="w")

        days = ["M", "T", "W", "T", "F", "S", "S"]
        for i, day in enumerate(days):
            tk.Checkbutton(self.days_frame, text=day, variable=self.day_vars[i], bg=self.colors["BG"], fg=self.colors["FG"],
                           selectcolor=self.colors["BG"], activebackground=self.colors["ACCENT"], activeforeground="white",
                           highlightthickness=0, bd=0).pack(side="left", padx=2)

        self.lbl_hours = lbl(cs, "Hours")
        self.lbl_hours.grid(row=1, column=0, sticky="nw", pady=5, padx=(0, 5))
        self.hours_frame = tk.Frame(cs, bg=self.colors["BG"], bd=0, highlightthickness=0)
        self.hours_frame.grid(row=1, column=1, sticky="w")

        self.chk_hours = tk.Checkbutton(self.hours_frame, text="Limit:", variable=self.var_use_hours,
                                        bg=self.colors["BG"], fg=self.colors["FG"], selectcolor=self.colors["BG"],
                                        activebackground=self.colors["BG"], activeforeground=self.colors["FG"],
                                        command=self.toggle_hours_entry)
        self.chk_hours.pack(side="left")

        hour_vals = [f"{h:02d}" for h in range(24)]
        min_vals = [f"{m:02d}" for m in range(0, 60, 15)]
        self.e_start_h = ttk.Combobox(self.hours_frame, values=hour_vals, width=3, state="readonly")
        self.e_start_h.set("08")
        self.e_start_h.pack(side="left", padx=(5, 0))

        self.lbl_c1 = tk.Label(self.hours_frame, text=":", bg=self.colors["BG"], fg=self.colors["FG"])
        self.lbl_c1.pack(side="left")

        self.e_start_m = ttk.Combobox(self.hours_frame, values=min_vals, width=3, state="readonly")
        self.e_start_m.set("00")
        self.e_start_m.pack(side="left")

        self.lbl_to = tk.Label(self.hours_frame, text=" to ", bg=self.colors["BG"], fg=self.colors["FG"])
        self.lbl_to.pack(side="left")

        self.e_end_h = ttk.Combobox(self.hours_frame, values=hour_vals, width=3, state="readonly")
        self.e_end_h.set("22")
        self.e_end_h.pack(side="left")

        self.lbl_c2 = tk.Label(self.hours_frame, text=":", bg=self.colors["BG"], fg=self.colors["FG"])
        self.lbl_c2.pack(side="left")

        self.e_end_m = ttk.Combobox(self.hours_frame, values=min_vals, width=3, state="readonly")
        self.e_end_m.set("00")
        self.e_end_m.pack(side="left")

        self.lbl_in = tk.Label(self.hours_frame, text=" in ", bg=self.colors["BG"], fg=self.colors["FG"])
        self.lbl_in.pack(side="left")
        self.cb_timezone = ttk.Combobox(self.hours_frame, textvariable=self.v_timezone, values=TZ_LABELS, state="readonly", width=6)
        self.cb_timezone.pack(side="left")

        self.toggle_hours_entry()

        self.lbl_pattern = lbl(cs, "Pattern")
        self.lbl_pattern.grid(row=2, column=0, sticky="nw", pady=5, padx=(0, 5))
        self.pattern_frame = tk.Frame(cs, bg=self.colors["BG"])
        self.pattern_frame.grid(row=2, column=1, sticky="ew")

        self.chk_pattern = tk.Checkbutton(self.pattern_frame, text="Anchor at:", variable=self.var_use_pattern,
                                         bg=self.colors["BG"], fg=self.colors["FG"], selectcolor=self.colors["BG"],
                                         activebackground=self.colors["BG"], activeforeground=self.colors["FG"],
                                         command=self.toggle_pattern_entry)
        self.chk_pattern.pack(side="left")

        lbl_pattern_help = tk.Label(self.pattern_frame, text="(?)", bg=self.colors["BG"], fg="#777", font=("Segoe UI", 8, "bold"), cursor="hand2")
        lbl_pattern_help.pack(side="left", padx=(0, 5))
        ToolTip(lbl_pattern_help, "Forces triggers to snap to specific times (e.g. :00, :30) instead of floating based on when you click done.")

        self.e_pattern_hour = tk.Entry(self.pattern_frame, bg=self.colors["INPUT"], fg=self.colors["TEXT_MAIN"],
                                       width=3, relief="flat", insertbackground=self.colors["FG"],
                                       disabledbackground=self.colors["DISABLED"], disabledforeground="#777")
        self.e_pattern_hour.pack(side="left", padx=(5, 0))

        tk.Label(self.pattern_frame, text=":", bg=self.colors["BG"], fg=self.colors["FG"]).pack(side="left")

        self.cb_pattern_minute = ttk.Combobox(self.pattern_frame, textvariable=self.v_pattern_minute,
                                               values=["00", "15", "30", "45"], state="readonly", width=4)
        self.cb_pattern_minute.pack(side="left")

        self.cb_pattern_timezone = ttk.Combobox(self.pattern_frame, textvariable=self.v_pattern_timezone,
                                               values=TZ_LABELS, state="readonly", width=6)
        self.cb_pattern_timezone.pack(side="left", padx=(5, 0))

        def set_pattern_to_now():
            now_zone = self.get_now_zone(self.v_pattern_timezone.get())
            self.e_pattern_hour.delete(0, 'end')
            self.e_pattern_hour.insert(0, str(now_zone.hour))
            self.v_pattern_minute.set(f"{now_zone.minute:02d}")

        tk.Button(self.pattern_frame, text="Now", command=set_pattern_to_now,
                  bg=self.colors["INPUT"], fg=self.colors["FG"], relief="flat", font=("Segoe UI", 7)).pack(side="left", padx=(5, 0))

        self.toggle_pattern_entry()

        self.toggle_one_time_entry()

        bf = tk.Frame(self.edit_frame, bg=self.colors["BG"])
        bf.pack(fill="x", padx=10, pady=(0, 10))
        self.btn_save = tk.Button(bf, text="+ ADD REMINDER", command=self.save_reminder,
                                  bg=self.colors["ACCENT"], fg="white", relief="flat", font=("Segoe UI", 10, "bold"))
        self.btn_save.pack(side="left", fill="x", expand=True)

        tk.Button(bf, text="CLEAR", command=self.clear_form,
                  bg=self.colors["INPUT"], fg=self.colors["FG"], relief="flat").pack(side="left", padx=5)
        tk.Button(bf, text="HIDE", command=self._hide_editor,
                  bg=self.colors["INPUT"], fg=self.colors["FG"], relief="flat").pack(side="left", padx=(0, 5))

        self.btn_cancel = tk.Button(bf, text="CANCEL", command=self.cancel_edit,
                                    bg=self.colors["INPUT"], fg=self.colors["FG"], relief="flat")
        self.btn_cancel.pack(side="left", padx=(0, 5))
        self.btn_cancel.pack_forget()

        self._editor_built = True

    def _bound_to_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def update_scroll_region(self):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if self.scrollable_frame.winfo_height() > self.canvas.winfo_height():
            self.scrollbar.pack(side="right", fill="y")
        else:
            self.scrollbar.pack_forget()

    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_frame, width=event.width)
        if self.scrollable_frame.winfo_height() > event.height:
            self.scrollbar.pack(side="right", fill="y")
        else:
            self.scrollbar.pack_forget()

    def set_title_bar_dark(self, dark=True):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value))
        except:
            pass

    def toggle_theme(self):
        if self.is_dark_mode:
            self.colors = PALETTE_LIGHT
            self.is_dark_mode = False
        else:
            self.colors = PALETTE_DARK
            self.is_dark_mode = True
        for item in self.cache:
            item['widget_ref'] = None
            item['lbl_title'] = None
            item['lbl_status'] = None
        self.build_ui()
        self.set_title_bar_dark(self.is_dark_mode)

    def restart_app(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE settings SET window_x=NULL, window_y=NULL WHERE id=1")
            conn.commit()
            conn.close()
        except: pass
        if self.icon:
            self.icon.stop()
        self.release_lock()
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable], startupinfo=startupinfo, creationflags=0x08000000)
        else:
            python = sys.executable
            script = os.path.abspath(__file__)
            if 'python.exe' in python.lower():
                python = python.replace('python.exe', 'pythonw.exe')
            try:
                with open(script, "r", encoding='utf-8') as f:
                    source = f.read()
                compile(source, script, "exec")
                subprocess.Popen([python, script], startupinfo=startupinfo, creationflags=0x08000000)
            except Exception as e:
                messagebox.showerror("Cannot Restart", f"Error: {e}\n\nScript: {script}\nPython: {python}")
                return
        self.root.quit()
        sys.exit()

    def toggle_confirm_entry(self):
        if self.var_double_check.get() == 1:
            self.e_confirm_msg.config(state='normal', fg=self.colors["TEXT_MAIN"])
        else:
            self.e_confirm_msg.config(state='disabled')

    def toggle_pattern_entry(self):
        if self.var_use_pattern.get() == 1:
            self.e_pattern_hour.config(state="normal", fg=self.colors["TEXT_MAIN"])
            self.cb_pattern_minute.config(state="readonly")
            self.cb_pattern_timezone.config(state="readonly")
        else:
            self.e_pattern_hour.config(state="normal")
            self.e_pattern_hour.delete(0, 'end')
            self.e_pattern_hour.config(state="disabled")
            
            self.cb_pattern_minute.config(state="normal") 
            self.v_pattern_minute.set("00")
            self.cb_pattern_minute.config(state="disabled")
            
            self.cb_pattern_timezone.config(state="disabled")

    def on_snooze_combo_change(self, event=None):
        if self.v_max_snoozes.get() == "Custom":
            self.e_custom_snooze.config(state="normal", fg=self.colors["TEXT_MAIN"])
            self.e_custom_snooze.delete(0, 'end')
            self.e_custom_snooze.insert(0, "15")
            self.e_custom_snooze.focus()
        else:
            self.e_custom_snooze.config(state="disabled")
            self.e_custom_snooze.delete(0, 'end')

    def toggle_snooze_entry(self):
        if self.var_enable_snooze.get() == 1:
            self.cb_max_snoozes.config(state="readonly")
            self.cb_snooze_behavior.config(state="readonly")
            if self.v_max_snoozes.get() == "Custom":
                self.e_custom_snooze.config(state="normal", fg=self.colors["TEXT_MAIN"])
            else:
                self.e_custom_snooze.config(state="disabled")
        else:
            self.cb_max_snoozes.config(state="disabled")
            self.e_custom_snooze.config(state="disabled")
            self.cb_snooze_behavior.config(state="disabled")

    def toggle_hours_entry(self):
        widgets = [self.e_start_h, self.e_start_m, self.e_end_h, self.e_end_m]
        labels = [self.lbl_to, self.lbl_c1, self.lbl_c2, self.lbl_in]
        if self.var_use_hours.get() == 1:
            for w in widgets:
                w.config(state='readonly')
            for l in labels:
                l.config(fg=self.colors["FG"])
            self.cb_timezone.config(state="readonly")
        else:
            for w in widgets:
                w.config(state='disabled')
            for l in labels:
                l.config(fg="#777")
            self.cb_timezone.config(state="disabled")

    def toggle_one_time_entry(self):
        try:
            current_height = self.edit_frame.winfo_height()
            self.edit_frame.config(height=current_height)
            self.edit_frame.pack_propagate(False)
        except:
            pass

        if self.var_one_time.get() == 1:
            self.lbl_interval.config(text="One-Time")
            self.e_int.pack_forget()
            self.one_time_frame.pack(side="left", fill="x", expand=True)

            self.constraints_section.grid_remove()

            if not self.v_tt_mm.get() or not self.v_tt_dd.get():
                now_zone = self.get_now_zone(self.v_tt_tz.get())
                self.v_tt_mm.set(f"{now_zone.month:02d}")
                self.v_tt_dd.set(f"{now_zone.day:02d}")
                self.v_tt_yy.set(now_zone.strftime("%y"))
                self.v_tt_hh.set(f"{now_zone.hour:02d}")
                self.v_tt_min.set(f"{now_zone.minute:02d}")

        else:
            self.lbl_interval.config(text="Every")
            self.one_time_frame.pack_forget()
            self.e_int.pack(side="left")

            self.constraints_section.grid()

        self.root.after(50, lambda: self.edit_frame.pack_propagate(True))

    def pick_color(self):
        color = colorchooser.askcolor(title="Choose Popup Background", initialcolor=self.popup_color)
        if color[1]:
            self.popup_color = color[1]
            self.color_preview.config(bg=self.popup_color)

    def test_sound(self):
        self.play_sound_once(self.v_sound.get())

    def play_sound_once(self, sound_name):
        def beep(freq, dur):
            try:
                winsound.Beep(freq, dur)
            except:
                winsound.MessageBeep(winsound.MB_OK)
        try:
            if sound_name == "Default":
                beep(800, 200)
            elif sound_name == "Ping":
                beep(1200, 150)
            elif sound_name == "Double":
                beep(1000, 100)
                time.sleep(0.1)
                beep(1000, 100)
            elif sound_name == "Long":
                beep(700, 600)
            elif sound_name == "Error":
                winsound.MessageBeep(winsound.MB_ICONHAND)
            else:
                beep(800, 200)
        except:
            pass

    def start_sound_loop(self, sound_name, stop_event):
        while not stop_event.is_set():
            self.play_sound_once(sound_name)
            for _ in range(20): 
                if stop_event.is_set():
                    break
                time.sleep(0.1)

    def load_reminder_into_form(self, r_id):
        self._ensure_editor()
        item_data = next((i for i in self.cache if i['id'] == r_id), None)
        if not item_data:
            return
        if self.editing_id is None:
            self.add_draft = self.get_current_form_data()
        self.editing_id = r_id
        self.set_form_data(item_data)
        self.btn_save.config(text="UPDATE REMINDER", bg=self.colors["SUCCESS"])
        self.btn_cancel.pack(side="right", padx=(5, 0))

    def get_current_form_data(self):
        return {
            'title': self.e_title.get(),
            'message': self.e_msg.get(),
            'interval_minutes': self._parse_interval(self.e_int.get()),
            'sound': self.v_sound.get(),
            'active_days': [v.get() for v in self.day_vars],
            'start_hour': self.e_start_h.get(),
            'start_minute': self.e_start_m.get(),
            'end_hour': self.e_end_h.get(),
            'end_minute': self.e_end_m.get(),
            'double_check': self.var_double_check.get(),
            'confirm_msg': self.e_confirm_msg.get(),
            'use_active_hours': self.var_use_hours.get(),
            'timezone': self.v_timezone.get(),
            'popup_bg_color': self.popup_color,
            'enable_snooze': self.var_enable_snooze.get(),
            'max_snoozes': self.v_max_snoozes.get(),
            'custom_snooze': self.e_custom_snooze.get(),
            'use_start_pattern': self.var_use_pattern.get(),
            'pattern_hour': self.e_pattern_hour.get(),
            'pattern_minute': self.v_pattern_minute.get(),
            'pattern_timezone': self.v_pattern_timezone.get(),
            'snooze_behavior': self.v_snooze_behavior.get(),
            'is_one_time': self.var_one_time.get()
        }

    def set_form_data(self, data):
        self.e_title.delete(0, 'end')
        self.e_title.insert(0, data['title'])
        self.e_msg.delete(0, 'end')
        self.e_msg.insert(0, data['message'])
        self.e_int.set(self._format_interval(int(data['interval_minutes'])))
        self.v_sound.set(data['sound'])
        if isinstance(data['active_days'], str):
            active_days = [int(x) for x in data['active_days'].split(',')]
            for i, v in enumerate(self.day_vars):
                v.set(1 if i in active_days else 0)
        else:
            for i, v in enumerate(self.day_vars):
                v.set(data['active_days'][i])
        self.e_start_h.set(f"{int(data.get('start_hour', 8)):02d}")
        self.e_start_m.set(f"{int(data.get('start_minute', 0)):02d}")
        self.e_end_h.set(f"{int(data.get('end_hour', 22)):02d}")
        self.e_end_m.set(f"{int(data.get('end_minute', 0)):02d}")
        self.var_double_check.set(data['double_check'])
        self.e_confirm_msg.delete(0, 'end')
        self.e_confirm_msg.insert(0, data['confirm_msg'])
        self.toggle_confirm_entry()
        self.var_use_hours.set(data['use_active_hours'])
        self.v_timezone.set(data.get('timezone', 'ET'))
        self.toggle_hours_entry()
        self.popup_color = data['popup_bg_color'] if data['popup_bg_color'] else "#111111"
        self.color_preview.config(bg=self.popup_color)
        
        self.var_enable_snooze.set(data.get('enable_snooze', 1))
        self.v_max_snoozes.set(str(data.get('max_snoozes', 3)))
        self.v_snooze_behavior.set(data.get('snooze_behavior', 'shift'))
        self.toggle_snooze_entry()

        self.var_one_time.set(data.get('is_one_time', 0))
        if data.get('one_time_date'):
            try:
                task_tz = data.get('timezone', 'PHT')
                self.v_tt_tz.set(task_tz)
                dt_utc = datetime.strptime(data.get('one_time_date'), "%Y-%m-%d %H:%M")
                dt_zone = self.convert_utc_to_zone(dt_utc, task_tz)
                
                self.v_tt_mm.set(f"{dt_zone.month:02d}")
                self.v_tt_dd.set(f"{dt_zone.day:02d}")
                self.v_tt_yy.set(dt_zone.strftime("%y"))
                self.v_tt_hh.set(f"{dt_zone.hour:02d}")
                self.v_tt_min.set(f"{dt_zone.minute:02d}")
            except:
                pass
        self.toggle_one_time_entry()
        
        self.var_use_pattern.set(data.get('use_start_pattern', 0))
        self.e_pattern_hour.delete(0, 'end')
        if data.get('pattern_hour') is not None:
             self.e_pattern_hour.insert(0, str(data.get('pattern_hour')))
        self.v_pattern_minute.set(f"{int(data.get('pattern_minute', 0)):02d}")
        self.v_pattern_timezone.set(data.get('pattern_timezone', 'PHT')) 
        self.toggle_pattern_entry()

    def duplicate_reminder(self, r_id):
        self._ensure_editor()
        item_data = next((i for i in self.cache if i['id'] == r_id), None)
        if not item_data:
            return
        if self.editing_id is None:
            self.add_draft = self.get_current_form_data()
        self.editing_id = None
        self.set_form_data(item_data)
        self.e_title.insert(0, "[COPY] ")
        self.btn_save.config(text="+ ADD DUPLICATE", bg=self.colors["ACCENT"])
        self.btn_cancel.pack(side="right", padx=(5, 0))

    def cancel_edit(self):
        self._ensure_editor()
        self.editing_id = None
        if self.add_draft:
            self.set_form_data(self.add_draft)
            self.add_draft = None
        else:
            self.clear_form() 
        self.btn_save.config(text="+ ADD REMINDER", bg=self.colors["ACCENT"])
        self.btn_cancel.pack_forget()

    def clear_form(self):
        self._ensure_editor()
        self.editing_id = None
        self.add_draft = None
        self.e_title.delete(0, 'end')
        self.e_msg.delete(0, 'end')
        self.e_int.set("1h")
        self.var_double_check.set(0)
        self.e_confirm_msg.delete(0, 'end')
        self.e_confirm_msg.insert(0, "Are you sure?")
        self.toggle_confirm_entry()
        self.var_use_hours.set(0)
        self.v_timezone.set("ET")
        self.toggle_hours_entry()
        self.popup_color = "#111111"
        self.color_preview.config(bg=self.popup_color)
        for v in self.day_vars:
            v.set(1)
        self.var_enable_snooze.set(1)
        self.v_max_snoozes.set("3")
        self.e_custom_snooze.delete(0, 'end')
        self.v_snooze_behavior.set("shift")
        self.var_use_pattern.set(0)
        self.e_pattern_hour.delete(0, 'end')
        self.v_pattern_minute.set("00")
        self.v_pattern_timezone.set("PHT") # Reset defaults to PHT
        self.toggle_snooze_entry()
        self.toggle_pattern_entry()
        
        self.var_one_time.set(0)
        self.v_tt_mm.set("")
        self.v_tt_dd.set("")
        self.v_tt_yy.set(datetime.now().strftime("%y"))
        self.v_tt_hh.set("")
        self.v_tt_min.set("")
        self.v_tt_tz.set("PHT")
        
        self.toggle_one_time_entry()
        self.btn_save.config(text="+ ADD REMINDER", bg=self.colors["ACCENT"])
        self.btn_cancel.pack_forget()

    def save_reminder(self):
        self._ensure_editor()
        t = self.e_title.get().strip()
        if not t:
            messagebox.showerror("Error", "Title cannot be empty!")
            return
        m = self.e_msg.get()
        s = self.v_sound.get()
        tz = self.v_timezone.get()
        
        is_one_time = self.var_one_time.get()
        one_time_date_utc = None
        inter = 60
        
        try:
            if is_one_time:
                try:
                    mm = int(self.v_tt_mm.get())
                    dd = int(self.v_tt_dd.get())
                    yy = int(self.v_tt_yy.get())
                    hh = int(self.v_tt_hh.get())
                    mn = int(self.v_tt_min.get())
                    
                    if not (1 <= mm <= 12) or not (1 <= dd <= 31) or not (0 <= hh <= 23) or not (0 <= mn <= 59):
                        raise ValueError
                    
                    target_date = f"20{yy:02d}-{mm:02d}-{dd:02d}"
                    task_tz = self.v_tt_tz.get()
                    tz = task_tz 
                    
                    dt_zone = datetime.strptime(f"{target_date} {hh:02d}:{mn:02d}", "%Y-%m-%d %H:%M")
                    dt_utc = self.convert_zone_to_utc(dt_zone, task_tz)
                    one_time_date_utc = dt_utc.strftime("%Y-%m-%d %H:%M")
                    
                except ValueError:
                     messagebox.showerror("Error", "Invalid Date/Time.\nCheck format and values.")
                     return
            else:
                inter = self._parse_interval(self.e_int.get())

            start_h = int(self.e_start_h.get())
            start_m = int(self.e_start_m.get())
            end_h = int(self.e_end_h.get())
            end_m = int(self.e_end_m.get())
            dc = self.var_double_check.get()
            cm = self.e_confirm_msg.get()
            use_hours = self.var_use_hours.get()
            
            bg_col = self.popup_color
            enable_snooze = self.var_enable_snooze.get()
            max_snoozes_str = self.v_max_snoozes.get()
            if max_snoozes_str == "Unli":
                max_snoozes = 999
            elif max_snoozes_str == "Custom":
                try:
                    max_snoozes = int(self.e_custom_snooze.get())
                    if max_snoozes < 1:
                        max_snoozes = 1
                except ValueError:
                    messagebox.showerror("Error", "Invalid custom snooze value!")
                    return
            else:
                max_snoozes = int(max_snoozes_str)
            
            snooze_behavior = self.v_snooze_behavior.get()
            use_pattern = self.var_use_pattern.get()
            pattern_hour_str = self.e_pattern_hour.get().strip()
            pattern_hour = int(pattern_hour_str) if pattern_hour_str else None
            pattern_minute = int(self.v_pattern_minute.get())
            pattern_tz = self.v_pattern_timezone.get()
            
            days = [str(i) for i, v in enumerate(self.day_vars) if v.get() == 1]
            days_str = ",".join(days)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            now_utc = self.get_now_utc()
            
            if is_one_time:
                first_trig = one_time_date_utc + ":00"
            elif use_pattern:
                first_trig_dt = self.calculate_next_trigger_with_pattern(
                    now_utc, inter,
                    use_pattern, 
                    pattern_hour,
                    pattern_minute, 
                    pattern_tz,
                    use_hours, 
                    start_h, 
                    start_m,
                    end_h, 
                    end_m, 
                    days_str,
                    tz
                )
                first_trig = first_trig_dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                first_trig = now_utc.strftime("%Y-%m-%d %H:%M:%S")  # fire immediately on first check_loop

            new_item = {
                'title': t, 'message': m, 'interval_minutes': inter, 'sound': s,
                'active_days': days_str, 
                'start_hour': start_h, 'start_minute': start_m, 
                'end_hour': end_h, 'end_minute': end_m,
                'double_check': dc, 'confirm_msg': cm, 'use_active_hours': use_hours,
                'timezone': tz, 'popup_bg_color': bg_col, 'is_active': 1, 
                'enable_snooze': enable_snooze, 'max_snoozes': max_snoozes, 'snoozes_used': 0,
                'use_start_pattern': use_pattern, 'pattern_hour': pattern_hour,
                'pattern_minute': pattern_minute, 'pattern_timezone': pattern_tz,
                'snooze_behavior': snooze_behavior,
                'is_one_time': is_one_time, 'one_time_date': one_time_date_utc,
                'widget_ref': None, 'lbl_title': None, 'lbl_status': None
            }
            
            if self.editing_id:
                new_item['id'] = self.editing_id
                old_item = next((i for i in self.cache if i['id'] == self.editing_id), None)
                if old_item:
                    if old_item.get('use_start_pattern') != use_pattern or \
                       old_item.get('pattern_hour') != pattern_hour or \
                       old_item.get('pattern_minute') != pattern_minute or \
                       old_item.get('pattern_timezone') != pattern_tz or \
                       old_item.get('is_one_time') != is_one_time or \
                       old_item.get('one_time_date') != one_time_date_utc:
                        new_item['snoozes_used'] = 0
                        new_item['next_trigger'] = first_trig
                    else:
                         new_item['snoozes_used'] = old_item.get('snoozes_used', 0)
                         if is_one_time:
                             new_item['next_trigger'] = first_trig
                         else:
                             new_item['next_trigger'] = old_item['next_trigger']
                        
                    new_item['sort_order'] = old_item['sort_order']
                    new_item['is_active'] = old_item['is_active']

                    # Auto-reactivate a Done Target Task if the new target date is in the future
                    if is_one_time and one_time_date_utc:
                        try:
                            new_target_utc = datetime.strptime(one_time_date_utc, "%Y-%m-%d %H:%M")
                            if new_target_utc > self.get_now_utc():
                                new_item['is_active'] = 1
                        except Exception:
                            pass
                self.bg_save_item(new_item)
                for i, item in enumerate(self.cache):
                    if item['id'] == self.editing_id:
                        self.cache[i] = new_item
                        break
            else:
                c.execute("SELECT MAX(sort_order) FROM reminders")
                res = c.fetchone()[0]
                new_order = (res + 1) if res is not None else 0
                
                c.execute("""INSERT INTO reminders (title, message, next_trigger, interval_minutes, sound, active_days, 
                             start_hour, start_minute, end_hour, end_minute, 
                             double_check, confirm_msg, use_active_hours, timezone, popup_bg_color, sort_order, is_active,
                             enable_snooze, max_snoozes, snoozes_used,
                             use_start_pattern, pattern_hour, pattern_minute, pattern_timezone, snooze_behavior,
                             is_one_time, one_time_date)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", 
                             (t, m, first_trig, inter, s, days_str, start_h, start_m, end_h, end_m, dc, cm, use_hours, tz, bg_col, new_order, 1,
                             enable_snooze, max_snoozes, 0, use_pattern, pattern_hour, pattern_minute, pattern_tz, snooze_behavior,
                             is_one_time, one_time_date_utc))
                new_item['id'] = c.lastrowid
                new_item['next_trigger'] = first_trig
                new_item['sort_order'] = new_order
                conn.commit()
                self.cache.append(new_item)
            conn.close()
            self.clear_form() 
            self.refresh_list()
        except ValueError:
            messagebox.showerror("Error", "Invalid numeric input")

    def toggle_active(self, r_id, current_val):
        new_val = 0 if current_val == 1 else 1
        saved = False
        for item in self.cache:
            if item['id'] == r_id:
                item['is_active'] = new_val
                item['widget_ref'] = None

                if new_val == 1:
                    try:
                        trig_time = datetime.strptime(item['next_trigger'], "%Y-%m-%d %H:%M:%S")

                        now_utc = self.get_now_utc()
                        if trig_time < now_utc:
                            if item.get('is_one_time', 0) == 0:
                                next_trig_dt = self.get_next_valid_time(
                                    now_utc, 0,
                                    item['use_active_hours'],
                                    item['start_hour'],
                                    item['start_minute'],
                                    item['end_hour'],
                                    item['end_minute'],
                                    item['active_days'],
                                    item.get('timezone', 'ET')
                                )
                                item['next_trigger'] = next_trig_dt.strftime("%Y-%m-%d %H:%M:%S")

                            self.bg_save_item({'id': r_id, 'is_active': new_val, 'next_trigger': item['next_trigger']})
                            saved = True
                    except:
                        pass

                break
        self.refresh_list()
        if not saved:
            self.bg_save_item({'id': r_id, 'is_active': new_val})

    def move_item(self, r_id, direction):
        idx = -1
        for i, item in enumerate(self.cache):
            if item['id'] == r_id:
                idx = i
                break
        if idx == -1:
            return
        swap_idx = idx + direction
        if 0 <= swap_idx < len(self.cache):
            self.cache[idx], self.cache[swap_idx] = self.cache[swap_idx], self.cache[idx]
            self.cache[idx]['sort_order'], self.cache[swap_idx]['sort_order'] = self.cache[swap_idx]['sort_order'], self.cache[idx]['sort_order']
            self.redraw_order_only()
            self.bg_save_order()

    def redraw_order_only(self):
        for item in self.cache:
            if item['widget_ref']:
                item['widget_ref'].pack_forget()
        for item in self.cache:
            if item['widget_ref']:
                item['widget_ref'].pack(fill="x", pady=2)

    def update_list_status(self):
        for item in self.cache:
            if not item.get('lbl_status'):
                continue
            tz_label = item.get('timezone', 'ET')
            display_tz = self._tz_label_from_windows_id(self.cached_tz) if self.cached_tz else self._get_personal_zone()
            trig_disp = "??"
            if item['next_trigger']:
                try:
                    dt_utc = datetime.strptime(item['next_trigger'], "%Y-%m-%d %H:%M:%S")
                    dt_zone = self.convert_utc_to_zone(dt_utc, display_tz)
                    trig_disp = dt_zone.strftime("%m-%d %H:%M") + f" {display_tz}"
                except:
                    pass
            status_extras = f" | {tz_label}" if item['use_active_hours'] else ""
            if item.get('is_one_time', 0):
                type_lbl = "ONE-TIME"
                info_lbl_str = "??"
                if item.get('one_time_date'):
                    try:
                        ot_dt_utc = datetime.strptime(item['one_time_date'], "%Y-%m-%d %H:%M")
                        ot_dt_zone = self.convert_utc_to_zone(ot_dt_utc, tz_label)
                        info_lbl_str = ot_dt_zone.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                info_lbl = f"{info_lbl_str} {tz_label}"
            else:
                type_lbl = self._format_interval(item['interval_minutes'])
                info_lbl = f"{item['sound']}{status_extras}"
            status_txt = f"{type_lbl} | {info_lbl} | Next: {trig_disp}"
            if not item['is_active']:
                if item.get('is_one_time', 0):
                    status_txt = f"{type_lbl} | (DONE)"
                else:
                    status_txt = f"{type_lbl} | (PAUSED)"
            item['lbl_status'].config(text=status_txt)

    def refresh_list(self):
        for w in self.scrollable_frame.winfo_children():
            w.pack_forget()
        self.cache.sort(key=lambda x: x['sort_order'])
        for item in self.cache:
            r_id = item['id']
            is_active = item['is_active']
            trig_disp = "??"
            is_past = False
            
            tz_label = item.get('timezone', 'ET')
            display_tz = self._tz_label_from_windows_id(self.cached_tz) if self.cached_tz else self._get_personal_zone()

            if item['next_trigger']:
                try:
                    dt_utc = datetime.strptime(item['next_trigger'], "%Y-%m-%d %H:%M:%S")
                    dt_zone = self.convert_utc_to_zone(dt_utc, display_tz)
                    trig_disp = dt_zone.strftime("%m-%d %H:%M") + f" {display_tz}"
                    if dt_utc < self.get_now_utc():
                        is_past = True
                except:
                    pass

            status_extras = f" | {tz_label}" if item['use_active_hours'] else ""
            
            if item.get('is_one_time', 0):
                type_lbl = "ONE-TIME"
                info_lbl_str = "??"
                if item.get('one_time_date'):
                    try:
                        ot_dt_utc = datetime.strptime(item['one_time_date'], "%Y-%m-%d %H:%M")
                        ot_dt_zone = self.convert_utc_to_zone(ot_dt_utc, tz_label)
                        info_lbl_str = ot_dt_zone.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                info_lbl = f"{info_lbl_str} {tz_label}"
            else:
                type_lbl = self._format_interval(item['interval_minutes'])
                info_lbl = f"{item['sound']}{status_extras}"
                
            status_txt = f"{type_lbl} | {info_lbl} | Next: {trig_disp}"
            if not is_active:
                if item.get('is_one_time', 0):
                     status_txt = f"{type_lbl} | (DONE)"
                else:
                     status_txt = f"{type_lbl} | (PAUSED)"

            if item.get('widget_ref') and item['widget_ref'].winfo_exists() and item.get('lbl_status'):
                card_bg = self.colors["CARD_BG"] if is_active else self.colors["CARD_INACTIVE"]
                fg_color = self.colors["TEXT_MAIN"] if is_active else self.colors["TEXT_DIM"]
                item['lbl_status'].config(text=status_txt, bg=card_bg, fg=self.colors["TEXT_DIM"] if is_active else "#666")
                item['lbl_title'].config(text=item['title'], bg=card_bg, fg=fg_color)
                item['widget_ref'].config(bg=card_bg)
                item['widget_ref'].pack(fill="x", pady=2)
            else:
                card_bg = self.colors["CARD_BG"] if is_active else self.colors["CARD_INACTIVE"]
                fg_color = self.colors["TEXT_MAIN"] if is_active else self.colors["TEXT_DIM"]
                f = tk.Frame(self.scrollable_frame, bg=card_bg, pady=5, padx=5)
                f.pack(fill="x", pady=2)
                item['widget_ref'] = f 
                
                toggle_bg = self.colors["SUCCESS"] if is_active else self.colors["ERROR"]
                toggle_txt = "ON" if is_active else "OFF"
                toggle_cmd = lambda rid=r_id, val=is_active: self.toggle_active(rid, val)
                
                if not is_active and item.get('is_one_time', 0) and is_past:
                    toggle_bg = self.colors["WARNING"] 
                    toggle_txt = "EDIT"
                    toggle_cmd = lambda rid=r_id: self.load_reminder_into_form(rid)
                
                if not is_active and item.get('is_one_time', 0) and not is_past:
                     toggle_bg = "#777" 
                     toggle_txt = "DONE"
                
                tk.Button(f, text=toggle_txt, bg=toggle_bg, fg="white", 
                          relief="flat", width=4, font=("Segoe UI", 8, "bold"),
                          command=toggle_cmd).pack(side="left", padx=5)
                
                btns = tk.Frame(f, bg=card_bg)
                btns.pack(side="right", padx=(0, 5))
                
                tk.Button(btns, text="↑", command=lambda rid=r_id: self.move_item(rid, -1), 
                          bg=card_bg, fg=fg_color, activebackground=card_bg, activeforeground=fg_color,
                          font=("Segoe UI", 12, "bold"), relief="flat", padx=5).pack(side="left")
                tk.Button(btns, text="↓", command=lambda rid=r_id: self.move_item(rid, 1), 
                          bg=card_bg, fg=fg_color, activebackground=card_bg, activeforeground=fg_color,
                          font=("Segoe UI", 12, "bold"), relief="flat", padx=5).pack(side="left")
                tk.Button(btns, text="DUP", command=lambda rid=r_id: self.duplicate_reminder(rid), 
                          bg=self.colors["ACCENT"], fg="white", relief="flat", font=("Segoe UI", 8, "bold"), width=4).pack(side="left", padx=4)
                tk.Button(btns, text="EDIT", command=lambda rid=r_id: self.load_reminder_into_form(rid), 
                          bg=self.colors["BTN_EDIT"], fg="white", relief="flat", font=("Segoe UI", 8, "bold"), width=5).pack(side="left", padx=4)
                tk.Button(btns, text="DEL", command=lambda rid=r_id, itm=item: self.bg_delete_item(rid) or self.cache.remove(itm) or itm['widget_ref'].destroy() or self.refresh_list(), 
                          bg=self.colors["BTN_DEL"], fg="white", relief="flat", font=("Segoe UI", 8, "bold"), width=5).pack(side="left", padx=4)

                info = tk.Frame(f, bg=card_bg)
                info.pack(side="left", fill="x", expand=True)
                item['lbl_title'] = tk.Label(info, text=item['title'], font=("Segoe UI", 10, "bold"), bg=card_bg, fg=fg_color)
                item['lbl_title'].pack(anchor="w")
                if item['message']:
                    tk.Label(info, text=item['message'], font=("Segoe UI", 9, "italic"), bg=card_bg, fg=self.colors["TEXT_DIM"] if is_active else "#777").pack(anchor="w")
                item['lbl_status'] = tk.Label(info, text=status_txt, font=("Segoe UI", 8), bg=card_bg, fg=self.colors["TEXT_DIM"] if is_active else "#666")
                item['lbl_status'].pack(anchor="w")

        self.root.after(10, self.update_scroll_region)

    def show_aggressive_popup(self, r_id, title, message, interval, sound, double_check, confirm_msg, bg_color, enable_snooze, max_snoozes, snoozes_used):
        item_data = next((i for i in self.cache if i['id'] == r_id), None)
        
        popup = tk.Toplevel(self.root)
        popup.title("REMINDER")
        popup.withdraw()
        popup.overrideredirect(True)
        popup.attributes('-topmost', True)
        popup.configure(bg=bg_color) 
        stop_sound = threading.Event()
        sound_thread = threading.Thread(target=self.start_sound_loop, args=(sound, stop_sound), daemon=True)
        sound_thread.start()
        main_content = tk.Frame(popup, bg=bg_color)
        confirm_content = tk.Frame(popup, bg=bg_color)
        main_content.pack(fill="both", expand=True, padx=20, pady=20)
        tk.Label(main_content, text=title, fg=self.colors["ACCENT"], bg=bg_color, font=("Segoe UI", 18, "bold"), wraplength=400).pack(pady=(10, 5))
        if message:
            tk.Label(main_content, text=message, fg="#ddd", bg=bg_color, font=("Segoe UI", 11, "italic"), wraplength=400).pack(pady=10)
        
        snoozes_left = max_snoozes - snoozes_used
        can_snooze = enable_snooze and (max_snoozes == 999 or snoozes_left > 0)
        
        if enable_snooze:
            if can_snooze:
                if max_snoozes == 999:
                    counter_text = f"∞ snoozes available"
                else:
                    counter_text = f"{snoozes_left}/{max_snoozes} snoozes left"
                tk.Label(main_content, text=counter_text, fg="#888", bg=bg_color, font=("Segoe UI", 9)).pack(pady=(5, 0))
                
                snooze_frame = tk.Frame(main_content, bg=bg_color)
                snooze_frame.pack(pady=15)
                
                def close_and_snooze(minutes_offset):
                    try:
                        stop_sound.set()
                        now_utc = self.get_now_utc()
                        
                        if not item_data:
                            raise ValueError("item_data not found")
                        
                        new_snoozes_used = item_data.get('snoozes_used', 0) + 1
                        item_data['snoozes_used'] = new_snoozes_used
                        
                        try:
                            snooze_behavior = item_data.get('snooze_behavior', 'shift')
                            use_pattern = item_data.get('use_start_pattern', 0)
                            is_one_time = item_data.get('is_one_time', 0)
                            
                            if is_one_time:
                                next_trig_dt = now_utc + timedelta(minutes=minutes_offset)
                            elif snooze_behavior == 'keep' and use_pattern:
                                next_trig_dt = self.calculate_next_trigger_with_pattern(
                                    now_utc + timedelta(minutes=minutes_offset), 
                                    item_data['interval_minutes'],
                                    use_pattern, 
                                    item_data.get('pattern_hour'),
                                    item_data.get('pattern_minute', 0), 
                                    item_data.get('pattern_timezone', 'ET'),
                                    item_data['use_active_hours'], 
                                    item_data['start_hour'], 
                                    item_data['start_minute'],
                                    item_data['end_hour'], 
                                    item_data['end_minute'], 
                                    item_data['active_days'],
                                    item_data.get('timezone', 'ET')
                                )
                            else:
                                next_trig_dt = self.get_next_valid_time(
                                    now_utc, minutes_offset, 
                                    item_data['use_active_hours'], 
                                    item_data['start_hour'], 
                                    item_data['start_minute'], 
                                    item_data['end_hour'], 
                                    item_data['end_minute'], 
                                    item_data['active_days'],
                                    item_data.get('timezone', 'ET')
                                )
                        except Exception:
                            next_trig_dt = now_utc + timedelta(minutes=minutes_offset)
                        
                        next_trig = next_trig_dt.strftime("%Y-%m-%d %H:%M:%S")
                        item_data['next_trigger'] = next_trig
                        
                        self.bg_save_item({'id': r_id, 'next_trigger': next_trig, 'snoozes_used': new_snoozes_used})
                        self.gui_queue.put(('REFRESH_LIST',))
                        
                        if r_id in self.active_popups:
                            self.active_popups.remove(r_id)
                        
                        self.gui_queue.put(('UPDATE_ICON',))
                        popup.destroy()
                        
                    except Exception as e:
                        try:
                            stop_sound.set()
                            if r_id in self.active_popups:
                                self.active_popups.remove(r_id)
                            self.gui_queue.put(('UPDATE_ICON',))
                            popup.destroy()
                        except:
                            pass
                
                for m in [1, 3, 5, 10, 15]: 
                    btn = tk.Button(snooze_frame, text=f"+{m}m", bg="#333", fg="white",
                                   command=lambda m=m: close_and_snooze(m))
                    btn.pack(side="left", padx=5)
            else:
                warning_frame = tk.Frame(main_content, bg=bg_color)
                warning_frame.pack(pady=15)
                tk.Label(warning_frame, text=f"⚠️ 0/{max_snoozes} snoozes left", 
                        fg=self.colors["WARNING"], bg=bg_color, font=("Segoe UI", 12, "bold")).pack()
                tk.Label(warning_frame, text="Complete the task!", 
                        fg=self.colors["WARNING"], bg=bg_color, font=("Segoe UI", 11)).pack()
        
        def close_and_mark_done():
            try:
                stop_sound.set()
                now_utc = self.get_now_utc()
                
                if not item_data:
                    raise ValueError("item_data not found")
                
                item_data['snoozes_used'] = 0
                is_one_time = item_data.get('is_one_time', 0)
                
                if is_one_time:
                    item_data['is_active'] = 0
                    self.bg_save_item({'id': r_id, 'is_active': 0, 'snoozes_used': 0})
                else:
                    try:
                        use_pattern = item_data.get('use_start_pattern', 0)
                        if use_pattern:
                            next_trig_dt = self.calculate_next_trigger_with_pattern(
                                now_utc, interval,
                                use_pattern, 
                                item_data.get('pattern_hour'),
                                item_data.get('pattern_minute', 0), 
                                item_data.get('pattern_timezone', 'ET'),
                                item_data['use_active_hours'], 
                                item_data['start_hour'], 
                                item_data['start_minute'],
                                item_data['end_hour'], 
                                item_data['end_minute'], 
                                item_data['active_days'],
                                item_data.get('timezone', 'ET')
                            )
                        else:
                            next_trig_dt = self.get_next_valid_time(
                                now_utc, interval, 
                                item_data['use_active_hours'], 
                                item_data['start_hour'], 
                                item_data['start_minute'], 
                                item_data['end_hour'], 
                                item_data['end_minute'], 
                                item_data['active_days'],
                                item_data.get('timezone', 'ET')
                            )
                        
                        next_trig = next_trig_dt.strftime("%Y-%m-%d %H:%M:%S")
                        item_data['next_trigger'] = next_trig
                        self.bg_save_item({'id': r_id, 'next_trigger': next_trig, 'snoozes_used': 0})
                        
                    except Exception:
                        next_trig_dt = now_utc + timedelta(minutes=interval)
                        next_trig = next_trig_dt.strftime("%Y-%m-%d %H:%M:%S")
                        item_data['next_trigger'] = next_trig
                        self.bg_save_item({'id': r_id, 'next_trigger': next_trig, 'snoozes_used': 0})

                self.gui_queue.put(('REFRESH_LIST',))
                
                if r_id in self.active_popups:
                    self.active_popups.remove(r_id)
                
                self.gui_queue.put(('UPDATE_ICON',))
                popup.destroy()
                
            except Exception as e:
                try:
                    stop_sound.set()
                except:
                    pass
                try:
                    if r_id in self.active_popups:
                        self.active_popups.remove(r_id)
                    self.gui_queue.put(('UPDATE_ICON',))
                except:
                    pass
                try:
                    popup.destroy()
                except:
                    pass
        
        def attempt_done():
            if double_check:
                main_content.pack_forget()
                confirm_content.pack(fill="both", expand=True, padx=20, pady=20)
                center_popup()
            else:
                close_and_mark_done()
        
        btn_done_main = tk.Button(main_content, text="MARK DONE", command=attempt_done, 
                                  bg=self.colors["SUCCESS"], fg="white", font=("Segoe UI", 12, "bold"), width=20)
        btn_done_main.pack(pady=10)
        tk.Label(confirm_content, text="WAIT!", fg=self.colors["WARNING"], bg=bg_color, font=("Segoe UI", 24, "bold")).pack(pady=(10, 5))
        tk.Label(confirm_content, text=confirm_msg, fg=self.colors["WARNING"], bg=bg_color, font=("Segoe UI", 16, "bold"), wraplength=400).pack(pady=10)
        conf_btn_frame = tk.Frame(confirm_content, bg=bg_color)
        conf_btn_frame.pack(pady=20)
        
        def confirm_yes():
            btn_yes.config(state="disabled", text="...") 
            close_and_mark_done()
        
        def confirm_no():
            confirm_content.pack_forget()
            main_content.pack(fill="both", expand=True, padx=20, pady=20)
            center_popup()
        
        btn_no = tk.Button(conf_btn_frame, text="GO BACK", command=confirm_no, bg=self.colors["ERROR"], fg="white", font=("Segoe UI", 12, "bold"), width=12)
        btn_no.pack(side="left", padx=10)
        btn_yes = tk.Button(conf_btn_frame, text="CONFIRM DONE", command=confirm_yes, bg=self.colors["SUCCESS"], fg="white", font=("Segoe UI", 12, "bold"), width=16)
        btn_yes.pack(side="left", padx=10)
        
        def center_popup():
            popup.update_idletasks()
            width = popup.winfo_reqwidth()
            if width < 450:
                width = 450
            height = popup.winfo_reqheight()
            scr_w = self.root.winfo_screenwidth()
            scr_h = self.root.winfo_screenheight()
            x = (scr_w // 2) - (width // 2)
            y = (scr_h // 2) - (height // 2)
            popup.geometry(f'{width}x{height}+{x}+{y}')
            popup.deiconify()
        
        center_popup()

    def check_loop(self):
        while self.running:
            try:
                now_utc = self.get_now_utc()
                now_str_min = now_utc.strftime("%Y%m%d%H%M")
                
                if now_utc >= self.next_tz_check:
                    self.check_and_switch_timezone(now_utc)
                    self.gui_queue.put(('UPDATE_ICON',))
                    self.next_tz_check = now_utc + timedelta(seconds=60)
                    # Daily DST warning check (midnight UTC)
                    if now_utc.hour == 0 and now_utc.minute < 1 and not self._dst_warning_dismissed:
                        warning = self.get_dst_warning_if_needed(now_utc)
                        if warning:
                            self.gui_queue.put(('DST_WARNING', warning))

                needs_status_update = False
                for item in self.cache:
                    if not item['is_active']:
                        continue

                    try:
                        trig_time = datetime.strptime(item['next_trigger'], "%Y-%m-%d %H:%M:%S")
                    except:
                        continue

                    if now_utc >= trig_time:
                        r_id = item['id']
                        if r_id in self.active_popups:
                            continue

                        if self.last_trigger_minute.get(r_id) == now_str_min:
                            continue

                        is_one_time = item.get('is_one_time', 0)
                        should_trigger = False

                        if is_one_time:
                            should_trigger = True
                        else:
                            if self.is_time_valid(now_utc, item['use_active_hours'], item['start_hour'], item['start_minute'],
                                                  item['end_hour'], item['end_minute'], item['active_days'], item.get('timezone', 'ET')):
                                should_trigger = True
                            else:
                                next_trig_dt = self.get_next_valid_time(
                                    now_utc, 0,
                                    item['use_active_hours'],
                                    item['start_hour'],
                                    item['start_minute'],
                                    item['end_hour'],
                                    item['end_minute'],
                                    item['active_days'],
                                    item.get('timezone', 'ET')
                                )
                                next_trig = next_trig_dt.strftime("%Y-%m-%d %H:%M:%S")
                                item['next_trigger'] = next_trig
                                self.bg_save_item({'id': r_id, 'next_trigger': next_trig})
                                needs_status_update = True

                        if should_trigger:
                            self.last_trigger_minute[r_id] = now_str_min
                            self.active_popups.add(r_id)
                            self.gui_queue.put(('UPDATE_ICON',))
                            self.gui_queue.put(('SHOW_POPUP', r_id, item['title'], item['message'], item['interval_minutes'], 
                                               item['sound'], item['double_check'], item['confirm_msg'], item['popup_bg_color'],
                                               item.get('enable_snooze', 1), item.get('max_snoozes', 3), item.get('snoozes_used', 0)))
                if needs_status_update:
                    self.gui_queue.put(('UPDATE_STATUS',))
            except Exception as e:
                print(f"Check Loop Error: {e}")
            time.sleep(CHECK_INTERVAL)

    def process_queue(self):
        wake_file = os.path.join(DATA_DIR, 'wake.flag')
        if os.path.exists(wake_file):
            try:
                os.remove(wake_file)
                self.gui_queue.put(('SHOW_DASHBOARD',))
            except:
                pass

        try:
            while True:
                msg = self.gui_queue.get_nowait()
                cmd = msg[0]
                if cmd == 'SHOW_POPUP':
                    self.show_aggressive_popup(*msg[1:])
                elif cmd == 'SHOW_DASHBOARD':
                    self.root.deiconify()
                    self.root.lift()
                    self.root.attributes('-topmost', True)
                    self.root.after(100, lambda: self.root.attributes('-topmost', False))
                    self.root.focus_force()
                    self.refresh_list()
                elif cmd == 'REFRESH_LIST':
                    self.refresh_list()
                elif cmd == 'UPDATE_STATUS':
                    self.update_list_status()
                elif cmd == 'UPDATE_ICON':
                    if self.icon:
                        self.icon.icon = self.create_dynamic_icon()
                        try:
                            self.icon.update_menu()
                        except:
                            pass
                elif cmd == 'UNINSTALL':
                    self.uninstall_app()
                elif cmd == 'REFRESH_TZ_BLOCKS_UI':
                    self._render_tz_blocks_table()
                    self._check_dst_warning()
                elif cmd == 'DST_WARNING':
                    if not self._dst_warning_dismissed and len(msg) > 1:
                        self._dst_banner_label.config(text=f"\u26a0 {msg[1]}")
                        self._dst_banner_frame.pack(fill="x", padx=10, pady=(0, 5), before=self._blocks_table_frame)
                elif cmd == 'SAVE_FEEDBACK':
                    try:
                        self.save_dot.config(text="\u2713", fg=self.colors["ACCENT"])
                        self.root.after(2000, lambda: self.save_dot.config(text=""))
                    except:
                        pass
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def hide_window(self):
        self.save_window_position()
        self.root.withdraw()
    
    def start_tray(self):
        try:
            image = self.create_dynamic_icon()
            menu = pystray.Menu(
                item('Open Dashboard', lambda i, It: self.gui_queue.put(('SHOW_DASHBOARD',)), default=True),
                pystray.Menu.SEPARATOR,
                item('Quick Toggle Timezone', self.quick_toggle_tz),
                item(lambda item: 'Resume TZ Automation' if self.var_tz_paused.get() == 1 else 'Pause TZ Automation', self.toggle_tz_pause),
                pystray.Menu.SEPARATOR,
                item('Uninstall', lambda i, It: self.gui_queue.put(('UNINSTALL',))),
                item('Quit', lambda i, It: self.quit_app(i))
            )
            self.icon = pystray.Icon("gawi", image, "Gawi", menu)
            self.icon.run()
        except Exception as e:
            print(f"Tray icon error: {e}")
    
    def uninstall_app(self):
        if not messagebox.askyesno("Uninstall Gawi",
            "This will remove Gawi and all its data from this computer.\n\nContinue?"):
            return
        self.set_startup_registry(False)
        self.running = False
        self.release_lock()
        try:
            shutil.rmtree(DATA_DIR, ignore_errors=True)
        except:
            pass
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
            bat = os.path.join(os.environ.get('TEMP', '.'), '_gawi_uninstall.bat')
            with open(bat, 'w') as f:
                f.write(f'@echo off\nping -n 3 127.0.0.1 >nul\ndel /f /q "{exe_path}"\ndel /f /q "%~f0"\n')
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            subprocess.Popen(['cmd', '/c', bat], startupinfo=startupinfo, creationflags=0x08000000)
        if self.icon:
            self.icon.stop()
        self.root.quit()
        sys.exit()

    def quit_app(self, icon):
        try:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE settings SET window_x=?, window_y=? WHERE id=1", (x, y))
            conn.commit()
            conn.close()
        except: pass
        self.running = False
        self.release_lock()
        icon.stop()
        self.root.quit()
        sys.exit()

if __name__ == "__main__":
    app = GawiApp()