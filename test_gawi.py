"""
Gawi Engine Tests — non-UI logic coverage.
Run: pytest test_gawi.py -v
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import sys
import os

# Prevent tkinter/pystray/winsound from loading during tests
for mod in ['tkinter', 'tkinter.ttk', 'tkinter.font', 'tkinter.messagebox',
            'tkinter.colorchooser', 'pystray', 'PIL', 'PIL.Image', 'PIL.ImageDraw',
            'PIL.ImageTk', 'PIL.ImageFont', 'winsound', 'winreg']:
    sys.modules[mod] = MagicMock()

# Patch tk module-level references before import
tk_mock = sys.modules['tkinter']
tk_mock.StringVar = MagicMock
tk_mock.IntVar = MagicMock
tk_mock.BooleanVar = MagicMock
tk_mock.Frame = MagicMock
tk_mock.Label = MagicMock
tk_mock.Tk = MagicMock
ttk_mock = sys.modules['tkinter.ttk']
ttk_mock.Combobox = MagicMock

# Now import the module-level constants
sys.path.insert(0, os.path.dirname(__file__))

# We can't import gawi.pyw directly (it has side effects + GUI),
# so we extract the pure logic into a minimal test harness.
# Instead, we replicate the TZ_REGISTRY and test the algorithms directly.

TZ_REGISTRY = {
    "ET":  {"display": "Eastern",     "windows_id": "Eastern Standard Time",  "base_offset": -5, "has_dst": True,  "dst_offset": -4},
    "CT":  {"display": "Central",     "windows_id": "Central Standard Time",  "base_offset": -6, "has_dst": True,  "dst_offset": -5},
    "MT":  {"display": "Mountain",    "windows_id": "Mountain Standard Time", "base_offset": -7, "has_dst": True,  "dst_offset": -6},
    "PT":  {"display": "Pacific",     "windows_id": "Pacific Standard Time",  "base_offset": -8, "has_dst": True,  "dst_offset": -7},
    "PHT": {"display": "Philippines", "windows_id": "Singapore Standard Time","base_offset": 8,  "has_dst": False, "dst_offset": 8},
    "JST": {"display": "Japan",       "windows_id": "Tokyo Standard Time",    "base_offset": 9,  "has_dst": False, "dst_offset": 9},
    "GMT": {"display": "GMT/UTC",     "windows_id": "GMT Standard Time",      "base_offset": 0,  "has_dst": False, "dst_offset": 0},
}


# === Replicate core engine functions for testing ===

def get_offset_at(tz_label, utc_time):
    cfg = TZ_REGISTRY.get(tz_label)
    if not cfg:
        return 0
    if not cfg["has_dst"]:
        return cfg["base_offset"]
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


def convert_utc_to_zone(utc_time, tz_label):
    offset = get_offset_at(tz_label, utc_time)
    return utc_time + timedelta(hours=offset)


def convert_zone_to_utc(zone_time, tz_label):
    offset = get_offset_at(tz_label, zone_time)
    utc_guess = zone_time - timedelta(hours=offset)
    actual_offset = get_offset_at(tz_label, utc_guess)
    return zone_time - timedelta(hours=actual_offset)


def find_active_tz_block(now_utc, tz_blocks, personal_zone="PHT"):
    for block in sorted(tz_blocks, key=lambda b: b['sort_order']):
        zone_time = convert_utc_to_zone(now_utc, block['zone'])
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
    return personal_zone


def detect_tz_blocks_conflicts(tz_blocks, ref_utc):
    conflicts = []
    blocks = sorted(tz_blocks, key=lambda b: b['sort_order'])
    ref_date = ref_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            a, b = blocks[i], blocks[j]
            a_days = (a.get('active_days') or '0,1,2,3,4').split(',')
            b_days = (b.get('active_days') or '0,1,2,3,4').split(',')
            shared_days = set(a_days) & set(b_days)
            if not shared_days:
                continue
            a_start_local = ref_date.replace(hour=a['start_h'], minute=a['start_m'])
            a_end_local = ref_date.replace(hour=a['end_h'], minute=a['end_m'])
            if a_end_local <= a_start_local:
                a_end_local += timedelta(days=1)
            b_start_local = ref_date.replace(hour=b['start_h'], minute=b['start_m'])
            b_end_local = ref_date.replace(hour=b['end_h'], minute=b['end_m'])
            if b_end_local <= b_start_local:
                b_end_local += timedelta(days=1)
            a_cross = a['end_h'] * 60 + a['end_m'] <= a['start_h'] * 60 + a['start_m']
            b_cross = b['end_h'] * 60 + b['end_m'] <= b['start_h'] * 60 + b['start_m']
            a_utc_s = convert_zone_to_utc(a_start_local, a['zone'])
            a_utc_e = convert_zone_to_utc(a_end_local, a['zone'])
            b_utc_s = convert_zone_to_utc(b_start_local, b['zone'])
            b_utc_e = convert_zone_to_utc(b_end_local, b['zone'])
            a_intervals = [(a_utc_s, a_utc_e)]
            if a_cross:
                a_intervals.append((a_utc_s - timedelta(days=1), a_utc_e - timedelta(days=1)))
            b_intervals = [(b_utc_s, b_utc_e)]
            if b_cross:
                b_intervals.append((b_utc_s - timedelta(days=1), b_utc_e - timedelta(days=1)))
            overlap_found = False
            for as_, ae_ in a_intervals:
                for bs_, be_ in b_intervals:
                    if as_ < be_ and bs_ < ae_:
                        overlap_found = True
                        break
                if overlap_found:
                    break
            if overlap_found:
                conflicts.append((a['id'], b['id']))
    return conflicts


def is_time_valid(check_time_utc, use_hours, s_h, s_m, e_h, e_m, days_str, tz_label="ET"):
    zone_time = convert_utc_to_zone(check_time_utc, tz_label)
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


# ==============================
# TESTS
# ==============================


class TestTimezoneConversion:
    """Tests for get_offset_at, convert_utc_to_zone, convert_zone_to_utc."""

    def test_pht_no_dst(self):
        utc = datetime(2026, 1, 15, 12, 0, 0)
        assert get_offset_at("PHT", utc) == 8

    def test_pht_summer_no_dst(self):
        utc = datetime(2026, 7, 15, 12, 0, 0)
        assert get_offset_at("PHT", utc) == 8

    def test_et_standard_time(self):
        utc = datetime(2026, 1, 15, 12, 0, 0)
        assert get_offset_at("ET", utc) == -5

    def test_et_daylight_time(self):
        utc = datetime(2026, 7, 15, 12, 0, 0)
        assert get_offset_at("ET", utc) == -4

    def test_pt_standard_time(self):
        utc = datetime(2026, 1, 15, 12, 0, 0)
        assert get_offset_at("PT", utc) == -8

    def test_pt_daylight_time(self):
        utc = datetime(2026, 7, 15, 12, 0, 0)
        assert get_offset_at("PT", utc) == -7

    def test_gmt_always_zero(self):
        assert get_offset_at("GMT", datetime(2026, 1, 1, 0, 0)) == 0
        assert get_offset_at("GMT", datetime(2026, 7, 1, 0, 0)) == 0

    def test_unknown_tz_returns_zero(self):
        assert get_offset_at("FAKE", datetime(2026, 1, 1)) == 0

    def test_utc_to_pht(self):
        utc = datetime(2026, 3, 7, 1, 0, 0)
        pht = convert_utc_to_zone(utc, "PHT")
        assert pht == datetime(2026, 3, 7, 9, 0, 0)

    def test_utc_to_et_standard(self):
        utc = datetime(2026, 1, 15, 14, 0, 0)
        et = convert_utc_to_zone(utc, "ET")
        assert et == datetime(2026, 1, 15, 9, 0, 0)

    def test_utc_to_et_dst(self):
        utc = datetime(2026, 7, 15, 13, 0, 0)
        et = convert_utc_to_zone(utc, "ET")
        assert et == datetime(2026, 7, 15, 9, 0, 0)

    def test_roundtrip_utc_pht_utc(self):
        utc = datetime(2026, 3, 7, 4, 30, 0)
        pht = convert_utc_to_zone(utc, "PHT")
        back = convert_zone_to_utc(pht, "PHT")
        assert back == utc

    def test_roundtrip_utc_et_utc(self):
        utc = datetime(2026, 7, 15, 14, 0, 0)
        et = convert_utc_to_zone(utc, "ET")
        back = convert_zone_to_utc(et, "ET")
        assert back == utc

    def test_roundtrip_utc_et_utc_standard(self):
        utc = datetime(2026, 1, 15, 14, 0, 0)
        et = convert_utc_to_zone(utc, "ET")
        back = convert_zone_to_utc(et, "ET")
        assert back == utc

    def test_dst_boundary_march_2026(self):
        """2026 DST starts March 8 at 2:00 UTC for US zones."""
        # Just before DST
        pre_dst = datetime(2026, 3, 8, 1, 59, 0)
        assert get_offset_at("ET", pre_dst) == -5
        # Just after DST
        post_dst = datetime(2026, 3, 8, 2, 0, 0)
        # Need to verify: 2026 March 8 is a Sunday
        assert post_dst.weekday() == 6  # Sunday
        # After 2nd Sunday March 2AM UTC → DST active
        assert get_offset_at("ET", post_dst) == -4


class TestFindActiveTzBlock:
    """Tests for find_active_tz_block — the core scheduling engine."""

    def _block(self, id, zone, start_h, start_m, end_h, end_m, days="0,1,2,3,4", sort=0):
        return {'id': id, 'zone': zone, 'start_h': start_h, 'start_m': start_m,
                'end_h': end_h, 'end_m': end_m, 'active_days': days, 'sort_order': sort}

    def test_single_block_inside(self):
        """During ET 9-17 on a weekday → returns ET."""
        # Wednesday Jan 14 2026, 14:00 UTC = 9:00 AM ET (standard time)
        now = datetime(2026, 1, 14, 14, 0, 0)
        blocks = [self._block(1, "ET", 9, 0, 17, 0)]
        assert find_active_tz_block(now, blocks) == "ET"

    def test_single_block_outside(self):
        """Outside ET 9-17 → returns personal zone."""
        # Wednesday Jan 14, 23:00 UTC = 6:00 PM ET
        now = datetime(2026, 1, 14, 23, 0, 0)
        blocks = [self._block(1, "ET", 9, 0, 17, 0)]
        assert find_active_tz_block(now, blocks) == "PHT"

    def test_empty_blocks_returns_personal(self):
        now = datetime(2026, 1, 14, 14, 0, 0)
        assert find_active_tz_block(now, []) == "PHT"

    def test_weekend_excluded(self):
        """Saturday should not match Mon-Fri block."""
        # Saturday Jan 17 2026, 14:00 UTC = 9:00 AM ET
        now = datetime(2026, 1, 17, 14, 0, 0)
        blocks = [self._block(1, "ET", 9, 0, 17, 0, days="0,1,2,3,4")]
        assert find_active_tz_block(now, blocks) == "PHT"

    def test_weekend_included(self):
        """Saturday should match if days include 5 (Sat)."""
        now = datetime(2026, 1, 17, 14, 0, 0)
        blocks = [self._block(1, "ET", 9, 0, 17, 0, days="0,1,2,3,4,5")]
        assert find_active_tz_block(now, blocks) == "ET"

    def test_cross_midnight_before_midnight(self):
        """ET 22:00-06:00 — testing at 23:00 ET should match."""
        # Wednesday Jan 14, 04:00 UTC = 23:00 ET (standard)
        now = datetime(2026, 1, 15, 4, 0, 0)
        blocks = [self._block(1, "ET", 22, 0, 6, 0)]
        assert find_active_tz_block(now, blocks) == "ET"

    def test_cross_midnight_after_midnight(self):
        """ET 22:00-06:00 — testing at 03:00 ET should match."""
        # Thursday Jan 15, 08:00 UTC = 03:00 ET (standard)
        now = datetime(2026, 1, 15, 8, 0, 0)
        blocks = [self._block(1, "ET", 22, 0, 6, 0)]
        assert find_active_tz_block(now, blocks) == "ET"

    def test_cross_midnight_outside(self):
        """ET 22:00-06:00 — testing at 12:00 ET should NOT match."""
        now = datetime(2026, 1, 15, 17, 0, 0)
        blocks = [self._block(1, "ET", 22, 0, 6, 0)]
        assert find_active_tz_block(now, blocks) == "PHT"

    def test_first_match_wins(self):
        """Two overlapping blocks — lower sort_order wins."""
        now = datetime(2026, 1, 14, 14, 0, 0)
        blocks = [
            self._block(1, "ET", 9, 0, 17, 0, sort=0),
            self._block(2, "CT", 8, 0, 18, 0, sort=1),
        ]
        assert find_active_tz_block(now, blocks) == "ET"

    def test_null_active_days_defaults(self):
        """None active_days should default to Mon-Fri."""
        now = datetime(2026, 1, 14, 14, 0, 0)  # Wednesday
        block = self._block(1, "ET", 9, 0, 17, 0)
        block['active_days'] = None
        assert find_active_tz_block(now, [block]) == "ET"

    def test_pht_block(self):
        """PHT 6:30-22:00 — test at PHT 10:00 AM."""
        # PHT 10:00 AM = UTC 02:00
        now = datetime(2026, 1, 14, 2, 0, 0)
        blocks = [self._block(1, "PHT", 6, 30, 22, 0, days="0,1,2,3,4,5,6")]
        assert find_active_tz_block(now, blocks) == "PHT"

    def test_block_end_boundary_exclusive(self):
        """At exactly end time, block should NOT match (< not <=)."""
        # ET 17:00 exactly = UTC 22:00 (standard)
        now = datetime(2026, 1, 14, 22, 0, 0)
        blocks = [self._block(1, "ET", 9, 0, 17, 0)]
        assert find_active_tz_block(now, blocks) == "PHT"

    def test_block_start_boundary_inclusive(self):
        """At exactly start time, block SHOULD match (>=)."""
        # ET 9:00 exactly = UTC 14:00 (standard)
        now = datetime(2026, 1, 14, 14, 0, 0)
        blocks = [self._block(1, "ET", 9, 0, 17, 0)]
        assert find_active_tz_block(now, blocks) == "ET"


class TestConflictDetection:
    """Tests for detect_tz_blocks_conflicts."""

    def _block(self, id, zone, start_h, start_m, end_h, end_m, days="0,1,2,3,4", sort=0):
        return {'id': id, 'zone': zone, 'start_h': start_h, 'start_m': start_m,
                'end_h': end_h, 'end_m': end_m, 'active_days': days, 'sort_order': sort}

    def test_no_overlap(self):
        """ET 9-12 and ET 13-17 — no overlap."""
        ref = datetime(2026, 1, 14, 0, 0, 0)
        blocks = [
            self._block(1, "ET", 9, 0, 12, 0),
            self._block(2, "ET", 13, 0, 17, 0),
        ]
        assert detect_tz_blocks_conflicts(blocks, ref) == []

    def test_clear_overlap_same_zone(self):
        """ET 9-14 and ET 12-17 — overlaps 12-14."""
        ref = datetime(2026, 1, 14, 0, 0, 0)
        blocks = [
            self._block(1, "ET", 9, 0, 14, 0),
            self._block(2, "ET", 12, 0, 17, 0),
        ]
        conflicts = detect_tz_blocks_conflicts(blocks, ref)
        assert len(conflicts) == 1
        assert conflicts[0][:2] == (1, 2)

    def test_cross_timezone_overlap(self):
        """ET 9-12 and PT 6-9 — these overlap in UTC (ET 9AM = 14:00 UTC, PT 6AM = 14:00 UTC)."""
        ref = datetime(2026, 1, 14, 0, 0, 0)
        blocks = [
            self._block(1, "ET", 9, 0, 12, 0),
            self._block(2, "PT", 6, 0, 9, 0),
        ]
        conflicts = detect_tz_blocks_conflicts(blocks, ref)
        assert len(conflicts) == 1

    def test_no_shared_days(self):
        """Same time range but different days — no conflict."""
        ref = datetime(2026, 1, 14, 0, 0, 0)
        blocks = [
            self._block(1, "ET", 9, 0, 17, 0, days="0,1,2,3,4"),
            self._block(2, "ET", 9, 0, 17, 0, days="5,6"),
        ]
        assert detect_tz_blocks_conflicts(blocks, ref) == []

    def test_cross_midnight_conflict(self):
        """ET 22-06 and ET 0-08 — overlaps 0-06 in ET."""
        ref = datetime(2026, 1, 14, 0, 0, 0)
        blocks = [
            self._block(1, "ET", 22, 0, 6, 0),
            self._block(2, "ET", 0, 0, 8, 0),
        ]
        conflicts = detect_tz_blocks_conflicts(blocks, ref)
        assert len(conflicts) == 1

    def test_adjacent_no_conflict(self):
        """ET 9-12 and ET 12-17 — adjacent but not overlapping."""
        ref = datetime(2026, 1, 14, 0, 0, 0)
        blocks = [
            self._block(1, "ET", 9, 0, 12, 0),
            self._block(2, "ET", 12, 0, 17, 0),
        ]
        assert detect_tz_blocks_conflicts(blocks, ref) == []

    def test_null_active_days_defaults(self):
        """None active_days should still work in conflict detection."""
        ref = datetime(2026, 1, 14, 0, 0, 0)
        b1 = self._block(1, "ET", 9, 0, 14, 0)
        b2 = self._block(2, "ET", 12, 0, 17, 0)
        b1['active_days'] = None
        b2['active_days'] = None
        conflicts = detect_tz_blocks_conflicts([b1, b2], ref)
        assert len(conflicts) == 1

    def test_three_blocks_pairwise(self):
        """Three overlapping blocks — should detect all pairs."""
        ref = datetime(2026, 1, 14, 0, 0, 0)
        blocks = [
            self._block(1, "ET", 9, 0, 15, 0),
            self._block(2, "ET", 12, 0, 18, 0),
            self._block(3, "ET", 14, 0, 20, 0),
        ]
        conflicts = detect_tz_blocks_conflicts(blocks, ref)
        ids = [(c[0], c[1]) for c in conflicts]
        assert (1, 2) in ids
        assert (1, 3) in ids
        assert (2, 3) in ids


class TestIsTimeValid:
    """Tests for is_time_valid — active hours/days filtering."""

    def test_valid_weekday_no_hours(self):
        """Wednesday, no hour restriction → valid."""
        utc = datetime(2026, 1, 14, 14, 0, 0)
        assert is_time_valid(utc, False, 0, 0, 0, 0, "0,1,2,3,4", "ET") is True

    def test_invalid_weekend(self):
        """Saturday, Mon-Fri only → invalid."""
        utc = datetime(2026, 1, 17, 14, 0, 0)
        assert is_time_valid(utc, False, 0, 0, 0, 0, "0,1,2,3,4", "ET") is False

    def test_valid_within_hours(self):
        """Wednesday 10:00 ET, hours 9-17 → valid."""
        utc = datetime(2026, 1, 14, 15, 0, 0)  # 10:00 ET
        assert is_time_valid(utc, True, 9, 0, 17, 0, "0,1,2,3,4", "ET") is True

    def test_invalid_outside_hours(self):
        """Wednesday 20:00 ET, hours 9-17 → invalid."""
        utc = datetime(2026, 1, 15, 1, 0, 0)  # 20:00 ET
        assert is_time_valid(utc, True, 9, 0, 17, 0, "0,1,2,3,4", "ET") is False

    def test_boundary_start_inclusive(self):
        """Exactly at start hour → valid."""
        utc = datetime(2026, 1, 14, 14, 0, 0)  # 9:00 ET
        assert is_time_valid(utc, True, 9, 0, 17, 0, "0,1,2,3,4", "ET") is True

    def test_boundary_end_exclusive(self):
        """Exactly at end hour → invalid."""
        utc = datetime(2026, 1, 14, 22, 0, 0)  # 17:00 ET
        assert is_time_valid(utc, True, 9, 0, 17, 0, "0,1,2,3,4", "ET") is False

    def test_pht_timezone(self):
        """Check active hours work with PHT timezone."""
        utc = datetime(2026, 1, 14, 2, 0, 0)  # 10:00 PHT
        assert is_time_valid(utc, True, 8, 0, 22, 0, "0,1,2,3,4", "PHT") is True


class TestDSTBoundary:
    """Edge cases around DST transitions."""

    def test_et_offset_just_before_spring_forward(self):
        """March 8 2026 1:59 UTC — still standard time."""
        utc = datetime(2026, 3, 8, 1, 59, 0)
        assert get_offset_at("ET", utc) == -5

    def test_et_offset_at_spring_forward(self):
        """March 8 2026 2:00 UTC — DST kicks in."""
        utc = datetime(2026, 3, 8, 2, 0, 0)
        assert get_offset_at("ET", utc) == -4

    def test_all_us_zones_shift_together(self):
        """All US zones should transition at the same UTC moment."""
        pre = datetime(2026, 3, 8, 1, 59, 0)
        post = datetime(2026, 3, 8, 2, 0, 0)
        for tz in ["ET", "CT", "MT", "PT"]:
            cfg = TZ_REGISTRY[tz]
            assert get_offset_at(tz, pre) == cfg["base_offset"]
            assert get_offset_at(tz, post) == cfg["dst_offset"]

    def test_non_dst_zones_unaffected(self):
        """PHT, JST, GMT should never change."""
        dates = [datetime(2026, 1, 1), datetime(2026, 6, 1), datetime(2026, 12, 1)]
        for tz in ["PHT", "JST", "GMT"]:
            cfg = TZ_REGISTRY[tz]
            for d in dates:
                assert get_offset_at(tz, d) == cfg["base_offset"]

    def test_block_active_across_dst_spring(self):
        """ET 9-17 block should work correctly on both sides of DST."""
        block = {'id': 1, 'zone': 'ET', 'start_h': 9, 'start_m': 0,
                 'end_h': 17, 'end_m': 0, 'active_days': '0,1,2,3,4,5,6', 'sort_order': 0}
        # Before DST: ET 9AM = UTC 14:00 (offset -5)
        pre = datetime(2026, 3, 7, 14, 0, 0)  # Saturday
        assert find_active_tz_block(pre, [block]) == "ET"
        # After DST: ET 9AM = UTC 13:00 (offset -4)
        post = datetime(2026, 3, 9, 13, 0, 0)  # Monday
        assert find_active_tz_block(post, [block]) == "ET"
