# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Lite0812 / Yuris_YDG_Tool contributors
# SPDX-FileCopyrightText: msg-tool contributors
"""Bounded YU-RIS YDG QOI/WebP tiles with template-preserving image writes.

Format research: Yuris_YDG_Tool YDG_Tool.py and msg-tool yuris/img/ydg.rs.
See provenance/yuris-ydg.json. Pillow provides codecs; no GUI or DLL loading.
"""
from dataclasses import dataclass
import io
import struct

MAGIC = b"YDG\0YU-RIS\0\0"
MAX_BYTES = 128 << 20
MAX_PIXELS = 16 << 20
QOI_END = b"\0\0\0\0\0\0\0\1"


def imaging():
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("YDG conversion requires Pillow for WebP/PNG operations") from exc
    return Image


def _dimensions(width, height):
    if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > MAX_PIXELS:
        raise ValueError("YDG dimensions exceed budget")


def _qoi_structure(data):
    if len(data) < 22 or data[-8:] != QOI_END:
        raise ValueError("invalid QOI terminator")
    width, height, channels, colorspace = struct.unpack_from(">IIBB", data, 4)
    _dimensions(width, height)
    if channels not in (3, 4) or colorspace not in (0, 1):
        raise ValueError("invalid QOI channels/colorspace")
    # Validate exact opcode consumption before asking the image library to decode.
    position, pixels, end = 14, 0, len(data) - 8
    while pixels < width * height:
        if position >= end:
            raise ValueError("truncated QOI pixels")
        code = data[position]
        position += 1
        extra = 3 if code == 254 else 4 if code == 255 else 1 if code & 192 == 128 else 0
        run = (code & 63) + 1 if 192 <= code < 254 else 1
        position += extra
        pixels += run
        if position > end or pixels > width * height:
            raise ValueError("truncated QOI opcode or oversized run")
    if position != end:
        raise ValueError("unconsumed QOI payload")
    return width, height, channels, colorspace


def _qoi_hash(pixel):
    r, g, b, a = pixel
    return (r * 3 + g * 5 + b * 7 + a * 11) & 63


def _qoi_decode(data):
    """Decode a bounded QOI tile without relying on Pillow's optional plugin."""
    width, height, channels, colorspace = _qoi_structure(data)
    end = len(data) - 8
    position = 14
    previous = (0, 0, 0, 255)
    index = [(0, 0, 0, 0)] * 64
    pixels = bytearray()
    total = width * height
    while len(pixels) // 4 < total:
        if position >= end:
            raise ValueError("truncated QOI pixels")
        code = data[position]
        position += 1
        if code == 0xFE:
            if position + 3 > end:
                raise ValueError("truncated QOI RGB opcode")
            previous = (data[position], data[position + 1], data[position + 2], previous[3])
            position += 3
            run = 1
        elif code == 0xFF:
            if position + 4 > end:
                raise ValueError("truncated QOI RGBA opcode")
            previous = tuple(data[position:position + 4])
            position += 4
            run = 1
        elif code & 0xC0 == 0x00:
            previous = index[code & 63]
            run = 1
        elif code & 0xC0 == 0x40:
            previous = tuple((value + delta) & 255 for value, delta in zip(
                previous, (((code >> 4) & 3) - 2, ((code >> 2) & 3) - 2,
                           (code & 3) - 2, 0)))
            run = 1
        elif code & 0xC0 == 0x80:
            if position >= end:
                raise ValueError("truncated QOI luma opcode")
            second = data[position]
            position += 1
            dg = (code & 63) - 32
            dr = ((second >> 4) & 15) - 8 + dg
            db = (second & 15) - 8 + dg
            previous = tuple((value + delta) & 255 for value, delta in zip(
                previous, (dr, dg, db, 0)))
            run = 1
        elif code & 0xC0 == 0xC0:
            run = (code & 63) + 1
        else:  # pragma: no cover - all byte values are covered above
            raise ValueError("unknown QOI opcode")
        if len(pixels) // 4 + run > total:
            raise ValueError("oversized QOI run")
        for _ in range(run):
            pixels.extend(previous)
            index[_qoi_hash(previous)] = previous
    if position != end:
        raise ValueError("unconsumed QOI payload")
    return "qoi", width, height, channels, colorspace, bytes(pixels)


