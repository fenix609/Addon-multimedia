# -*- coding: utf-8 -*-
"""
rellenar_vistas.py  -  Rellena las imágenes (icon, thumb, poster, banner, fanart) en todos los niveles
del addon multimedia, para que cualquier vista de Kodi (Póster, Banner, Fanart, Muro, Miniatura...)
tenga contenido en el menú principal, en los submenús, en las series y en las temporadas.

USO:   python rellenar_vistas.py  [carpeta_con_los_xml]  [carpeta_de_salida]
       (por defecto: la carpeta donde está el script, y se escribe en ./salida)

REGLAS (para cada <section>, <submenu>, <folder> y <tree> raíz):
  1. Se respeta SIEMPRE lo que ya hayas puesto tú.
  2. Lo que falte se hereda del nivel superior (sección -> submenú -> serie -> temporada).
  3. Dentro del mismo nivel se completan entre sí:
       thumb <- poster <- icon          (miniatura / póster / icono)
       poster <- thumb ;  icon <- thumb
       banner <- (banner heredado) <- fanart    (un banner es horizontal; el fanart es lo más parecido)
  4. Los enlaces https://imgur.com/XXXX (página web, no imagen) pasan a https://i.imgur.com/XXXX.jpg
     (los de tipo i.imgur.com ya son imágenes y no se tocan).
  5. clearlogo no se rellena (es un logo con transparencia; copiar otra imagen quedaría mal).
  6. Se corrigen los & sueltos dentro de las URL (deben ir como &amp;, si no el XML no se puede leer).
  7. También se rellenan los <group>, <channel> e <item> (episodios, vídeos, canales...) de los archivos
     que cuelgan de menú.xml. Videos.xml, Musica.xml y Fotos.xml se copian sin tocar si menú.xml no los enlaza.

Si algún nivel se queda sin imagen porque no hay NINGUNA arriba, el script lo lista al final.
Para dar una imagen por defecto a todo, rellena DEFECTO (abajo).
"""
import os
import re
import sys

KEYS = ['icon', 'thumb', 'poster', 'banner', 'fanart']

# Imagen por defecto (URL directa) para lo que no tenga nada en ningún nivel. Déjalo vacío si no quieres.
DEFECTO = {'icon': '', 'thumb': '', 'poster': '', 'banner': '', 'fanart': ''}

TAG_RE = re.compile(r'<!--.*?-->|<(/?)([A-Za-z_][\w\-]*)((?:[^>"\']|"[^"]*"|\'[^\']*\')*?)(/?)>', re.S)
ATTR_RE = re.compile(r'([\w\-:]+)\s*=\s*"([^"]*)"')
BARE_AMP = re.compile(r'&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)')
IMGUR_PAGE = re.compile(r'^https?://(?:www\.)?imgur\.com/(?:a/|gallery/)?([A-Za-z0-9]{5,8})/?$')

NODOS = ('section', 'submenu', 'folder', 'group')
HOJAS = ('item', 'channel')
RAICES_ARBOL = ('tree',)          # raíz donde sí se escriben imágenes
RAICES_SOLO_HEREDAR = ('lista', 'tdt', 'menu')
PROBLEMAS = []


def arreglar_url(v):
    m = IMGUR_PAGE.match((v or '').strip())
    return 'https://i.imgur.com/%s.jpg' % m.group(1) if m else v


def completar(propio, heredado):
    """propio / heredado: dict clave -> url ('' si falta). Devuelve el dict final."""
    p = {k: propio.get(k, '') for k in KEYS}
    h = {k: heredado.get(k, '') for k in KEYS}
    # 3) completar dentro del propio nivel (miniatura / póster / icono)
    thumb = p['thumb'] or p['poster'] or p['icon']
    poster = p['poster'] or p['thumb'] or p['icon']
    icon = p['icon'] or p['thumb'] or p['poster']
    out = {
        'thumb': thumb or h['thumb'] or h['poster'] or h['icon'],
        'poster': poster or h['poster'] or h['thumb'] or h['icon'],
        'icon': icon or h['icon'] or h['thumb'] or h['poster'],
        'fanart': p['fanart'] or h['fanart'],
    }
    out['banner'] = p['banner'] or h['banner'] or out['fanart']
    for k in KEYS:
        if not out[k]:
            out[k] = DEFECTO.get(k, '')
    return out


