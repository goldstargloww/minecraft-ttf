import io
import requests
import os
import json
import zipfile
import unicodedata
import pygame
import PIL.Image
import fontTools.fontBuilder
import fontTools.pens.t2CharStringPen


def main():
    latest = get_latest()
    if latest is not None:
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
        with zipfile.ZipFile(cached_path, 'r') as jar:
            prefix = 'assets/minecraft/font/'
            for entry in jar.namelist():
                if entry.startswith(prefix) and not entry.startswith(f'{prefix}include/'):
                    name = entry.removeprefix(prefix).removesuffix('.json')
                    text = jar.read(entry)
                    data = json.loads(text)
                    convert_font(name, data, jar)

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

def convert_font(name, data: dict, jar: zipfile.ZipFile):
    providers: list[dict] = []
    providers.extend(data['providers'])
    index = 0
    while index < len(providers):
        if providers[index]['type'] == 'reference':
            reference = read_json(jar, providers[index]['id'], 'font')
            del providers[index]
            providers[index:index] = reference['providers']
        index += 1

    font = fontTools.fontBuilder.FontBuilder(1024, isTTF=False)
    familyName = f"Minecraft-{name}"
    styleName = "Normal"
    version = "0.1"
    nameStrings = dict(
        familyName=dict(en=familyName),
        styleName=dict(en=styleName),
        uniqueFontIdentifier= familyName + "." + styleName,
        fullName=familyName + "-" + styleName,
        psName=familyName + "-" + styleName,
        version="Version " + version,
    )
    pen = fontTools.pens.t2CharStringPen.T2CharStringPen(600, None)
    pen.moveTo((0, 0))
    pen.closePath()
    charString = pen.getCharString()
    defined_glyphs = ['.notdef', '.null']
    codepoints: dict[int, str] = {}
    char_widths: dict[str, int] = {'.notdef': 0, '.null': 0}
    char_strings = {'.notdef': charString, '.null': charString}
    for provider in providers:
        print(provider)
        if provider['type'] == 'space':
            for char,width in provider['advances'].items():
                char_name = unicodedata.name(char)
                defined_glyphs.append(char_name)
                codepoints[ord(char)] = char_name
                char_widths[char_name] = width
                char_strings[char_name] = charString
        elif provider['type'] == 'bitmap':
            img = read_image(jar, provider['file'])
            glyph_width = img.width // len(provider['chars'][0])
            glyph_height = img.height // len(provider['chars'])
            scale = 100
            for y,row in enumerate(provider['chars']):
                for x,char in enumerate(row):
                    if char == '\u0000':
                        continue
                    glyph = img.crop((x * glyph_width, y * glyph_width, (x + 1) * glyph_width, (y + 1) * glyph_height))
                    pen = vectorize(glyph, scale)
                    charString2 = pen.getCharString()
                    char_name = unicodedata.name(char)
                    defined_glyphs.append(char_name)
                    codepoints[ord(char)] = char_name
                    char_widths[char_name] = glyph_width * scale
                    char_strings[char_name] = charString2
    font.setupGlyphOrder(defined_glyphs)
    font.setupCharacterMap(codepoints)
    font.setupCFF(nameStrings["psName"], {"FullName": nameStrings["psName"]}, char_strings, {})
    lsb = {gn: cs.calcBounds(None)[0] for gn, cs in char_strings.items()}
    metrics = {}
    for gn, advanceWidth in char_widths.items():
        metrics[gn] = (advanceWidth, lsb[gn])
    font.setupHorizontalMetrics(metrics)
    font.setupHorizontalHeader(ascent=824, descent=200)
    font.setupNameTable(nameStrings)
    font.setupOS2(sTypoAscender=824, usWinAscent=824, usWinDescent=200)
    font.setupPost()
    font.save(f'out/{name}.otf')

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

def vectorize(glyph: PIL.Image.Image, scale: int):
    pen = fontTools.pens.t2CharStringPen.T2CharStringPen(glyph.width * scale, None)
    def move_pen(point: tuple[int, int]):
        x, y = point
        pen.moveTo((x * scale, (glyph.height - y) * scale))
    def line_pen(point: tuple[int, int]):
        x, y = point
        pen.lineTo((x * scale, (glyph.height - y) * scale))
    glyph = glyph.convert('RGBA')
    surface = pygame.image.fromstring(glyph.tobytes(), glyph.size, 'RGBA')
    mask = pygame.mask.from_surface(surface)
    regions = mask.connected_components()
    for region in regions:
        outline_points = outline(region)
        move_pen(outline_points[0])
        for point in outline_points:
            line_pen(point)
        pen.closePath()
    if len(regions) == 0:
        move_pen((0, 0))
        pen.closePath()
    return pen

def get_latest() -> dict | None:
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
    return None

if __name__ == '__main__':
    main()
