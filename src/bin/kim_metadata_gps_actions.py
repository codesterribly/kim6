"""Field-level GPS actions. Metadata stays read-only; proposals belong to Editor."""
from dataclasses import dataclass
from pathlib import Path
import re

from PySide6.QtCore import Qt, QRect, QEvent, QPersistentModelIndex
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QLabel,
    QToolButton, QMenu, QStyledItemDelegate, QStyleOptionViewItem,
    QStyleOptionToolButton, QStyle, QToolTip, QMessageBox)

from kim_location import coordinate, summarize, coordinate_category, location_kind, proposal_problem, FORMATS
from kim_metadata_reader import MetadataEntry


def is_gps_entry(entry):
    return isinstance(entry, MetadataEntry) and bool(
        location_kind(entry_key(entry)) == 'gps' or
        re.search(r'Latitude|Longitude|Coordinates|GPSPosition|LocationShown|LocationCreated', entry.name))


def entry_key(entry):
    # Reader family 0 is EXIF/XMP; the GPS parser uses family 1. Keep storage
    # paths and document identities, dropping only ExifTool's Copy labels.
    groups = entry.groups
    group = groups[1] if len(groups) > 2 else groups[0] if groups else 'Unknown'
    if group == 'GPS' and groups[0] != 'EXIF':
        group = groups[0] + '-' + group
    context = [g for g in groups[3:] if not re.fullmatch(r'Copy\d+', g)]
    return ':'.join((group, *context, entry.name))


def _degrees(value, latitude, ref=None):
    text = str(value).strip()
    match = re.fullmatch(r'''([+-]?\d+) deg (\d+)' ([\d.]+)"\s*([NSEW])?''', text)
    if match:
        degree, minute, second, hemisphere = match.groups()
        if float(minute) >= 60 or float(second) >= 60:
            raise ValueError('Invalid coordinate')
        value = (abs(float(degree)) + float(minute) / 60 + float(second) / 3600) * (-1 if degree.startswith('-') else 1)
        ref = hemisphere or ref
    else:
        match = re.fullmatch(r'([+-]?[\d.]+)(?:,([\d.]+))?\s*([NSEW])', text)
        if match:
            degree, minute, hemisphere = match.groups()
            if minute and float(minute) >= 60:
                raise ValueError('Invalid coordinate')
            value = float(degree) + float(minute or 0) / 60
            ref = hemisphere
    ref = {'North': 'N', 'South': 'S', 'East': 'E', 'West': 'W'}.get(ref, ref)
    return coordinate(value, ref, latitude)


def _normalize(value, name=''):
    if isinstance(value, dict):
        return {key: _normalize(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item, name) for item in value]
    if name.endswith(('LatitudeRef', 'LongitudeRef')):
        return {'North': 'N', 'South': 'S', 'East': 'E', 'West': 'W'}.get(value, value)
    if name.endswith(('Latitude', 'Longitude')):
        try:
            return _degrees(value, name.endswith('Latitude'))
        except ValueError:
            pass
    return value


@dataclass(frozen=True)
class GPSField:
    path: str
    position: object
    camera: bool
    provenance: str
    reason: str = ''


