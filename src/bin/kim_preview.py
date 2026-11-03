"""Standalone read-only plans, shared Qt view and approved publication guards.

Plans are invocation-private scratch data, never user exports. Only the existing
kim_all publishers write images. Filename seeds come from its policy/affix rules.
"""
import contextlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
from functools import lru_cache
import sys
from kim_psd_source import run_process, inspection_context, checkpoint


def identity(path):
    info=os.lstat(path)
    if stat.S_ISLNK(info.st_mode): reason = 'is a symbolic link'
    elif stat.S_ISDIR(info.st_mode): reason = 'is a folder, not an image or GPX file'
    elif not stat.S_ISREG(info.st_mode): reason = 'is not a regular file'
    elif info.st_nlink != 1: reason = 'has ' + str(info.st_nlink) + ' hard links'
    else: reason = None
    if reason: raise ValueError(str(path) + ' — ' + reason + '. Select an independent regular file.')
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_mode,info.st_uid,info.st_gid]


def absolute(path):
    if any(c in str(path) for c in '\n\r'): raise ValueError('Paths containing line breaks are unsupported.')
    path=Path(os.path.abspath(path))
    return str(path.parent.resolve(strict=True)/path.name)


@contextlib.contextmanager
def inspection_path(path):
    # Inspect through an inherited descriptor so even access times stay intact.
    # Fail closed when the filesystem/user cannot provide O_NOATIME.
    try: fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NOATIME)
    except PermissionError as exc:
        raise ValueError('Cannot inspect this source without changing its access time. Preview requires ownership or permission for read-only, no-access-time inspection: '+str(path)) from exc
    try: yield f'/proc/self/fd/{fd}',fd
    finally: os.close(fd)


def read_metadata(path, tags):
    with inspection_path(path) as (opened,fd):
        with os.fdopen(os.dup(fd),'rb') as stream:
            result=run_process(['exiftool','-json','-G1',*tags,'--','-'],text=True,stdin=stream)
    if result.returncode: raise ValueError('Cannot inspect metadata: '+result.stderr.strip())
    data=json.loads(result.stdout)[0]
    if 'ExifTool:Error' in data: raise ValueError(str(data['ExifTool:Error']))
    return data


def text(value):
    if value is None: return ''
    if isinstance(value,list): return ', '.join(map(str,value))
    return str(value)


def field(data, tag):
    group,name=tag.split(':',1) if ':' in tag else ('',tag)
    groups={'EXIF':('IFD0','ExifIFD','GPS','InteropIFD'),'IPTC':('IPTC',),'ICC_Profile':('ICC_Profile','ICC-header',)}.get(group,(group,))
    return text(next((v for k,v in data.items() if k.split(':')[-1]==name and
                      (not group or k.rsplit(':',1)[0] in groups)),''))


def split_name(path):
    name=Path(path).name
    if '.' in name and not (name.startswith('.') and name.count('.')==1):
        stem,ext=name.rsplit('.',1); return stem,('.'+ext if ext else '')
    return name,''


def target_snapshot(target):
    parent=Path(target).parent
    if not parent.is_dir() or not os.access(parent,os.W_OK|os.X_OK):
        raise ValueError('Destination directory is unavailable: '+str(parent))
    info=parent.stat()
    return {'parent':[info.st_dev,info.st_ino],
            'entry':identity(target) if os.path.lexists(target) else None}


def allocate(source, candidate, policy, reserved, separator='_', sequential=None, rename=False):
    candidate=absolute(candidate); stem,ext=split_name(candidate); n=1
    target=candidate
    while os.path.lexists(target) or target in reserved:
        checkpoint()
        if rename and policy=='overwrite' and target==source: break
        if policy=='overwrite' and not rename: break
        if rename and policy=='overwrite' and sequential is None and separator is None:
            raise ValueError('The planned filename is occupied: '+target)
        if sequential is not None:
            sequential[0]+=1
            if sequential[0]>=10**18: raise ValueError('Sequential numbering is exhausted.')
            target=str(Path(candidate).parent/(sequential[1]+str(sequential[0]).zfill(sequential[2])+ext))
        else:
            target=str(Path(candidate).parent/(stem+(separator or '_')+str(n)+ext)); n+=1
    if target in reserved: raise ValueError('Two images would use the same destination: '+target)
    reserved.add(target)
    return target


def finish_entry(entry, target, policy):
    entry['target']=target; entry['destination']=target_snapshot(target)
    entry['publication']='overwrite' if policy=='overwrite' and entry['destination']['entry'] is not None else 'create'
    if entry['publication']=='overwrite' and target!=entry['source']:
        entry['warnings'].append('Replace existing derived output (explicitly approved).')


