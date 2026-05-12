from __future__ import annotations

import ctypes
import struct
import sys
from pathlib import Path


RT_ICON = 3
RT_GROUP_ICON = 14
LOAD_LIBRARY_AS_DATAFILE = 0x00000002


def enum_resource_names(module_handle: int, resource_type: int) -> list[int]:
    names: list[int] = []
    kernel32 = ctypes.windll.kernel32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)

    def callback(_hmodule: int, _lptype: int, lpname: int, _lparam: int) -> int:
        value = ctypes.cast(lpname, ctypes.c_void_p).value
        if value is not None:
            names.append(int(value))
        return 1

    callback_fn = callback_type(callback)
    kernel32.EnumResourceNamesW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, callback_type, ctypes.c_long]
    kernel32.EnumResourceNamesW.restype = ctypes.c_int
    kernel32.EnumResourceNamesW(module_handle, ctypes.c_void_p(resource_type), callback_fn, 0)
    return names


def enum_group_icon_entries(exe_path: Path, group_id: int = 1) -> list[tuple[int, int, int, int]]:
    kernel32 = ctypes.windll.kernel32
    kernel32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    kernel32.LoadLibraryExW.restype = ctypes.c_void_p
    kernel32.FindResourceW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    kernel32.FindResourceW.restype = ctypes.c_void_p
    kernel32.SizeofResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.SizeofResource.restype = ctypes.c_uint32
    kernel32.LoadResource.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.LoadResource.restype = ctypes.c_void_p
    kernel32.LockResource.argtypes = [ctypes.c_void_p]
    kernel32.LockResource.restype = ctypes.c_void_p
    kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
    kernel32.FreeLibrary.restype = ctypes.c_int

    handle = kernel32.LoadLibraryExW(str(exe_path), None, LOAD_LIBRARY_AS_DATAFILE)
    if not handle:
        raise ctypes.WinError()
    try:
        hrsrc = kernel32.FindResourceW(handle, ctypes.c_void_p(group_id), ctypes.c_void_p(RT_GROUP_ICON))
        if not hrsrc:
            return []
        size = kernel32.SizeofResource(handle, hrsrc)
        hglob = kernel32.LoadResource(handle, hrsrc)
        ptr = kernel32.LockResource(hglob)
        data = ctypes.string_at(ptr, size)
        _reserved, _icon_type, count = struct.unpack_from("<HHH", data, 0)
        offset = 6
        entries: list[tuple[int, int, int, int]] = []
        for _ in range(count):
            width, height, _color_count, _reserved_byte, _planes, bit_count, bytes_in_res, _res_id = struct.unpack_from("<BBBBHHIH", data, offset)
            entries.append((256 if width == 0 else width, 256 if height == 0 else height, bit_count, bytes_in_res))
            offset += 14
        return entries
    finally:
        kernel32.FreeLibrary(handle)


def parse_ico_entries(ico_path: Path) -> list[tuple[int, int, int, int]]:
    data = ico_path.read_bytes()
    _reserved, _icon_type, count = struct.unpack_from("<HHH", data, 0)
    offset = 6
    entries: list[tuple[int, int, int, int]] = []
    for _ in range(count):
        width, height, _color_count, _reserved_byte, _planes, bit_count, bytes_in_res, _image_offset = struct.unpack_from("<BBBBHHII", data, offset)
        entries.append((256 if width == 0 else width, 256 if height == 0 else height, bit_count, bytes_in_res))
        offset += 16
    return entries


def verify_icon(exe_path: Path) -> tuple[list[int], list[int]]:
    kernel32 = ctypes.windll.kernel32
    kernel32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    kernel32.LoadLibraryExW.restype = ctypes.c_void_p
    kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
    kernel32.FreeLibrary.restype = ctypes.c_int
    handle = kernel32.LoadLibraryExW(str(exe_path), None, LOAD_LIBRARY_AS_DATAFILE)
    if not handle:
        raise ctypes.WinError()
    try:
        group_icons = enum_resource_names(handle, RT_GROUP_ICON)
        icons = enum_resource_names(handle, RT_ICON)
        return group_icons, icons
    finally:
        kernel32.FreeLibrary(handle)


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("Usage: python verify_exe_icon.py <exe_path> [ico_path]")
        return 2

    exe_path = Path(sys.argv[1]).resolve()
    group_icons, icons = verify_icon(exe_path)
    print(f"GROUP_ICON={group_icons}")
    print(f"ICON={icons}")
    if len(sys.argv) == 3:
        ico_path = Path(sys.argv[2]).resolve()
        exe_entries = enum_group_icon_entries(exe_path)
        ico_entries = parse_ico_entries(ico_path)
        print(f"EXE_GROUP_ENTRIES={exe_entries}")
        print(f"ICO_ENTRIES={ico_entries}")
        return 0 if group_icons and icons and exe_entries == ico_entries else 1
    return 0 if group_icons and icons else 1


if __name__ == "__main__":
    raise SystemExit(main())
