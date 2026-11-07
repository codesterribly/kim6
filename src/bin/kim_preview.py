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
from kim_process import run_process, inspection_context, checkpoint


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
                             'Removes descriptive EXIF, IPTC, XMP and comments, including image capture dates and rights. Keeps ICC and orientation. Signed Content Credentials may remain.')
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
    if matching==0 and other==0:
        entry['status']='skip'
        entry['skip_reason']='No matching removable PNG metadata.'
    entry['rows'].append([Path(entry['source']).name,'PNG container text / ancillary metadata',
                          f'{matching} matching text / EXIF blocks; {other} other removable chunks',
                          'Apply native '+mode+' filter','Container filter; image data, ICC and presentation chunks preserved'])
    if mode=='ai':
        for row in entry['rows']:
            if row[1]=='Other descriptive metadata': row[3]='Preserve recognized image text metadata; filter unclassified PNG metadata'; row[4]='Native PNG filtering'
        entry['warnings'].append('PNG AI removal also removes unclassified text and unknown ancillary chunks; recognized ordinary image text metadata is preserved. Mixed AI/image text or unknown XML may block safe filtering.')


def date_plan(entry, config):
    from kim_date_tools import resolve

    if (
        config.get('kind') in (
            'reference-to-exif',
            'reference-to-file',
        )
        and entry['source'] == config.get('reference_path')
    ):
        entry['status'] = 'skip'
        entry['skip_reason'] = 'Reference image, unchanged.'
        entry['rows'] = [[
            Path(entry['source']).name,
            'Reference',
            '',
            '',
            'Unchanged',
        ]]
        return
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
    entry['warnings'].append(
        'Camera clocks keep the selected timezone interpretation. File Modification Date is preserved.'
        if 'epoch_ns' not in result else
        'Sets only the entered File Modification Date; embedded dates are unchanged.'
        if config['kind'] == 'set-file' else
        'Changes only the File Modification Date; the capture clock requires a known timezone.'
    )


def format_class(fmt):
    fmt=fmt.upper()
    if re.match(r'^PNG[0-9]',fmt): return 'PNG'
    for canonical,aliases in {'JPEG':('JPG','JPE','JFIF','JPS','PJPEG'), 'TIFF':('TIF','TIFF64','PTIF'),
                             'PNG':('APNG','PNG8','PNG24','PNG32','PNG48','PNG64'), 'BMP':('BMP2','BMP3','DIB'),
                             'GIF':('GIF87',),'JP2':('J2C','J2K','JPC','JPM','JPT'),'HEIC':('HEIF',)}.items():
        if fmt in aliases: return canonical
    return fmt


class InapplicableConversion(ValueError):
    """Valid input, but the requested conversion cannot preserve content."""