def _qoi_encode(width, height, pixels, channels=4, colorspace=0):
    """Encode RGBA pixels using the deterministic QOI reference operations."""
    if channels not in (3, 4) or colorspace not in (0, 1):
        raise ValueError("invalid QOI channels/colorspace")
    if len(pixels) != width * height * 4:
        raise ValueError("RGBA payload size mismatch")
    output = bytearray(b"qoif")
    output.extend(struct.pack(">IIBB", width, height, channels, colorspace))
    index = [None] * 64
    previous = (0, 0, 0, 255)
    run = 0
    total = width * height
    for number in range(total):
        offset = number * 4
        current = tuple(pixels[offset:offset + 4])
        if channels == 3 and current[3] != 255:
            raise ValueError("RGB QOI tile cannot retain translated alpha")
        if current == previous:
            run += 1
            if run == 62 or number == total - 1:
                output.append(0xC0 | (run - 1))
                run = 0
            continue
        if run:
            output.append(0xC0 | (run - 1))
            run = 0
        slot = _qoi_hash(current)
        if index[slot] == current:
            output.append(slot)
        else:
            index[slot] = current
            dr = current[0] - previous[0]
            dg = current[1] - previous[1]
            db = current[2] - previous[2]
            da = current[3] - previous[3]
            if da == 0 and -2 <= dr <= 1 and -2 <= dg <= 1 and -2 <= db <= 1:
                output.append(0x40 | ((dr + 2) << 4) | ((dg + 2) << 2) | (db + 2))
            elif da == 0 and -32 <= dg <= 31 and -8 <= dr - dg <= 7 and -8 <= db - dg <= 7:
                output.append(0x80 | (dg + 32))
                output.append(((dr - dg + 8) << 4) | (db - dg + 8))
            elif channels == 3:
                output.append(0xFE)
                output.extend(current[:3])
            else:
                output.append(0xFF)
                output.extend(current)
        previous = current
    output.extend(QOI_END)
    return bytes(output)


