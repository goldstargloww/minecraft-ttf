import io
import requests
import os
import json
import zipfile
import pygame
import PIL.Image
import fontTools.fontBuilder
import fontTools.pens.ttGlyphPen
import fontTools.ttLib.tables._g_l_y_f


def main():
    latest = get_latest()
    name = latest['id']
    meta_url = latest['url']
    cached_path = f'out/minecraft-{name}.jar'
    if not os.path.exists(cached_path):
        print('Downloading minecraft jar...')
        response = requests.get(meta_url)
        data = response.json()
        client_jar = data['downloads']['client']['url']
        response = requests.get(client_jar)
        os.makedirs('out', exist_ok=True)
        with open(cached_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=16 * 1024):
                f.write(chunk)
    aglfn = get_aglfn()
    with zipfile.ZipFile(cached_path, 'r') as jar:
        prefix = 'assets/minecraft/font/'
        for entry in jar.namelist():
            if entry.startswith(prefix) and not entry.startswith(f'{prefix}include/'):
                name = entry.removeprefix(prefix).removesuffix('.json')
                text = jar.read(entry)
                data = json.loads(text)
                convert_font(name, data, jar, aglfn)

def get_latest() -> dict:
    cached_path = 'out/manifest.json'
    try:
        with open(cached_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print('Downloading version manifest...')
        manifest_url = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'
        response = requests.get(manifest_url)
        data = response.json()
        os.makedirs('out', exist_ok=True)
        with open(cached_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    snapshot_id = data['latest']['snapshot']
    for version in data['versions']:
        if version['id'] == snapshot_id:
            return version
    raise ValueError(snapshot_id)

def get_aglfn() -> dict[str, str]:
    cached_path = 'out/aglfn.txt'
    if not os.path.exists(cached_path):
        print('Downloading Adobe AGLFN...')
        response = requests.get('https://raw.githubusercontent.com/adobe-type-tools/agl-aglfn/refs/heads/master/aglfn.txt')
        with open(cached_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=16 * 1024):
                f.write(chunk)
    aglfn_map = {}
    with open(cached_path, 'r', encoding='utf-8') as aglfn:
        for line in aglfn.readlines():
            if line.startswith('#') or line.isspace() or len(line) == 0:
                continue
            unihex, name, _uniname = line.split(';')
            uninum = int(unihex, 16)
            codepoint = chr(uninum)
            aglfn_map[codepoint] = name
    return aglfn_map

    

def read_json(jar: zipfile.ZipFile, resource: str, kind: str) -> dict:
    namespace, rest = resource.split(':')
    path = f'assets/{namespace}/{kind}/{rest}.json'
    text = jar.read(path)
    data = json.loads(text)
    return data

def read_image(jar: zipfile.ZipFile, resource: str):
    namespace, rest = resource.split(':')
    path = f'assets/{namespace}/textures/{rest}'
    data = jar.read(path)
    img = PIL.Image.open(io.BytesIO(data))
    return img

def convert_font(name: str, data: dict, jar: zipfile.ZipFile, aglfn: dict[str, str]):
    providers: list[dict] = []
    providers.extend(data['providers'])
    index = 0
    while index < len(providers):
        if providers[index]['type'] == 'reference':
            reference = read_json(jar, providers[index]['id'], 'font')
            del providers[index]
            providers[index:index] = reference['providers']
        index += 1
    print(name)
    scale = 2
    path = fontTools.pens.ttGlyphPen.TTGlyphPen(None)
    path.moveTo((0, 0))
    path.closePath()
    empty_path = path.glyph()
    seen_chars = set()
    fonts = {'regular': {}, 'bold': {}}
    def add_bitmap_glyph(char: str, glyph: PIL.Image.Image):
        seen_chars.add(char)
        bold_glyph = PIL.Image.new('RGBA', (glyph.width + 1, glyph.height + 1))
        bold_glyph.paste(glyph, (0, 0), glyph)
        bold_glyph.paste(glyph, (1, 0), glyph)
        (path, width) = vectorize(glyph, scale, (0, 1))
        (bold_path, bold_width) = vectorize(bold_glyph, scale, (0, 1))
        fonts['regular'][char] = {'width': (width + 1) * scale, 'path': path}
        fonts['bold'][char] = {'width': (bold_width + 1) * scale, 'path': bold_path}
    missing = PIL.Image.new('RGBA', (5, 8))
    missing_px = missing.load()
    for y in range(missing.height):
        for x in range(missing.width):
            if x == 0 or y == 0 or x == missing.width - 1 or y == missing.height - 1:
                missing_px[x, y] = (255, 255, 255, 255)
    add_bitmap_glyph('.notdef', missing)
    for provider in providers:
        print('\t' + str(provider))
        if provider['type'] == 'space':
            for char,width in provider['advances'].items():
                if char in seen_chars:
                    continue
                seen_chars.add(char)
                fonts['regular'][char] = {'width': width * scale, 'path': empty_path}
                fonts['bold'][char] = {'width': (width + 1) * scale, 'path': empty_path}
        elif provider['type'] == 'bitmap':
            img = read_image(jar, provider['file'])
            glyph_width = img.width // len(provider['chars'][0])
            glyph_height = img.height // len(provider['chars'])
            for y,row in enumerate(provider['chars']):
                for x,char in enumerate(row):
                    if char == '\u0000':
                        continue
                    if char in seen_chars:
                        continue
                    glyph = img.crop((x * glyph_width, y * glyph_height, (x + 1) * glyph_width, (y + 1) * glyph_height)).convert('RGBA')
                    add_bitmap_glyph(char, glyph)
    for style, data in fonts.items():
        font = make_font(name, style, empty_path, data, aglfn)
        font.save(f'out/{name}-{style}.ttf')

def make_font(name: str, style: str, empty_path: fontTools.ttLib.tables._g_l_y_f.Glyph, char_data: dict, aglfn: dict[str, str]) -> fontTools.fontBuilder.FontBuilder:
    version = '0.1'
    nameStrings = dict(
        familyName = dict(en = name),
        styleName = dict(en = style),
        uniqueFontIdentifier = name + '.' + style,
        fullName = name + '-' + style,
        psName = name + '-' + style,
        version = 'Version ' + version,
    )
    defined_glyphs = ['.notdef', '.null']
    codepoints = {}
    char_widths = {'.notdef': 0, '.null': 0}
    char_paths = {'.notdef': empty_path, '.null': empty_path}
    for char, data in char_data.items():
        if char not in ('.notdef', '.null'):
            char_name = aglfn.get(char, 'uni' + format(ord(char), '04x'))
            defined_glyphs.append(char_name)
            codepoints[ord(char)] = char_name
        else:
            char_name = char
        char_widths[char_name] = data['width']
        char_paths[char_name] = data['path']
    font = fontTools.fontBuilder.FontBuilder(24, isTTF=True)
    font.setupGlyphOrder(defined_glyphs)
    font.setupCharacterMap(codepoints)
    font.setupGlyf(char_paths)
    metrics = {}
    glyphTable = font.font["glyf"]
    for gn, advanceWidth in char_widths.items():
        metrics[gn] = (advanceWidth, glyphTable[gn].xMin)
    font.setupHorizontalMetrics(metrics)
    font.setupHorizontalHeader(ascent=14, descent=2)
    font.setupNameTable(nameStrings)
    font.setupOS2(sTypoAscender=14, usWinAscent=14, sTypoDescender=2, usWinDescent=2, sCapHeight=14, sxHeight=10, yStrikeoutPosition=6, yStrikeoutSize=2)
    font.setupPost(underlinePosition=2, underlineThickness=2)
    return font

def start_point(mask: pygame.mask.Mask) -> tuple[int, int]:
    w, h = mask.get_size()
    for y in range(h):
        for x in range(w):
            if mask.get_at((x, y)) == 1:
                return (x, y)
    raise ValueError(mask)

def is_set(mask: pygame.mask.Mask, point: tuple[int, int]) -> bool:
    x, y = point
    if x < 0 or y < 0:
        return False
    w, h = mask.get_size()
    if x >= w or y >= h:
        return False
    return mask.get_at(point) == 1

def outline(mask: pygame.mask.Mask) -> list[tuple[int, int]]:
    start = start_point(mask)
    facing = 'up'
    pos = start
    result = []
    while True:
        x, y = pos
        top_left = is_set(mask, (x - 1, y - 1))
        top_right = is_set(mask, (x, y - 1))
        bottom_left = is_set(mask, (x - 1, y))
        bottom_right = is_set(mask, (x, y))
        if top_left and bottom_right and not top_right and not bottom_left:
            if facing == 'up':
                facing = 'left'
                pos = (x - 1, y)
            else:
                facing = 'right'
                pos = (x + 1, y)
        elif top_right and bottom_left and not top_left and not bottom_right:
            if facing == 'right':
                facing = 'up'
                pos = (x, y - 1)
            else:
                facing = 'down'
                pos = (x, y + 1)
        elif top_left and not bottom_left:
            facing = 'left'
            pos = (x - 1, y)
        elif top_right and not top_left:
            facing = 'up'
            pos = (x, y - 1)
        elif bottom_right and not top_right:
            facing = 'right'
            pos = (x + 1, y)
        elif bottom_left and not bottom_right:
            facing = 'down'
            pos = (x, y + 1)
        result.append(pos)
        if pos == start:
            break
    return result

def neighbor_connected(mask: pygame.mask.Mask) -> list[pygame.mask.Mask]:
    w, h = mask.get_size()
    pixels_checked = set()
    result = []
    for y in range(h):
        for x in range(w):
            pos = (x, y)
            if pos not in pixels_checked:
                if mask.get_at(pos) == 1:
                    region = pygame.mask.Mask((w, h))
                    pixel_queue = [pos]
                    while len(pixel_queue) > 0:
                        pixel = pixel_queue.pop()
                        px, py = pixel
                        if px < 0 or px >= w or py < 0 or py >= h or pixel in pixels_checked or mask.get_at(pixel) != 1:
                            pixels_checked.add(pixel)
                            continue
                        pixels_checked.add(pixel)
                        region.set_at(pixel, 1)
                        pixel_queue.append((px - 1, py))
                        pixel_queue.append((px + 1, py))
                        pixel_queue.append((px, py - 1))
                        pixel_queue.append((px, py + 1))
                    result.append(region)
                pixels_checked.add(pos)
    return result 

def separate_regions(mask: pygame.mask.Mask) -> tuple[list[pygame.mask.Mask], list[pygame.mask.Mask]]:
    filled = mask.connected_components()
    w, h = mask.get_size()
    inverted = pygame.mask.Mask((w + 2, h + 2))
    inverted.draw(mask, (1, 1))
    inverted.invert()
    big_unfilled = neighbor_connected(inverted)
    unfilled = []
    for big in big_unfilled[1:]:
        fixed = pygame.mask.Mask((w, h))
        fixed.draw(big, (-1, -1))
        unfilled.append(fixed)
    return (filled, unfilled)

def vectorize(glyph: PIL.Image.Image, scale: int, offset: tuple[int, int]) -> tuple[fontTools.ttLib.tables._g_l_y_f.Glyph, int]:
    ox, oy = offset
    pen = fontTools.pens.ttGlyphPen.TTGlyphPen(None)
    def move_pen(point: tuple[int, int]):
        x, y = point
        x += ox
        y += oy
        pen.moveTo((x * scale, (glyph.height - y) * scale))
    def line_pen(point: tuple[int, int]):
        x, y = point
        x += ox
        y += oy
        pen.lineTo((x * scale, (glyph.height - y) * scale))
    glyph = glyph.convert('RGBA')
    surface = pygame.image.fromstring(glyph.tobytes(), glyph.size, 'RGBA')
    mask = pygame.mask.from_surface(surface)
    filled, empty = separate_regions(mask)
    if len(filled) == 0:
        move_pen((0, 0))
        pen.closePath()
        width = 0
    else:
        width = max(map(lambda x: x.right, mask.get_bounding_rects()))
        for region in filled:
            outline_points = outline(region)
            move_pen(outline_points[0])
            for point in outline_points[1:]:
                line_pen(point)
            pen.closePath()
        for region in empty:
            outline_points = list(reversed(outline(region)))
            move_pen(outline_points[0])
            for point in outline_points[1:]:
                line_pen(point)
            pen.closePath()
    return (pen.glyph(), width)

if __name__ == '__main__':
    main()
