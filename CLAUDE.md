# Gawi — CLAUDE.md

> **Gawi** (Filipino: Habit / Custom / Way) — an aggressive accountability reminder tool for Windows. Multi-timezone (ET, CT, MT, PT, PHT, JST, GMT) with configurable work/personal zone pair, intrusive-by-design popups. Think Habitica meets a system utility.

---

## 🤖 Agent Instructions (Read First)

### The Golden Rules

1. **NEVER split `gawi.pyw` into multiple files.** Single-file architecture is intentional — it keeps the entire codebase in one LLM context window. No MVC, no modules, no imports from local files.
2. **NEVER introduce new dependencies** without explicit user approval. The app must stay double-click runnable with `pythonw gawi.pyw`. Current approved deps: `tkinter`, `pystray`, `Pillow`, `sqlite3` (stdlib), `winsound` (stdlib), standard library only beyond those.
3. **NEVER use ORMs.** Raw `sqlite3` strings only. No SQLAlchemy, no Peewee.
4. **NEVER touch the `History/` folder.** Version backups live there. Do not read, modify, or reference files inside it.
5. **NEVER use `datetime.now()` anywhere in scheduling logic.** All engine logic uses `self.get_now_utc()` which returns a naive UTC datetime. The system clock is untrusted because the Timezone Switcher actively changes the Windows timezone.
6. **Prefer repetition over abstraction in UI code.** Verbose, repeated widget blocks are intentional — they allow surgical edits without breaking adjacent rows. Don't refactor UI blocks into helpers unless explicitly asked.
7. **Always update this file (CLAUDE.md / agent.md) after completing a feature or confirming a bug fix.** Move items from Active Bugs → Recently Fixed, update Roadmap checkboxes, bump version notes.
8. **Always push to GitHub after committing.** Don't ask — just `git push` after every commit.

### How to Make Changes

- **Surgical edits only.** Find the exact function, edit the minimum lines needed. Do not reformat surrounding code.
- **Before editing any scheduling logic**, re-read the "Biological Clock" and "Critical Mechanisms" sections below. The UTC rules are subtle and easy to break.
- **Test the change mentally** against the known bug scenarios listed in Known Issues before submitting.
- **After any change to `get_next_valid_time`, `calculate_next_trigger_with_pattern`, `reset_stale_reminders`, or `close_and_mark_done`**: trace through the Hibernate Scenario in the bug notes to confirm it's fixed.

### Feature Completion Checklist

Before marking anything done:
- ✅ Implement the code change
- ✅ Trace through edge cases mentally (especially timezone + hibernate scenarios)
- ✅ Update this file: move bugs to Recently Fixed, tick roadmap checkboxes, add version note
- ✅ Suggest next steps to user

### Bug Discovery Protocol

When a new bug is found mid-task:
- ✅ Add it immediately to "Known Issues > Active Bugs" with priority, root cause, and exact fix location
- ✅ Do NOT silently fix it without documenting it here first
- Priority scale: **P1** = wrong data / silent logic failure, **P2** = UX broken / feels wrong, **P3** = cosmetic / polish

### Testing Protocol

