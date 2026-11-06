"""Show exact point-component preservation and the direct rain windows."""
import datetime as dt
import os
from pathlib import Path

def render(output, hourly, merged):
    os.environ.setdefault('MPLCONFIGDIR',str(output/'.matplotlib_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as dates
    wib = dt.timezone(dt.timedelta(hours=7))
    fig,axes = plt.subplots(2,3,figsize=(16,9))
    fig.subplots_adjust(left=.065,right=.98,top=.84,bottom=.14,wspace=.28,hspace=.40)
    fig.suptitle('V7 combines V5 humidity with V6 rainfall',fontsize=20,y=.96)
    fig.text(.5,.90,'Same 3 November issue. Point values at window end; rain is a whole-window total.',ha='center',fontsize=11,color='#536778')
    for i,station in enumerate(['X50','X66']):
        sample = [r for r in hourly if r['station']==station and 0<r['time']-r['issue']<=24*3600]
        times = [dt.datetime.fromtimestamp(r['time'],wib) for r in sample]
        for j,(key,label,color) in enumerate([('selected_t','Temperature (C)','#2464b4'),('selected_h','Humidity (%)','#238d64')]):
            values = [r[key] for r in sample]
            axes[i,j].plot(times,values,color='#9ca7b4',linewidth=4,alpha=.6,label='V5 source')
            axes[i,j].plot(times,values,color=color,linestyle='--',linewidth=1.8,label='V7 (identical)')
            axes[i,j].set_title(station+' - '+label)
            axes[i,j].xaxis.set_major_locator(dates.HourLocator(byhour=[0,6,12,18],tz=wib))
            axes[i,j].xaxis.set_major_formatter(dates.DateFormatter('%d %b\n%H:%M',tz=wib))
            axes[i,j].set_ylabel(label)
            axes[i,j].grid(alpha=.2)
            if i==0: axes[i,j].legend(fontsize=8,loc='best')
        rain = [r for r in merged if r['station']==station]
        source = {r['time']:r for r in hourly if r['station']==station}
        old = [sum(source[r['issue']+k*3600]['selected_rain'] for k in range(1,r['horizon']+1)) for r in rain]
        axes[i,2].bar([k-.18 for k in range(4)],old,width=.36,color='#9ca7b4',label='V5 hourly amounts summed')
        axes[i,2].bar([k+.18 for k in range(4)],[r['rainfall_mm'] for r in rain],width=.36,color='#df7c21',label='V7 / V6 rain component')
        axes[i,2].set_xticks(range(4),['1','6','12','24'])
        axes[i,2].set_xlabel('Forecast window (hours)')
        axes[i,2].set_ylabel('Rain (mm over whole window)')
        axes[i,2].set_title(station+' - rainfall')
        axes[i,2].grid(axis='y',alpha=.2)
        if i==0: axes[i,2].legend(fontsize=8)
    fig.text(.065,.045,'Rain forecasts remain experimental. This is a component comparison, not a new accuracy test. All times WIB (UTC+7).',fontsize=10,color='#536778')
    fig.savefig(output/'V7_merged_forecasts.png',dpi=160,facecolor='white')
    plt.close(fig)