def base_entry(path):
    source=absolute(path)
    if '\n' in source or '\r' in source: raise ValueError('Filenames containing line breaks are unsupported.')
    return dict(source=source,identity=identity(source),status='change',warnings=[],rows=[],args=[])


def rights_plan(entry, config):
    from kim_recipe_image import COPYRIGHT_TAGS, NO_LEGACY_IPTC
    tags=['-FileType','-DateTimeOriginal']+['-'+t for group in COPYRIGHT_TAGS.values() for t in group]
    data=read_metadata(entry['source'],tags); fmt=field(data,'FileType').lower()
    if fmt=='extended webp': fmt='webp'
    if fmt not in ('jpeg','png','tiff','webp','avif','heic','heif','jp2','jxl','psd'):
        raise ValueError('This format cannot safely store the requested rights fields: '+fmt.upper())
    year=config.get('year') or (re.match(r'^(\d{4}):',field(data,'DateTimeOriginal')) or [None,str(dt.datetime.now().year)])[1]
    changed=False
    for key,label in [('creator','Creator / Artist'),('notice','Copyright Notice'),('rights','Usage Rights')]:
        value=config.get(key,'')
        tags=[tag for tag in COPYRIGHT_TAGS[key] if fmt not in NO_LEGACY_IPTC or not tag.startswith('IPTC:')]
        if key=='notice': value=value.replace('{YEAR}',year)
        for tag in tags:
            current=field(data,tag)
            state='Preserve unchanged' if not value else 'Already correct' if current==value else 'Set / replace'
            entry['rows'].append([Path(entry['source']).name,label+' ('+tag+')',current or '(absent)',value or 'Preserve unchanged',state])
            if value:
                entry['args'].append('-'+tag+'='+value)
                changed |= current!=value
    if not changed: entry['status']='skip'
    if '{YEAR}' in config.get('notice','') and not re.match(r'^\d{4}:',field(data,'DateTimeOriginal')) and not config.get('year'):
        entry['warnings'].append('No capture year; the existing operation uses the current calendar year ('+year+').')


def removal_plan(entry, config):
    from kim_recipe_image import GPS_TAGS, AI_TAGS
    mode=config['mode']; do_ai=mode=='ai' or config.get('remove_ai')=='true'
    tags=['-FileType','-EXIF:all','-IPTC:all','-XMP:all','-Comment','-ICC_Profile:ProfileDescription','-ICC_Profile:ProfileFileSignature']
    data=read_metadata(entry['source'],tags)
    if mode!='all' and Path(entry['source']).suffix.upper() in ('.DNG','.CR2','.CR3','.NEF','.ARW','.RAF','.ORF','.RW2','.PEF','.SRW','.3FR','.IIQ','.KDC','.X3F'):
        raise ValueError('The existing selective metadata publisher does not edit camera RAW files.')
    gps_names={t.split(':')[-1] for t in GPS_TAGS if '*' not in t and not t.endswith(':all')}
    gps={k:v for k,v in data.items() if k.startswith('GPS:') or (k.startswith('XMP-') and k.split(':')[-1].startswith('GPS')) or (k.startswith('XMP-iptcExt:') and k.split(':')[-1] in gps_names)}
    ai={k:v for k,v in data.items() if k.split(':')[-1] in {t.split(':')[-1] for t in AI_TAGS}}
    digital=field(data,'XMP-iptcExt:DigitalSourceType')
    if any(v in digital for v in ('trainedAlgorithmicMedia','compositeWithTrainedAlgorithmicMedia','algorithmicMedia')): ai['DigitalSourceType']=digital
    descriptive={k:v for k,v in data.items() if (k.startswith(('IFD0:','ExifIFD:','IPTC:','XMP-')) or k.split(':')[-1]=='Comment') and k!='IFD0:Orientation' and k not in gps and k not in ai}
    for label,present,remove in [('Recognized GPS coordinates',bool(gps),mode in ('all','gps')),
                                 ('Recognized AI fields',bool(ai),mode=='all' or do_ai),
                                 ('Other descriptive metadata',bool(descriptive),mode=='all'),
                                 ('ICC profile',any(k.startswith(('ICC_Profile:','ICC-header:')) for k in data),False),
                                 ('Orientation',bool(field(data,'IFD0:Orientation')),False)]:
        entry['rows'].append([Path(entry['source']).name,label,'Present' if present else 'Not recognized / absent',
                              'Remove' if remove else 'Preserve','Requested removal' if remove else 'Unchanged'])
    entry['warnings'].append('Unrecognized provenance and signed Content Credentials may remain. GPS removal covers recognized coordinates, not complete location anonymization.' if mode!='all' else
                             'Removes descriptive EXIF, IPTC, XMP and comments, including capture dates and rights. Keeps ICC and orientation. Signed Content Credentials may remain.')
    if Path(entry['source']).suffix.lower() in ('.png','.apng'):
        inspect_png_removal(entry,mode,do_ai)
    # The native PNG filter intentionally also handles container text/chunks.
    if mode!='all' and Path(entry['source']).suffix.lower() not in ('.png','.apng') and not (gps if mode=='gps' else ai) and not (do_ai and ai):
        entry['status']='skip'


