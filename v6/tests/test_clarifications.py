import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from clarification_review import TimingHistory,keep_raw_adc
from data import normalize,rain_hours,window_label
from features import History


def fixture():
    raw=[]
    for i in range(13):
        raw.append({'timestamp_ms':str((i*600+8)*1000),'rf':'0','rfc':'3','srm':str(10000-i*100),'sm':'10','rid':str(i),'error':'E3 E12'})
    records=[normalize(r) for r in raw];hours,intervals,_=rain_hours(records)
    data={'records':records,'times':[r['time'] for r in records],'hours':hours,'intervals':intervals}
    return raw,{'X50':data,'X66':data}


class ClarificationTests(unittest.TestCase):
    def test_threshold_flag_retains_raw_adc_not_sm(self):
        raw,data=fixture();raw[4].update(error='E3 E8 E11 E12',srm='3900',sm='')
        data['X66']['records'][4]=normalize(raw[4]);before=copy.deepcopy(data)
        maps={s:{int(r['timestamp_ms'])/1000:r for r in raw} for s in data}
        result=keep_raw_adc(data,maps)
        self.assertEqual(result['X66']['records'][4]['srm'],3900)
        self.assertIsNone(result['X66']['records'][4]['sm'])
        self.assertTrue(result['X66']['records'][4]['soil_ok'])
        self.assertEqual(data,before)

    def test_missing_raw_adc_stays_missing(self):
        raw,data=fixture();raw[4].update(error='E11',srm='',sm='')
        maps={s:{int(r['timestamp_ms'])/1000:r for r in raw} for s in data}
        result=keep_raw_adc(data,maps)
        self.assertIsNone(result['X50']['records'][4]['srm'])
        self.assertFalse(result['X50']['records'][4]['soil_ok'])

    def test_seven_thousand_is_not_hardcoded(self):
        raw,data=fixture();raw[4].update(error='E11',srm='6500',sm='')
        maps={s:{int(r['timestamp_ms'])/1000:r for r in raw} for s in data}
        self.assertEqual(keep_raw_adc(data,maps)['X66']['records'][4]['srm'],6500)

    def test_one_hour_reproduces_original_history(self):
        _,data=fixture()
        self.assertEqual(History(data).get('X50',10800),TimingHistory(data,3600).get('X50',10800))

    def test_csv_timestamp_sensitivity_never_uses_future_sample(self):
        _,data=fixture();h=TimingHistory(data,0)
        self.assertEqual(h.get('X66',7200)['srm_latest'],8900)
        self.assertLessEqual(h.audit[-1]['max_csv_timestamp_used'],7200)
        self.assertEqual(TimingHistory(data,3600).get('X66',7200)['srm_latest'],9500)

    def test_gauge_labels_are_unchanged_by_soil_policy(self):
        raw,data=fixture();raw[4].update(error='E11',srm='4000',sm='')
        maps={s:{int(r['timestamp_ms'])/1000:r for r in raw} for s in data}
        before=window_label(data['X66'],0,1)
        self.assertEqual(window_label(keep_raw_adc(data,maps)['X66'],0,1),before)

    def test_unknown_fault_does_not_become_valid_adc(self):
        raw,data=fixture();raw[4].update(error='E11 E99',srm='4000',sm='')
        for s in data:data[s]['records'][4]=normalize(raw[4])
        maps={s:{int(r['timestamp_ms'])/1000:r for r in raw} for s in data}
        self.assertIsNone(keep_raw_adc(data,maps)['X66']['records'][4]['srm'])


if __name__=='__main__':unittest.main()