def gps_field(record, entry=None):
    """Resolve only this representation, never a preferred source's coordinates."""
    if record is None:
        return None
    if entry is None:
        embedded = [item for item in record.entries if item.source == record.path
                    and coordinate_category(entry_key(item)) == 'camera'
                    and re.search(r'GPS(?:Latitude|Longitude)$', item.name)]
        if embedded:
            contexts = [gps_field(record, item) for item in embedded]
            positions = {tuple(item.position) for item in contexts if item.position is not None}
            if len(positions) == 1 and all(item.camera for item in contexts):
                return contexts[0]
            return GPSField(record.path, None, False, 'Embedded camera GPS',
                            'Embedded camera GPS is incomplete or ambiguous. Inspect its individual fields; editing is unavailable.')
        return GPSField(record.path, None, True, 'No embedded camera GPS coordinates')
    if not is_gps_entry(entry):
        return None
    cache = getattr(record, '_gps_field_actions', None)
    if cache is None:
        # One lazy index, bounded by the GPS entries, not all tag row widgets.
        sources = {}
        for item in record.entries:
            if is_gps_entry(item):
                sources.setdefault(item.source, []).append(item)
        cache = record._gps_field_actions = (sources, {}, {})
    sources, resolved, summaries = cache
    if id(entry) in resolved:
        return resolved[id(entry)]
    key = entry_key(entry)
    group = key.split(':')[0]
    category = coordinate_category(key)
    camera = entry.source == record.path and category == 'camera'
    provenance = ('Embedded image' if entry.source == record.path else 'Sidecar ' + Path(entry.source).name) + ' · ' + entry.group + ' · ' + ('derived' if group == 'Composite' else category)
    position = None
    # Composite/packed positions are display representations, not verified
    # camera records. Map their own value without making them editable.
    if entry.name == 'LocationISO6709' and isinstance(entry.value, str):
        camera = False
        match = re.fullmatch(r'([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)(?:[+-]\d+(?:\.\d+)?)?/?', entry.value.strip())
        if match:
            try:
                position = (coordinate(match[1], None, True), coordinate(match[2], None, False))
            except ValueError:
                pass
    elif entry.name in ('GPSPosition', 'GPSCoordinates', 'Coordinates', 'Position') and isinstance(entry.value, str):
        camera = False
        parts = entry.value.split(', ')
        if len(parts) != 2:
            parts = entry.value.split(',')
        if len(parts) == 2:
            try:
                position = (_degrees(parts[0], True), _degrees(parts[1], False))
            except ValueError:
                pass
    else:
        context = key.rsplit(':', 1)[0]
        cohort = [item for item in sources.get(entry.source, ()) if entry_key(item).rsplit(':', 1)[0] == context]
        # Composite is deliberately excluded by the existing GPS engine.
        summary_key = (entry.source, context)
        if summary_key not in summaries:
            raw = {}
            for index, item in enumerate(cohort):
                item_key = entry_key(item)
                if item_key in raw:
                    item_key = item_key.rsplit(':', 1)[0] + f':Copy{index}:' + item.name
                raw[item_key] = _normalize(item.value, item.name)
            # Some display records encode hemispheres in the coordinate
            # strings. Pass those explicit references to the existing parser.
            for item in cohort:
                if item.name.endswith(('Latitude', 'Longitude')):
                    hemisphere = re.search(r'([NSEW])$', str(item.value).strip())
                    if hemisphere:
                        item_key = entry_key(item)
                        ref_key = item_key + 'Ref'
                        ref = hemisphere[1]
                        if ref_key in raw and raw[ref_key] != ref:
                            raw[item_key] = 'Contradictory hemisphere references'
                        else:
                            raw.setdefault(ref_key, ref)
            summaries[summary_key] = summarize(raw)
        info = summaries[summary_key]
        candidates = info['categories'][category]['records']
        if isinstance(entry.value, (dict, list)):
            candidates = [r for r in candidates if any(key in tag for tags in r['tags'].values() for tag in tags)]
        elif re.search(r'Latitude|Longitude', entry.name):
            candidates = [r for r in candidates if any(key in tags for tags in r['tags'].values())]
        if len(candidates) == 1 and not candidates[0]['issues'] and not info['categories'][category]['issues']:
            position = candidates[0]['position']
        # A technical tag may act on its verified camera record only.
        if camera and (info['categories']['camera']['issues'] or len(candidates) != 1):
            camera = False
        if group == 'Composite' and position is None and entry.name in ('GPSLatitude', 'GPSLongitude'):
            other_name = 'GPSLongitude' if entry.name == 'GPSLatitude' else 'GPSLatitude'
            other = [item for item in cohort if item.name == other_name]
            if len(other) == 1:
                try:
                    lat, lon = (entry, other[0]) if entry.name == 'GPSLatitude' else (other[0], entry)
                    position = (_degrees(lat.value, True), _degrees(lon.value, False))
                except ValueError:
                    pass
    reason = '' if camera else 'Editing this representation is unsupported. Only verified embedded camera GPS can be proposed; sidecar, depicted, destination, structured and derived records stay unchanged.'
    result = GPSField(record.path, position, camera, provenance, reason)
    resolved[id(entry)] = result
    return result


def action_owner(widget):
    original = widget
    while widget is not None:
        if hasattr(widget, 'gps_drafts') or hasattr(widget, '_current_path'):
            return widget
        widget = widget.parent()
    return original