def inspect_png_removal(entry,mode,remove_ai):
    import struct
    from kim_png_metadata import SIG,TEXT,IMAGE,PRESENTATION,MAX_TEXT,text_payload,orientation_only
    matching=0; other=0
    with inspection_path(entry['source']) as (_,fd), os.fdopen(os.dup(fd),'rb') as stream:
        if stream.read(8)!=SIG: raise ValueError('Selected PNG has an invalid container signature.')
        size=os.fstat(fd).st_size
        while stream.tell()+12<=size:
            checkpoint()
            length,tag=struct.unpack('>I4s',stream.read(8))
            if stream.tell()+length+4>size: raise ValueError('Truncated PNG metadata container.')
            if tag in TEXT or tag==b'eXIf':
                if length>MAX_TEXT: raise ValueError('PNG metadata exceeds the native safety limit.')
                payload=stream.read(length)
                if tag==b'eXIf':
                    if mode!='all': raise ValueError('Selective PNG EXIF edits require TIFF IFD filtering and are refused by the existing container engine.')
                    matching+=bool(orientation_only(payload)!=payload)
                else: matching+=text_payload(tag,payload,mode,remove_ai)!=payload
            else:
                if tag not in IMAGE|PRESENTATION:
                    if not tag[0]&0x20: raise ValueError('Unknown critical PNG chunk.')
                    if mode in ('all','ai'): other+=1
                stream.seek(length,1)
            stream.seek(4,1)
            if tag==b'IEND': break
    entry['rows'].append([Path(entry['source']).name,'PNG container text / ancillary metadata',
                          f'{matching} matching text / EXIF blocks; {other} other removable chunks',
                          'Apply native '+mode+' filter','Container filter; image data, ICC and presentation chunks preserved'])
    if mode=='ai':
        for row in entry['rows']:
            if row[1]=='Other descriptive metadata': row[3]='Preserve recognized photo text; filter unclassified PNG metadata'; row[4]='Native PNG filtering'
        entry['warnings'].append('PNG AI removal also removes unclassified text and unknown ancillary chunks; recognized ordinary photo text is preserved. Mixed AI/photo text or unknown XML may block safe filtering.')


def date_plan(entry, config):
    from kim_date_tools import resolve
    config=dict(config,_preview=True)
    result=resolve(entry['source'],config)
    entry['args']=result['args']; entry['date_result']=result
    if 'epoch_ns' in result:
        current=Path(entry['source']).stat().st_mtime_ns
        entry['rows'].append([Path(entry['source']).name,'File Modification Date',
                              dt.datetime.fromtimestamp(current/10**9).astimezone().isoformat(),result['preview'],'Set modification time only; embedded dates preserved'])
        if current==result['epoch_ns']: entry['status']='skip'
    else:
        changed=False
        for assignment in result['args']:
            tag,value=assignment[1:].split('=',1); current=field(result['current'],tag)
            changed |= current!=value
            entry['rows'].append([Path(entry['source']).name,tag,current or '(absent)',value or 'Clear field',
                                  'Already correct' if current==value else 'Set / replace'])
        if not changed: entry['status']='skip'
    entry['warnings'].append('Camera clocks keep the selected timezone interpretation. File Modification Date is preserved.' if 'epoch_ns' not in result else
                             'Changes only the File Modification Date; the preview displays the capture clock and its known offset.')


def format_class(fmt):
    fmt=fmt.upper()
    if re.match(r'^PNG[0-9]',fmt): return 'PNG'
    for canonical,aliases in {'JPEG':('JPG','JPE','JFIF','JPS','PJPEG'), 'TIFF':('TIF','TIFF64','PTIF'),
                             'PNG':('APNG','PNG8','PNG24','PNG32','PNG48','PNG64'), 'BMP':('BMP2','BMP3','DIB'),
                             'GIF':('GIF87',),'JP2':('J2C','J2K','JPC','JPM','JPT'),'HEIC':('HEIF',)}.items():
        if fmt in aliases: return canonical
    return fmt