When fixing agent-detected bugs (bugs NOT reported by the user):
- ✅ After implementing fixes, provide a **step-by-step test scenario** the user can follow to verify each fix
- ✅ Keep instructions simple and non-technical — describe what to click/do and what should happen
- ✅ Group related fixes into a single test flow where possible (don't make the user test 10 things separately)

---

## Project Structure

```
gawi.pyw                   # ← THE ONLY FILE YOU EDIT. Everything lives here.
CLAUDE.md                  # This file (also saved as agent.md)
gawi_req_installer.bat     # Dependency installer for script mode users
gawi_installer.txt         # Setup instructions for script mode users
gawi.db                    # SQLite database (script mode: next to .pyw / exe mode: %APPDATA%\Gawi)
gawi.lock                  # Single-instance PID lock file
wake.flag                  # Signal file: written by new instance, read by running instance to deiconify
icon2.png                  # System tray base icon (PIL loads this)
Gawi_Distribution/         # Self-contained bundle for distribution (no DB)
History/                   # ⛔ DO NOT TOUCH. Version backups.
```

---

## Architecture

### Threading Model

| Thread | Role |
|--------|------|
| **Main Thread** | Tkinter UI event loop — all widget reads/writes MUST happen here or via `gui_queue` |
| **Checker Thread** | `check_loop()` — runs every 5s, evaluates triggers, posts to `gui_queue` |
| **Tray Thread** | `start_tray()` — pystray blocking loop, daemon |
| **Sound Thread** | Spawned per popup, non-blocking audio playback |
| **TZ Setter Thread** | Spawned by `set_timezone()`, daemon — runs PowerShell `Set-TimeZone` silently |

**Critical threading rule:** Never call Tkinter widget methods from the Checker or Tray threads. Always use `self.gui_queue.put(...)` and let `process_queue()` (which runs on the main thread via `root.after`) dispatch them.

### Dual-Mode Portability

| Mode | `DATA_DIR` | `RESOURCE_DIR` | Startup Registry |
|------|------------|----------------|-----------------|
| **Script (`.pyw`)** | `os.path.dirname(os.path.abspath(__file__))` | same | `pythonw.exe "script_path"` |
| **Compiled (`.exe`)** | `%APPDATA%\Gawi` | `sys._MEIPASS` | `sys.executable` directly |

Detection: `getattr(sys, 'frozen', False)` — True when compiled with PyInstaller.

---

## The Biological Clock (UTC Engine — Read Before Touching Scheduling)

**Core principle:** UTC is the single source of truth. The Windows system clock is untrusted because the Timezone Switcher feature actively changes it.

### Key Functions

```python
self.get_now_utc()                          # → naive UTC datetime. USE THIS everywhere, never datetime.now()
self.convert_utc_to_zone(utc_dt, "PHT")    # → PHT (UTC+8), always fixed
self.convert_utc_to_zone(utc_dt, "ET")     # → ET (UTC-4 DST or UTC-5 standard), DST-aware
self.convert_utc_to_zone(utc_dt, "CT")     # → CT, MT, PT, JST, GMT also supported
self.convert_zone_to_utc(zone_dt, "PHT")   # → back to UTC from any zone (two-pass for DST boundary safety)
self.get_offset_at("ET", utc_dt)           # → generic offset lookup from TZ_REGISTRY; DST-aware for US zones
```

### Timezone Labels (TZ_REGISTRY)
- `"ET"` — Eastern Time, UTC-5/UTC-4 DST
- `"CT"` — Central Time, UTC-6/UTC-5 DST
- `"MT"` — Mountain Time, UTC-7/UTC-6 DST
- `"PT"` — Pacific Time, UTC-8/UTC-7 DST
- `"PHT"` — Philippines Time, UTC+8, no DST
- `"JST"` — Japan Standard Time, UTC+9, no DST
- `"GMT"` — GMT/UTC, offset 0, no DST
- `"LOCAL"` — **DEPRECATED AND REMOVED.** Never reintroduce this.

### DB Storage Rule
All `next_trigger` values in the DB are stored as **naive UTC strings** in format `"%Y-%m-%d %H:%M:%S"`. Never store local time. Never store timezone-aware datetimes.

---

## Critical Mechanisms

### Scheduling Flow (Recurring Reminders)

```
check_loop() fires every 5s
  → compares now_utc >= item['next_trigger'] (parsed as naive UTC)
  → if true AND time is valid (is_time_valid check):
      → post SHOW_POPUP to gui_queue
  → if true AND time is NOT valid (outside active hours/days):
      → call get_next_valid_time() to find next valid UTC slot
      → save to DB and cache, post REFRESH_LIST

User presses DONE on popup:
  → close_and_mark_done() runs
  → if use_start_pattern: call calculate_next_trigger_with_pattern(now_utc, interval, ...)
  → else: call get_next_valid_time(now_utc, interval, ...)
  → save new next_trigger to DB and cache
```

### Start Pattern System (Anchored Scheduling)

Decouples trigger time from task completion time. Prevents "Daily Alarm Trap" where pressing DONE at 6PM pushes a daily 9AM task to the next day's 9AM+completion_offset.

- User sets an anchor: e.g., `pattern_hour=9, pattern_minute=0, pattern_timezone="PHT"`
- `calculate_next_trigger_with_pattern()` converts anchor to UTC, then uses interval as a grid stepping forward until it's in the future
- **"Now" button** sets pattern to `now + 1 minute` in the selected TZ

### One-Time Task Logic (formerly Target Task)

- `is_one_time = 1` in DB
- Remains `is_active = 1` until explicitly marked Done (persistent accountability)
- **Zombie Prevention**: If `next_trigger` is in the past and user tries to toggle ON, button becomes "EDIT" — forces new future time selection
- **Accountability Check**: On startup, if a target task's `next_trigger` is in the past, it fires immediately

### reset_stale_reminders() — Startup Behavior

Runs once on every app launch, before `check_loop` starts. Finds all recurring reminders whose `next_trigger < now_utc` and recalculates to a future time.

✅ **Fixed in v9.8:** Now checks `use_start_pattern` and routes to `calculate_next_trigger_with_pattern()` when enabled. Anchor grid preserved across hibernate/resume.

### Minute-Lock

Prevents duplicate popups within the same minute. Dict: `{reminder_id: "YYYYMMDDHHMM"}`. Checked in `check_loop` before firing.

### Ghost Buster Refresh

`refresh_list()` calls `pack_forget()` on all existing reminder cards before rebuilding. Prevents phantom widget stacking. The reuse path (when `widget_ref` exists) updates text/colors in-place instead of destroying and recreating widgets.

### Lightweight Status Updates

`update_list_status()` updates only the status text label on existing widgets — no layout changes, no widget creation. Used by `check_loop` via `UPDATE_STATUS` queue command for stale-item reschedules. `check_loop` batches all stale updates and posts a single `UPDATE_STATUS` instead of per-item `REFRESH_LIST`.

### High-Speed Static UI (Show/Hide Pattern)

Editor widgets are **lazy-loaded on first Add/Edit click** via `_build_editor()`. On startup, only a "+ ADD NEW REMINDER" placeholder button is shown. Once built, widgets are toggled with `grid_remove()` / `grid()` — never destroyed and rebuilt. The `constraints_section` frame wraps the Days/Hours/Pattern rows so they collapse with one call. `_ensure_editor()` guards all entry points (`save_reminder`, `load_reminder_into_form`, `clear_form`, `duplicate_reminder`, `cancel_edit`).

---

## Database Schema

```sql
CREATE TABLE reminders (
    id INTEGER PRIMARY KEY,
    title TEXT,
    message TEXT,
    next_trigger TEXT,              -- Naive UTC string: "YYYY-MM-DD HH:MM:SS"
    interval_minutes INTEGER,
    sound TEXT DEFAULT 'Default',
    active_days TEXT DEFAULT '0,1,2,3,4,5,6',  -- Comma-separated weekday ints (0=Mon)
    start_hour INTEGER DEFAULT 0,
    start_minute INTEGER DEFAULT 0,
    end_hour INTEGER DEFAULT 23,
    end_minute INTEGER DEFAULT 0,
    double_check INTEGER DEFAULT 0,
    confirm_msg TEXT DEFAULT 'Are you sure?',
    use_active_hours INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    popup_bg_color TEXT DEFAULT '#111111',
    timezone TEXT DEFAULT 'ET',     -- TZ label for active hours interpretation
    enable_snooze INTEGER DEFAULT 1,
    max_snoozes INTEGER DEFAULT 3,
    snoozes_used INTEGER DEFAULT 0,
    use_start_pattern INTEGER DEFAULT 0,
    pattern_hour INTEGER DEFAULT NULL,  -- NULL = minute-only anchor
    pattern_minute INTEGER DEFAULT 0,
    pattern_timezone TEXT DEFAULT 'ET',
    snooze_behavior TEXT DEFAULT 'shift',  -- 'shift' or 'keep'
    is_one_time INTEGER DEFAULT 0,
    one_time_date TEXT DEFAULT NULL
);

CREATE TABLE settings (
    id INTEGER PRIMARY KEY,           -- Always id=1, single row
    work_start_h INTEGER DEFAULT 7,
    work_start_m INTEGER DEFAULT 0,
    work_end_h INTEGER DEFAULT 17,
    work_end_m INTEGER DEFAULT 0,
    tz_paused INTEGER DEFAULT 0,
    window_x INTEGER DEFAULT NULL,   -- NULL = first launch → center on primary monitor
    window_y INTEGER DEFAULT NULL,   -- Saved on hide/quit, restored on startup
    work_days TEXT DEFAULT '0,1,2,3,4',  -- Comma-separated weekday ints (0=Mon), configurable
    work_zone TEXT DEFAULT 'ET',     -- TZ label for work hours (legacy, used for auto-migration)
    personal_zone TEXT DEFAULT 'PHT', -- TZ label for personal hours (key into TZ_REGISTRY)
    baseline_display_zone TEXT DEFAULT 'ET' -- TZ for displaying block times in comparison view
);

CREATE TABLE tz_blocks (
    id INTEGER PRIMARY KEY,
    zone TEXT NOT NULL,              -- TZ label from TZ_REGISTRY (e.g., "ET", "PT")
    start_h INTEGER NOT NULL,       -- 0-23 (in the block's own zone)
    start_m INTEGER NOT NULL,       -- 0-59
    end_h INTEGER NOT NULL,         -- 0-23
    end_m INTEGER NOT NULL,         -- 0-59
    active_days TEXT NOT NULL DEFAULT '0,1,2,3,4',  -- CSV weekday ints (0=Mon)
    sort_order INTEGER DEFAULT 0    -- First-match-wins priority (lower = higher priority)
);
```

**Migration pattern:** `init_db()` uses `ALTER TABLE ADD COLUMN IF NOT EXISTS` style migrations via PRAGMA + loop. Always add new columns here — never recreate the table. On first load, if `tz_blocks` is empty, auto-creates one block from existing `work_zone`/`work_start_h`/`work_end_h` settings.

---

## UI Architecture

### Layout Zones (Editor)

```
ZONE 1 — Daily Drivers (rows 0–3):
  Title* [────────────────────────] [One-Time Task ☐]
  Message [──────────────────────────────────────]
  Every [1h▼] / One-Time: [MM]/[DD]/[YY] — [HH]:[MM] (●)PHT ( )ET  [+15m][+1h]
  Sound [Default ▼][▶]  |  Color [■][Pick]

ZONE 2 — Logic Constraints (constraints_section frame, hidden for One-Time Tasks):
  Confirm [☐ Require Double-Check] [message entry]
  Snooze  [☐ Enable] Max:[3] Behavior:[shift▼]
  Days    [☐M][☐T][☐W][☐T][☐F][☐S][☐S]
  Hours   [☐ Use Active Hours] Start:[HH]:[MM] End:[HH]:[MM]
  Pattern [☐ Use Start Pattern] [HH]:[MM] TZ:[PHT▼]
  TZ      [ET▼]

ACTION BUTTONS (right-aligned):
  [CANCEL] [UPDATE] or [ADD]
```

### Column Lock Rule

`gf.columnconfigure(0, minsize=90, weight=0)` — Column 0 is fixed at 90px. This prevents the label column from shifting when right-side content changes width.

### UI/UX Rules

- **Smart Inputs**: Prefer Spinners/Dropdowns over free-text parsing
- **Layout Packing**: Pack Action Buttons (right) BEFORE expanding Info Text (middle) to prevent off-grid icons
- **Compact Headers**: Maximize list space; no large static decorative text
- **Tooltips**: Use `ToolTip()` for explanations; don't add static label clutter
- **Draft Memory**: Loading a reminder into the editor carries over all fields; "Janitor" cleanup explicitly clears fields not part of the loaded reminder

---

## Timezone Switcher (Multi-Zone Time Blocks)

Automatically switches the Windows system timezone between work zone blocks and a personal zone. Supports multiple work blocks (e.g., ET 9-12 + PT 1-5) with first-match-wins priority.

### Key Functions

```python
get_current_timezone()          # PowerShell Get-TimeZone — returns Windows TZ ID string
set_timezone(timezone_id)       # PowerShell Set-TimeZone — runs async on daemon thread
find_active_tz_block(now_utc)   # Returns TZ label of first matching work block, or personal zone
check_and_switch_timezone(now_utc)  # Called in check_loop every 60s; uses find_active_tz_block()
get_minutes_until_next_switch() # Scans forward minute-by-minute to find next zone change
quick_toggle_tz()               # Tray menu: toggle between current block zone and personal zone
toggle_tz_pause()               # Tray menu + UI: suspends automation, saves to settings DB
update_header()                 # Reads cached TZ state, updates header label, re-schedules itself
load_tz_blocks()                # Query tz_blocks table, populate self.tz_blocks cache
save_tz_block(block_dict)       # INSERT or UPDATE a block, reload cache
delete_tz_block(block_id)       # DELETE a block, rebuild sort_order
reorder_tz_blocks(block_id, direction)  # Swap sort_order with adjacent block
detect_tz_blocks_conflicts()    # Pairwise UTC overlap detection, returns (id_a, id_b, explanation)
get_dst_warning_if_needed(now_utc)  # Warns 7 days before DST if new conflicts would appear
_get_personal_zone()            # Read from settings var, fallback "PHT"
```

### Tray Icon States

| State | Color | Shape |
|-------|-------|-------|
| Any work block active | Green | Battery bars (minutes until next switch) |
| Personal zone (no block) | Blue | Battery bars (minutes until next switch) |
| Paused | Gray | Battery bars |
| < 60 min to switch | Any | Countdown number |
| Active popups | Any | + Red badge (top-right) |

### Settings Persistence

Personal zone and baseline display zone stored in `settings` table (id=1). Work blocks stored in `tz_blocks` table (zone, start/end, days, sort_order). Loaded at startup via `load_global_settings()` + `load_tz_blocks()`. Blocks saved individually via `save_tz_block()`. Auto-migration on first load creates one block from legacy `work_zone`/`work_start_h`/`work_end_h` settings.

---

## Color Palettes

```python
PALETTE_DARK  # is_dark_mode=True  — BG: #1e1e1e
PALETTE_LIGHT # is_dark_mode=False — BG: #e0e0e0 (soft grey)
```

Palette is stored in `self.colors`. All widgets reference `self.colors["KEY"]`. Toggle via `toggle_theme()` which rebuilds the full UI with `build_ui()`.

---

## Configuration Constants

```python
APP_ID = 'Gawi.Pro.v9.9.5'
CHECK_INTERVAL = 5          # seconds between check_loop iterations
TZ_REGISTRY = {...}         # Dict of 7 zones: ET, CT, MT, PT, PHT, JST, GMT — each with windows_id, base_offset, has_dst, dst_offset
TZ_LABELS = sorted(TZ_REGISTRY.keys())  # Alphabetically sorted list for UI dropdowns
```

Registry key for startup: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run\Gawi`

---

## Known Issues

### Active Bugs

- **P2 — Popup shrinks on second monitor (multi-DPI)**: On mixed-DPI setups (e.g., 1080p primary + 1440p secondary), Tkinter popups render small on the higher-DPI monitor. `SetProcessDpiAwareness(1)` was tried but broke icon rendering and overall UI sizing — reverted. **Parked** — no clean Tkinter fix without side effects.

### Known Behaviors

- **Reload always centers on primary monitor**: `restart_app()` clears saved `window_x`/`window_y` to `NULL` before relaunching. The new instance centers on primary via `apply_window_position()`.
- **Startup centers on first launch**: When `window_x`/`window_y` are `NULL` (first launch or post-reload), window centers on primary monitor. Subsequent hide/quit saves position for next normal launch.

### Recently Fixed

- ✅ **P1 — Day-of-week timezone mismatch** (v9.9.5): `calculate_next_trigger_with_pattern` and `check_loop` used `timezone` (active hours TZ) for day validation instead of `pattern_timezone`. UTC→ET weekday != UTC→PHT weekday near midnight, causing reminders to land on wrong days. Fixed by using `pattern_tz` when `use_start_pattern=1`.
- ✅ **P1 — SQL injection in `bg_save_item`** (v9.9.5): Column names from dict keys were interpolated into f-string SQL. Added `ALLOWED_REMINDER_COLUMNS` frozenset whitelist — only whitelisted column names reach the query.
- ✅ **P1 — Command injection in `set_timezone`** (v9.9.5): `timezone_id` passed directly to PowerShell. Now validated against `TZ_REGISTRY` valid Windows IDs before execution; cache reverts on failure.
- ✅ **P1 — Command injection in `set_startup_registry`** (v9.9.5): Paths with single quotes could break PowerShell shortcut creation. Fixed with `'` → `''` escaping.
- ✅ **P2 — Race condition on `active_popups`** (v9.9.5): Checker thread and main thread accessed `active_popups` set without synchronization. Added `threading.Lock` wrapping all access points.
- ✅ **P2 — DB connection leak in `bg_save_item`** (v9.9.5): `conn.close()` in try block skipped on exception. Fixed with `try/finally` pattern.
- ✅ **P3 — Bare except clauses** (v9.9.5): `init_db`, `bg_delete_item`, `get_current_timezone`, `_is_gawi_process` — all now catch `Exception` instead of bare `except:` and log errors.
- ✅ **P3 — `datetime.now()` in one-time task year default** (v9.9.5): Replaced with `self.get_now_utc().strftime("%y")` to stay consistent with UTC-first engine.
- ✅ **P1 — `get_next_valid_time` loop indentation** (v9.8): `candidate_utc += timedelta(minutes=1)` moved inside the `for` loop so it actually iterates through candidate minutes
- ✅ **P1 — Hibernate/resume pattern anchor** (v9.8): `reset_stale_reminders()` now checks `use_start_pattern` and routes to `calculate_next_trigger_with_pattern()` to preserve the anchor grid
- ✅ **P2 — Header TZ flicker** (v9.8): Introduced `self.cached_tz` — `update_header()` reads cache instead of spawning PowerShell subprocess on main thread every 5s. `set_timezone()` updates cache optimistically before async thread
- ✅ **P2 — Save feedback + delayed TZ switch** (v9.8): Added orange "unsaved" dot on field edit, green checkmark on save (auto-hides 2s). `save_global_settings()` now calls `check_and_switch_timezone()` immediately after save
- ✅ **P3 — Toggle bounce** (v9.8): `toggle_one_time_entry()` clamps editor frame height with `pack_propagate(False)` before layout change, releases after 50ms so resize is a single snap instead of animated
- ✅ Target Task auto-reactivation: editing a Done task with a future date now re-enables it without manual toggle
- ✅ Title box width instability on toggle (`row2_container` isolation)
- ✅ Days/Hours/Pattern 6-call cascade → single `constraints_section.grid_remove()`
- ✅ Color picker merged into Sound row (one fewer row, cleaner layout)
- ✅ Tray Double-Click restored after Target Task refactor
- ✅ **Perf — `create_dynamic_icon` PowerShell removal** (v9.8): Replaced `get_current_timezone()` subprocess with `self.cached_tz` in tray icon generation
- ✅ **Perf — Lightweight status updates** (v9.8): New `update_list_status()` method updates label text only, no widget rebuild. `check_loop` uses `UPDATE_STATUS` instead of `REFRESH_LIST`
- ✅ **Perf — Batched queue posts** (v9.8): `check_loop` collects stale-item updates and posts a single `UPDATE_STATUS` instead of N separate `REFRESH_LIST` messages
- ✅ **Perf — Widget reuse in `refresh_list()`** (v9.8): Reuse path now updates colors, title, and status text — only creates new widgets for genuinely new items

---

## Roadmap

### Completed ✅

**Phase 1 — UTC Migration (v9.5)**
- ✅ Purged LOCAL timezone. Engine decoupled from `datetime.now()`. 100% UTC-based.
- ✅ Active Hours/Days mapped explicitly to ET/PHT zones
- ✅ Start Pattern math rewritten (snaps UTC to zone and back)
- ✅ Snooze offsets calculated from absolute UTC
- ✅ Target Task (one-time) saves convert ET/PHT → UTC

**Phase 2 — Timezone Switcher + Target Task (v9.6)**
- ✅ PowerShell TZ switching integrated silently (daemon threads)
- ✅ `settings` table + "Pause TZ Automation" toggle
- ✅ 60s heartbeat in `check_loop` for TZ shift detection
- ✅ Dynamic battery/countdown tray icon + Discord-style badge
- ✅ `wake.flag` → `deiconify()` when second instance launched

**Phase 2.6 — Target Task High-Speed UI (v9.6)**
- ✅ "One-Time" renamed to "Target Task" with persistent accountability
- ✅ Segmented date entry `[MM]/[DD]/[YY] — [HH]:[MM]` with auto-tab
- ✅ PHT/ET radio buttons on trigger row
- ✅ `[+15m]`/`[+1h]` quick buttons

**Phase 2.7 — UI Alignment Polish (v9.7)**
- ✅ Title box extends to Target Task checkbox (`title_row` frame)
- ✅ `row2_container` isolates Every/One-Time swap from column widths
- ✅ `constraints_section` single-frame collapse (was 6 calls)
- ✅ Color merged into Sound row
- ✅ Target Task auto-reactivation on future date save
- ✅ PyInstaller `.exe` build with bundled icon, AppData portability

**Phase 3 — Distribution (v9.7)**
- ✅ Compiled standalone `.exe` with `--noconsole --onefile --icon`
- ✅ Dual-mode data path (AppData for `.exe`, script dir for `.pyw`)

### Planned

**Phase 2.8 — Bug Squash Sprint (v9.8)** ✅
- [x] Fix `get_next_valid_time` indentation (P1)
- [x] Fix `reset_stale_reminders` to use pattern calculator (P1)
- [x] Save feedback dot + immediate TZ switch on Save (P2)
- [x] Cache TZ state; remove PowerShell from `update_header` main thread (P2)

**Phase 2.9 — Performance Optimization (v9.8)** ✅
- [x] Remove PowerShell subprocess from `create_dynamic_icon()` hot path
- [x] Add `update_list_status()` lightweight refresh method
- [x] Batch `check_loop` queue posts (N→1)
- [x] Enhance widget reuse path in `refresh_list()` with color/title updates

**Phase 3.1 — Exe Distribution Fixes (v9.8.1)** ✅
- [x] Fix restart_app() crash in exe mode (P1) — exe-mode branch uses `sys.executable` directly
- [x] Fix startup checkbox for exe mode (P1) — shell:Startup shortcut instead of registry
- [x] Add tray icon error logging + `pystray._win32` hidden import (P1)
- [x] Switch sounds from `winsound.Beep()` to `winsound.MessageBeep()` (P2) — works on all hardware
- [x] Dynamic window height based on screen size (P2) — `min(1020, screenheight - 100)`
- [x] Add `insertbackground` to Target Task date/time entries (P2) — visible cursor in dark mode
- [x] Dark title bar via dwmapi `DwmSetWindowAttribute` (P3)
- [x] Day checkbox hover effect — blue accent on hover (P3)
- [x] Remove +1 minute from Anchor "Now" button (P3)

**Phase 3.2 — Bug Squash + Hardening (v9.9.1)** ✅
- [x] PID lock checks process name (pythonw.exe/python.exe/gawi.exe) — no more false locks from recycled PIDs
- [x] `refresh_list()` "Next:" display uses current system TZ (cached_tz) — consistent with `update_list_status()`
- [x] Popup centers on primary monitor with min-width 450 (height auto-fits content)
- [x] Reload centers on primary screen (`restart_app()` clears saved position to NULL)
- [x] `datetime.now()` → `datetime.now(timezone.utc)` for Target Task year default
- [x] `.strip()` on work hours parsing — prevents silent save failure on whitespace
- [x] `reset_stale_reminders()` logs errors instead of swallowing silently
- [x] `get_next_valid_time()` returns safe fallback with log when 7-day search fails
- [x] Day number validation clamped to 0-6 on load
- [x] CANCEL button properly initialized (pack then pack_forget)

**Phase 3.3 — Security + Correctness (v9.9.5)** ✅
- [x] Fix day-of-week timezone mismatch in pattern scheduling (P1) — pattern_tz vs active_tz
- [x] Fix SQL injection in `bg_save_item` (P1) — ALLOWED_REMINDER_COLUMNS whitelist
- [x] Fix command injection in `set_timezone` (P1) — validate against TZ_REGISTRY
- [x] Fix command injection in `set_startup_registry` (P1) — PowerShell single-quote escaping
- [x] Fix race condition on `active_popups` (P2) — threading.Lock
- [x] Fix DB connection leak in `bg_save_item` (P2) — try/finally
- [x] Replace bare except clauses with `except Exception` (P3)
- [x] Replace `datetime.now()` with `get_now_utc()` in one-time task year default (P3)

**Future**
- [ ] Analytics logs table + dashboard UI
- [x] Interval presets dropdown (15m–Monthly + custom input)
- [ ] Context presets (Deep Work / Admin modes)
- [ ] Snooze friction — free first snooze, confirmation on 2nd+, emergency 15m always available (ADHD-friendly)
- [x] More timezone support beyond ET/PHT (TZ_REGISTRY: ET, CT, MT, PT, PHT, JST, GMT)
- [x] Multi-zone time blocks (v9.9.4 — `tz_blocks` table, first-match-wins priority, ▲▼ reorder, conflict detection, baseline display zone, DST warnings, cross-midnight support)
- [ ] 15-minute time tracking / time blindness tool (parked — needs design)
- [ ] **Phase 4 — DearPyGui Migration** (rewrite UI layer only; keep scheduling engine, DB, threading model; GPU-accelerated immediate-mode rendering; ship same PyInstaller .exe)
- [ ] Anchor dates for Weekly/Monthly intervals (parked — needs design for day-of-week picker, day-of-month picker, TZ-aware anchoring)
- [ ] Always-visible day checkboxes (parked — Days checkboxes are hidden behind "Use Active Hours" toggle, but day filtering is useful independently. E.g., a "Daily" reminder that only fires Sat/Sun/Mon for weekend habits. Consider separating day selection from hour restrictions so the feature is more discoverable.)
- [x] Rename "Target Task" → "One-Time Task" in all UI strings

---

## Version History

### v9.9.5 (Current)
- **Security + Correctness Hardening**
- P1: Day-of-week timezone mismatch — `calculate_next_trigger_with_pattern` and `check_loop` now use `pattern_timezone` (not `timezone`) for weekday validation when `use_start_pattern=1`. Fixes reminders landing on wrong days when pattern TZ and active hours TZ straddle midnight differently.
- P1: SQL injection in `bg_save_item` — `ALLOWED_REMINDER_COLUMNS` frozenset whitelist prevents arbitrary column names in SQL
- P1: Command injection in `set_timezone` — validates `timezone_id` against `TZ_REGISTRY` valid Windows IDs; reverts cache on failure
- P1: Command injection in `set_startup_registry` — PowerShell single-quote escaping (`'` → `''`) for paths
- P2: Race condition on `active_popups` — `threading.Lock` wraps all read/write access (checker thread, main thread, tray icon)
- P2: DB connection leak in `bg_save_item` — `try/finally` ensures `conn.close()` runs on exception
- P3: Bare `except:` → `except Exception:` with logging in `init_db`, `bg_delete_item`, `get_current_timezone`, `_is_gawi_process`
- P3: `datetime.now()` → `self.get_now_utc()` for one-time task year default

### v9.9.4
- **Multi-Zone Time Blocks**
- New `tz_blocks` table: zone, start/end hours, active days, sort_order — supports unlimited work blocks
- `find_active_tz_block()` replaces `should_be_in_work_zone()` — first-match-wins priority for multiple overlapping blocks
- `detect_tz_blocks_conflicts()` — pairwise UTC overlap detection with cross-midnight support
- `get_dst_warning_if_needed()` — warns 7 days before DST transition if new conflicts would appear
- Baseline display zone dropdown — converts all block times to a chosen TZ for side-by-side comparison
- Block table UI with ▲▼ reorder, inline editor (zone/start/end/days), delete, conflict markers (⚠/✓)
- `get_minutes_until_next_switch()` rewritten — scans forward minute-by-minute for multi-block awareness
- Tray icon: green = any work block active, blue = personal zone, unchanged countdown/badge logic
- Auto-migration: on first load, existing `work_zone`/`work_start`/`work_end` settings become first block
- `check_and_switch_timezone()` simplified — uses `find_active_tz_block()` directly
- `quick_toggle_tz()` — toggles between current block zone and personal zone
- Cross-midnight blocks supported (e.g., 22:00-06:00)
- `baseline_display_zone` column added to settings table
- Old `work_zone`/`work_start_h`/`work_end_h` columns preserved for backward compatibility

### v9.9.3
- **Timezone Expansion — Named TZ Registry**
- `TZ_REGISTRY` dict with 7 timezones: ET, CT, MT, PT, PHT, JST, GMT — each with Windows ID, base offset, DST flag, and DST offset
- Generic `get_offset_at(tz_label, utc_time)` replaces `get_et_offset_at()` + `get_pht_offset()` — all US zones share DST date logic with zone-specific offsets
- `convert_utc_to_zone()` / `convert_zone_to_utc()` now fully generic (work with any registry key)
- TZ Switcher configurable: `work_zone` / `personal_zone` columns in settings DB, dropdown selectors in UI
- `should_be_in_et()` → `should_be_in_work_zone()` — uses configured work zone instead of hardcoded ET
- Tray icon: green = work zone (any), blue = personal zone (any) — color represents mode, not specific TZ
- All TZ dropdowns (reminder, pattern, one-time task) expanded from 2 options to 7
- One-Time Task: radio buttons replaced with Combobox for 7-zone support
- `_tz_label_from_windows_id()` reverse lookup for display logic
- Header shows dynamic zone label (e.g., "CT (Work Mode)" instead of hardcoded "ET (Work Mode)")
- Old `EASTERN_TZ_ID` / `PHT_TZ_ID` constants removed — all lookups go through `TZ_REGISTRY`

### v9.9.2
- **Interval Presets + One-Time Task Rename**
- Interval input replaced with `ttk.Combobox` dropdown: 15m, 30m, 1h, 2h, 4h, 8h, 12h, Daily, Weekly, Monthly — users can also type custom values
- `_format_interval()` / `_parse_interval()` helpers convert between int minutes and display strings
- Card list shows human-readable intervals (e.g., "Daily" instead of "1440m", "1h" instead of "60m")
- "Target Task" renamed to "One-Time Task" across all UI: checkbox label, interval label, card type badge

### v9.9.1
- **Bug Squash + Hardening**
- P1: PID lock checks process name (`pythonw.exe`/`python.exe`/`gawi.exe`) via `psapi.GetModuleBaseNameW` — no more false locks from recycled PIDs (e.g., Signal.exe reusing a PID)
- P1: `refresh_list()` and `update_list_status()` "Next:" display uses current system TZ (`cached_tz`) consistently
- P2: Popup height auto-fits content (removed forced 300px minimum that caused oversized popups)
- P2: Reload centers on primary monitor (`restart_app()` clears `window_x`/`window_y` to NULL)
- P2: Multi-monitor position validation uses virtual screen bounds (`GetSystemMetrics(76-79)`)
- Hardening: `datetime.now()` → `datetime.now(timezone.utc)` for Target Task year default
- Hardening: `.strip()` on work hours parsing — prevents silent save failure on whitespace
- Hardening: `reset_stale_reminders()` logs errors instead of swallowing silently
- Hardening: `get_next_valid_time()` returns safe fallback with log when 7-day search fails
- Hardening: Day number validation clamped to 0-6 on load
- Hardening: CANCEL button properly initialized (pack then pack_forget)

### v9.9
- **Habit accountability + UX fixes**
- Fix 0 (P2 regression): Sound variety restored — `winsound.Beep()` with `MessageBeep()` fallback; reverts v9.8.1 where all sounds were identical
- Fix 1: `reset_stale_reminders()` sets stale recurring reminders to `now_utc` — overdue habits fire immediately on launch (like Target Tasks already did)
- Fix 2: "Now" button in Start Pattern no longer auto-enables `use_start_pattern` — pre-fills anchor time only; permanent grid requires explicit checkbox
- Fix 3: New non-pattern habits start immediately on first save (`first_trig = now_utc`)
- Fix 4: "Next: …" display uses current system TZ (`ET`/`PHT` via `cached_tz`) with label — e.g., "Next: 03-01 14:30 ET"
- Fix 5 (P1): Battery icon weekend bug — new `get_minutes_until_next_switch()` helper is day-of-week aware; old code showed "0" countdown on Sunday at work-start time
- Fix 6: Configurable work days — `should_be_in_et()` and `get_minutes_until_next_switch()` now use `work_days` setting instead of hard-coded Mon-Fri; day checkboxes added to Timezone Switcher UI; `work_days` column added to `settings` table

### v9.8.1
- **Exe Distribution Fixes** — 10 issues reported from friend's Windows 11 testing
- P1: `restart_app()` now detects exe mode via `getattr(sys, 'frozen', False)` and re-launches `sys.executable` directly
- P1: Startup checkbox uses `shell:Startup` shortcut (.lnk) in exe mode instead of registry
- P1: `start_tray()` wrapped in try/except for silent crash detection; added `pystray._win32` to hidden imports
- P2: All sounds switched from `winsound.Beep()` (PC speaker) to `winsound.MessageBeep()` (system audio) for universal hardware compatibility
- P2: Window height now dynamic: `min(1020, screenheight - 100)` adapts to smaller screens
- P2: Target Task date/time entries now have `insertbackground=self.colors["FG"]` for visible cursor in dark mode
- P3: Dark title bar via `DwmSetWindowAttribute(DWMWA_USE_IMMERSIVE_DARK_MODE)` — applied on startup and theme toggle
- P3: Day checkboxes (M T W T F S S) now highlight blue on hover (`activebackground=ACCENT`)
- P3: Anchor "Now" button no longer adds +1 minute — sets exact current time

### v9.8
- Bug Squash Sprint: all 5 known bugs fixed
- P1: `get_next_valid_time` loop now iterates correctly through candidate minutes
- P1: `reset_stale_reminders` preserves start pattern anchor on hibernate/resume
- P2: `cached_tz` eliminates PowerShell subprocess from main thread; header updates instantly
- P2: Save feedback dot (orange unsaved / green saved) + immediate TZ switch on save
- P3: Toggle bounce eliminated via `pack_propagate(False)` height clamping
- Window position memory: first launch centers on primary monitor, subsequent launches restore last position
- **Perf**: `create_dynamic_icon()` uses `cached_tz` instead of PowerShell subprocess
- **Perf**: New `update_list_status()` for lightweight label-only refresh (no widget rebuild)
- **Perf**: `check_loop` batches stale-item updates into single `UPDATE_STATUS` post (was N×`REFRESH_LIST`)
- **Perf**: `refresh_list()` reuse path updates colors + title text, skipping full widget creation
- **Perf**: Lazy-loaded editor — 68 widgets deferred to first Add/Edit click (startup: 90→22 widgets)
- **UI**: Light mode palette shifted from blinding white to soft grey tones

### v9.7 (Previous)
- UI alignment polish: Title box, `row2_container`, `constraints_section`, Color+Sound merge
- Target Task auto-reactivation on future-date save
- PyInstaller `.exe` with bundled tray icon
- Dual-mode data path (AppData for exe, script dir for .pyw)

### v9.6
- Integrated Timezone Switcher (auto ET↔PHT based on work hours)
- Target Task persistence + segmented date entry
- Discord-style tray badge, dynamic battery icon
- Tray double-click restore

### v9.5
- Full UTC migration; LOCAL deprecated
- DST-aware ET offset computation

### v9.4
- Editor reordered: Action Zone (top) + Constraints Zone (bottom)
- Tooltips for Snooze Behavior and Start Pattern
- Start Pattern grid logic rebuilt (24h skip fix)

### v9.3
- Zombie Prevention: expired Target Tasks force EDIT instead of ON toggle
- Compact header

### v9.2
- One-Time Reminders (now Target Tasks)
- Smart segmented date UI

---

## Contact

**Francis** — Productivity-focused power user
**Location:** Philippines
**Primary TZ:** PHT (UTC+8) — personal/home
**Work TZ:** ET (UTC-4/UTC-5 DST) — professional hours
**Context:** Timezone Switcher automatically flips Windows system clock between PHT and ET based on configured work hours schedule.