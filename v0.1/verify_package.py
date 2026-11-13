"""Verify public package hashes, privacy patterns and percentage calculations offline."""
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from metrics import continuous,rain_event,rmse

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent

def rows(relative):
    with (ROOT/relative).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))

def privacy_structure():
    checks={
        'device_identifier':r'(?i)\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b',
        'legacy_site_label':r'(?i)X\d{2,}',
        'personal_home_path':r'(?i)[A-Z]:[\\/]Users[\\/]',
        'network_address':r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])',
        'sensitive_json_key':r'"(?:device_id|expected_device_id|latitude|longitude|elevation_m|ip_address)"\s*:'
    }
    findings=[]
    for p in BASE.rglob('*'):
        if not p.is_file() or {'__pycache__','.matplotlib_cache','.venv'}.intersection(p.parts):continue
        if p.suffix.lower() in ['.zip','.cbm','.pkl','.pickle']:
            findings.append({'file':p.relative_to(BASE).as_posix(),'category':'excluded_archive_or_binary'})
        if p.suffix.lower() not in ['.md','.py','.json','.csv','.txt']:continue
        text=p.read_text(encoding='utf-8')
        for category,pattern in checks.items():
            if re.search(pattern,text):findings.append({'file':p.relative_to(BASE).as_posix(),'category':category})
    return findings

def verify():
    manifest=json.loads((BASE/'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    for path,expected in manifest['files_sha256'].items():
        if hashlib.sha256((BASE/path).read_bytes()).hexdigest()!=expected:
            raise ValueError('Published file hash differs: '+path)
    findings=privacy_structure()
    if findings:raise ValueError('Structural privacy scan failed: '+json.dumps(findings))
    saved=json.loads((ROOT/'results/metrics.json').read_text(encoding='utf-8'))
    pairs=rows('data/point_evaluation.csv')
    for variable,tolerance in [('temperature',1),('humidity',5)]:
        a=[float(r['observed_'+variable+('_c' if variable=='temperature' else '_pct')]) for r in pairs]
        p=[float(r['predicted_'+variable+('_c' if variable=='temperature' else '_pct')]) for r in pairs]
        score=continuous(a,p,tolerance)
        for key,value in score.items():
            if not math.isclose(value,saved['point_evaluation'][variable][key],abs_tol=1e-12,rel_tol=1e-12):
                raise ValueError('Point metric differs: '+variable+'/'+key)
    cases=rows('data/rainfall_development.csv')
    for score in saved['rainfall_development']:
        subset=[r for r in cases if r['site']==score['site'] and int(r['horizon'])==score['horizon']]
        value=rain_event([float(r['observed_rain_mm']) for r in subset],[float(r['rain_probability']) for r in subset])
        for key,expected in value.items():
            actual=score[key]
            if expected is None:
                if actual is not None:raise ValueError('Unsupported metric differs')
            elif not math.isclose(float(expected),float(actual),abs_tol=1e-12,rel_tol=1e-12):
                raise ValueError('Rain metric differs: '+key)
    return {'version':'0.1','package_files_verified':len(manifest['files_sha256']),
        'structural_privacy_findings':0,'point_diagnostic_pairs':len(pairs),
        'rainfall_development_cases':len(cases),'percentage_metrics_reproduced':True}

if __name__=='__main__':print(json.dumps(verify(),indent=2))