def conversion_rules(input_format,frames,apng,webp_animation,config,extension):
    """The standalone encoder and its preview share these exact refusals/no-op rules.

    Header inspection supplies facts; pixel decoding and output verification
    remain in the established encoder after confirmation.
    """
    fmt=config['format']; source=format_class(input_format)
    if source in ('EXR','HDR') and input_format.upper()!=fmt.upper():
        raise ValueError('HDR / OpenEXR requires explicit tone mapping before conversion.')
    if apng and fmt!='apng': raise ValueError('Animated PNG requires APNG output to preserve playback.')
    if frames>1 and fmt not in ('gif','tif','tiff','tiff64','webp','avif','heic','heif','apng','pdf','ico','cur'):
        raise ValueError('Requested format cannot preserve this multi-frame input.')
    if (config['policy']=='overwrite' and extension.lower()==fmt and not config.get('jpeg_scan') and
        config.get('jpeg_optimize')!='true' and config.get('bmp5')!='true' and source==format_class(fmt)):
        return 'skip'
    if frames>1 and not apng:
        if source=='GIF' and fmt not in ('gif','apng'): raise ValueError('Animated GIF playback is not verified for this output format.')
        if source=='WEBP' and fmt!='webp': raise ValueError('Animated WebP playback cannot be preserved in this format.')
        if source in ('AVIF','HEIC'): raise ValueError('Multi-image AVIF/HEIC sequences cannot safely be re-encoded.')
        if source not in ('GIF','WEBP','AVIF','HEIC') and fmt in ('gif','gif87','webp','apng','avif','heic','heif'):
            raise ValueError('Multipage images cannot safely be converted to animated formats.')
    if frames==1 and source=='WEBP' and webp_animation and fmt!='webp':
        raise ValueError('Animated WebP requires WebP output to preserve playback.')
    return 'change'


