"""Shared native map display / coordinate picker. No filenames reach this module.

Only visible tiles are requested, after the persistent online-map opt-in. Qt's
HTTP disk cache honours server expiry / validators; no prefetch or geocoding.
Software QPainter rendering needs neither OpenGL nor QtWebEngine.
"""
from collections import OrderedDict
import math
import json
import os
from pathlib import Path
import sys
import time
import weakref
from PySide6 import __version__ as PYSIDE_VERSION

from PySide6.QtCore import (QObject, QPointF, QRectF, QStandardPaths, Qt, QTimer,
                            QUrl, Signal, QLockFile, QLibraryInfo, qVersion, QBuffer, QByteArray, QIODevice)
from PySide6.QtGui import QFontDatabase, QIcon, QImageReader, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QToolButton, QVBoxLayout, QWidget, QSizePolicy)
from kim_location import coordinate
from kim_location_ui import distance, position_text
from kim_settings_dialog import config_path, load_settings, save_settings

try:
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkRequest, QNetworkReply, QSslSocket
    NETWORK_IMPORT_ERROR = ''
except (ImportError, OSError, RuntimeError) as exc:
    NETWORK_IMPORT_ERROR = f'{type(exc).__name__}: {exc}'

TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
USER_AGENT = b'KIM6-LocationTools/1.0 (+https://github.com/codesterribly/kim6)'
MAX_LATITUDE = 85.05112878
DEBUG_MAP = os.environ.get('KIM_LOCATION_DEBUG') == '1'
MAP_FAILURE_TEXT = "Map imagery couldn't be loaded."


def debug_map(event, **data):
    if DEBUG_MAP:
        print('KIM6_MAP ' + json.dumps(dict(event=event, **data), ensure_ascii=False, default=str), file=sys.stderr, flush=True)


class TileResponseError(ValueError):
    """An expected response/network failure, distinct from a processing defect."""



def capability_problems():
    problems = []
    if NETWORK_IMPORT_ERROR:
        problems.append('QtNetwork is unavailable: ' + NETWORK_IMPORT_ERROR + '\n'
            'Kubuntu/Debian system Python: sudo apt install python3-pyside6.qtnetwork\n'
            'Pip-managed Python: use that interpreter with -m pip install --force-reinstall '
            f'PySide6-Essentials=={PYSIDE_VERSION} (matching the installed bindings).')
    elif not QSslSocket.supportsSsl():
        problems.append('QtNetwork has no working TLS backend. Repair the matching Qt Network / TLS runtime '
                        '(Kubuntu/Debian: sudo apt install --reinstall libqt6network6 ca-certificates; '
                        'pip-managed Python: reinstall matching PySide6-Essentials). Never disable certificate verification.')
    if not NETWORK_IMPORT_ERROR:
        for cls, member in ((QNetworkRequest, 'setTransferTimeout'), (QNetworkRequest, 'SameOriginRedirectPolicy'),
                            (QNetworkDiskCache, 'metaData'), (QNetworkReply, 'sslErrors')):
            if not hasattr(cls, member):
                problems.append(f'The installed QtNetwork API lacks {cls.__name__}.{member}. Repair matching PySide6 components.')
    if b'png' not in QImageReader.supportedImageFormats():
        problems.append('The Qt PNG image decoder is unavailable. Repair Qt Gui '
                        '(Kubuntu/Debian: sudo apt install --reinstall python3-pyside6.qtgui; '
                        'pip-managed Python: reinstall matching PySide6-Essentials).')
    platforms = [p.split(':')[0] for p in os.environ.get('QT_QPA_PLATFORM', '').split(';') if p]
    if not platforms: platforms = ['wayland', 'xcb'] if os.environ.get('WAYLAND_DISPLAY') else ['xcb']
    roots = [Path(QLibraryInfo.path(QLibraryInfo.PluginsPath)) / 'platforms']
    roots += [Path(p) for p in os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH', '').split(os.pathsep) if p]
    if not any(list(root.glob('libq' + platform + '*.so*')) for root in roots for platform in platforms):
        problems.append(f'Qt platform plugin files for {platforms!r} are missing. Repair the matching Qt Gui installation '
                        '(Kubuntu/Debian: sudo apt install --reinstall libqt6gui6; pip-managed Python: reinstall PySide6-Essentials). '
                        'Check QT_QPA_PLATFORM_PLUGIN_PATH for a stale override.')
    return problems


def check_graphical_session():
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY') or os.environ.get('QT_QPA_PLATFORM')):
        raise RuntimeError('No graphical display is configured. Launch from KDE, or establish SSH X11 forwarding '
                           'and a working DISPLAY / X authorization. Local module checks cannot validate a remote display.')


def world_point(position, zoom):
    lat, lon = position
    lat = max(-MAX_LATITUDE, min(MAX_LATITUDE, lat))
    scale = 256 * 2 ** zoom
    return QPointF((lon + 180) / 360 * scale,
                   (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * scale)


def geographic_point(point, zoom):
    scale = 256 * 2 ** zoom
    lon = (point.x() / scale * 360 + 180) % 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * max(0, min(scale, point.y())) / scale))))
    return [lat, lon]