def conversion_rules(input_format,frames,apng,webp_animation,config,extension):
    """The standalone encoder and its preview share these exact refusals/no-op rules.

    Header inspection supplies facts; pixel decoding and output verification
    remain in the established encoder after confirmation.
    """
    fmt=config['format'].lower(); source=format_class(input_format)
    if source in ('EXR','HDR') and input_format.upper()!=fmt.upper():
        raise InapplicableConversion('HDR / OpenEXR requires explicit tone mapping before conversion.')
    if apng and fmt!='apng': raise InapplicableConversion('Animated PNG requires APNG output to preserve playback.')
    if frames>1 and fmt not in ('gif','tif','tiff','tiff64','webp','avif','heic','heif','apng','pdf','ico','cur'):
        raise InapplicableConversion('Requested format cannot preserve this multi-frame input.')
    # Same-format conversion without explicit processing is unnecessary.
    # Keep processing if the extension does not describe the actual format.
    if (source==format_class(fmt) and format_class(extension)==source and
        not config.get('jpeg_scan') and
        config.get('jpeg_optimize')!='true' and
        config.get('bmp5')!='true' and
        config.get('strip_metadata') not in ('true', True) and
        not (fmt in ('jp2','jxl','heic','heif') and config.get('jp2_mode'))):
        return 'skip'
    if frames>1 and not apng:
        if source=='GIF' and fmt not in ('gif','apng'): raise InapplicableConversion('Animated GIF playback is not verified for this output format.')
        if source=='WEBP' and fmt!='webp': raise InapplicableConversion('Animated WebP playback cannot be preserved in this format.')
        if source in ('AVIF','HEIC'): raise InapplicableConversion('Multi-image AVIF/HEIC sequences cannot safely be re-encoded.')
        if source not in ('GIF','WEBP','AVIF','HEIC') and fmt in ('gif','gif87','webp','apng','avif','heic','heif'):
            raise InapplicableConversion('Multipage images cannot safely be converted to animated formats.')
    if frames==1 and source=='WEBP' and webp_animation and fmt!='webp':
        raise InapplicableConversion('Animated WebP requires WebP output to preserve playback.')
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
        entry['input_format']=input_format
        entry['psd']=psd
        entry['status']=conversion_rules(input_format,frames,animated and format_class(input_format)=='PNG',
                                         animated and format_class(input_format)=='WEBP',config,ext[1:])
    if entry['status']=='skip':
        entry['skip_reason']='Already '+format_class(input_format)+'; no conversion required.'
        return
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
                        if used!='DateTimeOriginal': entry['warnings'].append('No image capture date; existing rename behavior uses '+used+'.')
                    else: name=standalone(stem,method,config.get('value',''),config.get('replacement',''),number[0],number[2])
                    if not name or name in ('.','..') or any(c in name for c in '/\n\r'):
                        raise ValueError('Enter a filename without slashes or line breaks.')
                    directory=config.get('directory') or str(Path(source).parent)
                    if not Path(directory).is_absolute(): raise ValueError('Choose an absolute destination directory.')
                    candidate=str(Path(directory)/(name+ext))
                    unchanged=(
                        method in (
                            'lowercase','uppercase','spacestodash',
                            'spacestounderscore','underscorestospace',
                            'dashestospace','overwrite'
                        )
                        and absolute(candidate)==source
                    )
                    if unchanged:
                        entry['status']='skip'
                        entry['skip_reason']='Filename already satisfies this rename.'
                        target=source
                        reserved.add(source)
                    else:
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
                    elif operation=='convert':
                        try:
                            conversion_plan(entry,config,registry)
                        except InapplicableConversion as exc:
                            entry['status']='skip'
                            entry['skip_reason']=str(exc)
                            entry['input_format']=entry.get('input_format','Image')
                    else: raise ValueError('Unsupported preview operation')
                    candidate=seeds[index] if seeds else source
                    effective='create' if entry.get('psd') else policy
                    if entry['status']=='skip':
                        target=source
                        reserved.add(source)
                    else:
                        target=allocate(source,candidate,effective,reserved,'_' if operation=='convert' else '-')
                    finish_entry(entry,target,effective)
                    if entry['status']!='skip' and target!=absolute(candidate):
                        entry['warnings'].append('Filename collision: the displayed filename includes planned collision numbering.')
                    if operation=='convert':
                        skipped=entry['status']=='skip'
                        entry['rows']=[[
                            Path(source).name,
                            '(no output)' if skipped else Path(target).name,
                            '' if skipped else str(Path(target).parent),
                            entry.get('skip_reason',entry['input_format']+' → '+config['format'].upper()) if skipped else entry['input_format']+' → '+config['format'].upper(),
                            'Skipped' if skipped else ('Replace file' if entry['publication']=='overwrite' else 'Create file')
                        ]]
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
    config = plan.get('config') or {}

    if config.get('kind') in (
        'reference-to-exif',
        'reference-to-file',
    ):
        reference = config.get('reference_path')

        if not reference or not any(
            entry['source'] == reference
            for entry in plan['entries']
        ):
            raise ValueError(
                'Reference must be one of the selected images.'
            )

        if identity(reference) != config.get('reference_identity'):
            raise ValueError(
                'Reference image changed after preview. '
                'Review again.'
            )

    if not plan['entries']: raise ValueError('No selected images.')
    if plan.get('operation') == 'location':
        from kim_location import verify_dependencies
        verify_dependencies(plan)
    for entry in plan['entries']: verify_entry(entry)


def save_plan(path,plan):
    verify_plan(plan); Path(path).write_text(json.dumps(plan,ensure_ascii=True))


# Lazy Qt imports keep publication guards usable without constructing a GUI.
@lru_cache(maxsize=1)
def review_row_style(table, row, skipped):
    """Give skipped rows a palette-derived muted appearance."""
    if not skipped:
        return

    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QBrush, QPalette

    palette = QApplication.palette()

    foreground = QBrush(
        palette.color(QPalette.Disabled, QPalette.Text)
    )

    background = QBrush(
        palette.color(QPalette.AlternateBase)
    )

    for column in range(table.columnCount()):
        item = table.item(row, column)

        if item is not None:
            item.setForeground(foreground)
            item.setBackground(background)


