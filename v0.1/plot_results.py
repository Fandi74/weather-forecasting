"""Regenerate publication figures from the anonymous CSVs and defined metrics."""
import csv
import json
import math
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.matplotlib_cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def rows(name):
    with (ROOT/name).open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def main():
    output=ROOT/'graphs';output.mkdir(exist_ok=True)
    points=rows('data/point_forecasts.csv')
    windows=rows('data/window_forecasts.csv')
    pairs=rows('data/point_evaluation.csv')
    scores=json.loads((ROOT/'results/metrics.json').read_text(encoding='utf-8'))
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,3,figsize=(16,9))
    fig.subplots_adjust(left=.065,right=.98,top=.84,bottom=.14,wspace=.28,hspace=.4)
    fig.suptitle('Hybrid weather model v0.1: anonymous forecast comparison',fontsize=19,y=.96)
    fig.text(.5,.9,'Retrospective example. Point values at window end; rainfall is a whole-window total.',ha='center',color='#536778')
    for i,site in enumerate(['Site A','Site B']):
        sample=[r for r in points if r['site']==site and int(r['lead_hours'])<=24]
        lead=[int(r['lead_hours']) for r in sample]
        axes[i,0].plot(lead,[float(r['temperature_c']) for r in sample],color='#2464b4',label='v0.1; baseline retained')
        axes[i,0].set_title(site+' - temperature');axes[i,0].set_ylabel('Temperature (C)')
        axes[i,1].plot(lead,[float(r['baseline_humidity_pct']) for r in sample],color='#9ca7b4',linestyle='--',label='Statistical baseline')
        axes[i,1].plot(lead,[float(r['humidity_pct']) for r in sample],color='#238d64',label='v0.1 humidity')
        axes[i,1].set_title(site+' - humidity');axes[i,1].set_ylabel('Relative humidity (%)')
        for j in [0,1]:
            axes[i,j].set_xlabel('Forecast lead (hours)');axes[i,j].grid(alpha=.2)
            if i==0:axes[i,j].legend(fontsize=8)
        rain=[r for r in windows if r['site']==site]
        lookup={int(r['lead_hours']):r for r in points if r['site']==site}
        baseline=[sum(float(lookup[k]['baseline_rain_mm']) for k in range(1,int(r['horizon'])+1)) for r in rain]
        axes[i,2].bar([k-.18 for k in range(4)],baseline,width=.36,color='#9ca7b4',label='Hourly baseline summed')
        axes[i,2].bar([k+.18 for k in range(4)],[float(r['rainfall_mm']) for r in rain],width=.36,color='#df7c21',label='v0.1 rain window')
        axes[i,2].set_xticks(range(4),[r['horizon'] for r in rain])
        axes[i,2].set_title(site+' - rainfall');axes[i,2].set_xlabel('Window (hours)')
        axes[i,2].set_ylabel('Rain (mm over whole window)');axes[i,2].grid(axis='y',alpha=.2)
        if i==0:axes[i,2].legend(fontsize=8)
    fig.text(.065,.045,'These are prediction comparisons, not accuracy scores. Rainfall is experimental; overlapping windows must not be added.',color='#536778')
    fig.savefig(output/'forecast_comparison.png',dpi=160,facecolor='white');plt.close(fig)

    fig,axes=plt.subplots(2,1,figsize=(14,8),sharex=True)
    fig.subplots_adjust(top=.85,bottom=.13,hspace=.28)
    fig.suptitle('Site A: observations and v0.1 predictions',fontsize=19,y=.96)
    fig.text(.5,.905,'84 paired observations; retrospective diagnostic, not a new blind test.',ha='center',color='#536778')
    lead=[int(r['lead_hours']) for r in pairs]
    for ax,actual,predicted,label in [(axes[0],'observed_temperature_c','predicted_temperature_c','Temperature (C)'),
        (axes[1],'observed_humidity_pct','predicted_humidity_pct','Humidity (%)')]:
        ax.plot(lead,[float(r[actual]) for r in pairs],color='#202f3d',label='Observed',linewidth=1.8)
        ax.plot(lead,[float(r[predicted]) for r in pairs],color='#2464b4',label='v0.1',linewidth=1.6)
        ax.set_ylabel(label);ax.grid(alpha=.2)
    axes[1].plot(lead,[float(r['baseline_humidity_pct']) for r in pairs],color='#9ca7b4',linestyle='--',label='Statistical baseline')
    axes[0].legend(loc='best');axes[1].legend(loc='best');axes[1].set_xlabel('Forecast lead (hours)')
    fig.text(.10,.03,'Temperature reference averages two sensors; humidity uses the dedicated humidity sensor. No original device labels are shown.',color='#536778',fontsize=9)
    fig.savefig(output/'observations_vs_predictions.png',dpi=160,facecolor='white');plt.close(fig)

    pm=scores['point_evaluation'];rs=scores['rainfall_development']
    fig,axes=plt.subplots(1,2,figsize=(14,6))
    fig.subplots_adjust(top=.74,bottom=.26,wspace=.3)
    fig.suptitle('Explicit percentage metrics for distinct forecast tasks',fontsize=18,y=.96)
    fig.text(.5,.875,'Different tasks and evaluation samples: these percentages are not an overall model score.',ha='center',fontsize=10,color='#536778')
    left=[pm['temperature']['within_tolerance_pct'],pm['humidity']['within_tolerance_pct']]
    bars=axes[0].bar(['Temperature\nwithin 1 C','Humidity\nwithin 5 percentage points'],left,color=['#2464b4','#238d64'],width=.55)
    axes[0].set_title('Site A: 84 paired observations');axes[0].set_ylabel('Predictions within tolerance (%)')
    for bar,p in zip(bars,left):axes[0].text(bar.get_x()+bar.get_width()/2,p+2,f'{p:.1f}%',ha='center')
    one=[r for r in rs if r['horizon']==1]
    bars=axes[1].bar([r['site'] for r in one],[r['balanced_accuracy_pct'] for r in one],color=['#8b3fb0','#df7c21'],width=.55)
    axes[1].set_title('One-hour rain: earlier development replay');axes[1].set_ylabel('Rain occurrence balanced accuracy (%)')
    axes[1].axhline(50,color='#8a959f',linestyle='--',linewidth=1)
    for bar,r in zip(bars,one):
        axes[1].text(bar.get_x()+bar.get_width()/2,r['balanced_accuracy_pct']+2,f"{r['balanced_accuracy_pct']:.1f}%",ha='center')
        axes[1].text(bar.get_x()+bar.get_width()/2,5,f"n={r['n']}\nwet={r['wet_cases']}, dry={r['dry_cases']}",ha='center',fontsize=9,color='white')
    for ax in axes:ax.set_ylim(0,100);ax.grid(axis='y',alpha=.2)
    fig.text(.07,.075,'Rain event: window total >= 0.28 mm; decision threshold p >= 0.5. Rain scores use prior chronological refits,\nnot a new test of the exported final model. Dry-period prevalence makes ordinary accuracy misleading.',fontsize=10,color='#536778')
    fig.savefig(output/'percentage_accuracy.png',dpi=160,facecolor='white');plt.close(fig)

    fig,axes=plt.subplots(4,2,figsize=(16,14),sharex=True)
    fig.subplots_adjust(top=.91,bottom=.09,hspace=.32,wspace=.2)
    fig.suptitle('v0.1: seven-day anonymous point forecasts',fontsize=20,y=.97)
    for i,site in enumerate(['Site A','Site B','Site C','Site D']):
        sample=[r for r in points if r['site']==site]
        lead=[int(r['lead_hours']) for r in sample]
        for j,key,label,c in [(0,'temperature_c','Temperature (C)','#2464b4'),(1,'humidity_pct','Humidity (%)','#238d64')]:
            axes[i,j].plot(lead,[float(r[key]) for r in sample],color=c,linewidth=1.5)
            axes[i,j].set_title(site+' - '+label);axes[i,j].set_ylabel(label);axes[i,j].grid(alpha=.2)
            axes[i,j].set_xticks([24,48,72,96,120,144,168])
    axes[-1,0].set_xlabel('Forecast lead (hours)');axes[-1,1].set_xlabel('Forecast lead (hours)')
    fig.text(.07,.025,'Anonymized demonstration only. Humidity ensemble support is limited to Site A; other sites retain baseline/fallback behavior.',fontsize=10,color='#536778')
    fig.savefig(output/'seven_day_forecast.png',dpi=150,facecolor='white');plt.close(fig)

    fig,axes=plt.subplots(2,2,figsize=(14,9))
    fig.subplots_adjust(top=.84,bottom=.13,hspace=.34,wspace=.24)
    fig.suptitle('Rainfall development diagnostics: full window comparison',fontsize=18,y=.96)
    fig.text(.5,.9,'Chronological rolling-fit development evidence; not a fresh benchmark of exported final weights.',ha='center',color='#536778',fontsize=10)
    for i,site in enumerate(['Site A','Site B']):
        subset=[r for r in rs if r['site']==site];x=list(range(4))
        axes[i,0].plot(x,[r['balanced_accuracy_pct'] for r in subset],marker='o',color='#8b3fb0')
        axes[i,0].axhline(50,color='#9ca7b4',linestyle='--');axes[i,0].set_ylim(0,100)
        axes[i,0].set_title(site+' - occurrence');axes[i,0].set_ylabel('Balanced accuracy (%)')
        axes[i,1].bar([k-.18 for k in x],[r['raw_weather_rmse_mm'] for r in subset],width=.36,color='#9ca7b4',label='Raw weather forecast')
        axes[i,1].bar([k+.18 for k in x],[r['amount_rmse_mm'] for r in subset],width=.36,color='#df7c21',label='Selected rainfall method')
        axes[i,1].set_title(site+' - amount');axes[i,1].set_ylabel('RMSE (mm over window)')
        axes[i,1].legend(fontsize=8)
        for ax in axes[i]:
            ax.set_xticks(x,['1','6','12','24']);ax.set_xlabel('Forecast window (hours)');ax.grid(axis='y',alpha=.2)
    fig.text(.075,.035,'Lower amount RMSE is better. Rain amount has not consistently improved over raw weather forecasts. Samples/windows overlap.',color='#536778',fontsize=10)
    fig.savefig(output/'rainfall_development_comparison.png',dpi=160,facecolor='white');plt.close(fig)

if __name__=='__main__':main()