class TileStore(QObject):
    """One network manager/cache per process, shared by display and picker."""
    changed = Signal()
    preference_changed = Signal(bool)

    def __init__(self, parent):
        super().__init__(parent)
        self.enabled = load_settings(config_path())['KIM_LOCATION_ONLINE_MAPS'] == 'yes'
        self.stored_enabled = self.enabled
        self.tiles = OrderedDict(); self.active = {}; self.failed = {}; self.diagnostics = OrderedDict(); self.painted = set()
        self.views = weakref.WeakKeyDictionary()
        self.network = None; self.lock = None; self.problem = ''; self.initialization_problem = ''
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(180)
        self.timer.timeout.connect(self.request_visible)
        self.preference_timer = QTimer(self); self.preference_timer.setInterval(2000)
        self.preference_timer.timeout.connect(self.reload_preference); self.preference_timer.start()

    def initialize(self):
        if self.network or self.initialization_problem: return
        problems = capability_problems()
        if problems:
            self.initialization_problem = '\n'.join(problems)
            debug_map('unavailable', problems=problems); return
        try:
            root = Path(QStandardPaths.writableLocation(QStandardPaths.CacheLocation)) / 'location-tiles'
            root.mkdir(parents=True, exist_ok=True)
            self.lock = QLockFile(str(root / 'cache.lock'))
            if not self.lock.tryLock(0):
                raise OSError('Another KIM6 window owns the tile cache. Close it and choose Retry.')
            # Verify actual access, rather than relying on os.access().
            from tempfile import TemporaryFile
            with TemporaryFile(dir=root): pass
            self.network = QNetworkAccessManager(self)
            cache = QNetworkDiskCache(self.network)
            cache.setCacheDirectory(str(root)); cache.setMaximumCacheSize(128 * 1024 * 1024)
            self.network.setCache(cache)
            debug_map('initialized', cache=str(root), qt=qVersion(), pyside=PYSIDE_VERSION, tls_backend=QSslSocket.activeBackend())
        except Exception as exc:
            self.initialization_problem = 'Map cache / network initialization failed: ' + str(exc)
            debug_map('initialization-error', exception=repr(exc))
            if self.network: self.network.deleteLater()
            self.network = None
            if self.lock: self.lock.unlock(); self.lock = None

    def set_enabled(self, enabled):
        try:
            settings = load_settings(config_path()); settings['KIM_LOCATION_ONLINE_MAPS'] = 'yes' if enabled else 'no'
            save_settings(config_path(), settings)
            self.stored_enabled = enabled
        except (OSError, ValueError) as exc:
            QMessageBox.warning(None, 'Online map preference was not saved', str(exc) + '\nThe choice applies to this session.')
        self.apply_enabled(enabled)

    def reload_preference(self):
        try: enabled = load_settings(config_path())['KIM_LOCATION_ONLINE_MAPS'] == 'yes'
        except (OSError, ValueError) as exc:
            debug_map('settings-read-error', exception=repr(exc)); return
        if enabled != self.stored_enabled:
            self.stored_enabled = enabled; self.apply_enabled(enabled)

    def apply_enabled(self, enabled):
        self.enabled = enabled
        if not enabled:
            self.timer.stop()
            for reply, _ in list(self.active.values()): reply.abort()
        debug_map('online-preference', enabled=enabled)
        self.preference_changed.emit(enabled); self.changed.emit(); self.timer.start()

    def visible_keys(self):
        return set().union(*self.views.values()) if self.views else set()

    def update_view(self, view, keys):
        if self.views.get(view) != keys: debug_map('visible-tiles', tiles=sorted(keys), width=view.width(), height=view.height())
        self.views[view] = keys
        self.timer.start()

    def release(self, view):
        self.views.pop(view, None)
        # Stop requests for a hidden/closed map immediately.
        visible = self.visible_keys()
        for key, (reply, _) in list(self.active.items()):
            if key not in visible: reply.abort()

    def image(self, key):
        cached = self.tiles.get(key)
        if cached:
            self.tiles.move_to_end(key); return cached[0]
        return None

    def fresh(self, key):
        cached = self.tiles.get(key)
        return bool(cached and cached[1] > time.time())

    def request_visible(self):
        visible = self.visible_keys() if self.enabled else set()
        for key, (reply, _) in list(self.active.items()):
            if key not in visible: reply.abort()
        if not visible: return
        self.initialize()
        if not self.network or self.problem:
            self.changed.emit(); return
        needed = [key for key in sorted(visible) if not self.fresh(key) and key not in self.active and key not in self.failed]
        for key in needed[:max(0, 4 - len(self.active))]:
            try: self.start_request(key)
            except Exception as exc:
                self.problem = MAP_FAILURE_TEXT
                self.diagnostics[key] = dict(stage='request-initialization', failure_kind='application', exception=repr(exc))
                self.failed[key] = self.diagnostics[key]
                active = self.active.pop(key, None)
                if active:
                    active[0].abort(); active[0].deleteLater()
                debug_map('request-exception', tile=key, exception=repr(exc))
                break
        self.changed.emit()

    def start_request(self, key):
        z, x, y = key
        request = QNetworkRequest(QUrl(TILE_URL.format(z=z, x=x, y=y)))
        request.setRawHeader(b'User-Agent', USER_AGENT)
        request.setAttribute(QNetworkRequest.CacheLoadControlAttribute, QNetworkRequest.PreferCache)
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.SameOriginRedirectPolicy)
        request.setTransferTimeout(15000)
        debug_map('request', tile=key, url=request.url().toString(), user_agent=USER_AGENT.decode(), cache='PreferCache')
        reply = self.network.get(request)
        self.active[key] = (reply, bytearray())
        reply.setReadBufferSize(512 * 1024)
        reply.readyRead.connect(lambda k=key: self.collect(k))
        reply.sslErrors.connect(lambda errors, k=key: self.ssl_errors(k, errors))
        reply.finished.connect(lambda k=key: self.finished(k))

    def ssl_errors(self, key, errors):
        if key in self.active:
            self.active[key][0].setProperty('kim_tls_error', '; '.join(error.errorString() for error in errors))

    def collect(self, key):
        if key not in self.active: return
        reply, data = self.active[key]; data.extend(bytes(reply.readAll()))
        if len(data) > 1024 * 1024 and not reply.property('kim_abort_reason'):
            reply.setProperty('kim_abort_reason', 'Tile response exceeded the 1 MiB safety limit.')
            if not reply.isFinished(): reply.abort()

    def finished(self, key):
        if key not in self.active: return
        reply = self.active[key][0]
        record = dict(tile=key, url=reply.url().toString(), stage='response')
        try:
            self.collect(key)
            reply, data = self.active.pop(key)
            status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            record.update(http=status, qt_error=str(reply.error()), error_string=reply.errorString(),
                          network_error=reply.error() != QNetworkReply.NoError,
                          tls=reply.property('kim_tls_error') or '', bytes=len(data),
                          from_cache=reply.attribute(QNetworkRequest.SourceIsFromCacheAttribute), signature=bytes(data[:16]).hex(),
                          redirect=reply.attribute(QNetworkRequest.RedirectionTargetAttribute),
                          abort_reason=reply.property('kim_abort_reason') or '')
            if reply.error() == QNetworkReply.OperationCanceledError and not record['abort_reason']:
                record['stage'] = 'canceled'; return
            if not self.enabled or key not in self.visible_keys():
                record['stage'] = 'no-longer-visible'; return
            if record['abort_reason']: raise TileResponseError(record['abort_reason'])
            if reply.error() != QNetworkReply.NoError: raise TileResponseError(reply.errorString())
            record['stage'] = 'response-headers'
            record.update(content_type=bytes(reply.rawHeader('Content-Type')).decode('latin-1'),
                          cache_control=bytes(reply.rawHeader('Cache-Control')).decode('latin-1'),
                          expires_header=bytes(reply.rawHeader('Expires')).decode('latin-1'),
                          etag=bytes(reply.rawHeader('ETag')).decode('latin-1'))
            if status not in (200, 304): raise TileResponseError('Unexpected HTTP response: ' + str(status))
            record['stage'] = 'png-validation'
            if not (len(data) >= 24 and data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR' and
                    int.from_bytes(data[16:20], 'big') == 256 and int.from_bytes(data[20:24], 'big') == 256):
                raise TileResponseError('Expected a 256 × 256 PNG tile; received a different response.')
            record['stage'] = 'decode'
            buffer = QBuffer(); buffer.setData(QByteArray(bytes(data))); buffer.open(QIODevice.ReadOnly)
            reader = QImageReader(buffer, b'PNG'); image = reader.read()
            if image.isNull(): raise TileResponseError('PNG decoding failed: ' + reader.errorString())
            metadata = self.network.cache().metaData(reply.url()); expires = metadata.expirationDate().toSecsSinceEpoch()
            record.update(stage='decoded', width=image.width(), height=image.height(), expires=expires)
            self.tiles[key] = (QPixmap.fromImage(image), expires if expires > time.time() else time.time() + 30)
            while len(self.tiles) > 96:
                evicted, _ = self.tiles.popitem(last=False); self.painted.discard(evicted)
            self.failed.pop(key, None)
        except Exception as exc:
            record['exception'] = f'{type(exc).__name__}: {exc}'
            record['failure_kind'] = ('http' if record.get('http') not in (None, 200, 304) else
                                      'network' if record.get('network_error') and not record.get('abort_reason') else
                                      'response') if isinstance(exc, TileResponseError) else 'application'
            if isinstance(exc, TileResponseError) and record['stage'] in ('png-validation', 'decode'):
                try:
                    cache = self.network.cache() if self.network else None
                    if cache: record['invalid_cached_response_removed'] = cache.remove(reply.url())
                except Exception as cache_exc: record['cache_error'] = repr(cache_exc)
            self.failed[key] = record
            if len(self.failed) > 128: self.failed.pop(next(iter(self.failed)))
            if record['failure_kind'] == 'application' or record.get('http') in (403, 429) or record.get('http') is None:
                self.problem = MAP_FAILURE_TEXT
        finally:
            self.active.pop(key, None)
            self.diagnostics[key] = record
            while len(self.diagnostics) > 32: self.diagnostics.popitem(last=False)
            debug_map('reply', **record)
            reply.deleteLater(); self.changed.emit(); self.timer.start()

    def retry(self):
        self.failed.clear(); self.problem = ''; self.painted.clear()
        if not self.network: self.initialization_problem = ''
        self.timer.start(); self.changed.emit()