def review_icon(image, skipped):
    from PySide6.QtGui import QIcon, QPixmap, QPainter
    from PySide6.QtCore import Qt

    pixmap = QPixmap.fromImage(image)

    if not skipped:
        return QIcon(pixmap)

    result = QPixmap(pixmap.size())
    result.fill(Qt.transparent)

    painter = QPainter(result)
    painter.setOpacity(0.45)
    painter.drawPixmap(0, 0, pixmap)
    painter.end()

    return QIcon(result)


def fit_review_table(table, maximum_rows=6):
    """Fit small selections, scroll larger selections."""
    count = min(table.rowCount(), maximum_rows)

    height = (
        table.horizontalHeader().height()
        + 2 * table.frameWidth()
        + 12
        + sum(
            table.rowHeight(row)
            for row in range(count)
        )
    )

    table.setFixedHeight(max(94, height))
    return table.height()


def format_plan_row(entry, mode):
    """Summarize each inspected metadata operation."""
    status = entry['status']

    if status == 'error':
        return [
            Path(entry['source']).name,
            'Inspection failed',
            entry.get('error', 'Cannot inspect'),
            'Blocked',
        ]

    category = {
        'gps': 'Recognized GPS coordinates',
        'ai': 'Recognized AI fields',
    }.get(mode)

    matches = [
        row for row in entry['rows']
        if len(row) > 2 and row[1] == category
    ]

    evidence = (
        matches[0][2]
        if matches
        else 'Descriptive / container metadata'
    )

    if status == 'skip':
        evidence = 'None requiring removal'

    operation = {
        'gps': 'recognized GPS coordinates',
        'ai': 'recognized AI fields',
        'all': 'descriptive metadata',
    }[mode]

    return [
        Path(entry['source']).name,
        evidence,
        (
            'Remove ' + operation
            if status == 'change'
            else entry.get('skip_reason', 'No change')
        ),
        'Ready' if status == 'change' else 'Skipped',
    ]