def poner_attrs(tag_text, valores):
    """Pone/actualiza los atributos de imagen en el texto de una etiqueta sin tocar el resto."""
    for k in KEYS:
        v = valores.get(k, '')
        if not v:
            continue
        pat = re.compile(r'(\s%s\s*=\s*")[^"]*(")' % k)
        if pat.search(tag_text):
            tag_text = pat.sub(lambda m: m.group(1) + v + m.group(2), tag_text, count=1)
        else:
            tag_text = re.sub(r'\s*(/?>)\s*$', lambda m: ' %s="%s"%s' % (k, v, m.group(1)), tag_text, count=1)
    return tag_text


def procesar(nombre, carpeta, heredado, salida, ya):
    if nombre in ya:
        return
    ruta = os.path.join(carpeta, nombre)
    if not os.path.isfile(ruta):
        print('  (aviso) no existe', nombre)
        return
    ya.add(nombre)
    texto = open(ruta, encoding='utf-8').read()

    pila = []          # arte final de cada elemento abierto (para heredar)
    pendientes = []    # (archivo, arte) que hay que procesar después
    partes = []
    pos = 0
    primera_raiz = True

    for m in TAG_RE.finditer(texto):
        partes.append(texto[pos:m.start()])
        pos = m.end()
        tag = m.group(0)
        if tag.startswith('<!--'):
            partes.append(tag)
            continue
        cierre, nom, attrs, autocierre = m.group(1), m.group(2), m.group(3), m.group(4)
        if cierre:
            if pila:
                pila.pop()
            partes.append(tag)
            continue

        padre = pila[-1] if pila else heredado
        d = dict((k, fixed) for k, v in ATTR_RE.findall(attrs) for fixed in [arreglar_url(v)])
        propio = {k: d.get(k, '') for k in KEYS}
        final = padre
        nuevo = tag

        es_raiz = (len(pila) == 0)
        escribe = False
        if nom in NODOS:
            escribe = True
        elif nom in RAICES_ARBOL and es_raiz:
            escribe = True
        elif nom in RAICES_SOLO_HEREDAR and es_raiz:
            final = completar(propio, padre)
        elif nom in HOJAS:
            escribe = True      # episodios, vídeos, canales...

        if escribe:
            final = completar(propio, padre)
            nuevo = poner_attrs(tag, final)
            if nom in NODOS or (nom in RAICES_ARBOL and es_raiz):
                faltan = [k for k in ('thumb', 'fanart', 'banner') if not final[k]]
                if faltan:
                    PROBLEMAS.append('%s > %s "%s": sin %s' % (nombre, nom, d.get('name', d.get('id', '')), ', '.join(faltan)))
        elif nuevo != tag:
            pass
        # reescribir URLs de imgur en etiquetas que no se completan (por ejemplo items con thumb de página)
        if not escribe and 'imgur.com' in tag:
            nuevo = re.sub(r'"(https?://(?:www\.)?imgur\.com/[^"]+)"',
                           lambda mm: '"%s"' % arreglar_url(mm.group(1)), tag)

        if 'file' in d and nom in NODOS:
            pendientes.append((d['file'], final))

        nuevo = BARE_AMP.sub('&amp;', nuevo)   # un & suelto en una URL rompe el XML
        partes.append(nuevo)
        if not autocierre:
            pila.append(final)

    partes.append(texto[pos:])
    os.makedirs(salida, exist_ok=True)
    with open(os.path.join(salida, nombre), 'w', encoding='utf-8', newline='') as f:
        f.write(''.join(partes))
    print('  OK', nombre)

    for arch, arte in pendientes:
        procesar(arch, carpeta, arte, salida, ya)


def main():
    carpeta = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    salida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(carpeta, 'salida')
    print('Entrada:', carpeta)
    print('Salida :', salida)
    ya = set()
    procesar('menú.xml', carpeta, {}, salida, ya)
    # El resto de XML que no cuelgan de menú.xml (Videos, Música, Fotos...) se copian tal cual.
    for n in sorted(os.listdir(carpeta)):
        if n.lower().endswith('.xml') and n not in ya:
            import shutil
            os.makedirs(salida, exist_ok=True)
            shutil.copy2(os.path.join(carpeta, n), os.path.join(salida, n))
            print('  = (copiado sin cambios)', n)
    if PROBLEMAS:
        print('\nNiveles que siguen sin alguna imagen (no hay ninguna arriba de donde heredar):')
        for p in PROBLEMAS:
            print('  -', p)


if __name__ == '__main__':
    main()