def _decode(data):
    if data.startswith(b"qoif"):
        return _qoi_decode(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if len(data) < 20 or struct.unpack_from("<I", data, 4)[0] + 8 != len(data):
            raise ValueError("invalid WebP RIFF length")
        codec, colorspace = "webp", 0
        Image = imaging()
        with Image.open(io.BytesIO(data), formats=["WEBP"]) as image:
            width, height = image.size
            _dimensions(width, height)
            channels = 4 if "A" in image.getbands() else 3
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("animated WebP is not a YDG tile")
    else:
        raise ValueError("unsupported YDG tile codec")
    with Image.open(io.BytesIO(data), formats=[codec.upper()]) as image:
        if image.size != (width, height):
            raise ValueError("tile dimensions changed during decode")
        pixels = image.convert("RGBA").tobytes()
    return codec, width, height, channels, colorspace, pixels


def _encode(codec, width, height, pixels, channels=4, colorspace=0):
    _dimensions(width, height)
    if len(pixels) != width * height * 4:
        raise ValueError("RGBA payload size mismatch")
    if codec == "qoi":
        data = _qoi_encode(width, height, pixels, channels, colorspace)
    elif codec == "webp":
        Image = imaging()
        image = Image.frombytes("RGBA", (width, height), pixels)
        output = io.BytesIO()
        image.save(output, format="WEBP", lossless=True, exact=True, method=6)
        data = output.getvalue()
    else:
        raise ValueError("unsupported YDG tile codec")
    if _decode(data)[-1] != pixels:
        raise ValueError("image codec did not retain exact RGBA pixels")
    return data


@dataclass(frozen=True)
class Tile:
    offset: int
    size: int
    x: int
    y: int
    width: int
    height: int
    reserved: int
    codec: str
    channels: int
    colorspace: int
    pixels: bytes


@dataclass(frozen=True)
class Resource:
    width: int
    height: int
    table_offset: int
    tiles: tuple[Tile, ...]
    pixels: bytes


def read_ydg(data: bytes) -> Resource:
    if not isinstance(data, bytes) or not 40 <= len(data) <= MAX_BYTES or data[:12] != MAGIC:
        raise ValueError("expected bounded YDG resource")
    version, header_size, file_size = struct.unpack_from("<III", data, 12)
    if version != 100 or not 36 <= header_size <= 4096 or header_size + 4 > len(data):
        raise ValueError("unsupported YDG version/header layout")
    if file_size != len(data):
        raise ValueError("YDG file size mismatch")
    width, height = struct.unpack_from("<HH", data, 32)
    _dimensions(width, height)
    count, = struct.unpack_from("<I", data, header_size)
    table_offset, table_end = header_size + 4, header_size + 4 + count * 16
    if not 0 < count <= height or table_end > len(data):
        raise ValueError("invalid YDG tile table")
    descriptors = [struct.unpack_from("<IIHHI", data, table_offset + i * 16) for i in range(count)]
    previous = table_end
    for offset, size, x, tile_height, reserved in sorted(descriptors):
        if not size or offset < previous or offset + size > len(data):
            raise ValueError("overlapping or out-of-range YDG tiles")
        previous = offset + size
    canvas = imaging().new("RGBA", (width, height), (0, 0, 0, 0))
    tiles, y = [], 0
    for offset, size, x, tile_height, reserved in descriptors:
        codec, tw, th, channels, colorspace, pixels = _decode(data[offset:offset + size])
        if th != tile_height or y + th > height or x + tw > width:
            raise ValueError("YDG tile geometry mismatch")
        canvas.paste(imaging().frombytes("RGBA", (tw, th), pixels), (x, y))
        tiles.append(Tile(offset, size, x, y, tw, th, reserved, codec, channels, colorspace, pixels))
        y += th
    if y != height:
        raise ValueError("YDG tile heights do not cover canvas")
    return Resource(width, height, table_offset, tuple(tiles), canvas.tobytes())


def rebuild_ydg(original: bytes, pixels: bytes) -> bytes:
    resource = read_ydg(original)
    if not isinstance(pixels, bytes) or len(pixels) != resource.width * resource.height * 4:
        raise ValueError("replacement must retain YDG canvas dimensions")
    Image = imaging()
    canvas = Image.frombytes("RGBA", (resource.width, resource.height), pixels)
    chunks = {}
    for tile in resource.tiles:
        value = canvas.crop((tile.x, tile.y, tile.x + tile.width, tile.y + tile.height)).tobytes()
        chunks[tile.offset] = (original[tile.offset:tile.offset + tile.size] if value == tile.pixels
                              else _encode(tile.codec, tile.width, tile.height, value,
                                           tile.channels, tile.colorspace))
    table_end = resource.table_offset + len(resource.tiles) * 16
    out, cursor, offsets = bytearray(original[:table_end]), table_end, {}
    for tile in sorted(resource.tiles, key=lambda item: item.offset):
        out.extend(original[cursor:tile.offset])
        offsets[tile.offset] = len(out)
        out.extend(chunks[tile.offset])
        cursor = tile.offset + tile.size
    out.extend(original[cursor:])
    if len(out) > MAX_BYTES:
        raise ValueError("rebuilt YDG exceeds budget")
    for index, tile in enumerate(resource.tiles):
        struct.pack_into("<II", out, resource.table_offset + index * 16,
                         offsets[tile.offset], len(chunks[tile.offset]))
    struct.pack_into("<I", out, 20, len(out))
    result = bytes(out)
    check = read_ydg(result)
    if check.pixels != pixels:
        raise ValueError("replacement changes pixels outside original tile rectangles")
    return result


def create_ydg(width, height, pixels, *, codec="qoi", section_height=160):
    """Explicit new format-100 resource; template rebuild is preferred for games."""
    _dimensions(width, height)
    if type(section_height) is not int or section_height <= 0:
        raise ValueError("invalid section height")
    if len(pixels) != width * height * 4:
        raise ValueError("RGBA payload size mismatch")
    heights = [min(section_height, height - y) for y in range(0, height, section_height)]
    out = bytearray(52 + len(heights) * 16)
    out[:12] = MAGIC
    struct.pack_into("<II", out, 12, 100, 48)
    struct.pack_into("<HH", out, 32, width, height)
    struct.pack_into("<I", out, 48, len(heights))
    y = 0
    for index, th in enumerate(heights):
        data = _encode(codec, width, th, pixels[y * width * 4:(y + th) * width * 4])
        struct.pack_into("<IIHHI", out, 52 + index * 16, len(out), len(data), 0, th, 0)
        out.extend(data)
        y += th
    struct.pack_into("<I", out, 20, len(out))
    result = bytes(out)
    if read_ydg(result).pixels != pixels:
        raise ValueError("new YDG verification failed")
    return result


def png_bytes(resource):
    image = imaging().frombytes("RGBA", (resource.width, resource.height), resource.pixels)
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=4)
    return stream.getvalue()


def read_png(data, width, height):
    if len(data) > MAX_BYTES:
        raise ValueError("PNG exceeds budget")
    with imaging().open(io.BytesIO(data), formats=["PNG"]) as image:
        if image.size != (width, height) or getattr(image, "n_frames", 1) != 1:
            raise ValueError("PNG must retain original dimensions and a single frame")
        return image.convert("RGBA").tobytes()
