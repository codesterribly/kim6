"""Small shared Qt controls. Importing this module never starts an application."""
from PySide6.QtCore import QDate, QLocale, QTime, Qt, Signal, QEvent
from PySide6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QToolButton, QCalendarWidget, QTimeEdit, QCheckBox, QComboBox,
    QSpinBox, QDoubleSpinBox, QButtonGroup, QLabel, QDialogButtonBox, QFormLayout)

def tr(text):
    import gettext
    import os
    from pathlib import Path
    return gettext.translation('kim6',localedir=os.environ.get('TEXTDOMAINDIR') or
        Path(__file__).resolve().parent.parent/'locale',fallback=True).gettext(text)


HELP = {
    'capture': ('Photo Capture Date', "The date and time the photograph was taken, stored inside the image as metadata. This is different from the file's modification date."),
    'timezone': ('Camera Timezone', "The timezone where the photograph was taken. If you don't know it, choose Unknown. KIM6 won't guess based on your computer's timezone."),
    'dates': ('Date Fields / All Dates', "Choose which dates inside the photograph to update. This doesn't change the file's modification date unless you also select that operation."),
    'settings': ('Reset from Settings', 'Use the value from KIM6 Settings instead of a custom recipe value. Future changes in Settings will automatically apply to this recipe.'),
    'color': ('Color Profile / sRGB', 'Color profiles tell applications how colors should appear. sRGB is a good choice for web sharing and general compatibility. KIM6 converts colors using the original profile when available.'),
    'quality': ('Compression Quality', 'Higher quality generally preserves more detail but creates larger files. Lower quality generally makes smaller files but may lose detail. Results vary by image and format.'),
    'resize': ('Resize to Fit / Exact Dimensions', 'Resize to Fit keeps the original proportions within your chosen dimensions. Exact Dimensions forces the specified width and height, which can stretch the image.'),
    'strip': ('Remove All Metadata', 'Removes embedded information such as camera details, dates, GPS, copyright and color profiles. Use the more specific removal options if you want to keep other information.'),
    'output': ('Output Filename / Location', 'KIM6 saves new files without replacing existing ones. If a filename is taken, it adds a number. The final name is checked again when saving.'),
    'psd': ('PSD Compatibility', "KIM6 uses Photoshop's saved composite when available, or ImageMagick's best-effort reconstruction. Complex layers and effects may look different. Your original PSD is never modified."),
}


class HelpButton(QToolButton):
    """Click-only help: no tooltip, hover event, or auto-open behavior."""
    def __init__(self, topic, parent=None, context=None):
        super().__init__(parent)
        self.topic = topic
        self.explanation = ("Use the current value from KIM6 Settings for this batch instead of your custom value. The preview shows the value that will be applied." if topic=='settings' and context=='batch' else HELP[topic][1])
        self.setText('?'); self.setAutoRaise(True); self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName('Help: ' + tr(HELP[topic][0]))
        self.clicked.connect(self.open_help)
        self.help_dialog = None

    def open_help(self):
        if self.help_dialog is not None:
            self.help_dialog.raise_(); return
        dialog = QDialog(self); dialog.setWindowTitle(tr(HELP[self.topic][0]))
        layout = QVBoxLayout(dialog)
        label = QLabel(tr(self.explanation)); label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        layout.addWidget(label); buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        dialog.resize(420, 150); self.help_dialog = dialog
        dialog.finished.connect(lambda *_: self.clear_help(dialog))
        dialog.open()

    def clear_help(self, dialog):
        self.help_dialog = None; dialog.deleteLater(); self.setFocus()


def with_help(widget, topic, context=None):
    row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0,0,0,0)
    layout.addWidget(widget, 1); layout.addWidget(HelpButton(topic,context=context)); return row