_store = None


def tile_store():
    global _store
    if _store is None: _store = TileStore(QApplication.instance())
    return _store


class TileMap(QWidget):
    position_changed = Signal(object)

    def __init__(self, parent=None, interactive=False, units='metric'):
        super().__init__(parent)
        self.interactive = interactive; self.units = units; self.zoom = 13
        self.selected = None; self.centre = world_point([0, 0], self.zoom)
        self.empty_text = 'No camera coordinates recorded'; self.drag_origin = None; self.dragged = False
        self.store = tile_store(); self.store.changed.connect(self.map_changed)
        self.setMinimumSize(0, 110); self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setFocusPolicy(Qt.StrongFocus); self.setCursor(Qt.OpenHandCursor)
        self.setAccessibleName('Location map. Arrow keys pan; plus and minus zoom.' + (' Space selects the center.' if interactive else ''))
        self.fetch_timer = QTimer(self); self.fetch_timer.setSingleShot(True); self.fetch_timer.setInterval(180)
        self.fetch_timer.timeout.connect(self.publish_view)
        if interactive: self.zoom = 2; self.centre = world_point([0, 0], self.zoom)

    def set_position(self, position, empty_text='No camera coordinates recorded'):
        value = None if position is None else [coordinate(position[0], None, True), coordinate(position[1], None, False)]
        if value != self.selected:
            self.store.release(self)
            self.selected = value
            if value is not None: self.centre = world_point(value, self.zoom)
            debug_map('position', coordinates=value, zoom=self.zoom, projected_center=[self.centre.x(), self.centre.y()])
        self.empty_text = empty_text; self.update(); self.fetch_timer.start()
        if value is None and not self.interactive: self.store.release(self)

    def tile_rectangles(self):
        origin = self.centre - QPointF(self.width() / 2, self.height() / 2)
        n = 2 ** self.zoom
        for x in range(math.floor(origin.x() / 256), math.floor((origin.x() + self.width()) / 256) + 1):
            for y in range(max(0, math.floor(origin.y() / 256)), min(n - 1, math.floor((origin.y() + self.height()) / 256)) + 1):
                yield (self.zoom, x % n, y), QRectF(x * 256 - origin.x(), y * 256 - origin.y(), 256, 256)

    def covered(self):
        return self.selected is None or abs(self.selected[0]) <= MAX_LATITUDE

    def publish_view(self):
        active = self.isVisible() and self.covered() and (self.interactive or self.selected is not None)
        self.store.update_view(self, {key for key, _ in self.tile_rectangles()} if active else set())

    def map_changed(self):
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self); palette = self.palette()
        painter.fillRect(self.rect(), palette.brush(QPalette.Base))
        if self.selected is None and not self.interactive:
            painter.setPen(palette.color(QPalette.Text)); painter.drawText(self.rect().adjusted(16, 16, -16, -16), Qt.AlignCenter | Qt.TextWordWrap, self.empty_text); return
        if not self.covered():
            painter.setPen(palette.color(QPalette.Text)); painter.drawText(self.rect().adjusted(16, 16, -16, -16), Qt.AlignCenter | Qt.TextWordWrap,
                'This latitude is outside the map’s coverage (±85.0511°).\nThe camera coordinates remain valid; use the coordinate readout.'); return
        for key, rect in self.tile_rectangles():
            image = self.store.image(key) if self.store.enabled else None
            if image is not None:
                painter.drawPixmap(rect, image, QRectF(0, 0, 256, 256))
                if key not in self.store.painted:
                    self.store.painted.add(key); debug_map('painted', tile=key, width=self.width(), height=self.height(), dpr=self.devicePixelRatioF())
            else:
                painter.setPen(palette.color(QPalette.Midlight)); painter.drawRect(rect)
        if self.selected is not None:
            point = world_point(self.selected, self.zoom); scale = 256 * 2 ** self.zoom
            dx = (point.x() - self.centre.x() + scale / 2) % scale - scale / 2
            point = QPointF(self.width() / 2 + dx, self.height() / 2 + point.y() - self.centre.y())
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(palette.color(QPalette.Text), 4)); painter.setBrush(palette.brush(QPalette.Base)); painter.drawEllipse(point, 10, 10)
            painter.setPen(QPen(palette.color(QPalette.Highlight), 3)); painter.drawEllipse(point, 7, 7)
            painter.drawLine(point + QPointF(-16, 0), point + QPointF(16, 0)); painter.drawLine(point + QPointF(0, -16), point + QPointF(0, 16))
        lat = geographic_point(self.centre, self.zoom)[0]
        metres = 90 * math.cos(math.radians(lat)) * 2 * math.pi * 6378137 / (256 * 2 ** self.zoom)
        box = QRectF(6, self.height() - 36, min(self.width() - 12, 180), 30)
        painter.fillRect(box, palette.brush(QPalette.Base)); painter.setPen(palette.color(QPalette.Text))
        painter.drawText(box.adjusted(8, 0, -4, -7), Qt.AlignLeft | Qt.AlignVCenter, distance(metres, self.units))
        painter.drawLine(QPointF(14, self.height() - 12), QPointF(104, self.height() - 12))

    def resizeEvent(self, event):
        if hasattr(self, 'fetch_timer'): self.fetch_timer.start()
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event); self.fetch_timer.start()

    def hideEvent(self, event):
        self.fetch_timer.stop(); self.store.release(self); super().hideEvent(event)

    def zoom_by(self, delta, anchor=None):
        zoom = max(1, min(19, self.zoom + delta))
        if zoom == self.zoom: return
        offset = (anchor if anchor is not None else QPointF(self.width()/2, self.height()/2)) - QPointF(self.width()/2, self.height()/2)
        self.centre = (self.centre + offset) * 2 ** (zoom - self.zoom) - offset
        self.zoom = zoom; self.reposition()

    def reposition(self):
        scale = 256 * 2 ** self.zoom
        self.centre.setX(self.centre.x() % scale); self.centre.setY(max(0, min(scale, self.centre.y())))
        self.update(); self.fetch_timer.start()

    def wheelEvent(self, event):
        if event.angleDelta().y(): self.zoom_by(1 if event.angleDelta().y() > 0 else -1, event.position())
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus(); self.drag_origin = event.position(); self.last_drag = event.position(); self.dragged = False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self.drag_origin is not None:
            if (event.position() - self.drag_origin).manhattanLength() > QApplication.startDragDistance(): self.dragged = True
            if self.dragged: self.centre -= event.position() - self.last_drag; self.reposition()
            self.last_drag = event.position()

    def select_at(self, point):
        if not self.interactive: return
        self.selected = geographic_point(self.centre + point - QPointF(self.width()/2, self.height()/2), self.zoom)
        self.position_changed.emit(list(self.selected)); self.update(); self.fetch_timer.start()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drag_origin is not None:
            if not self.dragged: self.select_at(event.position())
            self.drag_origin = None; self.setCursor(Qt.OpenHandCursor); self.update()

    def keyPressEvent(self, event):
        directions = {Qt.Key_Left: (-80, 0), Qt.Key_Right: (80, 0), Qt.Key_Up: (0, -80), Qt.Key_Down: (0, 80)}
        if event.key() in directions:
            x, y = directions[event.key()]; self.centre += QPointF(x, y); self.reposition()
        elif event.key() in (Qt.Key_Plus, Qt.Key_Equal): self.zoom_by(1)
        elif event.key() == Qt.Key_Minus: self.zoom_by(-1)
        elif event.key() == Qt.Key_Space and self.interactive: self.select_at(QPointF(self.width()/2, self.height()/2))
        else: super().keyPressEvent(event)

    def stop_requests(self):
        self.fetch_timer.stop(); self.store.release(self)