def field_actions(owner, field):
    if field is None:
        return []
    snapshot = getattr(owner, '_gps_snapshots', {}).get(field.path)
    proposal = getattr(owner, 'gps_drafts', {}).get(field.path) if field.camera else None
    position = field.position
    if field.camera and position is None and snapshot:
        position = (snapshot.get('existing') or {}).get('position')
    if proposal and position is None:
        position = proposal['proposed']['position']
    actions = [('View on map…', 'globe', position is not None, field.provenance if position is not None else 'A complete, valid coordinate pair is required.', position)]
    reason = field.reason
    if field.camera and snapshot and snapshot['blocked']:
        reason = '\n'.join(snapshot['blocked'])
    if field.camera and hasattr(owner, 'gps_drafts') and snapshot is None:
        reason = 'Checking embedded camera GPS before editing.'
    if field.camera and Path(field.path).suffix.lower() not in {
            suffix for extensions in FORMATS.values()
            for suffix in extensions}:
        reason = 'GPS proposals are unavailable for this image extension.'
    label = 'Edit GPS' if proposal or position is not None else 'Add GPS'
    actions.append((label, 'document-edit', field.camera and not reason,
                    reason or ('Propose embedded camera GPS for ' + field.path + '. Other representations stay unchanged.'), None))
    if proposal:
        actions.append(('Discard change', 'edit-undo', True, 'Discard this unwritten camera GPS proposal; retain other drafts.', None))
    return actions


def show_field_map(parent, field, position):
    """Reuse the native map, fixed to the selected representation."""
    from kim_location_map import LocationMap
    from kim_location_ui import position_text
    dialog = QDialog(parent)
    dialog.setWindowTitle('View on map')
    dialog.resize(720, 540)
    layout = QVBoxLayout(dialog)
    provenance = field.provenance
    if (
        position is not None
        and 'No embedded camera GPS coordinates' in provenance
    ):
        visible_source = (
            'GPS coordinates from selected metadata'
        )
    else:
        visible_source = provenance

    label = QLabel(
        visible_source + '\n' + position_text(position)
    )
    label.setToolTip(
        'Metadata source: ' + provenance
    )
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    layout.addWidget(label)
    location_map = LocationMap(dialog, interactive=False, persistent=False)
    location_map.set_position(position)
    layout.addWidget(location_map)
    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec()


def dispatch(owner, field, action):
    label, _icon, enabled, _tip, position = action
    if not enabled:
        return
    if label == 'View on map…':
        show_field_map(owner, field, position)
    elif hasattr(owner, 'gps_drafts'):
        if field.path != owner._active_path():
            return
        if label == 'Discard change':
            owner.discard_gps_proposal()
        else:
            owner.add_gps_location()
    else:
        if getattr(owner, '_closing', False) or getattr(owner, '_gps_dialog', None) is not None:
            return
        # Inspect and select in the existing proposal dialog before creating
        # any Editor or its background workers. The clicked field owns the path.
        from kim_location_dialog import LocationDialog
        from kim_metadata_editor import MetadataEditor
        dialog = LocationDialog('apply', [field.path], 'proposal', None)
        dialog.setParent(owner, dialog.windowFlags())
        owner._gps_dialog = dialog
        try:
            if dialog.exec() != QDialog.Accepted or getattr(owner, '_closing', False):
                return
            proposal = dialog.proposal
            if proposal is None:
                return
            problem = proposal_problem(proposal)
            if problem:
                QMessageBox.warning(owner, 'GPS proposal changed', problem)
                return
        finally:
            owner._gps_dialog = None
            dialog.reject()
            dialog.deleteLater()
            if getattr(owner, '_closing', False):
                owner._finish_close()
        editors = getattr(owner, '_gps_editors', None)
        if editors is None:
            editors = owner._gps_editors = []
        editor = MetadataEditor([field.path])
        editor.gps_drafts[field.path] = proposal
        editor._refresh_pending()
        editor.setAttribute(Qt.WA_DeleteOnClose)
        editors.append(editor)
        editor.destroyed.connect(lambda: editors.remove(editor) if editor in editors else None)
        editor.show()
        editor.form_scroll.ensureWidgetVisible(editor.gps_section)


def add_field_controls(layout, owner, field):
    for action in field_actions(owner, field):
        label, icon, enabled, tip, _position = action
        button = QToolButton()
        button.setObjectName('gpsFieldAction')
        button.setText(label)
        button.setAccessibleName('View on map' if label == 'View on map…' else label)
        if label == "View on map…":
            button.setIcon(QIcon.fromTheme(
                "map-globe",
                QIcon.fromTheme(
                    "globe",
                    button.style().standardIcon(
                        QStyle.SP_DriveNetIcon
                    ),
                ),
            ))
            button.setText('Map')
            button.setToolButtonStyle(
                Qt.ToolButtonTextBesideIcon
            )
        else:
            if label in ("Edit GPS", "Add GPS"):
                button.setIcon(QIcon.fromTheme("document-edit"))
                button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            else:
                button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setAutoRaise(False)
        button.setEnabled(enabled)
        button.setToolTip(('View on map' if label == 'View on map…' else label) + '\n' + tip)
        button.clicked.connect(lambda checked=False, target=field, selected=action: dispatch(owner, target, selected))
        layout.addWidget(button)