def conversion_plan(entry,config,registry):
    fmt=config['format']; output=format_class(fmt)
    coder={'dib':'BMP','jfif':'JPEG','heif':'HEIC'}.get(fmt,fmt.upper())
    if not any(re.match(r'^\s*'+re.escape(coder)+r'\*?\s+(?:\S+\s+)?[r-]w[+-]\s',line) for line in registry.splitlines()):
        raise ValueError('Requested encoder is unavailable: '+fmt.upper())
    with inspection_path(entry['source']) as (opened,fd):
        with os.fdopen(os.dup(fd),'rb') as stream: signature=stream.read(26)
        psd=signature.startswith(b'8BPS')
        if psd:
            from kim_psd_source import WARNING
            import struct
            if len(signature)!=26: raise ValueError('Truncated PSD header')
            version=struct.unpack('>H',signature[4:6])[0]
            height,width,depth,mode=struct.unpack('>IIHH',signature[14:26])
            if version!=1 or not width or not height or max(width,height)>30000 or width*height>100000000 or depth not in (8,16) or mode not in (1,3,4):
                raise ValueError('Unsupported PSD version, canvas, depth or color mode.')
            input_format='PSD'; frames=1; entry['warnings'].append(WARNING)
        else:
            with os.fdopen(os.dup(fd),'rb') as stream:
                stream.seek(0)
                result=run_process(['identify','-regard-warnings','-ping','-format','%m|%w|%h\n','-'],text=True,stdin=stream)
            if result.returncode: raise ValueError('Cannot safely inspect image headers: '+result.stderr.strip())
            records=[line.split('|') for line in result.stdout.splitlines()]
            if not records or any(len(r)!=3 or not r[1].isdigit() or not r[2].isdigit() or int(r[1])*int(r[2])<1 for r in records):
                raise ValueError('Invalid image dimensions or image list.')
            input_format=records[0][0]; frames=len(records)
        # Container control chunks, never a decoded frame count for preview.
        animated=False
        with os.fdopen(os.dup(fd),'rb') as stream:
            stream.seek(0); sig=stream.read(12)
            if sig.startswith(b'\x89PNG\r\n\x1a\n') or (sig[:4]==b'RIFF' and sig[8:]==b'WEBP'):
                import struct
                png=sig.startswith(b'\x89PNG'); stream.seek(8 if png else 12)
                size=os.fstat(fd).st_size
                while stream.tell()+8<=size:
                    checkpoint()
                    raw=stream.read(8)
                    length,tag=struct.unpack('>I4s',raw) if png else (lambda t,n:(n,t))(*struct.unpack('<4sI',raw))
                    if stream.tell()+length+(4 if png else length%2)>size: raise ValueError('Truncated image container.')
                    if tag in (b'acTL',b'ANIM',b'ANMF'): animated=True
                    stream.seek(length+(4 if png else length%2),1)
        _,ext=split_name(entry['source'])
        entry['status']=conversion_rules(input_format,frames,animated and format_class(input_format)=='PNG',
                                         animated and format_class(input_format)=='WEBP',config,ext[1:])
    data=read_metadata(entry['source'],['-ICC_Profile:ProfileDescription','-ICC_Profile:ProfileFileSignature','-EXIF:all','-IPTC:all','-XMP:all'])
    has_icc=bool(field(data,'ICC_Profile:ProfileFileSignature'))
    if psd and mode==4 and not has_icc:
        raise ValueError('Unprofiled CMYK PSD has unknown source colors; assign a valid ICC profile before exporting.')
    if psd and fmt=='pdf':
        entry['warnings'].append('Export one PDF page with sRGB pixels at 72 pixels per inch; camera/descriptive metadata and embedded ICC are removed. Photoshop source is preserved.')
    elif psd:
        entry['warnings'].append('Photoshop pixels are normalized to sRGB. Original CMYK/grayscale profiles are not copied onto transformed pixels; existing output profile checks apply.')
    elif has_icc:
        entry['warnings'].append('Embedded ICC profile: byte-for-byte retention is required for profile-bearing output; incompatible encoders stop before publication.')
    if output in ('BMP','GIF','PDF'):
        entry['warnings'].append('This output has limited descriptive metadata support. Existing format-specific retention rules apply.')
    entry['input_format']=input_format
    entry['psd']=psd
    if output in ('JPEG','AVIF','HEIC') or (output=='JP2' and config.get('jp2_mode')!='lossless'):
        entry['warnings'].append('Lossy output encoding; output size is known only after encoding.')
    if output=='JPEG': entry['warnings'].append('JPEG cannot retain transparency. Photoshop composites are flattened onto white by the existing source adapter.')
    elif output in ('BMP','PDF'): entry['warnings'].append('Transparency support depends on the requested encoder/settings. Photoshop composites are flattened onto white for this output.')
    if output=='GIF': entry['warnings'].append('Palette encoding reduces colors and transparency precision.')
    entry['warnings'].append('ICC compatibility and metadata retention are verified at encoding; unsupported preservation stops the file. Some formats cannot retain all source metadata.')
    if frames>1 or animated: entry['warnings'].append('Playback / page preservation must pass existing output verification before publication.')