def qt_classes():
    from PySide6.QtCore import QThread,Signal,Qt,QSize,QTimer
    from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
                                  QDialog,QApplication,QComboBox,QPushButton)

    from PySide6.QtGui import QPixmap, QIcon

    class PreviewView(QWidget):
        def __init__(self,parent=None):
            super().__init__(parent); layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
            self.summary=QLabel('Inspecting selected images…'); self.summary.setTextFormat(Qt.PlainText); self.summary.setWordWrap(True); layout.addWidget(self.summary)
            self.table=QTableWidget(0,5); self.table.setWordWrap(False); self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel); self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(self.table)
            self.table.setIconSize(QSize(84, 64))

            self._thumbnail_jobs = []
            self._thumbnail_timer = QTimer(self)
            self._thumbnail_timer.setInterval(0)
            self._thumbnail_timer.timeout.connect(
                self.load_next_thumbnail
            )


        def load_next_thumbnail(self):
            """Fill filename cells without modifying source images."""
            if not self._thumbnail_jobs:
                self._thumbnail_timer.stop()
                return

            row, path, skipped = self._thumbnail_jobs.pop(0)
            item = self.table.item(row, 0)

            if item is None:
                return

            try:
                from kim_photo_selection import read_thumbnail

                image, _stamp = read_thumbnail(
                    path,
                    QSize(84, 64)
                )

                if image.isNull():
                    raise ValueError('No preview decoder')

                item.setIcon(
                    review_icon(image, skipped)
                )

            except Exception as exc:
                # An unavailable decoder does not invalidate a
                # separately verified conversion plan.
                item.setToolTip(
                    item.toolTip()
                    + '\nPreview unavailable: '
                    + str(exc)
                )

        def show_plan(self, plan):
            self.plan = plan
            self._thumbnail_timer.stop()
            self._thumbnail_jobs.clear()

            operation = plan['operation']
            entries = plan['entries']

            ready = sum(
                e['status'] == 'change' for e in entries
            )
            skipped = sum(
                e['status'] == 'skip' for e in entries
            )
            blocked = sum(
                e['status'] == 'error' for e in entries
            )
            warnings = sum(
                bool(e['warnings']) for e in entries
            )

            labels = {
                'rename': 'Rename Images',
                'convert': 'Convert Format',
                'copyright': 'Set Creator and Copyright',
                'strip': 'Remove Metadata',
                'date': 'Image Capture Dates',
                'location': 'Image Location Tools',
            }

            name = labels[operation]

            if operation == 'location':
                from kim_location import TITLES
                name = TITLES[plan['config']['kind']]

            elif operation == 'date':
                name = {
                    'set': 'Set Image Capture Date',
                    'shift': 'Adjust Image Capture Date',
                    'exif-to-file': 'Set File Date from Image Capture Date',
                    'file-to-exif': 'Set Image Capture Date',
                    'set-file': 'Set File Modification Date',
                    'reference-to-exif': 'Set Image Capture Date',
                    'reference-to-file': 'Set File Modification Date',
                }[plan['config']['kind']]

            elif operation == 'convert':
                name += ' — ' + plan['config']['format'].upper()

            elif operation == 'strip':
                name += ' — ' + {
                    'gps': 'Remove GPS Coordinates',
                    'ai': 'Remove AI Metadata',
                    'all': 'Remove Descriptive Metadata',
                }[plan['config']['mode']]

            if plan['policy'] == 'create':
                policy = (
                    'Create renamed copies'
                    if operation == 'rename'
                    else 'Create new files (originals untouched)'
                )
            else:
                policy = (
                    'Rename selected originals'
                    if operation == 'rename'
                    else 'Explicitly approved replacement'
                )

            summary = (
                f'{name} — {policy}\n'
                f'Selected: {plan["total"]}   '
                f'Ready: {ready}   '
                f'Skipped: {skipped}   '
                f'Warnings: {warnings}   '
                f'Blocked: {blocked}'
            )

            if not ready and not blocked:
                summary += (
                    '\nNo selected files require this operation.'
                )

            self.summary.setText(summary)

            if operation == 'rename':
                headings = (
                    'Current filename',
                    'Proposed filename',
                    'Destination directory',
                    'Status',
                )

            elif operation == 'convert':
                headings = (
                    'Image / filename',
                    'Proposed filename',
                    'Destination directory',
                    'Planned transformation',
                    'Status',
                )

            elif operation == 'strip':
                headings = (
                    'Image / filename',
                    'Recognized metadata',
                    'Planned operation',
                    'Status',
                )

            else:
                headings = (
                    'Current filename',
                    'Field or category',
                    'Current value',
                    'Proposed change',
                    'Status' if operation == 'date' else 'Status / warnings',
                )

            self.table.setColumnCount(len(headings))
            self.table.setHorizontalHeaderLabels(headings)

            self.table.setRowCount(
                len(entries)
                if operation == 'strip'
                else sum(
                    len(entry['rows'])
                    for entry in entries
                )
            )

            header = self.table.horizontalHeader()
            header.setStretchLastSection(False)
            header.setMinimumSectionSize(72)
            header.setResizeContentsPrecision(40)

            # Give filenames the remaining space while allowing
            # users to resize the substantive review columns.
            for column in range(len(headings)):
                header.setSectionResizeMode(
                    column, QHeaderView.Interactive
                )

            header.setSectionResizeMode(
                0, QHeaderView.Stretch
            )

            if operation == 'rename':
                self.table.setColumnWidth(1, 230)
                self.table.setColumnWidth(2, 210)
            elif operation == 'convert':
                self.table.setColumnWidth(1, 210)
                self.table.setColumnWidth(2, 200)
                self.table.setColumnWidth(3, 190)
            elif operation == 'strip':
                self.table.setColumnWidth(1, 210)
                self.table.setColumnWidth(2, 240)
            else:
                self.table.setColumnWidth(1, 150)
                self.table.setColumnWidth(2, 190)
                self.table.setColumnWidth(3, 230)

            header.setSectionResizeMode(
                len(headings) - 1,
                QHeaderView.ResizeToContents
            )

            row = 0

            for entry in entries:
                status = entry['status']

                status_label = {
                    'change': 'Ready',
                    'skip': 'Skipped',
                    'error': 'Blocked',
                }[status]

                tooltip = '\n'.join(filter(None, [
                    entry['source'],
                    entry.get('error', ''),
                    entry.get('skip_reason', ''),
                    *entry['warnings'],
                    *(
                        ' | '.join(
                            str(value)
                            for value in values
                        )
                        for values in entry['rows']
                    ),
                ]))

                if operation == 'strip':
                    rows = [
                        format_plan_row(
                            entry,
                            plan['config']['mode'],
                        )
                    ]

                elif operation == 'rename':
                    rows = [
                        [
                            values[0],
                            values[1],
                            values[2],
                            status_label,
                        ]
                        for values in entry['rows']
                    ]

                elif operation == 'convert':
                    rows = [
                        [
                            values[0],
                            values[1],
                            values[2],
                            values[3],
                            status_label,
                        ]
                        for values in entry['rows']
                    ]

                else:
                    rows = [
                        list(values)
                        for values in entry['rows']
                    ]

                for values in rows:
                    if (
                        operation not in (
                            'rename', 'convert', 'strip'
                        )
                        and entry['warnings']
                    ):
                        values[-1] += (
                            '\n' + '\n'.join(entry['warnings'])
                        )

                    for column, value in enumerate(values):
                        item = QTableWidgetItem(str(value))
                        item.setToolTip(tooltip)

                        self.table.setItem(
                            row, column, item
                        )

                    self.table.setRowHeight(
                        row,
                        76 if operation in (
                            'strip', 'convert'
                        ) else 30,
                    )

                    review_row_style(
                        self.table,
                        row,
                        status == 'skip',
                    )

                    if operation in ('strip', 'convert'):
                        self._thumbnail_jobs.append((
                            row,
                            entry['source'],
                            status == 'skip',
                        ))

                    row += 1

            fit_review_table(self.table)

            if self._thumbnail_jobs:
                self._thumbnail_timer.start()

            return not blocked and ready > 0

    class PlanWorker(QThread):
        progress=Signal(int,int,str)
        def __init__(self,operation,policy,files,config,seeds,parent):
            super().__init__(parent); self.arguments=(operation,policy,files,config,seeds); self.plan=None; self.error=None
        def run(self):
            try: self.plan=build_plan(*self.arguments,progress=self.progress.emit,cancelled=self.isInterruptionRequested)
            except Exception as exc: self.error=str(exc)

    class PreviewDialog(QDialog):
        def __init__(self, spec, parent=None):
            super().__init__(parent)

            self.spec = spec
            self.plan = None
            self.failure = None
            self.worker = None
            self.closing = False
            self.pending = False

            self.setWindowTitle(
                'KIM6 — Remove Metadata'
                if spec['operation'] == 'strip'
                else 'Preview Changes'
            )

            layout = QVBoxLayout(self)
            self.mode_select = None

            if spec['operation'] == 'strip':
                controls = QHBoxLayout()
                controls.addWidget(QLabel('Remove'))

                self.mode_select = QComboBox()

                for label, mode in (
                    ('Recognized GPS coordinates', 'gps'),
                    ('Recognized AI metadata', 'ai'),
                    (
                        'Descriptive metadata '
                        '(keep ICC and orientation)',
                        'all',
                    ),
                ):
                    self.mode_select.addItem(label, mode)

                selected = self.mode_select.findData(
                    spec['config']['mode']
                )
                self.mode_select.setCurrentIndex(
                    max(0, selected)
                )

                controls.addWidget(
                    self.mode_select, 1
                )
                layout.addLayout(controls)

                note = QLabel(
                    'Removes recognized metadata only. '
                    'Original pixels, ICC profiles, and '
                    'orientation are preserved. '
                    'Unrecognized location/provenance and '
                    'signed credentials may remain.'
                )
                note.setWordWrap(True)
                layout.addWidget(note)

            self.view = PreviewView()
            layout.addWidget(self.view)

            # Explicit order while keeping both buttons right-aligned.
            # Do not reverse the dialog's layout direction.
            button_row = QHBoxLayout()
            button_row.addStretch(1)

            self.apply = QPushButton('Apply Changes')
            self.apply.setEnabled(False)
            self.apply.clicked.connect(self.accept)
            button_row.addWidget(self.apply)

            cancel_button = QPushButton('Cancel')
            cancel_button.clicked.connect(self.reject)
            button_row.addWidget(cancel_button)

            layout.addLayout(button_row)

            if self.mode_select is not None:
                self.mode_select.currentIndexChanged.connect(
                    self.mode_changed
                )

            self.start_plan()

        def start_plan(self):
            self.plan = None
            self.failure = None
            self.apply.setEnabled(False)

            config = dict(self.spec['config'])
            seeds = self.spec['seeds']

            if self.mode_select is not None:
                mode = self.mode_select.currentData()
                config['mode'] = mode
                seeds = self.spec['strip_seeds'][mode]

            self.worker = PlanWorker(
                self.spec['operation'],
                self.spec['policy'],
                self.spec['files'],
                config,
                seeds,
                self,
            )

            self.worker.progress.connect(
                lambda i, n, path:
                self.view.summary.setText(
                    f'Inspecting image {i+1} of {n}: '
                    f'{Path(path).name}'
                )
            )

            self.worker.finished.connect(
                self.plan_finished
            )
            self.worker.start()

        def mode_changed(self, *_):
            self.apply.setEnabled(False)
            self.plan = None

            self.view._thumbnail_timer.stop()
            self.view._thumbnail_jobs.clear()
            self.view.table.setRowCount(0)
            self.view.summary.setText(
                'Inspecting selected images…'
            )

            if self.worker:
                self.pending = True
                self.worker.requestInterruption()
            else:
                self.start_plan()

        def plan_finished(self):
            worker, self.worker = self.worker, None

            try:
                if self.closing:
                    super().reject()

                elif self.pending:
                    self.pending = False
                    self.start_plan()

                elif worker.error:
                    self.show_failure(worker.error)

                else:
                    self.plan = worker.plan

                    self.apply.setEnabled(
                        self.view.show_plan(self.plan)
                    )

                    errors = [
                        entry['error']
                        for entry in self.plan['entries']
                        if entry['status'] == 'error'
                    ]

                    if errors:
                        self.failure = '\n'.join(errors)
                        print(
                            'Preview Changes: ' + self.failure,
                            file=sys.stderr,
                        )

                    width = (
                        990
                        if self.spec['operation'] == 'convert'
                        else 880
                        if self.mode_select
                        else 1050
                    )

                    extra = (
                        178 if self.mode_select else 125
                    )

                    self.resize(
                        width,
                        min(
                            785,
                            max(
                                245,
                                self.view.table.height() + extra,
                            ),
                        ),
                    )

            except Exception as exc:
                self.show_failure(str(exc))

            finally:
                worker.deleteLater()

        def show_failure(self, message):
            self.failure = message
            self.apply.setEnabled(False)

            self.view.summary.setText(
                'Preview Changes could not be planned. '
                'No images were changed.\n'
                + message
                + '\nCancel and review a fresh plan.'
            )

            print(
                'Preview Changes: ' + message,
                file=sys.stderr,
            )

        def accept(self):
            if self.worker or not self.apply.isEnabled():
                return

            try:
                verify_plan(self.plan)
            except Exception as exc:
                self.show_failure(str(exc))
                return

            super().accept()

        def reject(self):
            if self.worker:
                self.closing = True
                self.worker.requestInterruption()
                self.apply.setEnabled(False)
            else:
                super().reject()

        def closeEvent(self, event):
            if self.worker:
                self.reject()
                event.ignore()
            else:
                event.accept()

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
        spec=dict(operation=operation,policy=policy,files=values[::2],
                  seeds=values[1::2],config=dict(zip(pairs[::2],pairs[1::2])))
        if operation=='strip':
            spec['strip_seeds']={}
            for mode in ('gps','ai','all'):
                raw=Path(path+'.strip-'+mode+'.seeds').read_bytes().split(b'\0')[:-1]
                values=[os.fsdecode(v) for v in raw]
                if len(values)!=len(spec['files']):
                    raise ValueError('Incomplete metadata output filenames')
                spec['strip_seeds'][mode]=values
        Path(path).write_text(json.dumps(spec))
    elif command=='confirm':
        from PySide6.QtWidgets import QApplication,QDialog
        app=QApplication(sys.argv[:1]); dialog=qt_classes()[2](json.loads(Path(path).read_text()))
        if dialog.exec()!=QDialog.Accepted: return 125 if dialog.failure is not None else 130
        save_plan(path+'.approved',dialog.plan)
    else:
        plan=json.loads(Path(path).read_text())
        if command=='verify': verify_plan(plan)
        elif command=='policy': print(plan['policy'])
        elif command=='config': print(plan['config'][args[0]])
        elif command=='guard':
            if plan.get('operation') == 'location':
                from kim_location import verify_dependencies
                verify_dependencies(plan)
            target=absolute(args[0]); entry=next(e for e in plan['entries'] if e.get('target')==target); verify_entry(entry)
        elif command == 'entry':
            # One pre-item observation; publication guards still reload the plan.
            if plan.get('operation') == 'location':
                from kim_location import verify_dependencies
                verify_dependencies(plan)
            source = absolute(args[0])
            entry = next(e for e in plan['entries'] if e['source'] == source)
            verify_entry(entry)
            sys.stdout.buffer.write(b''.join(value.encode() + b'\0' for value in (entry['status'], entry['target'])))
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