class EmptyDateInput(QWidget):
    """The text is the value; the calendar's navigation page is never a value.

    QDateEdit cannot express null without reserving a valid historical date.
    A separate calendar avoids that sentinel, including for keyboard selection.
    ISO entry is unambiguous; the calendar uses the user's locale and year menu.
    """
    dateChanged = Signal(QDate)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.edit = QLineEdit(); self.edit.setPlaceholderText('Choose date… (YYYY-MM-DD)')
        self.edit.setClearButtonEnabled(True); self.edit.setAccessibleName('Photo Capture Date, YYYY-MM-DD')
        layout.addWidget(self.edit)
        self.button = QPushButton('Calendar…'); self.button.clicked.connect(self.open_calendar); layout.addWidget(self.button)
        self.calendar = QCalendarWidget(); self.calendar.setMinimumDate(QDate(1,1,1)); self.calendar.setMaximumDate(QDate(9999,12,31))
        self.calendar.setLocale(QLocale()); self.calendar.setSelectionMode(QCalendarWidget.NoSelection)
        self.calendar.setCurrentPage(QDate.currentDate().year(),QDate.currentDate().month())
        self.popup = None
        self.calendar.focusProxy().installEventFilter(self)
        self.calendar.focusProxy().viewport().installEventFilter(self)
        self.edit.textChanged.connect(lambda *_: self.dateChanged.emit(self.date()))

    def eventFilter(self, watched, event):
        # Qt disables keyboard day navigation in NoSelection mode. Switch only
        # on an intentional day-selection gesture, never when opening/browsing
        # the calendar. Selection itself still does not change the stored text.
        if self.popup is not None and self.calendar.selectionMode()==QCalendarWidget.NoSelection:
            keyboard=(event.type()==QEvent.KeyPress and event.key() in
                (Qt.Key_Left,Qt.Key_Right,Qt.Key_Up,Qt.Key_Down,Qt.Key_PageUp,Qt.Key_PageDown,
                 Qt.Key_Home,Qt.Key_End,Qt.Key_Return,Qt.Key_Enter))
            if keyboard or event.type()==QEvent.MouseButtonPress:
                anchor=QDate(self.calendar.yearShown(),self.calendar.monthShown(),1)
                anchor=QDate(anchor.year(),anchor.month(),min(QDate.currentDate().day(),anchor.daysInMonth()))
                self.calendar.setSelectionMode(QCalendarWidget.SingleSelection)
                self.calendar.setSelectedDate(anchor)
        return super().eventFilter(watched,event)

    def date(self):
        return QDate.fromString(self.edit.text(), 'yyyy-MM-dd')

    def setDate(self, date):
        self.edit.setText(date.toString('yyyy-MM-dd') if date.isValid() else '')

    def clear(self):
        self.edit.clear()

    def calendarWidget(self):
        return self.calendar

    def open_calendar(self):
        if self.popup is not None: self.popup.raise_(); return
        chosen = self.date(); page = chosen if chosen.isValid() else QDate.currentDate()
        self.calendar.setSelectionMode(QCalendarWidget.SingleSelection if chosen.isValid() else QCalendarWidget.NoSelection)
        if chosen.isValid(): self.calendar.setSelectedDate(chosen)
        self.calendar.setCurrentPage(page.year(),page.month())
        dialog = QDialog(self); dialog.setWindowTitle('Choose Photo Capture Date')
        layout = QVBoxLayout(dialog); layout.addWidget(self.calendar)
        # Empty navigation must not commit today's internally selected date.
        # Explicit click or keyboard activation is the only calendar commit.
        self.calendar.clicked.connect(self.choose_date)
        self.calendar.activated.connect(self.choose_date)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        buttons.button(QDialogButtonBox.Reset).setText('Clear Date')
        buttons.button(QDialogButtonBox.Reset).clicked.connect(lambda: (self.clear(), dialog.reject()))
        buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        self.popup = dialog
        dialog.finished.connect(self.close_calendar); dialog.open(); self.calendar.setFocus()

    def choose_date(self, date):
        self.setDate(date)
        if self.popup: self.popup.accept()

    def close_calendar(self, *_):
        self.calendar.clicked.disconnect(self.choose_date); self.calendar.activated.disconnect(self.choose_date)
        self.calendar.setParent(self)
        self.calendar.hide()
        popup, self.popup = self.popup, None
        popup.deleteLater(); self.button.setFocus()


class EmptyTimeInput(QLineEdit):
    timeChanged = Signal(QTime)

    def __init__(self):
        super().__init__(); self.setPlaceholderText('Choose time… (HH:MM:SS)')
        self.setClearButtonEnabled(True)
        self.textChanged.connect(lambda *_: self.timeChanged.emit(self.time()))

    def time(self): return QTime.fromString(self.text(),'HH:mm:ss')
    def setTime(self, value): self.setText(value.toString('HH:mm:ss') if value.isValid() else '')
    def setDisplayFormat(self, _): pass  # Clock syntax is intentionally explicit.


class CaptureDateInput(QWidget):
    """A nullable date with an ordinary whole-second clock, shared by both UIs."""
    changed = Signal(str)

    def __init__(self, value='', parent=None):
        super().__init__(parent)
        layout = QFormLayout(self); layout.setContentsMargins(0,0,0,0)
        self.date = EmptyDateInput()
        self.time = QTimeEdit(QTime(0,0,0)); self.time.setDisplayFormat('HH:mm:ss')
        self.time.setAccessibleName('Photo Capture Time')
        layout.addRow('Photo Capture Date',with_help(self.date,'capture'))
        layout.addRow('Time',self.time)
        if value:
            parts = value.replace('T',' ').split(' ',1)
            if len(parts) == 2:
                self.date.setDate(QDate.fromString(parts[0],'yyyy-MM-dd'))
                clock = QTime.fromString(parts[1].split('.',1)[0],'HH:mm:ss')
                if clock.isValid(): self.time.setTime(clock)
        self.date.dateChanged.connect(self.update_value)
        self.time.timeChanged.connect(self.update_value)

    def value(self):
        # The clock alone never supplies a date. An explicit date selection
        # supplies midnight without inventing any timezone or fractional part.
        if not self.date.edit.text(): return ''
        return self.date.edit.text() + ' ' + self.time.time().toString('HH:mm:ss')

    def update_value(self,*_):
        self.changed.emit(self.value())