def build_plan(operation,policy,files,config=None,seeds=None,progress=lambda *_:None,cancelled=lambda:False):
    config=dict(config or {},policy=policy); reserved=set(); identities=set(); entries=[]
    registry=''
    if operation=='convert':
        with inspection_context(cancelled=cancelled):
            registry=run_process(['magick','-list','format'],text=True).stdout
    number=[config.get('start',1),config.get('value',''),config.get('padding',3)]
    with inspection_context(cancelled=cancelled):
        for index,path in enumerate(files):
            if cancelled(): raise ValueError('Planning cancelled')
            progress(index,len(files),str(path)); entry=dict(source=str(path),status='error',warnings=[],rows=[],args=[])
            try:
                entry=base_entry(path)
                key=tuple(entry['identity'][:2])
                if key in identities: raise ValueError('The same source identity was selected more than once.')
                identities.add(key); source=entry['source']
                if operation=='rename':
                    from kim_filename import standalone,DATE_FORMATS
                    method=config['method']; stem,ext=split_name(source)
                    if method=='exifdate':
                        # Retain the standalone executor's documented fallback order.
                        value=''; used=''
                        with inspection_path(source) as (opened,fd):
                            for tag in ('DateTimeOriginal','CreateDate','ModifyDate'):
                                with os.fdopen(os.dup(fd),'rb') as stream:
                                    stream.seek(0)
                                    result=run_process(['exiftool','-s3','-'+tag,'-d',DATE_FORMATS[config['value']],'--','-'],text=True,stdin=stream)
                                if result.returncode==0 and result.stdout.strip(): value=result.stdout.strip(); used=tag; break
                        if not value or not re.fullmatch(r'(?:IMG-)?\d{8}_\d{6}|\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}',value):
                            raise ValueError('No valid embedded date for the filename.')
                        name=value
                        if used!='DateTimeOriginal': entry['warnings'].append('No capture date; existing rename behavior uses '+used+'.')
                    else: name=standalone(stem,method,config.get('value',''),config.get('replacement',''),number[0],number[2])
                    if not name or name in ('.','..') or any(c in name for c in '/\n\r'):
                        raise ValueError('Enter a filename without slashes or line breaks.')
                    directory=config.get('directory') or str(Path(source).parent)
                    if not Path(directory).is_absolute(): raise ValueError('Choose an absolute destination directory.')
                    candidate=str(Path(directory)/(name+ext))
                    target=allocate(source,candidate,policy,reserved,'_' if method=='exifdate' or policy=='create' else None,number if method=='sequential' else None,rename=True)
                    if target!=absolute(candidate): entry['warnings'].append('Filename collision: the displayed filename includes planned collision numbering.')
                    if method=='sequential': number[0]+=1
                    if target==source: entry['status']='skip'
                    finish_entry(entry,target,'create' if target!=source else policy)
                    entry['rows']=[[Path(source).name,Path(target).name,str(Path(target).parent),{'sequential':'Sequential numbering','exifdate':'Embedded date filename','lowercase':'Lowercase','uppercase':'Uppercase','spacestodash':'Spaces to dashes','spacestounderscore':'Spaces to underscores','underscorestospace':'Underscores to spaces','dashestospace':'Dashes to spaces','addprefix':'Add prefix','addsuffix':'Add suffix','overwrite':'Replace text'}[method],'Unchanged' if target==source else ('Rename selected original' if policy=='overwrite' else 'Create renamed copy')]]
                else:
                    if operation=='copyright': rights_plan(entry,config)
                    elif operation=='strip': removal_plan(entry,config)
                    elif operation=='date': date_plan(entry,config)
                    elif operation=='convert': conversion_plan(entry,config,registry)
                    else: raise ValueError('Unsupported preview operation')
                    candidate=seeds[index] if seeds else source
                    effective='create' if entry.get('psd') else policy
                    target=allocate(source,candidate,effective,reserved,'_' if operation=='convert' else '-')
                    finish_entry(entry,target,effective)
                    if target!=absolute(candidate): entry['warnings'].append('Filename collision: the displayed filename includes planned collision numbering.')
                    if operation=='convert':
                        entry['rows']=[[Path(source).name,Path(target).name,str(Path(target).parent),entry['input_format']+' → '+config['format'].upper(),
                                        'Unchanged' if entry['status']=='skip' else ('Replace file' if entry['publication']=='overwrite' else 'Create file')]]
                if identity(source)!=entry['identity']: raise ValueError('Source changed during inspection; review a fresh plan.')
            except Exception as exc:
                entry['status']='error'; entry['error']=str(exc)
                entry['rows']=[[Path(path).name,'','','','Blocking error: '+str(exc)]]
            entries.append(entry)
    # A derived target must never alias a different selected original.
    selected={tuple(e['identity'][:2]) for e in entries if 'identity' in e}
    for entry in entries:
        destination=entry.get('destination',{}).get('entry')
        if destination and tuple(destination[:2]) in selected and entry['target']!=entry['source']:
            entry['status']='error'; entry['error']='Destination aliases a selected source.'
            for row in entry['rows']: row[4]='Blocking error: '+entry['error']
    return dict(operation=operation,policy=policy,total=len(files),config=config,entries=entries)


def verify_entry(entry):
    if entry['status']=='error': raise ValueError(entry.get('error','Blocking error'))
    if identity(entry['source'])!=entry['identity']: raise ValueError('Source changed after preview: '+entry['source'])
    if target_snapshot(entry['target'])!=entry['destination']: raise ValueError('Destination changed after preview: '+entry['target'])


def verify_plan(plan):
    if not plan['entries']: raise ValueError('No selected images.')
    if plan.get('operation') == 'location':
        from kim_location import verify_dependencies
        verify_dependencies(plan)
    for entry in plan['entries']: verify_entry(entry)


def save_plan(path,plan):
    verify_plan(plan); Path(path).write_text(json.dumps(plan,ensure_ascii=True))


