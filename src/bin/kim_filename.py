"""Filename-only transformations shared by Recipes and standalone preview/apply."""
DATE_FORMATS={'compact':'%Y%m%d_%H%M%S','iso':'%Y-%m-%d_%H-%M-%S','day_first':'%Y-%d-%m_%H-%M-%S','camera':'IMG-%Y%m%d_%H%M%S'}


def transform(name, step, index=1, capture=None):
    method,value=step['method'],step.get('value','')
    if method=='lowercase': return name.lower()
    if method=='uppercase': return name.upper()
    if method in ('spaces_to_dashes','spaces_to_underscores','underscores_to_spaces','dashes_to_spaces'):
        old,new={'spaces_to_dashes':(' ','-'),'spaces_to_underscores':(' ','_'),'underscores_to_spaces':('_',' '),'dashes_to_spaces':('-',' ')}[method]
        return name.replace(old,new)
    if method=='prefix': return value+name
    if method=='suffix': return name+value
    if method=='replace':
        if not value: raise ValueError('Enter the filename text to replace.')
        return name.replace(value,step['replacement'])
    if method=='sequential': return value+str(step['start']+index-1).zfill(step['padding'])
    if method=='capture_date':
        if capture is None: raise ValueError('The output name needs a capture date. Add Set Capture Date before Change Output Filename.')
        if value not in ('',*DATE_FORMATS): raise ValueError('Date filename style must be compact, iso, day_first or camera.')
        return capture.strftime(DATE_FORMATS[value or 'compact'])
    raise ValueError('Unknown filename method')


METHODS={'addprefix':'prefix','addsuffix':'suffix','overwrite':'replace','spacestodash':'spaces_to_dashes',
         'spacestounderscore':'spaces_to_underscores','underscorestospace':'underscores_to_spaces','dashestospace':'dashes_to_spaces'}


def standalone(name,method,value,replacement,start,padding):
    return transform(name,dict(method=METHODS.get(method,method),value=value,replacement=replacement,start=int(start),padding=int(padding)))


if __name__=='__main__':
    import sys
    print(standalone(*sys.argv[1:]))