class GPSActionDelegate(QStyledItemDelegate):
    """Paint native, readable action labels; allocate no row widgets."""
    def __init__(self, view, owner, resolver, columns=(1,)):
        super().__init__(view)
        self.view, self.owner, self.resolver = view, owner, resolver
        self.pressed = None
        self.columns = columns
        # Stretch headers otherwise shrink action cells to icon-sized widths.
        # Keep labels and a little metadata visible, using native scrolling
        # when the window cannot accommodate all columns.
        header = self.header = view.horizontalHeader() if hasattr(view, 'horizontalHeader') else view.header()
        labels = ('View on map…', 'Edit GPS…')
        if getattr(owner, 'gps_drafts', None):
            labels += ('Discard change',)
        minimum = sum(view.fontMetrics().horizontalAdvance(label) + 20 for label in labels) + 48
        header.setMinimumSectionSize(max(header.minimumSectionSize(), minimum))
        for column in columns:
            view.setItemDelegateForColumn(column, self)
        view.installEventFilter(self)

    def buttons(self, index, rect):
        field = self.resolver(index)
        actions = field_actions(self.owner, field)
        widths = [self.view.fontMetrics().horizontalAdvance(action[0]) + 20 for action in actions]
        if widths and sum(widths) + 48 > self.header.minimumSectionSize():
            # A retained proposal adds Discard change after delegate creation.
            self.header.setMinimumSectionSize(sum(widths) + 48)
        left = rect.right() - sum(widths) + 1
        buttons = []
        for action, width in zip(actions, widths):
            buttons.append((action, QRect(left, rect.top(), width, rect.height())))
            left += width
        return field, buttons

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        _field, buttons = self.buttons(index, option.rect)
        if buttons:
            size.setWidth(size.width() + sum(rect.width() for _, rect in buttons) + 6)
            size.setHeight(max(size.height(), option.fontMetrics.height() + 12))
        return size

    def paint(self, painter, option, index):
        field, buttons = self.buttons(index, option.rect)
        cell = QStyleOptionViewItem(option)
        if buttons:
            cell.rect.setRight(buttons[0][1].left() - 3)
        super().paint(painter, cell, index)
        for action, rect in buttons:
            tool = QStyleOptionToolButton()
            tool.rect = rect
            tool.state = QStyle.State_Raised | (QStyle.State_Enabled if action[2] else QStyle.State_None)
            tool.text = action[0]
            tool.font = option.font
            tool.toolButtonStyle = Qt.ToolButtonTextOnly
            self.view.style().drawComplexControl(QStyle.CC_ToolButton, tool, painter, self.view)

    def helpEvent(self, event, view, option, index):
        _field, buttons = self.buttons(index, option.rect)
        for action, rect in buttons:
            if rect.contains(event.pos()):
                QToolTip.showText(event.globalPos(), action[0] + '\n' + action[3], view)
                return True
        return super().helpEvent(event, view, option, index)

    def eventFilter(self, watched, event):
        if watched is self.view and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Menu, Qt.Key_F4):
            index = self.view.currentIndex()
            if index.column() not in self.columns:
                index = index.siblingAtColumn(self.columns[0])
            field, buttons = self.buttons(index, self.view.visualRect(index))
            if buttons:
                menu = QMenu(self.view)
                for action, _rect in buttons:
                    item = menu.addAction(action[0])
                    item.setEnabled(action[2]); item.setToolTip(action[3])
                    item.triggered.connect(lambda checked=False, selected=action: dispatch(self.owner, field, selected))
                menu.exec(self.view.viewport().mapToGlobal(self.view.visualRect(index).center()))
                return True
        return super().eventFilter(watched, event)

    def editorEvent(self, event, model, option, index):
        field, buttons = self.buttons(index, option.rect)
        if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease) and event.button() == Qt.LeftButton:
            for action, rect in buttons:
                if rect.contains(event.position().toPoint()):
                    if event.type() == QEvent.MouseButtonPress:
                        self.pressed = (QPersistentModelIndex(index), action[0])
                    else:
                        pressed, self.pressed = self.pressed, None
                        if pressed == (index, action[0]):
                            dispatch(self.owner, field, action)
                    return True
        return super().editorEvent(event, model, option, index)