# Lazy Qt imports keep publication guards usable without constructing a GUI.
@lru_cache(maxsize=1)
def qt_classes():
    from PySide6.QtCore import QThread,Signal,Qt
    from PySide6.QtWidgets import (QWidget,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
                                  QDialog,QDialogButtonBox,QApplication)

    class PreviewView(QWidget):
        def __init__(self,parent=None):
            super().__init__(parent); layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
            self.summary=QLabel('Inspecting selected images…'); self.summary.setTextFormat(Qt.PlainText); self.summary.setWordWrap(True); layout.addWidget(self.summary)
            self.table=QTableWidget(0,5); self.table.setWordWrap(False); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(self.table)

        def show_plan(self,plan):
            self.plan=plan
            entries=plan['entries']; changes=sum(e['status']=='change' for e in entries); skips=sum(e['status']=='skip' for e in entries)
            errors=sum(e['status']=='error' for e in entries); warnings=sum(bool(e['warnings']) for e in entries)
            label={'rename':'Rename Images','convert':'Convert Format','copyright':'Set Creator and Copyright','strip':'Remove Metadata','date':'Photo Dates','location':'Image Location Tools'}[plan['operation']]
            policy=('Create renamed copies' if plan['operation']=='rename' else 'Create new files (originals untouched)') if plan['policy']=='create' else ('Rename selected originals' if plan['operation']=='rename' else 'Explicitly approved replacement')
            settings=''
            if plan['operation']=='location':
                from kim_location import TITLES
                label=TITLES[plan['config']['kind']]
            elif plan['operation']=='date':
                label={'set':'Set Photo Capture Date','shift':'Adjust Photo Capture Date','exif-to-file':'Set File Date from Photo Capture Date','file-to-exif':'Set Photo Capture Date from File Date'}[plan['config']['kind']]
            elif plan['operation']=='convert':
                c=plan['config']; settings=' — '+c['format'].upper()
                if c.get('jp2_mode'): settings+='; JPEG 2000 '+c['jp2_mode']+' (quality '+c.get('jp2_quality','75')+')'
                if c.get('jpeg_scan'): settings+='; JPEG '+('progressive' if c['jpeg_scan']=='Plane' else 'baseline')
                if c.get('jpeg_optimize')=='true': settings+='; optimized JPEG Huffman coding'
                if c.get('bmp5')=='true': settings+='; BMP5'
            elif plan['operation']=='strip': settings=' — '+{'all':'Strip Metadata','gps':'Strip GPS Metadata','ai':'Strip AI Metadata'}[plan['config']['mode']]
            self.summary.setText(f'{label}{settings} — {policy}\nSelected images: {plan["total"]}   Planned changes: {changes}   Skipped / unchanged: {skips}   Warnings: {warnings}   Blocking errors: {errors}')
            rename = plan['operation'] == 'rename'

            if rename:
                names = [
                    'Current filename',
                    'Proposed filename',
                    'Destination directory',
                    'Status / warnings'
                ]
            elif plan['operation'] == 'convert':
                names = [
                    'Current filename',
                    'Proposed filename',
                    'Destination directory',
                    'Planned transformation',
                    'Status / warnings'
                ]
            else:
                names = [
                    'Current filename',
                    'Field or category',
                    'Current value',
                    'Proposed change',
                    'Status / warnings'
                ]

            self.table.setColumnCount(len(names))
            self.table.setHorizontalHeaderLabels(names)
            self.table.setRowCount(sum(len(e['rows']) for e in entries))

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.Stretch)

            if plan['operation'] == 'convert':
                header.setSectionResizeMode(3, QHeaderView.Fixed)
                self.table.setColumnWidth(3, 160)

            row = 0

            for entry in entries:
                details = '\n'.join([
                    entry['source'],
                    *(
                        ['Destination: ' + entry['target']]
                        if 'target' in entry else []
                    ),
                    entry.get('error', ''),
                    *entry['warnings']
                ])

                for values in entry['rows']:
                    displayed = (
                        (values[0], values[1], values[2], values[4])
                        if rename else values
                    )

                    for col, value in enumerate(displayed):
                        if col == len(displayed) - 1 and entry['warnings']:
                            value += '\n' + '\n'.join(entry['warnings'])

                        item = QTableWidgetItem(value)
                        item.setToolTip(value + '\n\n' + details)
                        self.table.setItem(row, col, item)

                    row += 1
            return not errors and changes>0

    class PlanWorker(QThread):
        progress=Signal(int,int,str)
        def __init__(self,operation,policy,files,config,seeds,parent):
            super().__init__(parent); self.arguments=(operation,policy,files,config,seeds); self.plan=None; self.error=None
        def run(self):
            try: self.plan=build_plan(*self.arguments,progress=self.progress.emit,cancelled=self.isInterruptionRequested)
            except Exception as exc: self.error=str(exc)

    class PreviewDialog(QDialog):
        def __init__(self,spec,parent=None):
            super().__init__(parent); self.setWindowTitle('Preview Changes'); self.resize(1050,580); self.closing=False; self.plan=None; self.failure=None
            layout=QVBoxLayout(self); self.view=PreviewView(); layout.addWidget(self.view)
            self.buttons=QDialogButtonBox(QDialogButtonBox.Apply|QDialogButtonBox.Cancel); layout.addWidget(self.buttons)
            self.apply=self.buttons.button(QDialogButtonBox.Apply); self.apply.setText('Apply Changes'); self.apply.setEnabled(False); self.apply.clicked.connect(self.accept)
            self.buttons.rejected.connect(self.reject)
            self.worker=PlanWorker(spec['operation'],spec['policy'],spec['files'],spec['config'],spec['seeds'],self)
            self.worker.progress.connect(lambda i,n,p:self.view.summary.setText(f'Inspecting image {i+1} of {n}: {Path(p).name}'))
            # QDialog.finished(int) is a native signal; never name this handler
            # "finished", which PySide replaces with that incompatible signal.
            self.worker.finished.connect(self.plan_finished); self.worker.start()
        def plan_finished(self):
            worker,self.worker=self.worker,None
            try:
                if self.closing: super().reject()
                elif worker.error: self.show_failure(worker.error)
                else:
                    self.plan=worker.plan; self.apply.setEnabled(self.view.show_plan(self.plan))
                    errors=[entry['error'] for entry in self.plan['entries'] if entry['status']=='error']
                    if errors:
                        self.failure='\n'.join(errors)
                        print('Preview Changes: '+self.failure,file=sys.stderr)
            except Exception as exc: self.show_failure(str(exc))
            finally: worker.deleteLater()
        def show_failure(self,message):
            self.failure=message; self.apply.setEnabled(False)
            self.view.summary.setText('Preview Changes could not be planned. No images were changed.\n'+message+'\nCancel and review a fresh plan.')
            print('Preview Changes: '+message,file=sys.stderr)
        def accept(self):
            if self.worker or not self.apply.isEnabled(): return
            try: verify_plan(self.plan)
            except Exception as exc: self.show_failure(str(exc)); return
            super().accept()
        def reject(self):
            if self.worker: self.closing=True; self.worker.requestInterruption(); self.apply.setEnabled(False); return
            super().reject()
        def closeEvent(self,event):
            if self.worker: self.reject(); event.ignore()
            else: event.accept()
    return PreviewView,PlanWorker,PreviewDialog