class CaptureDateOptions(QWidget):
    """One collapsed advanced form and one source of timezone/scope UI rules."""
    zone_changed = Signal(str)
    fields_changed = Signal(str)

    def __init__(self, zone='unknown', fields='capture', embedded=False, parent=None):
        super().__init__(parent)
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.toggle=QToolButton(); self.toggle.setText('Advanced Options')
        self.toggle.setCheckable(True); self.toggle.setArrowType(Qt.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon); layout.addWidget(self.toggle)
        self.content=QWidget(); self.form=QFormLayout(self.content); layout.addWidget(self.content)
        self.zone=QComboBox()
        self.zone.addItem('Unknown','unknown')
        if embedded: self.zone.addItem('Keep embedded timezone','embedded')
        self.zone.addItem('UTC (+00:00)','UTC'); self.zone.addItem('Explicit offset','custom')
        self.offset=QLineEdit(); self.offset.setPlaceholderText('±HH:MM')
        self.fields=QComboBox(); self.fields.addItem('Photo Capture Date only','capture'); self.fields.addItem('All embedded dates','all')
        self.form.addRow('Camera Timezone',with_help(self.zone,'timezone'))
        self.form.addRow('Explicit offset',self.offset)
        self.form.addRow('Date fields',with_help(self.fields,'dates'))
        self.set_zone(zone)
        self.fields.setCurrentIndex(max(0,self.fields.findData(fields)))
        self.content.hide()
        self.toggle.toggled.connect(self.expand)
        self.zone.currentIndexChanged.connect(self.update_zone)
        self.offset.textChanged.connect(lambda *_:self.zone_changed.emit(self.zone_value()))
        self.fields.currentIndexChanged.connect(lambda *_:self.fields_changed.emit(self.fields.currentData()))

    def expand(self, opened):
        self.content.setVisible(opened); self.toggle.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)

    def set_zone(self, zone):
        index=self.zone.findData(zone or 'unknown')
        self.zone.setCurrentIndex(index if index >= 0 else self.zone.findData('custom'))
        self.offset.setText(zone if index < 0 else '')
        self.form.setRowVisible(self.offset,self.zone.currentData()=='custom')

    def zone_value(self):
        return self.offset.text() if self.zone.currentData()=='custom' else self.zone.currentData()

    def update_zone(self,*_):
        self.form.setRowVisible(self.offset,self.zone.currentData()=='custom')
        self.zone_changed.emit(self.zone_value())


class CaptureAdjustment(QWidget):
    changed = Signal(int)

    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        self.sign = QComboBox(); self.sign.addItems(['Add','Subtract']); self.sign.setCurrentIndex(int(value < 0)); layout.addWidget(self.sign)
        self.parts = []; remaining = abs(value)
        for label,unit,maximum in [('days',86400,3652),('hours',3600,23),('minutes',60,59),('seconds',1,59)]:
            widget = QSpinBox(); widget.setRange(0,maximum); widget.setValue(remaining//unit); remaining %= unit
            widget.setSuffix(' '+label); widget.setAccessibleName('Adjust by '+label)
            self.parts.append((widget,unit)); layout.addWidget(widget); widget.valueChanged.connect(self.update_value)
        self.sign.currentIndexChanged.connect(self.update_value)

    def value(self):
        value = sum(w.value()*unit for w,unit in self.parts)
        return -value if self.sign.currentIndex() else value

    def update_value(self,*_): self.changed.emit(self.value())


class RotationInput(QWidget):
    changed = Signal(float)

    def __init__(self, value=0, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        bar = QHBoxLayout(); self.buttons = {}; self.group = QButtonGroup(self); self.group.setExclusive(True)
        self.degrees = QDoubleSpinBox(); self.degrees.setRange(-360,360); self.degrees.setDecimals(3)
        self.degrees.setSuffix('°'); self.degrees.setAccessibleName('Custom rotation degrees, positive turns right')
        self.degrees.setValue(value)
        for label,angle in [('90° Left',-90),('90° Right',90),('180°',180),('Custom',None)]:
            button = QPushButton(label); button.setCheckable(True); self.group.addButton(button); bar.addWidget(button); self.buttons[label] = button
            button.clicked.connect(lambda checked=False,a=angle: self.preset(a))
        layout.addLayout(bar); layout.addWidget(self.degrees)
        self.degrees.valueChanged.connect(self.value_changed); self.sync(value)

    def preset(self, angle):
        if angle is None: self.degrees.setFocus(); self.degrees.selectAll()
        else: self.degrees.setValue(angle)

    def sync(self,value):
        label = {-90:'90° Left',90:'90° Right',180:'180°'}.get(value,'Custom')
        self.buttons[label].setChecked(True)

    def value_changed(self,value): self.sync(value); self.changed.emit(value)