class LocationMap(QWidget):
    position_changed = Signal(object)

    def __init__(self, parent=None, interactive=False, units='metric'):
        super().__init__(parent)
        outer_layout = QVBoxLayout(self); outer_layout.setContentsMargins(0, 0, 0, 0)
        self.online = QPushButton('Enable Maps')
        self.online.setCheckable(False); self.online.setAutoDefault(False)
        self.online.setToolTip('Enable online maps and save this preference in KIM6 Settings. Visible map areas are requested from OpenStreetMap; image names stay local.')
        outer_layout.addWidget(self.online)
        map_area = QWidget(); layout = QVBoxLayout(map_area); layout.setContentsMargins(0, 0, 0, 0)
        self.canvas = TileMap(self, interactive, units)
        self.canvas_minimum = self.canvas.minimumHeight()
        self.content_splitter = QSplitter(Qt.Vertical); self.content_splitter.setChildrenCollapsible(False)
        self.content_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
        self.content_splitter.setMinimumSize(0, self.canvas_minimum)
        layout.addWidget(self.canvas, 1); self.content_splitter.addWidget(map_area)
        self.technical_panel = QWidget(); technical_layout = QVBoxLayout(self.technical_panel)
        technical_layout.setContentsMargins(0, 0, 0, 0)
        copy_row = QHBoxLayout(); copy_row.addStretch()
        self.copy_details = QPushButton('Copy Details'); self.copy_details.setAutoDefault(False)
        self.copy_details.clicked.connect(self.copy_technical_details); copy_row.addWidget(self.copy_details)
        technical_layout.addLayout(copy_row)
        self.technical_text = QPlainTextEdit(); self.technical_text.setReadOnly(True)
        self.technical_text.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.technical_text.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.technical_text.setMinimumSize(0, 0); self.technical_text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.technical_text.setAccessibleName('Map technical details')
        technical_layout.addWidget(self.technical_text, 1)
        self.content_splitter.addWidget(self.technical_panel); self.technical_panel.hide()
        outer_layout.addWidget(self.content_splitter, 1)
        self.store = self.canvas.store
        self.online.setVisible(not self.store.enabled); self.online.clicked.connect(lambda: self.store.set_enabled(True))
        self.store.preference_changed.connect(self.sync_preference); self.store.changed.connect(self.update_status)
        credit = QLabel('© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>')
        credit.setOpenExternalLinks(True); layout.addWidget(credit)
        row = QHBoxLayout()
        for label, delta, accessible in (('+', 1, 'Zoom In'), ('−', -1, 'Zoom Out')):
            button = QToolButton(); button.setText(label); button.setAccessibleName(accessible); button.setToolTip(accessible)
            button.setFocusPolicy(Qt.StrongFocus)
            button.clicked.connect(lambda checked=False, d=delta: self.canvas.zoom_by(d)); row.addWidget(button)
        centre = QPushButton(QIcon.fromTheme('mark-location'), 'Center'); centre.setAutoDefault(False)
        centre.clicked.connect(self.recenter); row.addWidget(centre)
        retry = QPushButton('Retry'); retry.setAutoDefault(False); retry.clicked.connect(self.store.retry); row.addWidget(retry)
        row.addStretch(); layout.addLayout(row)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred); layout.addWidget(self.status)
        self.technical_toggle = QToolButton(); self.technical_toggle.setText('Technical details')
        self.technical_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.technical_toggle.setCheckable(True); self.technical_toggle.setArrowType(Qt.RightArrow)
        self.technical_toggle.setAccessibleName('Expand map technical details')
        self.technical_toggle.toggled.connect(self.toggle_technical_details)
        self.technical_toggle.hide(); layout.addWidget(self.technical_toggle)
        self.canvas.position_changed.connect(self.position_changed)
        self.update_status()

    def set_position(self, position, empty_text='No camera coordinates recorded'):
        self.canvas.set_position(position, empty_text); self.update_status()

    def set_units(self, units):
        self.canvas.units = units; self.canvas.update()

    def sync_preference(self, enabled):
        self.online.setVisible(not enabled)
        self.canvas.publish_view(); self.update_status()

    def recenter(self):
        if self.canvas.selected is not None:
            self.canvas.centre = world_point(self.canvas.selected, self.canvas.zoom); self.canvas.reposition()

    def update_status(self):
        visible = {key for key, _ in self.canvas.tile_rectangles()}
        failures = [record for key, record in self.store.failed.items() if key in visible]
        if self.store.problem and not failures and self.store.failed:
            failures = [next(reversed(self.store.failed.values()))]
        has_position = self.canvas.selected is not None or self.canvas.interactive
        has_failure = bool(has_position and self.store.enabled and
                           (self.store.initialization_problem or self.store.problem or failures))
        if self.canvas.selected is None and not self.canvas.interactive: text = self.canvas.empty_text
        elif not self.store.enabled: text = 'Online maps are off in KIM6 Settings. The coordinate marker remains available.'
        elif has_failure: text = MAP_FAILURE_TEXT
        elif self.store.active: text = 'Loading geographic imagery…'
        else: text = 'Visible map areas are sent to OpenStreetMap. Drag or use arrow keys to pan.'
        self.status.setText(text); self.status.setToolTip(text)
        self.technical_toggle.setVisible(has_failure)
        if has_failure:
            detail = self.store.initialization_problem or (json.dumps(failures[-1], indent=2, ensure_ascii=False, default=str) if failures else self.store.problem)
            if self.technical_text.toPlainText() != detail: self.technical_text.setPlainText(detail)
        else:
            self.technical_toggle.setChecked(False); self.technical_text.clear()

    def toggle_technical_details(self, expanded):
        self.technical_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        # Reallocate the existing map viewport; never adjust the dialog's size.
        self.canvas.setMinimumHeight(min(self.canvas_minimum, self.fontMetrics().lineSpacing()*2) if expanded else self.canvas_minimum)
        self.technical_panel.setVisible(expanded)
        if expanded:
            height = max(1, self.content_splitter.height())
            self.content_splitter.setSizes([height*2//3, height-height*2//3])

    def copy_technical_details(self):
        QApplication.clipboard().setText(self.technical_text.toPlainText())

    def stop_requests(self): self.canvas.stop_requests()


def choose_location(parent, initial=None, units='metric'):
    """Selection changes proposed input only; publication still requires approval."""
    try:
        if initial is not None: initial = [coordinate(initial[0], None, True), coordinate(initial[1], None, False)]
        dialog = QDialog(parent); dialog.setWindowTitle('Choose an Image Location')
        available = dialog.screen().availableGeometry()
        dialog.resize(min(800, available.width()*9//10), min(680, available.height()*9//10))
        layout = QVBoxLayout(dialog)
        help_label = QLabel('Click to choose a position. Arrow keys pan; Space selects the center. Review the coordinates before using them.')
        help_label.setWordWrap(True); layout.addWidget(help_label)
        map_view = LocationMap(dialog, interactive=True, units=units); layout.addWidget(map_view, 1)
        if initial is not None: map_view.canvas.zoom = 13
        map_view.set_position(initial)
        readout = QLabel(); readout.setWordWrap(True); readout.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(readout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        use = buttons.button(QDialogButtonBox.Ok); use.setText('Use This Location'); use.setAutoDefault(False)
        buttons.button(QDialogButtonBox.Cancel).setAutoDefault(False)
        def update_selection(position):
            use.setEnabled(position is not None)
            readout.setText('Selected: ' + position_text(position) if position is not None else 'No location selected.')
        map_view.position_changed.connect(update_selection); update_selection(initial)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        try: accepted = dialog.exec() == QDialog.Accepted
        finally: map_view.stop_requests()
        selected = list(map_view.canvas.selected) if accepted and map_view.canvas.selected is not None else None
        dialog.deleteLater(); return selected
    except Exception as exc:
        debug_map('initialization-error', exception=repr(exc))
        QMessageBox.warning(parent, 'Map picker could not open',
            f'{type(exc).__name__}: {exc}\nUse a reference image or enter coordinates. '
            'For a remote session, check DISPLAY / WAYLAND_DISPLAY and Qt platform-plugin diagnostics in the launch terminal.')
        return None


if __name__ == '__main__' and sys.argv[1:] == ['--check']:
    import PySide6
    print(f'Python: {sys.executable}; PySide6: {PySide6.__version__}; Qt: {qVersion()}')
    print('Display variables: DISPLAY=' + ('set' if os.environ.get('DISPLAY') else 'unset') +
          ', WAYLAND_DISPLAY=' + ('set' if os.environ.get('WAYLAND_DISPLAY') else 'unset') +
          '; platform choice: ' + (os.environ.get('QT_QPA_PLATFORM') or 'automatic'))
    problems = capability_problems()
    if problems:
        print('\n'.join(problems), file=sys.stderr); raise SystemExit(1)
    print('Local map modules, TLS backend, PNG decoder and platform plugin files available. No plugin initialization, display or network connection tested.')