def main():
    command,path,*args=sys.argv[1:]
    if command=='is-psd':
        with inspection_path(path) as (_,fd): return 0 if os.read(fd,4)==b'8BPS' else 1
    if command=='conversion-check':
        frames,apng,webp,fmt,policy,ext,scan,optimize,bmp=args
        print(conversion_rules(path,int(frames),apng=='true',webp=='true',
              dict(format=fmt,policy=policy,jpeg_scan=scan,jpeg_optimize=optimize,bmp5=bmp),ext))
        return 0
    if command=='spec':
        operation,policy,*pairs=args
        values=Path(path+'.inputs').read_bytes().decode().split('\0')[:-1]
        Path(path).write_text(json.dumps(dict(operation=operation,policy=policy,files=values[::2],seeds=values[1::2],config=dict(zip(pairs[::2],pairs[1::2])))))
    elif command=='confirm':
        from PySide6.QtWidgets import QApplication,QDialog
        app=QApplication(sys.argv[:1]); dialog=qt_classes()[2](json.loads(Path(path).read_text()))
        if dialog.exec()!=QDialog.Accepted: return 125 if dialog.failure is not None else 130
        save_plan(path+'.approved',dialog.plan)
    else:
        plan=json.loads(Path(path).read_text())
        if command=='verify': verify_plan(plan)
        elif command=='guard':
            if plan.get('operation') == 'location':
                from kim_location import verify_dependencies
                verify_dependencies(plan)
            target=absolute(args[0]); entry=next(e for e in plan['entries'] if e.get('target')==target); verify_entry(entry)
        elif command in ('target','args','state','date'):
            source=absolute(args[0]); entry=next(e for e in plan['entries'] if e['source']==source)
            if command=='target': print(entry['target'])
            elif command=='state': print(entry['status'])
            else:
                values=entry['args'] if command=='args' else ([str(entry['date_result']['epoch_ns'])] if 'epoch_ns' in entry['date_result'] else entry['args'])
                sys.stdout.buffer.write(b''.join(v.encode()+b'\0' for v in values))
    return 0


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc: print('Preview Changes: '+str(exc),file=sys.stderr); raise SystemExit(1)
